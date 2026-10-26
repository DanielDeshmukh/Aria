"""Live STT language probe: does the pinned language transcribe the Hinglish
runbook line "Mera order kahan hai?" (scenario 9)?

Sarvam speaks it -> real Deepgram under settings.stt_language -> assert a
non-empty final arrives. This makes the en-IN trade-off measurable: if the
pinned default ever drops the line (T21 saw conf-0.0 empty finals under
en-IN), this fails locally and STT_LANGUAGE=multi is the one-env-var
fallback. Skipped in CI (no keys).
"""

from __future__ import annotations

import asyncio
import time

import pytest

from backend.audio_utils import pcm16_to_b64, resample_pcm16
from backend.config import get_settings
from backend.stt import DeepgramSTT
from backend.tts import SAMPLE_RATE as TTS_RATE
from backend.tts import SarvamTTS

_missing = [
    key
    for key in get_settings().missing_keys()
    if key in ("DEEPGRAM_API_KEY", "SARVAM_API_KEY")
]
pytestmark = pytest.mark.skipif(
    bool(_missing),
    reason="live STT probe needs: " + ", ".join(_missing),
)

STT_RATE = 16000
FRAME_BYTES = 3200  # 100 ms @ 16 kHz mono 16-bit
UTTERANCE = "Mera order kahan hai?"


@pytest.mark.timeout(60)
def test_hinglish_line_transcribes_under_pinned_language() -> None:
    async def scenario() -> None:
        tts = SarvamTTS()
        stt = DeepgramSTT(sample_rate=STT_RATE, encoding="linear16")
        finals: list[str] = []

        async def on_transcript(text: str, confidence, is_final: bool) -> None:
            if is_final and text.strip():
                finals.append(text.strip())

        async def on_speech_start() -> None:
            pass

        await stt.start(on_transcript=on_transcript, on_speech_start=on_speech_start)
        try:
            pcm = await tts.synth(UTTERANCE)
            assert len(pcm) > 4000
            pcm = resample_pcm16(pcm, TTS_RATE, STT_RATE)
            for offset in range(0, len(pcm), FRAME_BYTES):
                frame = pcm[offset : offset + FRAME_BYTES]
                await stt.send_audio(pcm16_to_b64(frame))
                # real-time mic cadence (like the keepalive): burst-fed speech
                # backlogs Deepgram — measured 2/4 no-final failures at
                # endpointing=800 when the frames were sent as fast as possible
                await asyncio.sleep(0.1)
            # Deepgram finalizes on the silent gap; the keepalive keeps the
            # cadence real-time after the speech frames stop.
            deadline = time.monotonic() + 8.0
            while not finals and time.monotonic() < deadline:
                await asyncio.sleep(0.1)
            assert finals, (
                f"{get_settings().stt_language!r} returned no non-empty final for "
                f"{UTTERANCE!r} — consider STT_LANGUAGE=multi"
            )
        finally:
            await stt.close()

    asyncio.run(scenario())
