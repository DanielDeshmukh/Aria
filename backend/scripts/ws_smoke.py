"""Remote WebSocket smoke test for a deployed (or local container) Aria.

Run: python -m backend.scripts.ws_smoke wss://<public-host>/ws/call
     (URL defaults to ws://localhost:7860/ws/call when omitted; works
     against the quick tunnel, a container, or local uvicorn)

Asserts the deployed voice session works end to end without a browser:
  1. connect, send `start` → greeting `state` + `audio` events within 15 s
  2. send `end` → `summary` event with the four required keys within 15 s

Exit code 0 iff both assertions pass. Every event type is printed with a
timestamp so failures show exactly where the pipeline stalled.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

import websockets

DEFAULT_URL = "ws://localhost:7860/ws/call"
REQUIRED_SUMMARY_KEYS = (
    "customer_intent",
    "order_id",
    "resolution_status",
    "call_summary",
)
PHASE_TIMEOUT = 15.0


async def smoke(url: str) -> int:
    t0 = time.monotonic()
    got_state: list[str] = []
    audio_count = 0
    summary: dict | None = None
    error_msg: str | None = None

    def stamp() -> str:
        return f"{time.monotonic() - t0:6.2f}s"

    async def drain(ws, until) -> bool:
        """Receive events, printing each, until `until()` is true or the
        phase timeout elapses. Returns True as soon as `until()` holds."""
        deadline = time.monotonic() + PHASE_TIMEOUT
        while time.monotonic() < deadline:
            if until():
                return True
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=deadline - time.monotonic())
            except asyncio.TimeoutError:
                break
            msg = json.loads(raw)
            kind = msg.get("type", "?")
            print(f"[{stamp()}] {kind}")
            if kind == "state":
                got_state.append(msg.get("state", ""))
            elif kind == "audio":
                nonlocal audio_count
                audio_count += 1
            elif kind == "summary":
                nonlocal summary
                summary = msg.get("summary") or {}
            elif kind == "error":
                nonlocal error_msg
                error_msg = msg.get("message", "unknown error")
            if until():
                return True
        return until()

    print(f"smoke → {url}")
    try:
        async with websockets.connect(url, open_timeout=20, ping_interval=20) as ws:
            print(f"[{stamp()}] connected")
            await ws.send(json.dumps({"type": "start"}))
            print(f"[{stamp()}] sent start")

            greeted = await drain(
                ws, lambda: audio_count > 0 and bool(got_state)
            )
            if not greeted:
                print(
                    f"FAIL: no greeting within {PHASE_TIMEOUT:.0f}s "
                    f"(states={got_state}, audio={audio_count}, error={error_msg})"
                )
                return 1
            print(f"[{stamp()}] greeting ok — states={got_state}, audio={audio_count}")

            await ws.send(json.dumps({"type": "end"}))
            print(f"[{stamp()}] sent end")

            got_summary = await drain(ws, lambda: summary is not None)
            if not got_summary:
                print(f"FAIL: no summary within {PHASE_TIMEOUT:.0f}s (error={error_msg})")
                return 1
            missing = [k for k in REQUIRED_SUMMARY_KEYS if k not in summary]
            if missing:
                print(f"FAIL: summary missing keys {missing}: {summary}")
                return 1
            print(f"[{stamp()}] summary ok — {json.dumps(summary, ensure_ascii=False)}")
    except OSError as exc:
        print(f"FAIL: connection error: {exc}")
        return 1

    print("PASS")
    return 0


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    try:
        return asyncio.run(smoke(url))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
