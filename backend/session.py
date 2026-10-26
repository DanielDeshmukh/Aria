"""CallSession: the single-call state machine behind /ws/call.

States: connecting -> listening <-> thinking -> speaking -> ended
(one-shot; barge-in cancels an in-flight turn; silence asks once).
All provider keys are read via backend.config — this module never touches env.
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
from typing import Any, Awaitable, Callable

from . import tools as tools_mod
from .normalize import has_foreign_script
from .prompts import SYSTEM_PROMPT
from .splitter import split_sentences
from .summary import build_summary, fallback_summary

SendFn = Callable[[dict], Awaitable[None]]

GREETING = "Hi, this is Aria from Aura Skincare. How can I help you today?"
REPEAT = "Sorry, I didn't catch that. Could you please repeat?"
STILL_THERE = "Are you still there? I'm happy to help if you need anything."
SILENCE_SECONDS = 9.0
# The nudge must never fire while the customer is talking: interims restart
# the 9 s countdown, and a fire additionally requires this much quiet since
# the last speech signal (interim or SpeechStarted).
SPEECH_FRESH_SECONDS = 2.0
LOW_CONFIDENCE = 0.55
INTERIM_MIN_INTERVAL = 0.2
# Vercel Functions (Hobby) kill WebSockets at maxDuration = 300 s: warn the
# client at 270 s, finish gracefully (summary + ended) at 295 s.
CALL_ENDING_SOON_SECONDS = 270.0
CALL_FORCE_END_SECONDS = 295.0


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
        self._tool_lookup_ms: float | None = None
        self._last_interim_at = 0.0
        self._last_user_speech_at = 0.0
        self._still_there_sent = False
        self._warn_handle: asyncio.TimerHandle | None = None
        self._end_handle: asyncio.TimerHandle | None = None

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
        self._cancel_call_deadlines()
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
        self._tool_lookup_ms = None
        self._schedule_call_deadlines()
        await self._set_state("connecting")
        greeting = asyncio.create_task(self._speak(GREETING))
        try:
            await self.stt.start(
                on_transcript=self._on_transcript,
                on_speech_start=self._on_speech_start,
            )
        except Exception as e:
            greeting.cancel()
            try:
                await greeting
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            await self._fail(f"speech-to-text unavailable: {type(e).__name__}")
            return
        try:
            await greeting
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
            text = (text or "").strip()
            now = time.monotonic()
            if text:
                # Interims stream while the customer talks: mark the speech
                # and restart the idle countdown so "still there?" can never
                # fire mid-sentence (finals alone arrive too late).
                self._last_user_speech_at = now
                if self.state == "listening":
                    self._arm_silence()
            # Deepgram does not emit SpeechStarted on our live config; a real
            # interim during our audio is the reliable barge-in signal.
            if text and self.state in ("speaking", "thinking"):
                await self._on_speech_start()
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
        if (confidence is not None and confidence < LOW_CONFIDENCE) or has_foreign_script(
            text
        ):
            # Unclear audio, or a final in a script outside Latin/Devanagari
            # (the language=multi Telugu mis-detection): never act on it —
            # same canned path as low confidence, no LLM turn.
            await self._canned_speak(REPEAT)
            return
        await self._start_turn(user_text=text)

    async def _on_speech_start(self) -> None:
        if self._closing or self._ended or not self._started:
            return
        self._last_user_speech_at = time.monotonic()
        if self.state in ("speaking", "thinking"):
            await self._cancel_turn()
            await self.send({"type": "barge_in"})
            await self._set_state("listening")
            self._arm_silence()
        elif self.state == "listening":
            # customer speech while idle: restart the idle countdown
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
        self._cancel_call_deadlines()
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
        self._cancel_call_deadlines()
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
        self._tool_lookup_ms = None
        await self._set_state("thinking")
        buffer = ""
        try:
            async for event in self.llm.chat(
                self.messages, tools_mod.TOOL_SCHEMAS, self._execute_tool
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

    def _execute_tool(self, name: str, args: dict) -> dict:
        """dispatch() plus capture of the lookup timing for the stats event."""
        result = tools_mod.dispatch(name, args)
        if name == "get_order_details":
            self._tool_lookup_ms = tools_mod.last_lookup_ms()
        return result

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
            stream = getattr(self.tts, "synth_stream", None)
            if stream is not None:
                # Streaming path: forward each PCM chunk as it arrives so the
                # first audio leaves before the sentence finished synthesizing.
                async for chunk in stream(text):
                    if not await self._emit_audio(chunk):
                        return
            else:
                audio = await self.tts.synth(text)
                if self._ended or self._closing:
                    return
                await self._emit_audio(audio)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self._fail(f"text-to-speech unavailable: {type(e).__name__}")
            return

    async def _emit_audio(self, chunk: bytes) -> bool:
        """Send one PCM chunk; stats/state ride on the first one.
        Returns False when the session ended and sending must stop."""
        if self._ended or self._closing:
            return False
        if not self._stats_sent:
            self._stats_sent = True
            await self._send_stats()
        if self.state != "speaking":
            await self._set_state("speaking")
        await self.send(
            {"type": "audio", "mime": self.tts.mime, "data": _b64(chunk)}
        )
        return True

    # ----------------------------------------------------------------- helpers
    async def _send_stats(self) -> None:
        payload: dict = {
            "type": "stats",
            "first_audio_ms": int((time.monotonic() - self._turn_started) * 1000),
        }
        if self._tool_lookup_ms is not None:
            payload["tool_lookup_ms"] = round(self._tool_lookup_ms, 2)
        await self.send(payload)

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
        if time.monotonic() - self._last_user_speech_at < SPEECH_FRESH_SECONDS:
            # the customer spoke too recently for this deadline (mid-sentence
            # burst the interim resets may have missed) — restart, never
            # interrupt
            self._arm_silence()
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

    # --------------------------------------------------------- call deadlines
    def _schedule_call_deadlines(self) -> None:
        """Vercel Functions terminate WebSockets at the function's maxDuration
        (300 s on Hobby): warn the client at CALL_ENDING_SOON_SECONDS, then end
        gracefully (summary + ended) at CALL_FORCE_END_SECONDS so the closing
        events are delivered while the socket is still alive. Uses
        loop.call_later handles — not tasks — so an idle session leaks nothing
        at loop shutdown. Plain uvicorn has no such limit, so this only runs
        when VERCEL is set (tests monkeypatch it to a small value)."""
        if not os.environ.get("VERCEL"):
            return
        loop = asyncio.get_running_loop()
        self._warn_handle = loop.call_later(
            CALL_ENDING_SOON_SECONDS, self._on_ending_soon
        )
        self._end_handle = loop.call_later(
            CALL_FORCE_END_SECONDS, self._on_force_end
        )

    def _cancel_call_deadlines(self) -> None:
        for handle in (self._warn_handle, self._end_handle):
            if handle is not None:
                handle.cancel()
        self._warn_handle = None
        self._end_handle = None

    def _on_ending_soon(self) -> None:
        if self._ended or self._closing:
            return
        asyncio.create_task(self._send_ending_soon())

    async def _send_ending_soon(self) -> None:
        try:
            await self.send(
                {
                    "type": "call_ending_soon",
                    "seconds_left": int(
                        CALL_FORCE_END_SECONDS - CALL_ENDING_SOON_SECONDS
                    ),
                }
            )
        except Exception:
            pass

    def _on_force_end(self) -> None:
        if self._ended or self._closing:
            return
        asyncio.create_task(self._force_end())

    async def _force_end(self) -> None:
        try:
            await self._end()
        except Exception:
            pass
