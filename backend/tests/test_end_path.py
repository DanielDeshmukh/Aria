"""End-path tests: summary + ended must ALWAYS be delivered, bounded in time.

Covers the production incident where the agent-initiated end (end_call tool)
left the page in LISTENING: _end awaited an unbounded summary LLM call, the
receive loop was blocked behind it, repeat End Call clicks did nothing, and
the socket eventually dropped with "Connection lost" and no summary.

Everything here is offline: fakes, monkeypatched timers, scripted 429s.
"""

from __future__ import annotations

import ast
import asyncio
import logging
import pathlib
import time

import pytest

import backend
import backend.session as session_mod
from backend.llm import LLMUnavailableError
from backend.session import STILL_THERE, CallSession
from backend.summary import SUMMARY_KEYS
from backend.tests._fakes import (
    HANG,
    EventBox,
    FakeLLM,
    FakeSTT,
    FakeTTS,
    wait_until,
)
from backend.tests.test_llm_failover import make_llm_complete, rate_limit

FAREWELL = "Thank you for reaching out. Have a great day!"


def make(llm: FakeLLM | None = None):
    stt, box = FakeSTT(), EventBox()
    llm = llm if llm is not None else FakeLLM()
    tts = FakeTTS()
    session = CallSession(stt=stt, llm=llm, tts=tts, send=box.send)
    return session, box, stt, llm, tts


async def to_listening(session) -> None:
    await session.handle({"type": "start"})
    await session.handle({"type": "playback_done"})


def assert_summary_and_ended(box: EventBox) -> dict:
    summaries = box.of("summary")
    assert len(summaries) == 1, f"expected exactly one summary, got {box.dump()}"
    assert set(SUMMARY_KEYS) <= set(summaries[0]["summary"]), summaries[0]
    assert box.states()[-1] == "ended", box.states()
    return summaries[0]


# ------------------------------------------------- end message vs. summary


def test_end_message_mid_turn_cancels_turn_and_sends_summary() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make(FakeLLM(rounds=[("hang",)]))
        await to_listening(session)
        await stt.emit_final("where is my order")
        await wait_until(lambda: llm.chat_calls == 1, what="turn started")
        await session.handle({"type": "end"})
        assert llm.cancelled, "the in-flight turn must be cancelled by end"
        assert_summary_and_ended(box)

    asyncio.run(scenario())


def test_end_with_hanging_summary_llm_times_out_to_fallback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(session_mod, "SUMMARY_TIMEOUT_SECONDS", 0.1)

    async def scenario() -> None:
        session, box, stt, llm, tts = make(FakeLLM(summary=HANG))
        await to_listening(session)
        started = time.monotonic()
        with caplog.at_level(logging.WARNING, logger="backend.session"):
            await asyncio.wait_for(session.handle({"type": "end"}), timeout=2.0)
        elapsed = time.monotonic() - started
        assert elapsed < 1.0, f"end handler took {elapsed:.2f}s - must stay within the budget"
        assert llm.complete_calls == 1
        summary = assert_summary_and_ended(box)
        # deterministic fallback (FakeLLM never returned its JSON)
        assert summary["summary"]["call_summary"]
        messages = [r.getMessage() for r in caplog.records]
        assert any("timed out" in m for m in messages), messages

    asyncio.run(scenario())


def test_end_with_failing_summary_llm_sends_fallback_summary() -> None:
    async def scenario() -> None:
        fail = FakeLLM(summary=RuntimeError("groq down"))
        session, box, stt, llm, tts = make(fail)
        await to_listening(session)
        await asyncio.wait_for(session.handle({"type": "end"}), timeout=2.0)
        assert llm.complete_calls == 1
        assert_summary_and_ended(box)

    asyncio.run(scenario())


def test_end_with_429_chain_summary_sends_fallback_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # REAL GroqLLM.complete(): every attempt 429s -> chain exhausted ->
    # LLMUnavailableError -> build_summary falls back -> ended still sent.
    llm, calls = make_llm_complete(monkeypatch, [rate_limit()] * 4)
    stt, box, tts = FakeSTT(), EventBox(), FakeTTS()
    session = CallSession(stt=stt, llm=llm, tts=tts, send=box.send)

    async def scenario() -> None:
        await to_listening(session)
        await asyncio.wait_for(session.handle({"type": "end"}), timeout=2.0)
        # summary chain is headroom-first (model-b, the fallback) and a 429
        # switches models immediately - one attempt per model, no retries:
        assert calls == ["model-b", "model-a"]
        assert_summary_and_ended(box)

    asyncio.run(scenario())


