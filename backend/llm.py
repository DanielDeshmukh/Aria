"""Groq LLM client (OpenAI-compatible): streaming text deltas + tool-call loop.

Resilience: one short backoff retry per model on 429, then a fallback model
chain (primary -> GROQ_FALLBACK_MODEL, a smaller tool-capable Groq model);
when the whole chain fails it raises LLMUnavailableError, which the session
answers with a spoken apology instead of dying. Every completed turn logs the
model that answered plus approximate token usage (~4 chars/token).

Pure helpers `feed_chunk` / `finalize_round` are unit-tested without a key.
Key access is via backend.config only (repr-safe).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Callable

import openai
from openai import AsyncOpenAI

from .config import get_settings

logger = logging.getLogger("backend.llm")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# One short retry on 429 per model before falling through the chain.
RETRY_BACKOFF_SECONDS = 0.5


class LLMUnavailableError(Exception):
    """Every model in the fallback chain failed (e.g. sustained rate limits)."""


def approx_tokens(chars: int) -> int:
    """Rough token estimate: ~4 characters per token (reported as approximate)."""
    return max(0, (chars + 3) // 4)


def _o(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class RoundAccumulator:
    """Accumulates one completion round: streamed text + fragmented tool calls."""

    def __init__(self) -> None:
        self.text_parts: list[str] = []
        self.tools: dict[int, dict] = {}


def feed_chunk(acc: RoundAccumulator, chunk: Any) -> list[dict]:
    """Consume one stream chunk; return emitted events (text deltas only)."""
    events: list[dict] = []
    choices = _o(chunk, "choices") or []
    if not choices:
        return events
    delta = _o(choices[0], "delta")
    if delta is None:
        return events
    content = _o(delta, "content")
    if content:
        acc.text_parts.append(content)
        events.append({"type": "text", "delta": content})
    for tc in _o(delta, "tool_calls") or []:
        index = _o(tc, "index", 0) or 0
        slot = acc.tools.setdefault(index, {"id": None, "name_parts": [], "arg_parts": []})
        tid = _o(tc, "id")
        if tid:
            slot["id"] = tid
        fn = _o(tc, "function")
        if fn:
            name = _o(fn, "name")
            if name:
                slot["name_parts"].append(name)
            arguments = _o(fn, "arguments")
            if arguments:
                slot["arg_parts"].append(arguments)
    return events


def finalize_round(acc: RoundAccumulator) -> tuple[str, list[dict]]:
    """Close one round: joined text + fully assembled tool calls (parsed args)."""
    text = "".join(acc.text_parts)
    calls: list[dict] = []
    for index in sorted(acc.tools):
        slot = acc.tools[index]
        name = "".join(slot["name_parts"])
        raw = "".join(slot["arg_parts"])
        try:
            args = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as exc:
            raise ValueError(f"tool {name!r} arguments not valid JSON: {raw!r}") from exc
        if not isinstance(args, dict):
            raise ValueError(f"tool {name!r} arguments must be a JSON object, got {type(args).__name__}")
        calls.append({"id": slot["id"] or f"call_{index}", "name": name, "args": args})
    return text, calls


class GroqLLM:
    def __init__(self) -> None:
        settings = get_settings()
        chain: list[str] = []
        for name in (settings.groq_model, settings.groq_fallback_model):
            name = (name or "").strip()
            if name and name not in chain:
                chain.append(name)
        self.models = chain or ["openai/gpt-oss-120b"]
        self.model = self.models[0]
        # Constructor must never raise on missing keys: request-time failures
        # surface to the session, which reports a NAMES-only error event.
        self._client = AsyncOpenAI(
            api_key=settings.groq_api_key or "missing-groq-key",
            base_url=GROQ_BASE_URL,
            timeout=30.0,
        )

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        execute_tool: Callable[[str, dict], dict],
    ) -> AsyncIterator[dict]:
        """Stream a turn: yields {"type":"text","delta"} live,
        {"type":"tool","name","args","result"} after each tool execution, and
        a final {"type":"llm_stats","model","approx_tokens"} before ending.

        Runs the tool loop internally: tool results are appended to `messages`
        and a follow-up completion starts, until a round ends text-only.
        Failure handling: 429 -> one backoff retry on the same model; a
        persistent 429 or any other API error -> next model in the chain;
        chain exhausted -> LLMUnavailableError.
        """
        prompt_chars = 0
        completion_chars = 0
        last_error: Exception | None = None
        for model in self.models:
            retried_429 = False
            while True:
                acc = RoundAccumulator()
                prompt_chars += len(json.dumps(messages, ensure_ascii=False)) + len(
                    json.dumps(tools or [], ensure_ascii=False)
                )
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "temperature": 0.3,
                    "max_completion_tokens": 400,
                    "reasoning_effort": "low",  # reasoning models think by default; voice needs speed
                }
                if tools:
                    kwargs["tools"] = tools
                try:
                    stream = await self._client.chat.completions.create(**kwargs)
                    async for chunk in stream:
                        for event in feed_chunk(acc, chunk):
                            yield event
                except asyncio.CancelledError:
                    raise
                except openai.RateLimitError as exc:
                    last_error = exc
                    if not retried_429:
                        retried_429 = True
                        logger.warning(
                            "groq 429 on %s - retrying once in %.1fs",
                            model,
                            RETRY_BACKOFF_SECONDS,
                        )
                        await asyncio.sleep(RETRY_BACKOFF_SECONDS)
                        continue
                    logger.warning(
                        "groq 429 persists on %s - switching model", model
                    )
                    break
                except openai.APIError as exc:
                    last_error = exc
                    logger.warning(
                        "groq %s on %s - switching model",
                        type(exc).__name__,
                        model,
                    )
                    break
                text, calls = finalize_round(acc)
                completion_chars += len(text) + len(
                    json.dumps(calls, ensure_ascii=False)
                )
                if not calls:
                    if text:
                        messages.append({"role": "assistant", "content": text})
                    self._report_turn(model, prompt_chars, completion_chars)
                    yield {
                        "type": "llm_stats",
                        "model": model,
                        "approx_tokens": approx_tokens(prompt_chars)
                        + approx_tokens(completion_chars),
                    }
                    return
                messages.append(
                    {
                        "role": "assistant",
                        "content": text or None,
                        "tool_calls": [
                            {
                                "id": c["id"],
                                "type": "function",
                                "function": {
                                    "name": c["name"],
                                    "arguments": json.dumps(c["args"], ensure_ascii=False),
                                },
                            }
                            for c in calls
                        ],
                    }
                )
                for c in calls:
                    result = execute_tool(c["name"], c["args"])
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": c["id"],
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                    yield {"type": "tool", "name": c["name"], "args": c["args"], "result": result}
        detail = (
            f"{type(last_error).__name__}: {last_error}" if last_error else "no models"
        )
        logger.error(
            "groq turn failed on all %d model(s) in the chain: %s",
            len(self.models),
            detail,
        )
        raise LLMUnavailableError(f"model chain failed: {detail}") from last_error

    @staticmethod
    def _report_turn(model: str, prompt_chars: int, completion_chars: int) -> None:
        """(d)+(e): which model answered and roughly how many tokens it cost."""
        p_tokens = approx_tokens(prompt_chars)
        c_tokens = approx_tokens(completion_chars)
        logger.info(
            "groq turn: model=%s tokens~%d (prompt~%d + completion~%d)",
            model,
            p_tokens + c_tokens,
            p_tokens,
            c_tokens,
        )

    async def complete(self, messages: list[dict]) -> str:
        """One-shot non-streaming completion (used by the summarizer)."""
        resp = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,
            max_completion_tokens=600,
            response_format={"type": "json_object"},
            reasoning_effort="low",
        )
        return resp.choices[0].message.content or ""
