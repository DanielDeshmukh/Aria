"""Phase 2: opened/unopened return-eligibility enforcement.

The one eligibility condition no order field can carry is the product's
condition (opened/used), so the decision lives in policy.OPENED_RETURN_RULE —
interpolated verbatim into the system prompt — and the tool flags carry the
matching condition fact for the in-window branch. Additive: existing suites
are untouched.
"""

from __future__ import annotations

from backend.data.orders import load_orders
from backend.policy import OPENED_RETURN_RULE, return_eligibility
from backend.prompts import SYSTEM_PROMPT
from backend import tools as tools_mod

ORDERS = load_orders()


def test_within_window_flags_require_unopened_condition() -> None:
    order = {**ORDERS["ORD-102"], "delivered_days_ago": 3}
    r = return_eligibility(order)
    assert r["return_eligible"] is True
    assert r["condition_required"] == "unopened, unused, original packaging"
    assert "unopened" in r["return_reason"]


def test_declined_branches_state_no_condition() -> None:
    # window/status denials keep their original shape — the condition is
    # irrelevant once the window or delivery gate already failed
    assert "condition_required" not in return_eligibility(ORDERS["ORD-102"])
    assert "condition_required" not in return_eligibility(ORDERS["ORD-101"])


def test_tool_flags_carry_condition_for_in_window_order(monkeypatch) -> None:
    in_window = {**ORDERS["ORD-102"], "delivered_days_ago": 3}
    monkeypatch.setitem(tools_mod.ORDERS, "ORD-102", in_window)
    flags = tools_mod.get_order_details("ORD-102")["flags"]
    assert flags["return_eligible"] is True
    assert flags["condition_required"] == "unopened, unused, original packaging"


def test_opened_rule_verbatim_in_prompt() -> None:
    assert OPENED_RETURN_RULE in SYSTEM_PROMPT
    for needle in (
        "Opened, used or unpackaged products cannot be returned",
        "even when the delivery was within the 7-day window",
        "never promise a refund",
        "48-hour replacement rule",  # stays separate from the damaged path
    ):
        assert needle in OPENED_RETURN_RULE, f"missing: {needle!r}"


def test_prompt_separates_opened_rule_from_damaged_path() -> None:
    # the damaged/defective 48-hour guardrail must remain intact alongside it
    assert "48 hours of delivery with photos" in SYSTEM_PROMPT
    assert "Product condition" in SYSTEM_PROMPT
