import asyncio
import logging

import pytest

from backend import tools as tools_mod
from backend.summary import SUMMARY_KEYS, build_summary, fallback_summary


def tracking_transcript() -> list[dict]:
    return [
        {"role": "customer", "text": "Where is my order ORD-101?"},
        {"role": "agent", "text": "Your order is out for delivery and expected by 6 PM today."},
    ]


def tool_entry(name: str, args: dict, result: dict) -> dict:
    return {"name": name, "args": args, "result": result}


def test_fallback_tracking_case() -> None:
    s = fallback_summary(tracking_transcript())
    assert set(SUMMARY_KEYS) <= set(s)
    assert s["customer_intent"] == "ORDER_TRACKING"
    assert s["order_id"] == "ORD-101"
    assert s["resolution_status"] == "RESOLVED"
    assert "ORD-101" in s["call_summary"]
    assert len(s["call_summary"]) <= 300


def test_fallback_cancellation_and_return_intents() -> None:
    cancel = fallback_summary([{"role": "customer", "text": "Can I cancel my order ORD-103?"}])
    assert cancel["customer_intent"] == "CANCELLATION"
    assert cancel["order_id"] == "ORD-103"

    ret = fallback_summary([{"role": "customer", "text": "My sunscreen arrived damaged"}])
    assert ret["customer_intent"] == "RETURN_REFUND"

    general = fallback_summary([{"role": "customer", "text": "Is COD available for a ₹3,000 order?"}])
    assert general["customer_intent"] == "GENERAL_QUERY"


def test_fallback_normalizes_spoken_ids() -> None:
    s = fallback_summary([{"role": "customer", "text": "check O R D one oh one"}])
    assert s["order_id"] == "ORD-101"


def test_fallback_empty_transcript_has_all_keys() -> None:
    s = fallback_summary([])
    assert set(SUMMARY_KEYS) <= set(s)
    assert s["order_id"] is None
    assert s["resolution_status"] == "UNRESOLVED"


def test_fallback_no_agent_replies_is_unresolved() -> None:
    s = fallback_summary([{"role": "customer", "text": "hello?"}])
    assert s["resolution_status"] == "UNRESOLVED"


class FakeLLM:
    def __init__(self, reply: str | Exception = "") -> None:
        self.reply = reply
        self.messages: list[dict] = []

    async def complete(self, messages: list[dict]) -> str:
        self.messages = messages
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def test_build_uses_llm_json_when_valid() -> None:
    llm = FakeLLM(
        '{"customer_intent": "ORDER_TRACKING", "order_id": "ORD-102", '
        '"resolution_status": "RESOLVED", "call_summary": "Asked about delivery.", "extra": 1}'
    )
    s = asyncio.run(build_summary(llm, tracking_transcript()))
    assert s["customer_intent"] == "ORDER_TRACKING"
    assert s["order_id"] == "ORD-102"
    assert s["extra"] == 1  # extras preserved


def test_build_falls_back_on_malformed_json() -> None:
    s = asyncio.run(build_summary(FakeLLM("sorry, here is a summary: ..."), tracking_transcript()))
    assert s["customer_intent"] == "ORDER_TRACKING"
    assert s["order_id"] == "ORD-101"


def test_build_falls_back_on_exception() -> None:
    s = asyncio.run(build_summary(FakeLLM(RuntimeError("boom")), tracking_transcript()))
    assert set(SUMMARY_KEYS) <= set(s)


def test_build_repairs_missing_and_bad_keys() -> None:
    llm = FakeLLM('{"customer_intent": "order tracking", "call_summary": ""}')
    s = asyncio.run(build_summary(llm, tracking_transcript()))
    assert s["customer_intent"] == "ORDER_TRACKING"  # normalized
    assert s["resolution_status"] == "RESOLVED"  # repaired from fallback
    assert s["call_summary"].strip()  # repaired
    assert s["order_id"] == "ORD-101"  # repaired


