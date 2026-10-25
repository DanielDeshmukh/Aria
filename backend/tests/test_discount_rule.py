"""Phase 3: discount/promo handling — policy entry + LLM exposure.

The PDF states no discount policy, so the only non-inventing answer is
"Aura offers none": recorded once in POLICY_TEXT (code), interpolated into
WHAT YOU KNOW, quotable via get_policy_info, and the guardrail sentence stays
in place. Additive: existing suites are untouched.
"""

from __future__ import annotations

from backend import tools as tools_mod
from backend.policy import POLICY_TEXT
from backend.prompts import SYSTEM_PROMPT

DISCOUNT_TEXT = POLICY_TEXT["discounts"]


def test_discount_policy_states_nothing_is_offered() -> None:
    for needle in ("no discounts", "promo codes", "coupon codes"):
        assert needle in DISCOUNT_TEXT, f"missing: {needle!r}"


def test_discount_policy_interpolated_into_prompt() -> None:
    assert DISCOUNT_TEXT in SYSTEM_PROMPT
    assert "Discounts & promo codes:" in SYSTEM_PROMPT
    # the guardrail sentence from before remains the enforcement phrasing
    assert "You offer no discounts and no exceptions" in SYSTEM_PROMPT


def test_policy_info_can_quote_discounts() -> None:
    result = tools_mod.dispatch("get_policy_info", {"topic": "discounts"})
    assert result == {"topic": "discounts", "policy_text": DISCOUNT_TEXT}


def test_discount_topic_in_tool_enum() -> None:
    schemas = [
        t
        for t in tools_mod.TOOL_SCHEMAS
        if t["function"]["name"] == "get_policy_info"
    ]
    topics = schemas[0]["function"]["parameters"]["properties"]["topic"]["enum"]
    assert "discounts" in topics
