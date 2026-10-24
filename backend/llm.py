"""Groq LLM client (OpenAI-compatible): streaming text deltas + tool-call loop.

Pure helpers `feed_chunk` / `finalize_round` are unit-tested without a key.
Key access is via backend.config only (repr-safe).
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Callable

from openai import AsyncOpenAI

from .config import get_settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


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
        self.model = settings.groq_model
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
        """Stream a turn: yields {"type":"text","delta"} live and
        {"type":"tool","name","args","result"} after each tool execution.

        Runs the tool loop internally: tool results are appended to `messages`
        and a follow-up completion starts, until a round ends text-only.
        """
        while True:
            acc = RoundAccumulator()
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "stream": True,
                "temperature": 0.3,
                "max_completion_tokens": 400,
                "reasoning_effort": "low",  # gpt-oss reasons by default; voice needs speed
            }
            if tools:
                kwargs["tools"] = tools
            stream = await self._client.chat.completions.create(**kwargs)
            async for chunk in stream:
                for event in feed_chunk(acc, chunk):
                    yield event
            text, calls = finalize_round(acc)
            if not calls:
                if text:
                    messages.append({"role": "assistant", "content": text})
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
