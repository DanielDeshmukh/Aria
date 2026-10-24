"""Live end-to-end voice: real Sarvam TTS -> real Deepgram STT -> real Groq
tool turn -> real post-call summary. Skipped entirely when any of the three
keys is absent (CI has none).
"""

from __future__ import annotations

import asyncio
import base64
import time

import pytest

from backend.audio_utils import resample_pcm16
from backend.config import get_settings
from backend.llm import GroqLLM
from backend.normalize import normalize_order_id
from backend.session import GREETING, CallSession
from backend.stt import DeepgramSTT
from backend.summary import SUMMARY_KEYS
from backend.tts import SAMPLE_RATE as TTS_RATE
from backend.tts import SarvamTTS

pytestmark = pytest.mark.skipif(
    bool(get_settings().missing_keys()),
    reason="live voice needs all keys: " + ", ".join(get_settings().missing_keys()),
)

# T11 lock: Sarvam emits linear16 @ 16000 — identical to Deepgram's input,
# so the resample below is an identity (kept explicit per plan).
STT_RATE = 16000
FRAME_BYTES = 3200  # 100 ms @ 16 kHz mono 16-bit
UTTERANCE = "Where is my order ORD one oh one?"


async def collect_until(
    events: list[dict],
    queue: "asyncio.Queue[dict]",
    pred,
    timeout: float,
    what: str,
    start: int = 0,
) -> int:
    """Pump the queue into `events` until pred matches an event at index >= start.

    Returns the index of the matched event (chain the next call from there).
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while True:
            try:
                events.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        for i in range(start, len(events)):
            if pred(events[i]):
                return i
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}; events={events!r}")


@pytest.mark.timeout(90)
def test_live_voice_tool_turn_and_summary() -> None:
    async def scenario() -> None:
        tts = SarvamTTS()
        events: list[dict] = []
        queue: asyncio.Queue[dict] = asyncio.Queue()

        async def send(msg: dict) -> None:
            await queue.put(msg)

        stt = DeepgramSTT(sample_rate=STT_RATE, encoding="linear16")
        session = CallSession(stt=stt, llm=GroqLLM(), tts=tts, send=send)
        try:
            # ---- greeting: transcript + audio + listening after playback_done
            await session.handle({"type": "start"})
            i = await collect_until(
                events, queue,
                lambda e: e.get("type") == "transcript"
                and e.get("role") == "agent"
                and e.get("text") == GREETING,
                timeout=30.0,
                what="greeting transcript",
            )
            i = await collect_until(
                events, queue,
                lambda e: e.get("type") == "audio",
                timeout=30.0,
                what="greeting audio",
                start=i + 1,
            )
            greeting_stats = next(e for e in events if e.get("type") == "stats")
            # Session start -> first audible audio (Deepgram connect + greeting
            # synth): warm p50 measured 1869 ms in T21's latency run, but a cold
            # Sarvam connect under API load has been observed up to ~7.5 s here.
            # This is a stall-detection sanity bound, not the latency gate —
            # T21's latency run owns that.
            assert 0 <= greeting_stats["first_audio_ms"] <= 10000, greeting_stats
            audio = events[i]
            assert audio["mime"] == "audio/l16;rate=16000"
            await session.handle({"type": "playback_done"})
            await collect_until(
                events, queue,
                lambda e: e.get("type") == "state" and e.get("state") == "listening",
                timeout=10.0,
                what="listening state",
            )

            # ---- TTS-generated utterance -> STT (100 ms frames)
            pcm = await tts.synth(UTTERANCE)
            assert len(pcm) > 8000
            pcm = resample_pcm16(pcm, TTS_RATE, STT_RATE)
            for i2 in range(0, len(pcm), FRAME_BYTES):
                frame = pcm[i2 : i2 + FRAME_BYTES]
                await session.handle(
                    {
                        "type": "audio",
                        "data": base64.b64encode(frame).decode("ascii"),
                    }
                )
            # trailing silence: Deepgram (endpointing=300 ms) finalizes the
            # utterance only when it sees silence in the stream.
            silence = base64.b64encode(b"\x00" * FRAME_BYTES).decode("ascii")
            for _ in range(10):  # 1 s of silence
                await session.handle({"type": "audio", "data": silence})

            # ---- tool turn
            i = await collect_until(
                events, queue,
                lambda e: e.get("type") == "tool",
                timeout=30.0,
                what="tool event",
            )
            tool = events[i]
            assert tool["name"] == "get_order_details"
            # STT heard "ORD one oh one" as "ORD-one 01" — the pipeline's
            # contract is that the arg normalizes to the canonical id.
            assert normalize_order_id(tool["args"]["order_id"]) == "ORD-101"
            assert tool["result"]["found"] is True

            # ---- spoken answer + turn latency
            i = await collect_until(
                events,
                queue,
                lambda e: e.get("type") == "transcript"
                and e.get("role") == "agent"
                and "out for delivery" in (e.get("text") or "").lower(),
                timeout=30.0,
                what="order-status reply",
                start=i + 1,
            )
            await collect_until(
                events, queue,
                lambda e: e.get("type") == "audio",
                timeout=30.0,
                what="reply audio",
                start=i + 1,
            )
            reply_stats = [e for e in events if e.get("type") == "stats"]
            assert len(reply_stats) >= 2  # reply turn emitted its own stats

            # ---- post-call summary
            await session.handle({"type": "end"})
            await collect_until(
                events, queue,
                lambda e: e.get("type") == "summary",
                timeout=30.0,
                what="summary event",
            )
            summary_ev = next(e for e in events if e.get("type") == "summary")
            summary = summary_ev["summary"]
            assert set(SUMMARY_KEYS) <= set(summary)
            assert summary["customer_intent"] == "ORDER_TRACKING"
            assert summary["order_id"] == "ORD-101"
            assert summary["resolution_status"] == "RESOLVED"
        finally:
            await session.close()

    asyncio.run(scenario())
