"""Deterministic provider fakes for session/route tests (no keys, no network)."""

from __future__ import annotations

import asyncio
import json
import time

DEFAULT_SUMMARY = {
    "customer_intent": "ORDER_TRACKING",
    "order_id": "ORD-101",
    "resolution_status": "RESOLVED",
    "call_summary": "Customer asked about ORD-101; Aria confirmed out for delivery.",
}


class FakeSTT:
    def __init__(self, start_error: Exception | None = None) -> None:
        self.start_error = start_error
        self.started = False
        self.closed = False
        self.audio: list[str] = []
        self.on_transcript = None
        self.on_speech_start = None

    async def start(self, on_transcript, on_speech_start) -> None:
        if self.start_error is not None:
            raise self.start_error
        self.started = True
        self.on_transcript = on_transcript
        self.on_speech_start = on_speech_start

    async def send_audio(self, b64: str) -> None:
        self.audio.append(b64)

    async def close(self) -> None:
        self.closed = True

    async def emit_final(self, text: str, confidence: float = 0.98) -> None:
        assert self.on_transcript, "start() first"
        await self.on_transcript(text, confidence, True)

    async def emit_interim(self, text: str, confidence: float = 0.9) -> None:
        assert self.on_transcript, "start() first"
        await self.on_transcript(text, confidence, False)

    async def emit_speech_start(self) -> None:
        assert self.on_speech_start, "start() first"
        await self.on_speech_start()


class FakeTTS:
    mime = "audio/wav"

    def __init__(self, fail: bool = False) -> None:
        self.synthed: list[str] = []
        self.fail = fail

    async def synth(self, text: str) -> bytes:
        if self.fail:
            raise RuntimeError("tts down")
        self.synthed.append(text)
        return b"RIFF-FAKE-AUDIO"

    async def close(self) -> None:
        pass


class FakeLLM:
    """Scripted rounds.

    Round tuples:
      ("tool", name, args)  -> yields a tool event (executes via execute_tool)
      ("text", sentence)    -> yields one text delta
      ("hang",)             -> sleeps until cancelled (sets self.cancelled)
      ("error", message)    -> raises RuntimeError(message)

    Default: all rounds replayed on EVERY chat() call (single-turn tests).
    advance=True: rounds are consumed across chat() calls, and a call ends
    after the first "text" round (a model turn ends when the model speaks) —
    so [text][tool+text] scripts a read-back turn followed by a confirmed
    tool turn (issue-3 test).
    """

    def __init__(
        self,
        rounds: list[tuple] | None = None,
        summary: dict | str | Exception | None = None,
        advance: bool = False,
    ) -> None:
        self.rounds = list(rounds or [])
        self.summary = summary if summary is not None else DEFAULT_SUMMARY
        self.advance = advance
        self._cursor = 0
        self.chat_calls = 0
        self.complete_calls = 0
        self.cancelled = False

    async def chat(self, messages, tools, execute_tool):
        self.chat_calls += 1
        if not self.advance:
            for r in self.rounds:
                async for event in self._run_round(r, execute_tool):
                    yield event
            return
        while self._cursor < len(self.rounds):
            r = self.rounds[self._cursor]
            self._cursor += 1
            async for event in self._run_round(r, execute_tool):
                yield event
            if r[0] == "text":
                return

    async def _run_round(self, r: tuple, execute_tool):
        kind = r[0]
        if kind == "tool":
            name, args = r[1], r[2]
            result = execute_tool(name, args)
            yield {"type": "tool", "name": name, "args": args, "result": result}
        elif kind == "text":
            yield {"type": "text", "delta": r[1]}
        elif kind == "hang":
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        elif kind == "error":
            raise RuntimeError(str(r[1]) if len(r) > 1 else "provider down")

    async def complete(self, messages) -> str:
        self.complete_calls += 1
        if isinstance(self.summary, Exception):
            raise self.summary
        if isinstance(self.summary, str):
            return self.summary
        return json.dumps(self.summary)


class EventBox:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def send(self, msg: dict) -> None:
        self.events.append(msg)

    def of(self, typ: str) -> list[dict]:
        return [m for m in self.events if m.get("type") == typ]

    def states(self) -> list[str]:
        return [m["state"] for m in self.of("state")]

    def dump(self) -> str:
        return json.dumps(self.events, ensure_ascii=False, default=str)


async def wait_until(pred, timeout: float = 2.0, what: str = "condition") -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"timed out waiting for {what}")
