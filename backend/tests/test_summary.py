import asyncio

import pytest

from backend.summary import SUMMARY_KEYS, build_summary, fallback_summary


def tracking_transcript() -> list[dict]:
    return [
        {"role": "customer", "text": "Where is my order ORD-101?"},
        {"role": "agent", "text": "Your order is out for delivery and expected by 6 PM today."},
    ]


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

    async def complete(self, messages: list[dict]) -> str:
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
