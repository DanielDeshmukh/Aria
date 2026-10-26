"""Groq LLM client (OpenAI-compatible): streaming text deltas + tool-call loop.

Resilience: the SDK's built-in retries are DISABLED (max_retries=0) so a 429
can never make the SDK sleep ~52 s inside an awaited handler - the incident
that hung the end-of-call path. Only this module handles 429s: chat() makes
one short backoff retry per model, a 60 s circuit breaker per rate-limited
model (Retry-After capped at 60 s) so subsequent turns go straight to the
fallback chain, then LLMUnavailableError when the chain fails. The SUMMARY
request rides a different order: GROQ_SUMMARY_MODEL (default = the fallback
model) first, other non-primary models next, the live-chat primary last -
and it never retries the model that just 429'd (TPM headroom matters more
than a second hit); when every candidate is cooling the request is skipped
entirely so the session falls straight back to the deterministic summary.
Every completed turn logs the model that answered with the API's REAL usage
numbers (Groq puts usage on the final stream chunk under x_groq.usage, or a
top-level usage object; chars/4 only as a labelled fallback) plus a chars
breakdown of what the prompt was made of (system/tools/history/tool_results).

Pure helpers `feed_chunk` / `finalize_round` / `prompt_breakdown` are
unit-tested without a key. Key access is via backend.config only (repr-safe).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Callable

import openai
from openai import AsyncOpenAI

from .config import get_settings

logger = logging.getLogger("backend.llm")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# One short retry on 429 per model before falling through the chain.
RETRY_BACKOFF_SECONDS = 0.5
# Circuit breaker: a model that returned 429 is skipped for this long, or
# the response's Retry-After value - whichever is smaller (hard cap 60 s).
COOLDOWN_SECONDS = 60.0
COOLDOWN_CAP_SECONDS = 60.0


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


def _chunk_usage(chunk: Any) -> tuple[int, int] | None:
    """(prompt_tokens, completion_tokens) from a stream chunk, if present.

    Per Groq's chunk schema, usage rides the FINAL chunk under x_groq.usage
    (and on the dedicated choices:[] chunk before [DONE] when
    stream_options.include_usage is set); a top-level usage may appear too -
    there the OpenAI SDK parses it into a pydantic CompletionUsage OBJECT,
    so both locations must be read by attribute, never gated on isinstance
    (that gate silently dropped real production usage - the 15:39 incident
    logged chars/4 despite Groq sending the numbers)."""
    for usage in (_o(chunk, "usage"), _o(_o(chunk, "x_groq"), "usage")):
        if usage is None:
            continue
        prompt = _o(usage, "prompt_tokens")
        completion = _o(usage, "completion_tokens")
        if prompt is None and completion is None:
            continue
        return (int(prompt or 0), int(completion or 0))
    return None


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


def prompt_breakdown(messages: list[dict], tools: list[dict] | None) -> dict:
    """Chars of ONE actual request, split by part: system / tool schemas /
    conversation history / tool results. Diagnostic composition only - the
    token numbers themselves come from the API's usage, never chars/4."""
    parts = {"system": 0, "tools": 0, "history": 0, "tool_results": 0}
    for msg in messages:
        size = len(json.dumps(msg, ensure_ascii=False))
        role = msg.get("role")
        if role == "system":
            parts["system"] += size
        elif role == "tool":
            parts["tool_results"] += size
        else:
            parts["history"] += size
    parts["tools"] = len(json.dumps(tools or [], ensure_ascii=False))
    return parts


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
        # Configured summary model (GROQ_SUMMARY_MODEL); empty = resolve to
        # the fallback model at request time (see _summary_chain).
        self.summary_model = (settings.groq_summary_model or "").strip()
        # max_retries=0: the SDK must NEVER sleep its own ~52 s backoff
        # inside an awaited handler (root cause of the 60 s end-of-call
        # hang). Only the chain below handles 429s. Constructor still never
        # raises on missing keys: request-time failures surface to the session.
        self._client = AsyncOpenAI(
            api_key=settings.groq_api_key or "missing-groq-key",
            base_url=GROQ_BASE_URL,
            timeout=30.0,
            max_retries=0,
        )
        # Circuit breaker: model -> monotonic deadline while rate-limited.
        self._cooldowns: dict[str, float] = {}

    # ------------------------------------------------------------ breaker
    @staticmethod
    def _retry_after_seconds(exc: openai.RateLimitError) -> float:
        raw = ""
        try:
            raw = (exc.response.headers.get("retry-after") or "").strip()
        except Exception:
            raw = ""
        try:
            seconds = float(raw)
        except ValueError:
            seconds = 0.0
        if seconds <= 0:
            seconds = COOLDOWN_SECONDS
        return min(seconds, COOLDOWN_CAP_SECONDS)

    def _mark_cooldown(self, model: str, exc: openai.RateLimitError) -> None:
        seconds = self._retry_after_seconds(exc)
        self._cooldowns[model] = time.monotonic() + seconds
        logger.info(
            "groq 429 on %s - cooling down for %.0fs (circuit breaker open)",
            model,
            seconds,
        )

    def _usable_models(self) -> list[str]:
        """Models to try for this request: rate-limited ones are skipped so
        turns go straight to the fallback while the breaker is open. Expired
        cooldowns recover (logged). If every model is cooling, the full chain
        is still attempted - a live attempt beats a guaranteed failure."""
        now = time.monotonic()
        usable: list[str] = []
        for model in self.models:
            deadline = self._cooldowns.get(model)
            if deadline is None:
                usable.append(model)
            elif deadline > now:
                logger.debug(
                    "circuit breaker: %s cooling for %.0fs more - skipping",
                    model,
                    deadline - now,
                )
            else:
                del self._cooldowns[model]
                logger.info(
                    "circuit breaker: %s cooldown elapsed - available again", model
                )
                usable.append(model)
        return usable or list(self.models)

    def _summary_chain(self) -> list[str]:
        """Models to try for the end-of-call summary, ordered by headroom.

        The summary must NOT start on the model serving the live chat - its
        TPM budget was just spent BY that call (15:39 incident: chat burned
        ~7k tokens, the summary 429'd on the primary). Order: the configured
        GROQ_SUMMARY_MODEL when set, else the fallback model (models[1]),
        then any other non-primary models, with the live-chat primary last as
        a last resort. Active circuit-breaker cooldowns are skipped (expired
        ones recover, logged), and each model appears at most once, so a model
        that just 429'd is never retried within one summary request. An empty
        list means every candidate is cooling - complete() then skips the API
        call outright and the caller ships the deterministic fallback."""
        now = time.monotonic()

        def usable(model: str) -> bool:
            deadline = self._cooldowns.get(model)
            if deadline is None:
                return True
            if deadline <= now:
                del self._cooldowns[model]
                logger.info(
                    "circuit breaker: %s cooldown elapsed - available again",
                    model,
                )
                return True
            logger.debug(
                "circuit breaker: %s cooling for %.0fs more - skipping",
                model,
                deadline - now,
            )
            return False

        primary = self.models[0] if self.models else ""
        preferred = self.summary_model or (
            self.models[1] if len(self.models) > 1 else primary
        )
        ordered: list[str] = []

        def add(model: str) -> None:
            if model and model not in ordered and usable(model):
                ordered.append(model)

        add(preferred)  # headroom first: configured summary model / fallback
        for model in self.models:  # other non-primary models
            if model not in (preferred, primary):
                add(model)
        add(primary)  # live-chat primary only as a last resort
        return ordered

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
        Failure handling: 429 -> one backoff retry on the same model AND a
        60 s circuit-breaker cooldown for it (later turns skip straight to
        the fallback); a persistent 429 or any other API error -> next model
        in the chain; chain exhausted -> LLMUnavailableError.
        """
        prompt_chars = 0
        completion_chars = 0
        usage_prompt = 0
        usage_completion = 0
        has_usage = False
        breakdown: dict = {}
        last_error: Exception | None = None
        for model in self._usable_models():
            retried_429 = False
            while True:
                acc = RoundAccumulator()
                breakdown = prompt_breakdown(messages, tools)
                # Chars only, for the composition breakdown; the token numbers
                # in the log come from the API's usage (real median ~1,850
                # prompt tokens/request - chars/4 was just a labelled fallback).
                prompt_chars = max(prompt_chars, sum(breakdown.values()))
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                    "temperature": 0.3,
                    "max_completion_tokens": 400,
                    "reasoning_effort": "low",  # reasoning models think by default; voice needs speed
                }
                if tools:
                    kwargs["tools"] = tools
                round_usage: tuple[int, int] | None = None
                try:
                    stream = await self._client.chat.completions.create(**kwargs)
                    async for chunk in stream:
                        found = _chunk_usage(chunk)
                        if found is not None:
                            round_usage = found
                        for event in feed_chunk(acc, chunk):
                            yield event
                    if round_usage is not None:
                        # one usage chunk per request: sum across the turn's
                        # tool-loop rounds for the real per-turn cost
                        has_usage = True
                        usage_prompt += round_usage[0]
                        usage_completion += round_usage[1]
                except asyncio.CancelledError:
                    raise
                except openai.RateLimitError as exc:
                    last_error = exc
                    self._mark_cooldown(model, exc)
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
                    usage = (usage_prompt, usage_completion) if has_usage else None
                    self._report_turn(
                        model, prompt_chars, completion_chars, breakdown, usage
                    )
                    yield {
                        "type": "llm_stats",
                        "model": model,
                        # real API tokens when the usage chunk arrived,
                        # chars/4 estimate otherwise (labelled in the log)
                        "approx_tokens": (usage_prompt + usage_completion)
                        if has_usage
                        else approx_tokens(prompt_chars)
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
    def _report_turn(
        model: str,
        prompt_chars: int,
        completion_chars: int,
        breakdown: dict,
        usage: tuple[int, int] | None = None,
    ) -> None:
        """Per-turn cost from the API's OWN usage numbers when available
        (stream_options.include_usage); chars/4 only as a labelled fallback
        for responses that carried no usage. The chars breakdown shows what
        the prompt was made of - it is diagnostic, never a token count."""
        if usage is not None:
            p_tokens, c_tokens = usage
            cost = f"tokens={p_tokens + c_tokens} (prompt={p_tokens} + completion={c_tokens}) [groq usage]"
        else:
            p_tokens = approx_tokens(prompt_chars)
            c_tokens = approx_tokens(completion_chars)
            cost = (
                f"tokens~{p_tokens + c_tokens} (prompt~{p_tokens} + completion~{c_tokens}) "
                "[chars/4 estimate - no usage chunk]"
            )
        logger.info(
            "groq turn: model=%s %s | prompt chars: system=%d tools=%d "
            "history=%d tool_results=%d",
            model,
            cost,
            breakdown.get("system", 0),
            breakdown.get("tools", 0),
            breakdown.get("history", 0),
            breakdown.get("tool_results", 0),
        )

    async def complete(self, messages: list[dict]) -> str:
        """One-shot non-streaming completion (used by the summarizer).

        Rides the same zero-retry client as chat() but a different strategy:
        _summary_chain() puts the model with the most TPM headroom first
        (GROQ_SUMMARY_MODEL / fallback - never the live-chat primary unless
        it is the last model standing), active breaker cooldowns are skipped,
        and a 429 switches to the NEXT model immediately - the summary never
        retries the model that just rate-limited it (no 0.5 s sleep either;
        the 6 s end-of-call budget is too precious). Empty chain = every
        candidate cooling -> skipped outright, no API call, caller falls back
        to the deterministic summary. The end handler wraps this in
        wait_for(SUMMARY_TIMEOUT) so a slow chain can never hold the call.
        """
        chain = self._summary_chain()
        if not chain:
            logger.info(
                "groq summary skipped - every candidate model is cooling down "
                "(circuit breaker); deterministic fallback will be used"
            )
            raise LLMUnavailableError("all models cooling down (circuit breaker)")
        logger.info("groq summary -> %s", " > ".join(chain))
        last_error: Exception | None = None
        for model in chain:
            try:
                resp = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.2,
                    max_completion_tokens=600,
                    response_format={"type": "json_object"},
                    reasoning_effort="low",
                )
                content = resp.choices[0].message.content or ""
                usage = _o(resp, "usage")
                prompt_tok = _o(usage, "prompt_tokens")
                if prompt_tok is not None:
                    logger.info(
                        "groq summary: model=%s chars=%d prompt_tokens=%d "
                        "completion_tokens=%d [groq usage]",
                        model,
                        len(content),
                        int(prompt_tok),
                        int(_o(usage, "completion_tokens") or 0),
                    )
                else:
                    logger.info(
                        "groq summary: model=%s chars=%d", model, len(content)
                    )
                return content
            except asyncio.CancelledError:
                raise
            except openai.RateLimitError as exc:
                last_error = exc
                self._mark_cooldown(model, exc)
                logger.warning(
                    "groq 429 on %s (summary) - not retrying it (headroom "
                    "matters); switching to the next model",
                    model,
                )
                continue
            except openai.APIError as exc:
                last_error = exc
                logger.warning(
                    "groq %s on %s (summary) - switching model",
                    type(exc).__name__,
                    model,
                )
                continue
        detail = (
            f"{type(last_error).__name__}: {last_error}" if last_error else "no models"
        )
        logger.error(
            "groq summary failed on all %d model(s) in the chain: %s",
            len(chain),
            detail,
        )
        raise LLMUnavailableError(f"summary model chain failed: {detail}") from last_error
