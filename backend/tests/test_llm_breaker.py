"""Root-cause tests for the 60 s end-of-call hang (Vercel 14:39:25).

The Groq SDK's built-in retry logged "Retrying request in 52.000000 seconds"
AFTER a 429 and slept inside our awaited handler - the SDK now runs with
max_retries=0, only our chain handles 429s, and a per-model circuit breaker
sends turns straight to the fallback while a model is rate-limited.

Offline: create() is scripted, cooldowns are inspected directly. No keys,
no network, no live calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import httpx
import openai
import pytest

from backend.llm import (
    COOLDOWN_CAP_SECONDS,
    COOLDOWN_SECONDS,
    GroqLLM,
    LLMUnavailableError,
    prompt_breakdown,
)
from backend.tests.test_llm_failover import (
    collect,
    make_llm,
    make_llm_complete,
    rate_limit,
    scripted,
    text_step,
)

REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def rate_limit_with(retry_after: str | None) -> openai.RateLimitError:
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    return openai.RateLimitError(
        "Rate limit reached",
        response=httpx.Response(429, request=REQUEST, headers=headers),
        body=None,
    )


# --------------------------------------------------- max_retries=0 (the fix)


def test_client_constructed_with_sdk_retries_disabled() -> None:
    llm = GroqLLM()
    assert llm._client.max_retries == 0, "SDK must never sleep its own ~52 s backoff"


def test_summary_path_uses_the_same_zero_retry_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # make_llm_complete patches exactly llm._client.chat.completions.create;
    # completing through that patch proves summary/complete() rides the
    # max_retries=0 client too - no SDK retry can hide inside the end handler.
    llm, calls = make_llm_complete(monkeypatch, ['{"ok": 1}'])
    assert llm._client.max_retries == 0
    out = asyncio.run(llm.complete([{"role": "user", "content": "sum"}]))
    assert out == '{"ok": 1}'
    assert calls == ["model-a"]  # exactly one request, no hidden SDK retries


# ------------------------------------------------------------ circuit breaker


def test_primary_429_opens_breaker_then_turns_go_straight_to_fallback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    llm, calls = make_llm(
        monkeypatch, [rate_limit(), rate_limit(), text_step("Fallback answer.")]
    )
    with caplog.at_level(logging.INFO, logger="backend.llm"):
        asyncio.run(collect(llm))
    # first turn keeps the in-turn retry (transient 429s can still succeed)
    assert calls == ["model-a", "model-a", "model-b"]
    messages = [r.getMessage() for r in caplog.records]
    assert any("cooling down for" in m for m in messages), messages
    assert "model-a" in llm._cooldowns
    # next turn: breaker open -> primary skipped entirely, no wasted call+retry
    calls.clear()
    monkeypatch.setattr(
        llm._client.chat.completions, "create", scripted([text_step("fb.")], calls)
    )
    events = asyncio.run(collect(llm))
    assert calls == ["model-b"]
    assert events[-1]["model"] == "model-b"


def test_breaker_recovers_after_cooldown_elapses(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    llm, calls = make_llm(monkeypatch, [rate_limit(), rate_limit(), text_step("x")])
    asyncio.run(collect(llm))  # opens the breaker on model-a
    llm._cooldowns["model-a"] = time.monotonic() - 0.01  # cooldown expired
    calls.clear()
    monkeypatch.setattr(
        llm._client.chat.completions, "create", scripted([text_step("back")], calls)
    )
    with caplog.at_level(logging.INFO, logger="backend.llm"):
        asyncio.run(collect(llm))
    assert calls == ["model-a"]  # primary is serving again
    messages = [r.getMessage() for r in caplog.records]
    assert any("available again" in m for m in messages), messages
    assert "model-a" not in llm._cooldowns  # cleared on recovery


def test_retry_after_header_used_and_capped_at_60() -> None:
    llm = GroqLLM()
    llm._mark_cooldown("model-a", rate_limit_with("120"))
    left = llm._cooldowns["model-a"] - time.monotonic()
    assert COOLDOWN_CAP_SECONDS - 1.0 <= left <= COOLDOWN_CAP_SECONDS + 0.5
    llm._mark_cooldown("model-a", rate_limit_with("5"))
    left = llm._cooldowns["model-a"] - time.monotonic()
    assert 4.0 <= left <= 5.5
    llm._mark_cooldown("model-a", rate_limit())  # no header -> default 60
    left = llm._cooldowns["model-a"] - time.monotonic()
    assert COOLDOWN_SECONDS - 1.0 <= left <= COOLDOWN_SECONDS + 0.5
    llm._mark_cooldown("model-a", rate_limit_with("not-a-number"))
    left = llm._cooldowns["model-a"] - time.monotonic()
    assert COOLDOWN_SECONDS - 1.0 <= left <= COOLDOWN_SECONDS + 0.5


def test_all_models_cooling_still_attempts_the_full_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm, calls = make_llm(monkeypatch, [text_step("still try.")])
    now = time.monotonic()
    llm._cooldowns = {"model-a": now + 60, "model-b": now + 60}
    events = asyncio.run(collect(llm))
    assert calls == ["model-a"]  # breaker is advisory: never fail closed
    assert events[-1]["type"] == "llm_stats"


# --------------------------------------------------------- prompt accounting


def test_turn_logs_real_api_usage_from_the_stream(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Groq's real numbers (median ~1,850 prompt tok/request) arrive in the
    # final stream chunk when include_usage is set - the log must use them,
    # not chars/4.
    usage = {
        "choices": [],
        "usage": {"prompt_tokens": 1850, "completion_tokens": 42},
    }
    llm, _ = make_llm(monkeypatch, [text_step("Hi there.") + [usage]])
    with caplog.at_level(logging.INFO, logger="backend.llm"):
        events = asyncio.run(collect(llm))
    assert events[-1]["approx_tokens"] == 1850 + 42  # real, not chars/4
    line = next(r.getMessage() for r in caplog.records if "groq turn" in r.getMessage())
    assert "[groq usage]" in line, line
    assert "prompt=1850" in line and "completion=42" in line, line
    assert "chars/4 estimate" not in line


def test_turn_falls_back_to_labelled_chars_estimate_without_usage(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    llm, _ = make_llm(monkeypatch, [text_step("hi")])
    with caplog.at_level(logging.INFO, logger="backend.llm"):
        asyncio.run(collect(llm))
    line = next(r.getMessage() for r in caplog.records if "groq turn" in r.getMessage())
    assert "[chars/4 estimate - no usage chunk]" in line, line


def test_turn_logs_prompt_breakdown(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    llm, _ = make_llm(monkeypatch, [text_step("hi")])
    with caplog.at_level(logging.INFO, logger="backend.llm"):
        asyncio.run(collect(llm))
    lines = [r.getMessage() for r in caplog.records if "groq turn" in r.getMessage()]
    assert lines, "per-turn cost log must be emitted"
    for needle in ("prompt chars:", "system=", "tools=", "history=", "tool_results="):
        assert needle in lines[0], f"missing {needle!r} in {lines[0]!r}"


def test_prompt_breakdown_sums_to_the_request_payload() -> None:
    messages = [
        {"role": "system", "content": "S" * 100},
        {"role": "user", "content": "u" * 50},
        {"role": "assistant", "content": "a" * 40},
        {"role": "tool", "tool_call_id": "c1", "content": "t" * 60},
    ]
    tools = [{"type": "function", "function": {"name": "x"}}]
    parts = prompt_breakdown(messages, tools)
    assert parts["system"] > 0
    assert parts["tools"] > 0
    assert parts["history"] > 0
    assert parts["tool_results"] > 0
    # parts measure per-message JSON; the list wrapper only adds separators
    per_message = sum(len(json.dumps(m, ensure_ascii=False)) for m in messages)
    assert sum(parts.values()) == per_message + len(
        json.dumps(tools, ensure_ascii=False)
    )


# ----------------------------------------------- summary skip while cooling


def test_summary_skipped_when_entire_chain_is_cooling(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    llm = GroqLLM()
    llm.models = ["model-a", "model-b"]
    now = time.monotonic()
    llm._cooldowns = {"model-a": now + 60, "model-b": now + 60}
    called: list = []

    async def create(**kwargs):
        called.append(kwargs.get("model"))
        raise AssertionError("API must not be called while the chain is cooling")

    monkeypatch.setattr(llm._client.chat.completions, "create", create)
    with caplog.at_level(logging.INFO, logger="backend.llm"):
        with pytest.raises(LLMUnavailableError):
            asyncio.run(llm.complete([{"role": "user", "content": "sum"}]))
    assert called == []  # request skipped, not wasted on a doomed call
    messages = [r.getMessage() for r in caplog.records]
    assert any("summary skipped" in m for m in messages), messages


def test_summary_avoids_a_cooled_model_and_uses_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm, calls = make_llm_complete(monkeypatch, ['{"ok": 1}'])
    llm._cooldowns["model-a"] = time.monotonic() + 60  # primary cooling only
    out = asyncio.run(llm.complete([{"role": "user", "content": "sum"}]))
    assert out == '{"ok": 1}'
    assert calls == ["model-b"]  # straight to the fallback, primary skipped
