"""CallSession: the single-call state machine behind /ws/call.

States: connecting -> listening <-> thinking -> speaking -> ended
(one-shot; barge-in cancels an in-flight turn; silence asks once).
All provider keys are read via backend.config — this module never touches env.
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Any, Awaitable, Callable

from . import tools as tools_mod
from .prompts import SYSTEM_PROMPT
from .splitter import split_sentences
from .summary import build_summary, fallback_summary

SendFn = Callable[[dict], Awaitable[None]]

GREETING = "Hi, this is Aria from Aura Skincare. How can I help you today?"
REPEAT = "Sorry, I didn't catch that. Could you please repeat?"
STILL_THERE = "Are you still there? I'm happy to help if you need anything."
SILENCE_SECONDS = 9.0
LOW_CONFIDENCE = 0.55
INTERIM_MIN_INTERVAL = 0.2


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class CallSession:
    def __init__(self, stt: Any, llm: Any, tts: Any, send: SendFn) -> None:
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.send = send
        self.state = "connecting"
        self.transcript: list[dict] = []
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._started = False
        self._ended = False
        self._closing = False
        self._turn_task: asyncio.Task | None = None
        self._silence_task: asyncio.Task | None = None
        self._turn_started = time.monotonic()
        self._stats_sent = False
        self._last_interim_at = 0.0
        self._still_there_sent = False

    # ------------------------------------------------------------------ wire
    async def handle(self, msg: Any) -> None:
        if not isinstance(msg, dict):
            return
        typ = msg.get("type")
        if typ == "start":
            await self._start()
        elif typ == "audio":
            if self._started and not self._ended:
                await self._on_audio(str(msg.get("data") or ""))
        elif typ == "playback_done":
            await self._on_playback_done()
        elif typ == "end":
            await self._end()

    async def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        await self._cancel_turn()
        self._cancel_silence()
        for closer in (self.stt, self.tts):
            try:
                await closer.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ flow
    async def _start(self) -> None:
        if self._ended:
            await self.send({"type": "error", "message": "session already ended"})
            return
        if self._started:
            await self.send({"type": "error", "message": "session already started"})
            return
        self._started = True
        self._turn_started = time.monotonic()
        self._stats_sent = False
        await self._set_state("connecting")
        try:
            await self.stt.start(
                on_transcript=self._on_transcript,
                on_speech_start=self._on_speech_start,
            )
        except Exception as e:
            await self._fail(f"speech-to-text unavailable: {type(e).__name__}")
            return
        try:
            await self._speak(GREETING)
        except Exception as e:
            await self._fail(f"text-to-speech unavailable: {type(e).__name__}")

    async def _on_audio(self, data: str) -> None:
        if not data:
            return
        try:
            await self.stt.send_audio(data)
        except Exception as e:
            await self._fail(f"speech-to-text unavailable: {type(e).__name__}")

    async def _on_transcript(
        self, text: str, confidence: float | None, is_final: bool
    ) -> None:
        if self._closing or self._ended or not self._started:
            return
        if not is_final:
            now = time.monotonic()
            if now - self._last_interim_at >= INTERIM_MIN_INTERVAL:
                self._last_interim_at = now
                await self.send(
                    {
                        "type": "transcript",
                        "role": "customer",
                        "text": text,
                        "final": False,
                    }
                )
            return
        text = (text or "").strip()
        if not text:
            return
        self._cancel_silence()
        self._still_there_sent = False
        self.transcript.append({"role": "customer", "text": text})
        await self.send(
            {"type": "transcript", "role": "customer", "text": text, "final": True}
        )
        if confidence is not None and confidence < LOW_CONFIDENCE:
            await self._canned_speak(REPEAT)
            return
        await self._start_turn(user_text=text)

    async def _on_speech_start(self) -> None:
        if self._closing or self._ended or not self._started:
            return
        if self.state in ("speaking", "thinking"):
            await self._cancel_turn()
            await self.send({"type": "barge_in"})
            await self._set_state("listening")
            self._arm_silence()

    async def _on_playback_done(self) -> None:
        if self._closing or self._ended or not self._started:
            return
        if self.state == "speaking":
            await self._set_state("listening")
            self._arm_silence()

    async def _end(self) -> None:
        if self._ended or self._closing:
            return
        self._ended = True
        await self._cancel_turn()
        self._cancel_silence()
        try:
            await self.stt.close()
        except Exception:
            pass
        try:
            summary = await build_summary(self.llm, self.transcript)
        except Exception:
            summary = fallback_summary(self.transcript)
        await self.send(
            {
                "type": "summary",
                "transcript": list(self.transcript),
                "summary": summary,
            }
        )
        await self._set_state("ended")

    async def _fail(self, message: str) -> None:
        if self._closing or self._ended:
            return
        await self.send({"type": "error", "message": message})
        self._ended = True
        await self._cancel_turn()
        self._cancel_silence()
        await self._set_state("ended")
        for closer in (self.stt, self.tts):
            try:
                await closer.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ turns
    async def _start_turn(self, user_text: str | None = None) -> None:
        self._cancel_silence()
        await self._cancel_turn()
        if user_text is not None:
            self.messages.append({"role": "user", "content": user_text})
        self._turn_task = asyncio.create_task(self._run_turn())

    async def _run_turn(self) -> None:
        self._turn_started = time.monotonic()
        self._stats_sent = False
        await self._set_state("thinking")
        buffer = ""
        try:
            async for event in self.llm.chat(
                self.messages, tools_mod.TOOL_SCHEMAS, tools_mod.dispatch
            ):
                if self._ended:
                    break  # a provider failed mid-turn; session already errored
                if event.get("type") == "text":
                    buffer = await self._flush(buffer + str(event.get("delta", "")))
                elif event.get("type") == "tool":
                    await self.send(
                        {
                            "type": "tool",
                            "name": event.get("name"),
                            "args": event.get("args"),
                            "result": event.get("result"),
                        }
                    )
            if not self._ended:
                await self._flush(buffer, final=True)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self._fail(f"language model unavailable: {type(e).__name__}")
            return
        if self.state == "thinking":
            await self._set_state("listening")
            self._arm_silence()

    async def _flush(self, buffer: str, final: bool = False) -> str:
        sentences, rest = split_sentences(buffer)
        for sentence in sentences:
            await self._speak(sentence)
        if final and rest.strip():
            await self._speak(rest.strip())
            return ""
        return rest

    async def _canned_speak(self, text: str) -> None:
        await self._cancel_turn()
        await self._speak(text)

    async def _speak(self, text: str) -> None:
        if self._closing or self._ended:
            return
        self.transcript.append({"role": "agent", "text": text})
        await self.send(
            {"type": "transcript", "role": "agent", "text": text, "final": True}
        )
        try:
            audio = await self.tts.synth(text)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self._fail(f"text-to-speech unavailable: {type(e).__name__}")
            return
        if not self._stats_sent:
            self._stats_sent = True
            await self._send_stats()
        if self.state != "speaking":
            await self._set_state("speaking")
        await self.send(
            {"type": "audio", "mime": self.tts.mime, "data": _b64(audio)}
        )

    # ----------------------------------------------------------------- helpers
    async def _send_stats(self) -> None:
        await self.send(
            {
                "type": "stats",
                "first_audio_ms": int((time.monotonic() - self._turn_started) * 1000),
            }
        )

    async def _set_state(self, state: str) -> None:
        self.state = state
        await self.send({"type": "state", "state": state})

    def _arm_silence(self) -> None:
        self._cancel_silence()
        if self._still_there_sent or self._ended or self._closing:
            return
        self._silence_task = asyncio.create_task(self._silence_fire())

    async def _silence_fire(self) -> None:
        try:
            await asyncio.sleep(SILENCE_SECONDS)
        except asyncio.CancelledError:
            return
        if self._closing or self._ended or self._still_there_sent:
            return
        self._still_there_sent = True
        try:
            await self._speak(STILL_THERE)
        except Exception as e:
            await self._fail(f"text-to-speech unavailable: {type(e).__name__}")

    def _cancel_silence(self) -> None:
        task = self._silence_task
        self._silence_task = None
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()

    async def _cancel_turn(self) -> None:
        task = self._turn_task
        self._turn_task = None
        if task is None or task.done():
            return
        if task is asyncio.current_task():
            return  # _fail/_canned called from inside the turn task itself
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
