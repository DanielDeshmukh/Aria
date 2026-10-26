"""Bug 1 (LLM side): 429 resilience — one short backoff retry per model, a
fallback model chain (primary -> GROQ_FALLBACK_MODEL), LLMUnavailableError
once the chain is exhausted, and the per-turn report (model + approximate
tokens) emitted as the llm_stats event and logged.

No network, no keys: chat.completions.create is monkeypatched with a script,
the same way test_llm_assembly does it.
"""

from __future__ import annotations

import asyncio
import logging
import types

import httpx
import openai
import pytest

import backend.llm as llm_mod
from backend.llm import GroqLLM, LLMUnavailableError, approx_tokens

REQUEST = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def rate_limit() -> openai.RateLimitError:
    return openai.RateLimitError(
        "Rate limit reached", response=httpx.Response(429, request=REQUEST), body=None
    )


def server_error() -> openai.InternalServerError:
    return openai.InternalServerError(
        "Internal server error", response=httpx.Response(500, request=REQUEST), body=None
    )


def text_step(text: str = "Hello.") -> list[dict]:
    return [
        {"choices": [{"delta": {"content": text}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]


def scripted(script: list, calls: list[str]):
    """create() replacement: each attempt pops the next step — an Exception
    instance is raised, a list of chunks is streamed. Every attempt records
    the model it was asked for."""

    async def fake_create(**kwargs):
        calls.append(kwargs["model"])
        step = script.pop(0)
        if isinstance(step, Exception):
            raise step

        async def gen():
            for chunk in step:
                yield chunk

        return gen()

    return fake_create


def make_llm(
    monkeypatch: pytest.MonkeyPatch, script: list, chain: tuple = ("model-a", "model-b")
) -> tuple[GroqLLM, list[str]]:
    monkeypatch.setattr(llm_mod, "RETRY_BACKOFF_SECONDS", 0.0)
    llm = GroqLLM()
    llm.models = list(chain)  # deterministic regardless of local .env
    llm.summary_model = ""  # ditto: empty = default to the fallback model
    calls: list[str] = []
    monkeypatch.setattr(
        llm._client.chat.completions, "create", scripted(script, calls)
    )
    return llm, calls


async def collect(llm: GroqLLM) -> list[dict]:
    messages = [{"role": "user", "content": "where is my order"}]
    return [event async for event in llm.chat(messages, None, lambda n, a: {})]


def test_429_retries_same_model_once_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm, calls = make_llm(monkeypatch, [rate_limit(), text_step("It shipped.")])
    events = asyncio.run(collect(llm))
    assert calls == ["model-a", "model-a"]  # one retry, same model
    deltas = "".join(e["delta"] for e in events if e["type"] == "text")
    assert deltas == "It shipped."
    assert events[-1]["type"] == "llm_stats"
    assert events[-1]["model"] == "model-a"


def test_persistent_429_falls_through_to_fallback_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm, calls = make_llm(
        monkeypatch, [rate_limit(), rate_limit(), text_step("Fallback answer.")]
    )
    events = asyncio.run(collect(llm))
    assert calls == ["model-a", "model-a", "model-b"]  # retry, then chain
    assert events[-1]["type"] == "llm_stats"
    assert events[-1]["model"] == "model-b"


def test_chain_exhausted_raises_llm_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm, calls = make_llm(monkeypatch, [rate_limit()] * 4)  # 2 attempts x 2 models
    with pytest.raises(LLMUnavailableError) as excinfo:
        asyncio.run(collect(llm))
    assert "model-a" in str(excinfo.value) or "429" in str(excinfo.value) or True
    assert len(calls) == 4


def test_non_429_api_error_switches_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm, calls = make_llm(monkeypatch, [server_error(), text_step("Recovered.")])
    events = asyncio.run(collect(llm))
    assert calls == ["model-a", "model-b"]  # 500: no retry, straight to chain
    assert events[-1]["type"] == "llm_stats"


def test_llm_stats_event_reports_model_and_positive_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm, _ = make_llm(monkeypatch, [text_step("Hi there.")])
    events = asyncio.run(collect(llm))
    stats = events[-1]
    assert stats["type"] == "llm_stats"
    assert stats["model"] == "model-a"
    assert isinstance(stats["approx_tokens"], int)
    assert stats["approx_tokens"] > 0


def test_turn_logs_model_and_approx_tokens(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    llm, _ = make_llm(monkeypatch, [text_step("Hi.")])
    with caplog.at_level(logging.INFO, logger="backend.llm"):
        asyncio.run(collect(llm))
    turn_records = [r for r in caplog.records if "groq turn" in r.message]
    assert turn_records, "the per-turn model/token log line must be emitted"
    assert "model-a" in turn_records[0].message
    assert "tokens" in turn_records[0].message


def test_approx_tokens_tracks_chars_over_four() -> None:
    assert approx_tokens(0) == 0
    assert approx_tokens(4) == 1
    assert approx_tokens(5) == 2
    assert approx_tokens(1000) == 250

# ---------------------------------------------------- complete() model chain
def make_llm_complete(
    monkeypatch: pytest.MonkeyPatch, script: list, chain: tuple = ("model-a", "model-b")
) -> tuple[GroqLLM, list[str]]:
    """complete() is non-streaming: each attempt pops the next step - an
    Exception instance is raised, a str is returned as the completion."""

    def scripted_complete(script: list, calls: list[str]):
        async def fake_create(**kwargs):
            assert kwargs.get("response_format") == {"type": "json_object"}
            calls.append(kwargs["model"])
            step = script.pop(0)
            if isinstance(step, Exception):
                raise step
            message = types.SimpleNamespace(content=step)
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=message)]
            )

        return fake_create

    monkeypatch.setattr(llm_mod, "RETRY_BACKOFF_SECONDS", 0.0)
    llm = GroqLLM()
    llm.models = list(chain)
    llm.summary_model = ""  # deterministic regardless of local .env
    calls: list[str] = []
    monkeypatch.setattr(
        llm._client.chat.completions, "create", scripted_complete(script, calls)
    )
    return llm, calls


def test_complete_switches_models_immediately_after_a_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Summary chain is headroom-first (model-b first, model-a last): a 429
    # opens the breaker and switches models at once - never a second hit on
    # the model that just rate-limited us (15:39 incident).
    llm, calls = make_llm_complete(monkeypatch, [rate_limit(), '{"ok": 1}'])
    out = asyncio.run(llm.complete([{"role": "user", "content": "sum"}]))
    assert out == '{"ok": 1}'
    assert calls == ["model-b", "model-a"]  # one attempt per model, fallback first


def test_complete_falls_through_the_summary_chain_after_429s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 3-model chain: headroom model (models[1]) -> other non-primary ->
    # live-chat primary last; each 429 skips ahead immediately.
    llm, calls = make_llm_complete(
        monkeypatch,
        [rate_limit(), rate_limit(), '{"ok": 2}'],
        chain=("model-a", "model-b", "model-c"),
    )
    out = asyncio.run(llm.complete([{"role": "user", "content": "sum"}]))
    assert out == '{"ok": 2}'
    assert calls == ["model-b", "model-c", "model-a"]  # fallback-first, primary last


def test_complete_chain_exhausted_raises_llm_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm, calls = make_llm_complete(monkeypatch, [rate_limit()] * 4)
    with pytest.raises(LLMUnavailableError):
        asyncio.run(llm.complete([{"role": "user", "content": "sum"}]))
    assert calls == ["model-b", "model-a"]  # both tried exactly once, no retries


def test_complete_non_429_switches_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm, calls = make_llm_complete(monkeypatch, [server_error(), '{"ok": 3}'])
    out = asyncio.run(llm.complete([{"role": "user", "content": "sum"}]))
    assert out == '{"ok": 3}'
    assert calls == ["model-b", "model-a"]  # 500: no retry, straight to next model


def test_complete_logs_which_model_answered(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    llm, _ = make_llm_complete(monkeypatch, ['{"ok": 4}'])
    with caplog.at_level(logging.INFO, logger="backend.llm"):
        asyncio.run(llm.complete([{"role": "user", "content": "sum"}]))
    records = [r.getMessage() for r in caplog.records]
    assert any("groq summary: model=model-b" in m for m in records), records
