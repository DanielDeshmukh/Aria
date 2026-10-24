"""Deepgram streaming STT.

Shell until Task 9 lands the real client: constructs without I/O so the
/ws/call route imports cleanly; start() fails at call time, which the session
surfaces as a NAMES-only error event.
"""

from __future__ import annotations

from typing import Awaitable, Callable

TranscriptCb = Callable[[str, float | None, bool], Awaitable[None]]
SpeechStartCb = Callable[[], Awaitable[None]]


class DeepgramSTT:
    def __init__(self, sample_rate: int = 16000, encoding: str = "linear16") -> None:
        self.sample_rate = sample_rate
        self.encoding = encoding

    async def start(self, on_transcript: TranscriptCb, on_speech_start: SpeechStartCb) -> None:
        raise RuntimeError("DeepgramSTT not implemented yet (task 9)")

    async def send_audio(self, b64: str) -> None:
        raise RuntimeError("DeepgramSTT not implemented yet (task 9)")

    async def close(self) -> None:
        pass
