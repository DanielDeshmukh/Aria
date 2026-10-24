"""Deepgram streaming STT (nova-3, language=multi, keyterm ORD ids).

language=multi (not en-IN): en-IN returned an empty conf=0.0 final for the
Hinglish runbook line "Mera order kahan hai?" while multi transcribes it at
conf 1.0 with equal English quality. No I/O in the constructor: `start()`
opens the socket so missing-key / network failures surface as the session's
error event, never at import.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

import websockets

from .audio_utils import b64_to_pcm16
from .config import get_settings

TranscriptCb = Callable[[str, float | None, bool], Awaitable[None]]
SpeechStartCb = Callable[[], Awaitable[None]]

DEEPGRAM_WS_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-3&language=multi&encoding=linear16&sample_rate={sample_rate}"
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
        self._keepalive: asyncio.Task | None = None
        self._last_audio_at = 0.0
        self._silence = b"\x00" * (sample_rate // 10)  # 100 ms linear16
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
        self._keepalive = asyncio.create_task(self._keepalive_loop())

    async def _keepalive_loop(self) -> None:
        """Feed silence to Deepgram at mic cadence while the client is idle.

        Proven by raw-socket probes: endpointing only fires when packets keep
        ARRIVING after the silent gap — burst-then-idle streams got their final
        only at the ~12 s idle close (code 1011), and even 100 ms of silence
        every 0.5 s never finalized; the cadence must stay near real-time
        (one frame per ~100 ms, exactly like a live microphone). Client frames
        reset the timestamp, so speech audio is never interleaved."""
        try:
            while True:
                await asyncio.sleep(0.1)
                ws = self._ws
                if ws is None:
                    return
                if time.monotonic() - self._last_audio_at >= 0.25:
                    await ws.send(self._silence)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def send_audio(self, b64: str) -> None:
        if self._ws is None:
            raise RuntimeError("start() first")
        self._last_audio_at = time.monotonic()
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
        keepalive, self._keepalive = self._keepalive, None
        reader, self._reader = self._reader, None
        ws, self._ws = self._ws, None
        for task in (keepalive, reader):
            if (
                task is not None
                and task is not asyncio.current_task()
                and not task.done()
            ):
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