def test_end_with_chain_in_cool_down_falls_back_without_waiting() -> None:
    # complete() skips the API entirely when every model is cooling down
    # (circuit breaker) and raises LLMUnavailableError -> build_summary logs
    # the reason and ships the deterministic fallback -> ended still sent.
    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(
                summary=LLMUnavailableError(
                    "all models cooling down (circuit breaker)"
                )
            )
        )
        await to_listening(session)
        started = time.monotonic()
        await asyncio.wait_for(session.handle({"type": "end"}), timeout=2.0)
        assert time.monotonic() - started < 1.0  # skipped, not waited out
        assert llm.complete_calls == 1  # the call was attempted, then refused
        summary = assert_summary_and_ended(box)
        assert summary["summary"]["call_summary"]

    asyncio.run(scenario())


def test_second_end_while_summary_hangs_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_mod, "SUMMARY_TIMEOUT_SECONDS", 0.2)

    async def scenario() -> None:
        session, box, stt, llm, tts = make(FakeLLM(summary=HANG))
        await to_listening(session)
        first = asyncio.create_task(session.handle({"type": "end"}))
        await asyncio.sleep(0.05)  # first _end is now inside the summary wait
        await session.handle({"type": "end"})  # repeat click mid-summary
        await asyncio.wait_for(first, timeout=2.0)
        assert llm.complete_calls == 1  # summarised exactly once
        assert len(box.of("summary")) == 1
        assert box.states().count("ended") == 1

    asyncio.run(scenario())


# ------------------------------------------ agent-initiated end (end_call)


def test_end_call_tool_ends_quietly_after_the_farewell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_mod, "FAREWELL_END_SECONDS", 0.05)

    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(
                rounds=[
                    ("tool", "end_call", {}),
                    ("text", FAREWELL),
                ]
            )
        )
        await to_listening(session)
        await stt.emit_final("that is all, thanks.")
        await wait_until(
            lambda: box.of("summary"), timeout=3.0, what="quiet end after farewell"
        )
        assert_summary_and_ended(box)
        agents = [m["text"] for m in box.of("transcript") if m["role"] == "agent"]
        # the splitter may break the farewell into two transcript rows
        assert FAREWELL in " ".join(agents), agents
        # the idle nudge must NOT follow a goodbye
        assert not any(STILL_THERE in t for t in agents), agents

    asyncio.run(scenario())


def test_end_call_cap_fires_when_model_never_speaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_mod, "END_CALL_MAX_SECONDS", 0.1)

    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(rounds=[("tool", "end_call", {}), ("hang",)])
        )
        await to_listening(session)
        await stt.emit_final("bye for now.")
        await wait_until(
            lambda: box.of("summary"), timeout=3.0, what="cap-driven quiet end"
        )
        assert llm.cancelled, "the hanging turn must be cancelled at the cap"
        assert_summary_and_ended(box)

    asyncio.run(scenario())


# -------------------------------------------- no event-loop blocking (B)


def test_no_time_sleep_or_sync_io_in_async_modules() -> None:
    """A time.sleep (or sync HTTP/subprocess import) in llm/summary/session
    would freeze the whole call - the exact class of bug behind the incident."""
    root = pathlib.Path(backend.__file__).parent
    forbidden_imports = {"requests", "subprocess", "urllib.request", "http.client"}
    for name in ("llm.py", "summary.py", "session.py"):
        src = (root / name).read_text(encoding="utf-8")
        tree = ast.parse(src, filename=name)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "sleep"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "time"
            ):
                raise AssertionError(f"time.sleep() in backend/{name}:{node.lineno}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in forbidden_imports, (
                        f"blocking import {alias.name!r} in backend/{name}:{node.lineno}"
                    )
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module not in forbidden_imports, (
                    f"blocking import {node.module!r} in backend/{name}:{node.lineno}"
                )
