"""Deepgram streaming STT (nova-3, en-IN, keyterm ORD ids).

No I/O in the constructor: `start()` opens the socket so missing-key /
network failures surface as the session's error event, never at import.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Awaitable, Callable

import websockets

from .audio_utils import b64_to_pcm16
from .config import get_settings

TranscriptCb = Callable[[str, float | None, bool], Awaitable[None]]
SpeechStartCb = Callable[[], Awaitable[None]]

DEEPGRAM_WS_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-3&language=en-IN&encoding=linear16&sample_rate={sample_rate}"
    "&interim_results=true&endpointing=300&smart_format=true"
    "&keyterm=ORD&keyterm=ORD-101&keyterm=ORD-102&keyterm=ORD-103"
)


@dataclass(frozen=True)
class TranscriptEvent:
    text: str
    confidence: float | None
    is_final: bool


@dataclass(frozen=True)
class SpeechStartedEvent:
    pass


def parse_deepgram(msg: dict) -> TranscriptEvent | SpeechStartedEvent | None:
    """Pure parser: Deepgram message -> event (Metadata/UtteranceEnd/etc -> None)."""
    kind = msg.get("type")
    if kind == "SpeechStarted":
        return SpeechStartedEvent()
    if kind == "Results":
        alternatives = ((msg.get("channel") or {}).get("alternatives")) or []
        if not alternatives:
            return None
        alt = alternatives[0]
        confidence = alt.get("confidence")
        return TranscriptEvent(
            text=str(alt.get("transcript", "")),
            confidence=float(confidence) if confidence is not None else None,
            is_final=bool(msg.get("is_final", False)),
        )
    return None


class DeepgramSTT:
    def __init__(
        self,
        api_key: str | None = None,
        sample_rate: int = 16000,
        encoding: str = "linear16",
    ) -> None:
        self.sample_rate = sample_rate
        self.encoding = encoding
        self._api_key = api_key
        self._ws = None
        self._reader: asyncio.Task | None = None
        self._on_transcript: TranscriptCb | None = None
        self._on_speech_start: SpeechStartCb | None = None

    async def start(self, on_transcript: TranscriptCb, on_speech_start: SpeechStartCb) -> None:
        key = (
            self._api_key
            if self._api_key is not None
            else get_settings().deepgram_api_key
        )
        if not key:
            raise RuntimeError("DEEPGRAM_API_KEY missing")
        url = DEEPGRAM_WS_URL.format(sample_rate=self.sample_rate)
        self._on_transcript = on_transcript
        self._on_speech_start = on_speech_start
        self._ws = await websockets.connect(
            url,
            additional_headers={"Authorization": f"Token {key}"},
            open_timeout=10,
            close_timeout=5,
        )
        self._reader = asyncio.create_task(self._read())

    async def send_audio(self, b64: str) -> None:
        if self._ws is None:
            raise RuntimeError("start() first")
        await self._ws.send(b64_to_pcm16(b64))

    async def _read(self) -> None:
        try:
            async for raw in self._ws:
                if not isinstance(raw, str):
                    continue
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                event = parse_deepgram(msg)
                if isinstance(event, TranscriptEvent) and self._on_transcript:
                    await self._on_transcript(event.text, event.confidence, event.is_final)
                elif isinstance(event, SpeechStartedEvent) and self._on_speech_start:
                    await self._on_speech_start()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass  # socket dropped mid-call; session owns the UX

    async def close(self) -> None:
        reader, self._reader = self._reader, None
        ws, self._ws = self._ws, None
        if reader is not None and not reader.done():
            reader.cancel()
            try:
                await reader
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
