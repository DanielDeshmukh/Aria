"""Probe the Sarvam Bulbul v4-flash streaming TTS WebSocket.

Run: python -m backend.scripts.probe_sarvam  (from repo root)

Confirms for Task 11: raw WS URL + auth header work, send/receive frame
shapes, audio chunk format (base64 in JSON vs binary), codec fields, and
the voices list. Exit code 0 iff total audio bytes > 0.
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import urllib.request

import websockets

from backend.config import get_settings

WS_URL = "wss://api.sarvam.ai/text-to-speech/ws?model=bulbul:v4-flash"
# Docs example speaker; the voices fetch below lists what's actually available.
VOICE = "simran_en_customer"
LANGUAGE = "en-IN"
TEXT = "Hello from Aria at Aura Skincare. Your order ORD one oh one is out for delivery."


async def probe_ws(key: str) -> int:
    total = 0
    config = {
        "type": "config",
        "data": {
            "speaker": VOICE,
            "language_code": LANGUAGE,
            "pace": 1.0,
            "min_buffer_size": 50,
            "max_chunk_length": 200,
            "output_audio_codec": "linear16",
        },
    }
    try:
        async with websockets.connect(
            WS_URL,
            additional_headers={"Authorization": f"Bearer {key}"},
            open_timeout=15,
            close_timeout=5,
        ) as ws:
            print(f"CONNECTED {WS_URL}")
            await ws.send(json.dumps(config))
            await ws.send(json.dumps({"type": "text", "data": {"text": TEXT}}))
            await ws.send(json.dumps({"type": "flush"}))
            print("sent config + text + flush")
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=6.0)
                except asyncio.TimeoutError:
                    print("idle timeout (no frame for 6s) — treating as end")
                    break
                if isinstance(raw, bytes):
                    total += len(raw)
                    print(f"BINARY frame: {len(raw)} bytes")
                    continue
                msg = json.loads(raw)
                data = msg.get("data")
                data_keys = list(data.keys()) if isinstance(data, dict) else None
                print(f"frame type={msg.get('type')!r} keys={list(msg)} data_keys={data_keys}")
                if isinstance(data, dict) and "audio" in data:
                    chunk = base64.b64decode(data["audio"])
                    total += len(chunk)
                    extra = {k: v for k, v in data.items() if k != "audio"}
                    print(f"  audio chunk: {len(chunk)} bytes | extra fields: {extra}")
                else:
                    print(f"  payload: {json.dumps(msg, ensure_ascii=False)[:400]}")
    except Exception as exc:
        print(f"WS FAILED: {type(exc).__name__}: {exc}")
        return -1
    print(f"TOTAL AUDIO BYTES: {total}")
    return total


def probe_voices(key: str) -> None:
    urls = (
        "https://api.sarvam.ai/text-to-speech/voices",
        "https://api.sarvam.ai/v1/text-to-speech/voices",
    )
    for url in urls:
        try:
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {key}"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", "replace")
                print(f"VOICES {url} -> {body[:1200]}")
                return
        except Exception as exc:
            print(f"voices {url} failed: {type(exc).__name__}: {exc}")


def main() -> int:
    key = get_settings().sarvam_api_key
    if not key:
        print("SARVAM_API_KEY missing")
        return 2
    total = asyncio.run(probe_ws(key))
    probe_voices(key)
    return 0 if total and total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