def test_build_handles_fenced_json() -> None:
    llm = FakeLLM(
        '```json\n{"customer_intent": "GENERAL_QUERY", "order_id": null, '
        '"resolution_status": "RESOLVED", "call_summary": "Chatted."}\n```'
    )
    s = asyncio.run(build_summary(llm, tracking_transcript()))
    assert s["customer_intent"] == "GENERAL_QUERY"
    assert s["order_id"] is None  # model said null — key present is what matters


# ------------------------------------- structured-facts fallback (tool_log)
def test_fallback_return_denial_ord102_is_resolved() -> None:
    """ORD-102 delivered 14 days ago: the return is denied, the agent explains
    it, so the deterministic fallback must say RESOLVED and quote the POLICY
    FACTS - never a transcript line."""
    result = tools_mod.get_order_details("ORD-102")
    assert result["flags"]["return_eligible"] is False
    tool_log = [tool_entry("get_order_details", {"order_id": "ORD-102"}, result)]
    transcript = [
        {
            "role": "customer",
            "text": "I got my sunscreen two weeks ago, can I return it?",
        },
        {
            "role": "agent",
            "text": "Returns are accepted within 7 days of delivery, so this "
            "one is outside the return window.",
        },
    ]
    s = fallback_summary(transcript, tool_log)
    assert s["customer_intent"] == "RETURN_REFUND"
    assert s["order_id"] == "ORD-102"
    assert s["resolution_status"] == "RESOLVED"
    summary = s["call_summary"]
    assert "ORD-102" in summary and "Hydrating Sunscreen SPF 50" in summary
    assert "14 days" in summary and "7 days" in summary  # policy facts
    assert not summary.startswith("Customer said")
    assert transcript[0]["text"] not in summary
    assert transcript[1]["text"] not in summary
    assert len(summary) <= 300


def test_fallback_tracking_ord101_from_tool_log() -> None:
    result = tools_mod.get_order_details("ORD-101")
    assert result["found"] is True
    tool_log = [tool_entry("get_order_details", {"order_id": "ORD-101"}, result)]
    s = fallback_summary(tracking_transcript(), tool_log)
    assert s["customer_intent"] == "ORDER_TRACKING"
    assert s["order_id"] == "ORD-101"
    assert s["resolution_status"] == "RESOLVED"
    summary = s["call_summary"]
    assert summary == (
        "Customer asked about ORD-101 (Vitamin C Serum (30ml)). "
        "Order status: Out for Delivery."
    )
    assert tracking_transcript()[0]["text"] not in summary


def test_fallback_cancel_ord103_confirmed_is_resolved() -> None:
    result = tools_mod.cancel_order("ORD-103", True)
    assert result["cancelled"] is True
    tool_log = [
        tool_entry(
            "cancel_order", {"order_id": "ORD-103", "confirmed": True}, result
        )
    ]
    transcript = [
        {"role": "customer", "text": "Please cancel order ORD-103"},
        {"role": "agent", "text": "Done - ORD-103 is cancelled now."},
    ]
    s = fallback_summary(transcript, tool_log)
    assert s["customer_intent"] == "CANCELLATION"
    assert s["order_id"] == "ORD-103"
    assert s["resolution_status"] == "RESOLVED"
    assert "ORD-103" in s["call_summary"]
    assert "cancelled" in s["call_summary"]
    assert transcript[1]["text"] not in s["call_summary"]


def test_fallback_cancel_ineligibility_explained_is_resolved() -> None:
    """A policy denial the agent explained counts as RESOLVED - not DECLINED,
    not UNRESOLVED."""
    result = tools_mod.cancel_order("ORD-101", False)
    assert result["error"] == "INELIGIBLE"
    tool_log = [
        tool_entry(
            "cancel_order", {"order_id": "ORD-101", "confirmed": False}, result
        )
    ]
    transcript = [
        {"role": "customer", "text": "cancel my order ORD-101"},
        {
            "role": "agent",
            "text": "Your order is out for delivery so it cannot be "
            "cancelled, but you may refuse it at the doorstep.",
        },
    ]
    s = fallback_summary(transcript, tool_log)
    assert s["customer_intent"] == "CANCELLATION"
    assert s["order_id"] == "ORD-101"
    assert s["resolution_status"] == "RESOLVED"
    assert "declined" in s["call_summary"]
    assert "ORD-101" in s["call_summary"]


