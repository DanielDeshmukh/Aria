"""Live two-turn cancellation: real TTS -> STT -> Groq tool flow.

Turn 1: "Please cancel my order ORD-103" (the fuller phrasing — a bare
"Cancel ORD-103" can be mis-decoded as Telugu under language=multi and hit
the foreign-script guard) -> the agent must read the order back and ask for
confirmation, never cancelling in the same breath.
Turn 2: "Yes." -> cancel_order(confirmed=true) must execute and only then
may the agent say the order is cancelled.

Skipped entirely when any key is absent (CI has none).
"""

from __future__ import annotations

import asyncio
import base64
import time

import pytest

from backend.audio_utils import resample_pcm16
from backend.config import get_settings
from backend.llm import GroqLLM
from backend.session import GREETING, CallSession
from backend.stt import DeepgramSTT
from backend.tts import SAMPLE_RATE as TTS_RATE
from backend.tts import SarvamTTS

pytestmark = pytest.mark.skipif(
    bool(get_settings().missing_keys()),
    reason="live voice needs all keys: " + ", ".join(get_settings().missing_keys()),
)

STT_RATE = 16000
FRAME_BYTES = 3200  # 100 ms @ 16 kHz mono 16-bit
UTTERANCE_1 = "Please cancel my order ORD-103"
UTTERANCE_2 = "Yes."


async def collect_until(
    events: list[dict],
    queue: "asyncio.Queue[dict]",
    pred,
    timeout: float,
    what: str,
    start: int = 0,
) -> int:
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


async def feed_utterance(session: CallSession, pcm: bytes) -> None:
    pcm = resample_pcm16(pcm, TTS_RATE, STT_RATE)
    for off in range(0, len(pcm), FRAME_BYTES):
        await session.handle(
            {
                "type": "audio",
                "data": base64.b64encode(pcm[off : off + FRAME_BYTES]).decode(
                    "ascii"
                ),
            }
        )
        # real-time mic cadence: burst-fed speech backlogs Deepgram past the
        # endpointing window (stt.py docstring: near-real-time cadence only)
        await asyncio.sleep(0.1)
    silence = base64.b64encode(b"\x00" * FRAME_BYTES).decode("ascii")
    for _ in range(12):  # 1.2 s trailing silence -> endpointing finalizes
        await session.handle({"type": "audio", "data": silence})


@pytest.mark.timeout(180)
def test_live_cancel_read_back_then_confirmed_tool_turn() -> None:
    async def scenario() -> None:
        tts = SarvamTTS()
        events: list[dict] = []
        queue: asyncio.Queue[dict] = asyncio.Queue()

        async def send(msg: dict) -> None:
            await queue.put(msg)

        stt = DeepgramSTT(sample_rate=STT_RATE, encoding="linear16")
        session = CallSession(stt=stt, llm=GroqLLM(), tts=tts, send=send)
        try:
            pcm1 = await tts.synth(UTTERANCE_1)
            pcm2 = await tts.synth(UTTERANCE_2)
            assert len(pcm1) > 8000 and len(pcm2) > 1000, (len(pcm1), len(pcm2))

            # ---- greeting -> listening
            await session.handle({"type": "start"})
            i = await collect_until(
                events, queue,
                lambda e: e.get("type") == "transcript"
                and e.get("role") == "agent"
                and e.get("text") == GREETING,
                timeout=30.0, what="greeting transcript",
            )
            i = await collect_until(
                events, queue, lambda e: e.get("type") == "audio",
                timeout=30.0, what="greeting audio", start=i + 1,
            )
            await session.handle({"type": "playback_done"})
            i = await collect_until(
                events, queue,
                lambda e: e.get("type") == "state" and e.get("state") == "listening",
                timeout=10.0, what="listening state",
            )

            # ---- turn 1: read back + ask, never cancel
            await feed_utterance(session, pcm1)
            i = await collect_until(
                events, queue,
                lambda e: e.get("type") == "tool",
                timeout=45.0, what="turn1 tool event", start=i + 1,
            )
            tool1 = events[i]
            if tool1["name"] == "cancel_order":
                # a refusal before confirmation is fine; a success is not
                assert tool1["result"]["cancelled"] is False, tool1
            else:
                assert tool1["name"] == "get_order_details", tool1
                assert tool1["result"]["found"] is True, tool1
            i = await collect_until(
                events, queue,
                lambda e: e.get("type") == "transcript"
                and e.get("role") == "agent"
                and "cancel" in (e.get("text") or "").lower(),
                timeout=45.0, what="turn1 confirmation question", start=i + 1,
            )
            i = await collect_until(
                events, queue, lambda e: e.get("type") == "audio",
                timeout=30.0, what="turn1 reply audio", start=i + 1,
            )
            await session.handle({"type": "playback_done"})
            i = await collect_until(
                events, queue,
                lambda e: e.get("type") == "state" and e.get("state") == "listening",
                timeout=15.0, what="listening after turn1", start=i + 1,
            )

            # ---- turn 2: explicit yes -> confirmed tool -> confirmation
            await feed_utterance(session, pcm2)
            i = await collect_until(
                events, queue,
                lambda e: e.get("type") == "tool"
                and e.get("name") == "cancel_order",
                timeout=45.0, what="turn2 cancel_order event", start=i + 1,
            )
            tool2 = events[i]
            assert tool2["args"].get("confirmed") is True, tool2["args"]
            assert tool2["result"]["cancelled"] is True, tool2["result"]
            i = await collect_until(
                events, queue,
                lambda e: e.get("type") == "transcript"
                and e.get("role") == "agent"
                and e.get("text") != GREETING,
                timeout=45.0, what="turn2 confirmation reply", start=i + 1,
            )
            reply = (events[i]["text"] or "").lower()
            assert "cancel" in reply, events[i]
        finally:
            await session.close()

    asyncio.run(scenario())
