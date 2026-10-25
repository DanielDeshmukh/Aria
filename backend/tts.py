"""Sarvam Bulbul v4 Flash TTS — streaming WebSocket, sentence-level synth.

Findings locked from backend/scripts/probe_sarvam.py (2026-10-24):
- URL: wss://api.sarvam.ai/text-to-speech/ws?model=bulbul:v4-flash
  (+ &send_completion_event=true -> server ends each utterance with
  {"type":"event","data":{"event_type":"final"}})
- auth: Authorization: Bearer <sarvam key>
- config frame must be the FIRST message after connect; audio format:
  {"output_audio_codec": "linear16", "speech_sample_rate": 16000}.
- speech_sample_rate IS honored: WS bytes/16000 == REST WAV duration at
  16000 (ratio 1.008); omitted -> 22050 (REST docs default).
- frames: send {"type":"text","data":{"text":...}} then {"type":"flush"};
  receive {"type":"audio","data":{"request_id","content_type":"audio/pcm",
  "audio":<base64 PCM16>}} chunks until the final event.
- without the URL flag there is no end marker -> idle-gap fallback below.
- voice: simran_en_customer (female, en-IN, customer-support persona;
  REST voices catalog) — override via SARVAM_VOICE env.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from typing import Any, AsyncIterator

import websockets
from websockets.exceptions import ConnectionClosed

from .config import get_settings

SARVAM_WS_URL = (
    "wss://api.sarvam.ai/text-to-speech/ws"
    "?model=bulbul:v4-flash&send_completion_event=true"
)
DEFAULT_VOICE = "simran_en_customer"
LANGUAGE_CODE = "en-IN"
SAMPLE_RATE = 16000
MAX_TEXT_CHARS = 500  # sentences are short by construction; hard API cap is far above
IDLE_TIMEOUT_SECONDS = 4.0  # fallback terminator if the final event never arrives
CONNECT_TIMEOUT = 15.0


def _chunk_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > limit and current:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


class SarvamTTS:
    """Persistent WS per instance: lazy connect in synth, reconnect after a drop."""

    mime = f"audio/l16;rate={SAMPLE_RATE}"

    def __init__(self) -> None:
        self._voice: str = get_settings().sarvam_voice or DEFAULT_VOICE
        self._ws: Any = None

    async def synth(self, text: str) -> bytes:
        text = text.strip()
        if not text:
            return b""
        for attempt in (1, 2):
            try:
                return await self._synthesize(text)
            except asyncio.CancelledError:
                # barge-in: drop the socket so stale frames cannot bleed
                # into the next utterance (Sarvam's own barge-in recipe).
                await self._drop()
                raise
            except (ConnectionClosed, OSError) as exc:
                await self._drop()
                if attempt == 2:
                    raise RuntimeError(
                        f"{type(exc).__name__}: Sarvam TTS connection failed twice"
                    ) from exc
        raise RuntimeError("unreachable")

    async def _synthesize(self, text: str) -> bytes:
        if self._ws is None:
            await self._connect()
        assert self._ws is not None
        out = bytearray()
        for piece in _chunk_text(text, MAX_TEXT_CHARS):
            await self._ws.send(json.dumps({"type": "text", "data": {"text": piece}}))
            await self._ws.send(json.dumps({"type": "flush"}))
            out += await self._collect()
        if not out:
            raise RuntimeError("SarvamTTS: no audio returned")
        return bytes(out)

    async def synth_stream(self, text: str) -> AsyncIterator[bytes]:
        """Yield PCM chunks as Sarvam produces them, so the first audio can
        reach the client before the whole sentence has synthesized.

        Retry mirrors synth(): one reconnect, but only before any chunk has
        been yielded — replaying after a partial send would corrupt audio.
        """
        text = text.strip()
        if not text:
            return
        sent_any = False
        for attempt in (1, 2):
            try:
                async for chunk in self._stream(text):
                    sent_any = True
                    yield chunk
                return
            except asyncio.CancelledError:
                # barge-in: drop the socket so stale frames cannot bleed
                # into the next utterance (same contract as synth()).
                await self._drop()
                raise
            except (ConnectionClosed, OSError) as exc:
                await self._drop()
                if sent_any:
                    raise RuntimeError(
                        f"{type(exc).__name__}: Sarvam TTS connection failed mid-stream"
                    ) from exc
                if attempt == 2:
                    raise RuntimeError(
                        f"{type(exc).__name__}: Sarvam TTS connection failed twice"
                    ) from exc
        raise RuntimeError("unreachable")

    async def _stream(self, text: str) -> AsyncIterator[bytes]:
        if self._ws is None:
            await self._connect()
        assert self._ws is not None
        produced = 0
        for piece in _chunk_text(text, MAX_TEXT_CHARS):
            await self._ws.send(json.dumps({"type": "text", "data": {"text": piece}}))
            await self._ws.send(json.dumps({"type": "flush"}))
            async for chunk in self._collect_stream():
                produced += len(chunk)
                yield chunk
        if not produced:
            raise RuntimeError("SarvamTTS: no audio returned")

    async def _collect_stream(self) -> AsyncIterator[bytes]:
        """Yield each audio frame until the final event or the idle gap."""
        assert self._ws is not None
        while True:
            try:
                raw = await asyncio.wait_for(
                    self._ws.recv(), timeout=IDLE_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                break  # idle gap = utterance complete (docs pattern)
            if not isinstance(raw, str):
                continue
            msg = json.loads(raw)
            kind = msg.get("type")
            if kind == "audio":
                yield base64.b64decode(msg["data"]["audio"])
            elif kind == "event" and msg.get("data", {}).get("event_type") == "final":
                break

    async def _connect(self) -> None:
        key = get_settings().sarvam_api_key
        if not key:
            raise RuntimeError("SARVAM_API_KEY missing")
        ws = await websockets.connect(
            SARVAM_WS_URL,
            additional_headers={"Authorization": f"Bearer {key}"},
            open_timeout=CONNECT_TIMEOUT,
            close_timeout=5,
        )
        await ws.send(
            json.dumps(
                {
                    "type": "config",
                    "data": {
                        "speaker": self._voice,
                        "language_code": LANGUAGE_CODE,
                        "pace": 1.0,
                        "min_buffer_size": 50,
                        "max_chunk_length": 200,
                        "output_audio_codec": "linear16",
                        "speech_sample_rate": SAMPLE_RATE,
                    },
                }
            )
        )
        self._ws = ws

    async def _collect(self) -> bytes:
        assert self._ws is not None
        buf = bytearray()
        while True:
            try:
                raw = await asyncio.wait_for(
                    self._ws.recv(), timeout=IDLE_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                break  # idle gap = utterance complete (docs pattern)
            if not isinstance(raw, str):
                continue
            msg = json.loads(raw)
            kind = msg.get("type")
            if kind == "audio":
                buf += base64.b64decode(msg["data"]["audio"])
            elif kind == "event" and msg.get("data", {}).get("event_type") == "final":
                break
        return bytes(buf)

    async def _drop(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()

    async def close(self) -> None:
        await self._drop()
