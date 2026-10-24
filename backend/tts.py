"""Sarvam Bulbul v4 Flash TTS.

Shell until Task 11 lands the real client (after the schema probe).
"""

from __future__ import annotations


class SarvamTTS:
    mime = "audio/wav"

    async def synth(self, text: str) -> bytes:
        raise RuntimeError("SarvamTTS not implemented yet (task 11)")

    async def close(self) -> None:
        pass
