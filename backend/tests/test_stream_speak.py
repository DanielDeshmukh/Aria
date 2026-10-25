"""Streaming _speak: one audio event per PCM chunk, stats on the first chunk.

The synth-only fakes in _fakes.py keep exercising the buffered fallback path;
this file covers a TTS that implements synth_stream, like the real SarvamTTS.
"""

from __future__ import annotations

import asyncio
import base64

from backend.session import GREETING, CallSession
from backend.tests._fakes import EventBox, FakeLLM, FakeSTT, wait_until


class ChunkedTTS:
    """Streaming-capable fake: yields three chunks per sentence."""

    mime = "audio/l16;rate=16000"

    def __init__(self) -> None:
        self.synthed: list[str] = []

    async def synth(self, text: str) -> bytes:
        raise AssertionError("streaming sessions must use synth_stream")

    async def synth_stream(self, text: str):
        self.synthed.append(text)
        for i in range(3):
            yield bytes([65 + i])

    async def close(self) -> None:
        pass


def test_greeting_streams_chunks_with_stats_on_first() -> None:
    async def scenario() -> None:
        box, tts = EventBox(), ChunkedTTS()
        session = CallSession(stt=FakeSTT(), llm=FakeLLM(), tts=tts, send=box.send)
        await session.handle({"type": "start"})
        await wait_until(lambda: len(box.of("audio")) >= 3, what="3 audio chunks")
        audio = box.of("audio")
        assert [a["data"] for a in audio] == [
            base64.b64encode(bytes([65 + i])).decode("ascii") for i in range(3)
        ]
        assert all(a["mime"] == tts.mime for a in audio)
        assert len(box.of("stats")) == 1  # stats ride on the first chunk only
        assert box.states() == ["connecting", "speaking"]
        assert tts.synthed == [GREETING]

    asyncio.run(scenario())
