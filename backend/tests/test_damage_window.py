"""Damaged/defective replacement guardrail.

When a return/refund is declined, Aria must only offer a replacement if the
48-hour-from-delivery damage-report window (with photos) still holds. The
verdict is computed in policy.return_eligibility from the delivery age
(flags the model actually reads) — the prompt alone never decides it.

Offline only: policy/tool flags + SYSTEM_PROMPT wording. No LLM calls.
"""

from __future__ import annotations

from backend import tools as tools_mod
from backend.data.orders import load_orders
from backend.policy import (
    DAMAGED_REPORT_HOURS,
    damage_report_eligibility,
    return_eligibility,
)
from backend.prompts import SYSTEM_PROMPT

ORDERS = load_orders()


def test_ord_102_delivered_14_days_ago_damage_window_passed() -> None:
    # The live ORD-102 flow: return declined (14 > 7 days) AND the damage
    # window must be reported as passed too — no replacement offer.
    assert ORDERS["ORD-102"]["delivered_days_ago"] == 14
    r = return_eligibility(ORDERS["ORD-102"])
    assert r["return_eligible"] is False
    assert r["damage_report_eligible"] is False
    reason = r["damage_report_reason"]
    assert "14 days" in reason
    assert "48 hours, with photos" in reason
    assert "has also passed" in reason


def test_delivered_1_day_ago_damage_window_still_open() -> None:
    order = {**ORDERS["ORD-102"], "delivered_days_ago": 1}
    r = return_eligibility(order)
    # 1 day is inside BOTH windows: a declined return (e.g. opened product)
    # may still lead to a photos-backed replacement offer.
    assert r["return_eligible"] is True
    assert r["damage_report_eligible"] is True
    reason = r["damage_report_reason"]
    assert "within the 48-hour" in reason
    assert "photos" in reason
    # exactly 48 hours (2 days) still counts; 3 days does not
    assert damage_report_eligibility({**order, "delivered_days_ago": 2})[
        "damage_report_eligible"
    ] is True
    assert damage_report_eligibility({**order, "delivered_days_ago": 3})[
        "damage_report_eligible"
    ] is False
    assert DAMAGED_REPORT_HOURS == 48


def test_flags_carry_damage_verdict_for_14_day_order() -> None:
    # What the model reads: get_order_details flags for the live ORD-102.
    flags = tools_mod.get_order_details("ORD-102")["flags"]
    assert flags["return_eligible"] is False
    assert flags["damage_report_eligible"] is False
    assert "48 hours, with photos" in flags["damage_report_reason"]
    assert "has also passed" in flags["damage_report_reason"]


def test_prompt_needles_for_48_hour_wording() -> None:
    for needle in (
        "48 hours of delivery with photos",  # the rule stated first
        "damage_report_eligible",  # prompt wired to the computed flag
        "48 hours, with photos",  # wording Aria must say when it passed
        "has also passed",
        "do NOT offer a replacement",
        "Offer a replacement only when damage_report_eligible is true",
    ):
        assert needle in SYSTEM_PROMPT, f"missing guardrail needle: {needle!r}"
