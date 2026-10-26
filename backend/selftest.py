"""Outbound connectivity self-test for the deployed Vercel function.

Answers the one question the docs leave open: whether a function instance can
open outbound WebSockets to Deepgram and Sarvam and reach Groq over HTTPS.
Each probe returns (ok, detail); detail is an HTTP status, a sentinel like
"DEEPGRAM_API_KEY missing", or an exception TYPE name — never a key, token,
or credential-bearing URL."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

import httpx
import websockets

from .config import get_settings

DEEPGRAM_WS_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-3&language={language}&encoding=linear16&sample_rate=16000"
)
SARVAM_WS_URL = "wss://api.sarvam.ai/text-to-speech/ws?model=bulbul:v4-flash"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"

CONNECT_TIMEOUT = 10.0

# (result key, module-level probe function name) — looked up at call time so
# tests can monkeypatch the probes without touching the route.
PROBES: tuple[tuple[str, str], ...] = (
    ("deepgram_ws", "_probe_deepgram_ws"),
    ("sarvam_ws", "_probe_sarvam_ws"),
    ("groq_https", "_probe_groq_https"),
)


async def _probe_deepgram_ws() -> tuple[bool, str]:
    key = get_settings().deepgram_api_key
    if not key:
        return False, "DEEPGRAM_API_KEY missing"
    ws = await websockets.connect(
        DEEPGRAM_WS_URL.format(language=get_settings().stt_language),
        additional_headers={"Authorization": f"Token {key}"},
        open_timeout=CONNECT_TIMEOUT,
        close_timeout=5,
    )
    await ws.close()
    return True, "ok"


async def _probe_sarvam_ws() -> tuple[bool, str]:
    key = get_settings().sarvam_api_key
    if not key:
        return False, "SARVAM_API_KEY missing"
    ws = await websockets.connect(
        SARVAM_WS_URL,
        additional_headers={"Authorization": f"Bearer {key}"},
        open_timeout=CONNECT_TIMEOUT,
        close_timeout=5,
    )
    await ws.close()
    return True, "ok"


async def _probe_groq_https() -> tuple[bool, str]:
    key = get_settings().groq_api_key
    if not key:
        return False, "GROQ_API_KEY missing"
    async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT) as client:
        response = await client.get(
            GROQ_MODELS_URL, headers={"Authorization": f"Bearer {key}"}
        )
    if response.status_code == 200:
        return True, "ok"
    return False, f"HTTP {response.status_code}"


async def run_selftest() -> dict[str, Any]:
    """Probe every provider once; result carries ok/detail/ms per probe and a
    top-level ok flag. Exception details are type names only."""
    out: dict[str, Any] = {}
    all_ok = True
    for key, fn_name in PROBES:
        probe: Callable[[], Awaitable[tuple[bool, str]]] = globals()[fn_name]
        started = time.monotonic()
        try:
            ok, detail = await probe()
        except Exception as exc:  # noqa: BLE001 — report, never propagate
            ok, detail = False, type(exc).__name__
        out[key] = {
            "ok": ok,
            "detail": detail,
            "ms": int((time.monotonic() - started) * 1000),
        }
        all_ok = all_ok and ok
    out["ok"] = all_ok
    return out
