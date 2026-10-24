"""Live LLM behaviour checks (GROQ_API_KEY required; skipped in CI without it)."""

from __future__ import annotations

import asyncio

import pytest

from backend.config import get_settings
from backend.llm import GroqLLM
from backend.prompts import SYSTEM_PROMPT
from backend.tools import TOOL_SCHEMAS, dispatch

pytestmark = pytest.mark.skipif(
    "GROQ_API_KEY" in get_settings().missing_keys(),
    reason="GROQ_API_KEY not set",
)


async def _chat(say: str, tools_seen: list) -> str:
    llm = GroqLLM()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": say},
    ]

    def execute(name: str, args: dict) -> dict:
        tools_seen.append((name, args))
        return dispatch(name, args)

    reply = ""
    async for event in llm.chat(messages, TOOL_SCHEMAS, execute):
        if event["type"] == "text":
            reply += event["delta"]
    return reply


def test_order_question_calls_tool_then_answers() -> None:
    tools_seen: list = []
    reply = asyncio.run(asyncio.wait_for(_chat("Where is my order ORD-101?", tools_seen), 45))
    assert tools_seen, "expected get_order_details to be called"
    name, args = tools_seen[0]
    assert name == "get_order_details"
    assert "101" in str(args["order_id"])
    lowered = reply.lower()
    assert "out for delivery" in lowered or "6 pm" in lowered
    assert len(reply) <= 600, "replies must stay concise (1-2 sentences)"


def test_out_of_scope_redirects_to_aura() -> None:
    tools_seen: list = []
    reply = asyncio.run(asyncio.wait_for(_chat("Can you book me a flight to Goa?", tools_seen), 45))
    assert tools_seen == [], "no tool should be called for an out-of-scope ask"
    lowered = reply.lower()
    assert "aura" in lowered or "skincare" in lowered
    assert "book" not in lowered or "can't" in lowered or "cannot" in lowered or "only" in lowered
    assert len(reply) <= 600
