"""Live LLM behaviour checks (GROQ_API_KEY required; skipped in CI without it)."""

from __future__ import annotations

import asyncio
import re

import pytest

from backend.config import get_settings
from backend.llm import GroqLLM
from backend.prompts import SYSTEM_PROMPT
from backend.tools import TOOL_SCHEMAS, dispatch

pytestmark = pytest.mark.skipif(
    "GROQ_API_KEY" in get_settings().missing_keys(),
    reason="GROQ_API_KEY not set",
)

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_HINDISH = re.compile(
    r"\b(aapka|aapki|aapne|bataiye|boliye|kijiye|karungi|hoon|raha|rahi|"
    r"nahi|haan|theek|lijiye|kahan|kaise|kya|mera|hai)\b",
    re.I,
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


async def _chat_turns(says: list[str]) -> list[str]:
    """Multi-turn conversation: keeps full history so the language switch
    (Hindi -> English) can be checked against the sticky rule."""
    llm = GroqLLM()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    replies: list[str] = []
    for say in says:
        messages.append({"role": "user", "content": say})
        tools_seen: list = []

        def execute(name: str, args: dict) -> dict:
            tools_seen.append((name, args))
            return dispatch(name, args)

        reply = ""
        async for event in llm.chat(messages, TOOL_SCHEMAS, execute):
            if event["type"] == "text":
                reply += event["delta"]
        messages.append({"role": "assistant", "content": reply})
        replies.append(reply)
    return replies


def _assert_english(say: str, reply: str) -> None:
    assert not _DEVANAGARI.search(reply), (
        f"Devanagari reply to English {say!r}: {reply!r}"
    )
    assert not _HINDISH.search(reply), (
        f"Hinglish marker in a reply to English {say!r}: {reply!r}"
    )


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


def test_english_customer_gets_english_only() -> None:
    """Issue 1 live repro: English questions must never draw a Hindi or
    Hinglish reply (the example phrase in the prompt used to prime it)."""
    for say in (
        "Where is my order ORD-101?",
        "Can you cancel my order ORD-103?",
        "What's the shipping charge on ORD-102?",
    ):
        tools_seen: list = []
        reply = asyncio.run(asyncio.wait_for(_chat(say, tools_seen), 45))
        _assert_english(say, reply)


def test_language_follows_latest_message() -> None:
    """Hindi first (Hinglish reply), then English (English reply) — the
    sticky switch-back rule from the live repro."""
    says = ["Mera order kahan hai?", "It's ORD-101, where is it right now?"]
    replies = asyncio.run(asyncio.wait_for(_chat_turns(says), 90))
    assert _DEVANAGARI.search(replies[0]) or _HINDISH.search(replies[0]), (
        f"expected a Hinglish reply to the Hindi message: {replies[0]!r}"
    )
    _assert_english(says[1], replies[1])


def test_ineligible_cancel_denied_without_confirmation_ask() -> None:
    """Issue 2 live: ORD-102 is Delivered — eligibility must be checked first
    and denied outright, with no 'shall I cancel?' question."""
    tools_seen: list = []
    reply = asyncio.run(
        asyncio.wait_for(_chat("Can you cancel my order ORD-102?", tools_seen), 45)
    )
    assert tools_seen, "expected an eligibility check before answering"
    assert not any(
        name == "cancel_order" and args.get("confirmed") is True
        for name, args in tools_seen
    ), f"cancelled without eligibility: {tools_seen}"
    lowered = reply.lower()
    assert any(
        d in lowered
        for d in (
            "delivered",
            "can't be cancelled",
            "cannot be cancelled",
            "not eligible",
            "ineligible",
        )
    ), f"no denial in reply: {reply!r}"
    for ask in ("would you like", "shall i cancel", "want me to cancel", "should i cancel"):
        assert ask not in lowered, f"asked for confirmation on an ineligible order: {reply!r}"


def test_eligible_cancel_reads_back_before_tool() -> None:
    """Issue 2 live: ORD-103 is Processing — read back and ask, never cancel
    before the customer says yes."""
    tools_seen: list = []
    reply = asyncio.run(asyncio.wait_for(_chat("Cancel ORD-103", tools_seen), 45))
    assert not any(
        name == "cancel_order" and args.get("confirmed") is True
        for name, args in tools_seen
    ), f"cancelled before confirmation: {tools_seen}"
    assert "?" in reply, f"expected a read-back confirmation question: {reply!r}"
    # the model sometimes emits a Unicode hyphen (U+2011) in "ORD‑103"
    assert re.search(r"ord[\s\u2010-\u2015-]*103", reply.lower()), reply