def test_fallback_unknown_order_id_is_unresolved() -> None:
    result = tools_mod.get_order_details("ORD-999")
    assert result["error"] == "NOT_FOUND"
    tool_log = [tool_entry("get_order_details", {"order_id": "ORD-999"}, result)]
    transcript = [
        {"role": "customer", "text": "where is order ORD-999"},
        {"role": "agent", "text": "I could not find that order."},
    ]
    s = fallback_summary(transcript, tool_log)
    assert s["resolution_status"] == "UNRESOLVED"
    assert s["order_id"] is None  # ORD-999 is not in the order DB
    assert "not found" in s["call_summary"]
    assert transcript[1]["text"] not in s["call_summary"]


def test_fallback_escalation_status() -> None:
    transcript = [
        {"role": "customer", "text": "I want a manager for my refund"},
        {
            "role": "agent",
            "text": "I will escalate this to a human agent and they will "
            "call you back.",
        },
    ]
    s = fallback_summary(transcript)
    assert s["resolution_status"] == "ESCALATED"
    assert "escalated" in s["call_summary"]
    assert transcript[0]["text"] not in s["call_summary"]


def test_fallback_never_quotes_raw_transcript_lines() -> None:
    transcript = [
        {"role": "customer", "text": "blablabla unique question one"},
        {"role": "agent", "text": "blablabla unique answer two"},
    ]
    s = fallback_summary(transcript)
    summary = s["call_summary"]
    assert "Customer said:" not in summary
    assert "Aria replied:" not in summary
    assert transcript[0]["text"] not in summary
    assert transcript[1]["text"] not in summary


def test_build_logs_reason_when_llm_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="backend.summary"):
        s = asyncio.run(build_summary(FakeLLM(RuntimeError("boom")), tracking_transcript()))
    assert set(SUMMARY_KEYS) <= set(s)
    messages = [r.getMessage() for r in caplog.records]
    assert any(
        "summary LLM failed" in m and "RuntimeError" in m for m in messages
    ), messages
    assert any("structured fallback" in m for m in messages), messages


def test_build_logs_reason_when_json_unparseable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = "sorry, here is a summary: ..."
    with caplog.at_level(logging.WARNING, logger="backend.summary"):
        s = asyncio.run(build_summary(FakeLLM(raw), tracking_transcript()))
    assert set(SUMMARY_KEYS) <= set(s)
    messages = [r.getMessage() for r in caplog.records]
    assert any("unparseable JSON" in m for m in messages), messages
    assert any(raw in m for m in messages), messages  # the excerpt is logged


def test_build_passes_tool_log_to_the_llm_prompt() -> None:
    llm = FakeLLM(
        '{"customer_intent": "RETURN_REFUND", "order_id": "ORD-102", '
        '"resolution_status": "RESOLVED", "call_summary": "Asked about a return."}'
    )
    result = tools_mod.get_order_details("ORD-102")
    tool_log = [tool_entry("get_order_details", {"order_id": "ORD-102"}, result)]
    s = asyncio.run(build_summary(llm, tracking_transcript(), tool_log))
    assert s["order_id"] == "ORD-102"
    prompt = llm.messages[-1]["content"]
    assert "Tool calls made during the call" in prompt
    assert "ORD-102" in prompt


@pytest.mark.skipif(
    not __import__("backend.config", fromlist=["get_settings"]).get_settings().groq_api_key,
    reason="GROQ_API_KEY not set",
)
def test_build_live_llm() -> None:
    import asyncio

    from backend.llm import GroqLLM

    s = asyncio.run(asyncio.wait_for(build_summary(GroqLLM(), tracking_transcript()), 30))
    assert set(SUMMARY_KEYS) <= set(s)
    assert s["order_id"] == "ORD-101"
    assert "ORD-101" in s["call_summary"]
