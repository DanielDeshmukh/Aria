"""CallSession: the single-call state machine behind /ws/call.

States: connecting -> listening <-> thinking -> speaking -> ended
(one-shot; barge-in cancels an in-flight turn; silence asks once).
All provider keys are read via backend.config — this module never touches env.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import time
from typing import Any, Awaitable, Callable

from . import tools as tools_mod
from .normalize import has_foreign_script, normalize_order_id
from .prompts import SYSTEM_PROMPT
from .splitter import split_sentences
from .summary import build_summary, fallback_summary

logger = logging.getLogger(__name__)

SendFn = Callable[[dict], Awaitable[None]]

GREETING = "Hi, this is Aria from Aura Skincare. How can I help you today?"
REPEAT = "Sorry, I didn't catch that. Could you please repeat?"
STILL_THERE = "Are you still there? I'm happy to help if you need anything."
# Spoken when the whole LLM model chain fails (rate limits, outage): the
# call stays alive — no error banner, no ended state.
LLM_TROUBLE = (
    "Sorry, I'm having a little trouble, could you say that again in a moment?"
)
SILENCE_SECONDS = 9.0
# After Aria's own closing offer ("anything else I can help with?") the
# customer gets a longer, polite window - and when it expires the call ends
# quietly (summary + ended) instead of nudging them about a question Aria
# already asked.
CLOSING_IDLE_SECONDS = 15.0
# The nudge must never fire while the customer is talking: interims restart
# the 9 s countdown, and a fire additionally requires this much quiet since
# the last speech signal (non-empty interim, non-empty final, or
# SpeechStarted). 3 s keeps "Are you still there?" at least a few seconds
# after the last transcript fragment (mid-sentence finals included).
SPEECH_FRESH_SECONDS = 3.0
# Client playback can lag server send-finish by a frame or two; when no
# playback_done arrives, the idle countdown starts this long after the audio
# has (estimated) finished playing.
PLAYBACK_MARGIN_SECONDS = 1.5
# Only used when the TTS output config exposes no usable sample rate - see
# _pcm_bytes_per_second (Sarvam's config gives 16000, so this is rare).
FALLBACK_SAMPLE_RATE = 16000
# Aria's closing offer - detected on the way out of _speak.
_CLOSING_OFFER_RE = re.compile(
    r"\banything else\b|\belse can i help\b|\belse i can help\b|\belse you need\b"
    r"|\belse i can do\b|\bfurther questions\b",
    re.I,
)
LOW_CONFIDENCE = 0.55
INTERIM_MIN_INTERVAL = 0.2
# Low-confidence finals are normally discarded, except two safe shapes:
# digit-like order ids (STT confidence on a bare "101" often lands below the
# gate) and short yes/no answers when Aria's last question was a yes/no
# confirmation (the read-back "yes" is frequently a soft murmur).
SHORT_YES_NO = frozenset(
    {
        "yes", "yeah", "yep", "yup", "ya", "sure", "ok", "okay", "correct",
        "right", "haan", "haa", "ha", "ji", "nahi", "na", "no", "nope",
        "nah", "please do", "please", "go ahead", "do it", "cancel it",
        "yes please", "no thanks", "of course", "absolutely", "definitely",
    }
)
_YES_NO_Q_START = re.compile(
    r"^(do you|would you|shall i|should i|can i|are you|is that|can we|"
    r"have you|did you)\b",
    re.I,
)
# Fragment coalescing: endpointing can finalize an utterance in pieces
# ("Can you tell me where my order" + "one zero one is?") and the first half
# alone gets a half-answer. A final that looks incomplete holds for
# FRAGMENT_HOLD_SECONDS so the next final can join it; a final with terminal
# punctuation (a complete sentence) is never delayed.
FRAGMENT_HOLD_SECONDS = 0.7
# Words that clearly stop mid-thought when they end an unpunctuated final.
DANGLING_FINAL_WORDS = frozenset(
    {
        "a", "an", "the", "my", "your", "our", "their", "her", "his", "its",
        "to", "of", "for", "and", "or", "nor", "in", "on", "at", "by",
        "with", "from", "into", "about", "is", "are", "was", "were", "be",
        "been", "am", "do", "did", "does", "have", "has", "had", "can",
        "could", "will", "would", "shall", "should", "may", "might", "that",
        "this", "it", "he", "she", "we", "they", "you", "i", "me", "us",
        "them", "what", "where", "when", "which", "who", "how", "why",
        "tell", "order",
    }
)
# Vercel Functions (Hobby) kill WebSockets at maxDuration = 300 s: warn the
# client at 270 s, finish gracefully (summary + ended) at 295 s.
CALL_ENDING_SOON_SECONDS = 270.0
CALL_FORCE_END_SECONDS = 295.0


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _pcm_bytes_per_second(tts: Any) -> float:
    """Bytes per second of the TTS output, for the playback-duration estimate.

    Sample rate and format come from the REAL TTS output config: an explicit
    sample_rate/speech_sample_rate attribute first, then the `rate=` parameter
    of the mime type (Sarvam advertises `audio/l16;rate=16000`, i.e. linear16
    = 2 bytes/sample). 16 kHz is assumed ONLY when neither is usable, and that
    fallback is logged so an unexpected config is never silent."""
    rate: int | None = None
    for attr in ("sample_rate", "speech_sample_rate"):
        value = getattr(tts, attr, None)
        if isinstance(value, (int, float)) and value > 0:
            rate = int(value)
            break
    if rate is None:
        match = re.search(r"rate=(\d+)", str(getattr(tts, "mime", "") or ""))
        if match:
            rate = int(match.group(1))
    if rate is None:
        logger.info(
            "playback estimate: TTS sample rate not in output config "
            "(mime=%r) - assuming %d Hz",
            getattr(tts, "mime", None),
            FALLBACK_SAMPLE_RATE,
        )
        rate = FALLBACK_SAMPLE_RATE
    # linear16/PCM16 mono: 2 bytes per sample (Sarvam's output_audio_codec).
    return float(rate * 2)


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
        self._estimate_task: asyncio.Task | None = None
        self._turn_started = time.monotonic()
        self._stats_sent = False
        self._tool_lookup_ms: float | None = None
        self._last_interim_at = 0.0
        self._last_user_speech_at = 0.0
        self._last_agent_question = ""
        self._pending_final = ""
        self._hold_task: asyncio.Task | None = None
        self._still_there_sent = False
        self._closing_offer = False
        self._last_playback_done_at = 0.0
        self._warn_handle: asyncio.TimerHandle | None = None
        self._end_handle: asyncio.TimerHandle | None = None
        # Tool outcomes recorded for the post-call summary fallback (facts,
        # never raw transcript lines) - see _execute_tool.
        self.tool_log: list[dict] = []
        # PCM byte accounting for the playback-duration estimate.
        self._audio_bytes_sent = 0
        self._audio_bytes_acked = 0
        self._bytes_per_sec: float | None = None

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
        self._cancel_hold()
        self._cancel_estimate()
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
        since_playback = (
            time.monotonic() - self._last_playback_done_at
            if self._last_playback_done_at
            else -1.0
        )
        if not is_final:
            text = (text or "").strip()
            now = time.monotonic()
            if text:
                logger.info(
                    "stt interim: conf=%s text=%r state=%s since_playback_done=%.2fs",
                    confidence,
                    text,
                    self.state,
                    since_playback,
                )
                # Interims stream while the customer talks: mark the speech
                # and restart the idle countdown so "still there?" can never
                # fire mid-sentence (finals alone arrive too late).
                self._last_user_speech_at = now
                if self.state == "listening":
                    self._arm_silence()
                if self._pending_final:
                    # the customer resumed mid-fragment: keep the join window
                    # open so the next final completes the sentence
                    self._arm_hold()
                # Deepgram does not emit SpeechStarted on our live config; a
                # real interim during our audio is the reliable barge-in signal.
                if self.state in ("speaking", "thinking"):
                    await self._on_speech_start()
            else:
                # Deepgram also sends empty interims; logged so a lost reply
                # can be reconstructed from the log line by line.
                logger.debug(
                    "stt interim: empty conf=%s state=%s since_playback_done=%.2fs",
                    confidence,
                    self.state,
                    since_playback,
                )
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
            logger.info(
                "stt gate: empty final ignored state=%s since_playback_done=%.2fs",
                self.state,
                since_playback,
            )
            return
        logger.info(
            "stt final: conf=%s text=%r state=%s since_playback_done=%.2fs",
            confidence,
            text,
            self.state,
            since_playback,
        )
        # A non-empty final is the last transcript fragment of an utterance
        # (endpointing can cut mid-sentence): count it as fresh speech so the
        # nudge cannot fire a moment after the finalisation. Empty finals are
        # ignored on purpose — Deepgram emits them throughout pure silence
        # (test_still_there_fires_despite_empty_finals).
        if self._closing_offer:
            logger.info(
                "customer replied after the closing offer - normal idle window"
            )
            self._closing_offer = False
        self._last_user_speech_at = time.monotonic()
        self._cancel_silence()
        self._still_there_sent = False
        self.transcript.append({"role": "customer", "text": text})
        await self.send(
            {"type": "transcript", "role": "customer", "text": text, "final": True}
        )
        if has_foreign_script(text):
            # A final in a script outside Latin/Devanagari (the language=multi
            # Telugu mis-detection): never act on it — same canned path as
            # low confidence, no LLM turn.
            logger.info("stt gate: foreign script -> repeat (text=%r)", text)
            await self._canned_speak(REPEAT)
            return
        if not self._final_acceptable(text, confidence):
            # Unclear audio: never act on it, canned repeat instead.
            logger.info(
                "stt gate: low confidence %s < %.2f -> repeat (text=%r)",
                confidence,
                LOW_CONFIDENCE,
                text,
            )
            await self._canned_speak(REPEAT)
            return
        # Fragment coalescing: join with a held fragment (or refine it) before
        # deciding whether the sentence is complete enough for the LLM.
        joined = text
        if self._pending_final:
            pending = self._pending_final
            if text.startswith(pending):
                joined = text  # Deepgram sent a longer restatement
            elif pending.startswith(text):
                joined = pending  # stale shorter duplicate
            else:
                joined = f"{pending} {text}"  # true mid-utterance split
            logger.info("stt gate: joined held fragment -> %r", joined)
        if self._looks_incomplete(joined):
            logger.info("stt gate: incomplete final held (%r)", joined)
            self._pending_final = joined
            self._arm_hold()
            return
        self._cancel_hold()
        logger.info("stt gate: accepted -> turn (final=%r)", joined)
        await self._start_turn(user_text=joined)

    def _final_acceptable(self, text: str, confidence: float | None) -> bool:
        """Gate for finals at LOW_CONFIDENCE: normally reject, but accept a
        digit-like order id (tools normalize it again) or a short yes/no
        answer when Aria's last question was a yes/no confirmation."""
        if confidence is None or confidence >= LOW_CONFIDENCE:
            return True
        if normalize_order_id(text) is not None:
            return True
        if self._is_yes_no_answer(text) and self._is_yes_no_question(
            self._last_agent_question
        ):
            return True
        return False

    @staticmethod
    def _is_yes_no_answer(text: str) -> bool:
        cleaned = text.strip().strip(".!?,;:\"'").lower()
        return cleaned in SHORT_YES_NO

    @staticmethod
    def _is_yes_no_question(question: str) -> bool:
        """True for Aria's confirmation questions (the cancel read-back among
        them); the greeting ("How can I help you today?") is not one."""
        question = question.strip()
        if not question.endswith("?"):
            return False
        return bool(
            _YES_NO_Q_START.match(question)
            or re.search(r"\bcancel\b", question, re.I)
            or re.search(r"\bstill there\b", question, re.I)
        )

    @staticmethod
    def _has_terminal_punct(text: str) -> bool:
        stripped = text.rstrip().rstrip("\"'”’)]»")
        return bool(stripped) and stripped[-1] in ".?!…"

    @classmethod
    def _looks_incomplete(cls, text: str) -> bool:
        """True when a final clearly stops mid-thought and should wait
        FRAGMENT_HOLD_SECONDS for the next final: no terminal punctuation AND
        (ends on a dangling word, or is under 3 words and answers neither a
        yes/no nor a digit/order-id). Complete sentences never wait."""
        if cls._has_terminal_punct(text):
            return False
        words = [w for w in (w.strip(".,;:!?") for w in text.lower().split()) if w]
        if not words:
            return False
        if words[-1] in DANGLING_FINAL_WORDS:
            return True
        return (
            len(words) < 3
            and not cls._is_yes_no_answer(text)
            and normalize_order_id(text) is None
        )

    # ------------------------------------------------------------ coalescing
    def _arm_hold(self) -> None:
        self._cancel_hold_task()
        self._hold_task = asyncio.create_task(self._hold_fire())

    async def _hold_fire(self) -> None:
        try:
            await asyncio.sleep(FRAGMENT_HOLD_SECONDS)
        except asyncio.CancelledError:
            return
        if self._closing or self._ended:
            return
        text = self._pending_final
        self._pending_final = ""
        self._hold_task = None
        if text:
            await self._start_turn(user_text=text)

    def _cancel_hold_task(self) -> None:
        task = self._hold_task
        self._hold_task = None
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()

    def _cancel_hold(self) -> None:
        self._cancel_hold_task()
        self._pending_final = ""

    async def _on_speech_start(self) -> None:
        if self._closing or self._ended or not self._started:
            return
        logger.info(
            "stt speech-start: marking fresh speech, state=%s", self.state
        )
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
        self._last_playback_done_at = time.monotonic()
        # The client drains its queue whenever the last buffered chunk plays -
        # including a gap BETWEEN two sentences while the server is still
        # producing. The bytes really did play, so ack them; but never start
        # the idle countdown from a drain that happened mid-turn (that is the
        # bogus 9 s nudge). The countdown then starts on the NEXT real
        # playback_done or on the duration estimate, never on send-finish.
        self._audio_bytes_acked = self._audio_bytes_sent
        if self.state != "speaking":
            logger.debug("playback_done: ignored (state=%s)", self.state)
            return
        if self._turn_task is not None and not self._turn_task.done():
            logger.info(
                "playback_done: deferred - turn still producing (state=%s)",
                self.state,
            )
            return
        self._cancel_estimate()
        logger.info("playback_done: accepted -> listening (idle countdown armed)")
        await self._set_state("listening")
        self._arm_silence()

    async def _end(self) -> None:
        if self._ended or self._closing:
            return
        self._ended = True
        self._cancel_call_deadlines()
        await self._cancel_turn()
        self._cancel_silence()
        self._cancel_hold()
        self._cancel_estimate()
        try:
            await self.stt.close()
        except Exception:
            pass
        try:
            summary = await build_summary(
                self.llm, self.transcript, self.tool_log
            )
        except Exception:
            # build_summary logs its own reasons; this is the last resort.
            logger.exception("summary build raised - using structured fallback")
            summary = fallback_summary(self.transcript, self.tool_log)
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
        self._cancel_hold()
        await self._set_state("ended")
        for closer in (self.stt, self.tts):
            try:
                await closer.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ turns
    async def _start_turn(self, user_text: str | None = None) -> None:
        self._cancel_silence()
        self._cancel_hold()
        await self._cancel_turn()
        # the gate already consumed it; a stale question must not legitimise
        # the next low-confidence murmur
        self._last_agent_question = ""
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
                elif event.get("type") == "llm_stats":
                    await self.send(
                        {
                            "type": "llm_stats",
                            "model": event.get("model"),
                            "approx_tokens": event.get("approx_tokens"),
                        }
                    )
            if not self._ended:
                await self._flush(buffer, final=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Provider failure after the model chain gave up (or any other LLM
            # error): keep the call alive — apologize once and go back to
            # listening. Never an error event, never `ended`.
            logger.exception("llm turn failed - speaking the graceful line")
            await self._canned_speak(LLM_TROUBLE)
            return
        if self.state == "thinking":
            # no audio was produced at all - nothing to wait for
            await self._set_state("listening")
            self._arm_silence()
        elif self.state == "speaking":
            if self._audio_bytes_acked >= self._audio_bytes_sent:
                # the client already drained everything we sent (its
                # playback_done was deferred while we were producing)
                logger.info(
                    "turn end: client already drained the audio -> listening"
                )
                await self._set_state("listening")
                self._arm_silence()
            else:
                # real audio is still playing: wait for playback_done, with
                # the duration estimate as the fallback
                self._schedule_estimate()

    def _execute_tool(self, name: str, args: dict) -> dict:
        """dispatch() plus capture of the lookup timing for the stats event
        and of the tool outcome for the post-call summary facts."""
        result = tools_mod.dispatch(name, args)
        if name == "get_order_details":
            self._tool_lookup_ms = tools_mod.last_lookup_ms()
        try:
            self.tool_log.append(
                {"name": name, "args": dict(args), "result": result}
            )
        except Exception:
            logger.debug("tool_log append failed", exc_info=True)
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
        self._cancel_hold()
        await self._cancel_turn()
        await self._speak(text)

    async def _speak(self, text: str) -> None:
        if self._closing or self._ended:
            return
        if _CLOSING_OFFER_RE.search(text):
            # Aria just offered to close: the customer then gets a longer,
            # polite window - and no "still there?" when it expires.
            self._closing_offer = True
            logger.info(
                "closing offer detected - idle window is now %.0fs",
                CLOSING_IDLE_SECONDS,
            )
        if text.rstrip().endswith("?"):
            # remembered for the low-confidence yes/no gate (issue 3): a short
            # "yes"/"no" after a confirmation question is accepted below
            # LOW_CONFIDENCE
            self._last_agent_question = text
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
        # The sentence is fully sent: arm the playback-duration estimate so
        # the idle countdown starts on playback (or estimate), never on
        # send-finish alone.
        if self.state == "speaking":
            self._schedule_estimate()

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
        self._audio_bytes_sent += len(chunk)
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
        if state != "speaking":
            # leaving the playing state: no more audio can arrive for this
            # utterance (playback_done or barge-in), so ack what was sent and
            # drop the estimate.
            self._audio_bytes_acked = self._audio_bytes_sent
            self._cancel_estimate()
        self.state = state
        await self.send({"type": "state", "state": state})

    # -------------------------------------------------------- playback timing
    def _schedule_estimate(self) -> None:
        """Arm the playback-duration fallback: if no playback_done arrives,
        the idle countdown starts PLAYBACK_MARGIN_SECONDS after the audio we
        sent is estimated to have finished playing. The sample rate/format
        come from the TTS output config (see _pcm_bytes_per_second)."""
        self._cancel_estimate()
        if self._closing or self._ended or self.state != "speaking":
            return
        if self._bytes_per_sec is None:
            self._bytes_per_sec = _pcm_bytes_per_second(self.tts)
        unsent = max(0, self._audio_bytes_sent - self._audio_bytes_acked)
        delay = unsent / self._bytes_per_sec + PLAYBACK_MARGIN_SECONDS
        logger.info(
            "playback estimate: no playback_done yet - arming in %.2fs "
            "(unsent_bytes=%d)",
            delay,
            unsent,
        )
        self._estimate_task = asyncio.create_task(self._estimate_fire(delay))

    async def _estimate_fire(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        self._estimate_task = None
        if self._closing or self._ended or self.state != "speaking":
            return
        if self._turn_task is not None and not self._turn_task.done():
            # more audio may still come from this turn; re-check later
            logger.info(
                "playback estimate: turn still producing - rearming"
            )
            self._schedule_estimate()
            return
        logger.info(
            "playback estimate: %.2fs elapsed without playback_done -> listening",
            delay,
        )
        await self._set_state("listening")
        self._arm_silence()

    def _cancel_estimate(self) -> None:
        task = self._estimate_task
        self._estimate_task = None
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()

    def _arm_silence(self) -> None:
        self._cancel_silence()
        if self._still_there_sent or self._ended or self._closing:
            return
        window = CLOSING_IDLE_SECONDS if self._closing_offer else SILENCE_SECONDS
        self._silence_task = asyncio.create_task(self._silence_fire(window))

    async def _silence_fire(self, window: float) -> None:
        try:
            await asyncio.sleep(window)
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
        if self._closing_offer:
            # Aria already asked whether there is anything else; after the
            # longer window the call ends quietly - no nudge.
            logger.info(
                "closing-offer idle window (%.0fs) elapsed - ending call quietly",
                window,
            )
            await self._end()
            return
        self._still_there_sent = True
        logger.info("idle %.1fs with no speech - speaking the nudge", window)
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
