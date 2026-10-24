"""Live Sarvam TTS synthesis (SARVAM_API_KEY required; skips in CI)."""

from __future__ import annotations

import asyncio

import pytest

from backend.config import get_settings
from backend.tts import SarvamTTS

pytestmark = pytest.mark.skipif(
    "SARVAM_API_KEY" in get_settings().missing_keys(),
    reason="SARVAM_API_KEY not set",
)


@pytest.mark.timeout(30)
def test_synth_sentence_returns_audio() -> None:
    async def scenario() -> None:
        tts = SarvamTTS()
        pcm = await tts.synth("Hello from Aria at Aura Skincare.")
        assert len(pcm) > 1000
        await tts.close()

    asyncio.run(scenario())
