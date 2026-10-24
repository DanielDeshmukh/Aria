"""Live Deepgram connection smoke test (DEEPGRAM_API_KEY required; skips in CI)."""

from __future__ import annotations

import asyncio

import pytest

from backend.audio_utils import pcm16_to_b64
from backend.config import get_settings
from backend.stt import DeepgramSTT

pytestmark = pytest.mark.skipif(
    "DEEPGRAM_API_KEY" in get_settings().missing_keys(),
    reason="DEEPGRAM_API_KEY not set",
)


@pytest.mark.timeout(20)
def test_connect_send_silence_close() -> None:
    async def scenario() -> None:
        stt = DeepgramSTT()
        seen: list = []

        async def on_transcript(text: str, confidence, is_final: bool) -> None:
            seen.append((text, is_final))

        async def on_speech_start() -> None:
            seen.append("speech-started")

        await stt.start(on_transcript=on_transcript, on_speech_start=on_speech_start)
        await stt.send_audio(pcm16_to_b64(b"\x00" * 32000))  # 1 s silence
        await asyncio.sleep(2)  # no exception within the budget = connection healthy
        await stt.close()

    asyncio.run(scenario())
