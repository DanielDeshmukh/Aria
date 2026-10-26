"""Post-call summary: LLM-produced JSON with a deterministic fallback, so the
4 required keys are always present even if the model misbehaves.

The fallback never quotes raw transcript lines ("Customer said: ..."): it
rebuilds the summary from structured facts - the tool calls the session
recorded, the policy verdicts they returned, and the intent/order-id rules -
and every silent downgrade to it is logged with its reason (LLM exception vs
unparseable JSON) so a low-quality summary is never unexplained again.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .normalize import normalize_order_id

logger = logging.getLogger(__name__)

SUMMARY_KEYS = ("customer_intent", "order_id", "resolution_status", "call_summary")

_INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("CANCELLATION", ("cancel", "cancell")),
    ("RETURN_REFUND", ("return", "refund", "damaged", "broken", "defective")),
    ("GENERAL_QUERY", ("cod", "shipping", "ingredient", "price", "discount")),
    ("ORDER_TRACKING", ("order", "delivery", "delivered", "status", "where", "track", "kahan")),
]

# The agent handing the call over: the escalation cue for resolution_status.
_ESCALATION_RE = re.compile(
    r"\bescalat|\bhuman agent|speak to (a )?human|manager|supervisor|"
    r"team will (contact|call|reach)|callback",
    re.I,
)

_SYSTEM = (
    "You produce the final JSON summary of a customer-support call. "
    "Respond with ONE JSON object and nothing else, with exactly these keys:\n"
    "- customer_intent: UPPER_SNAKE_CASE (e.g. ORDER_TRACKING, CANCELLATION, "
    "RETURN_REFUND, GENERAL_QUERY)\n"
    "- order_id: a string like ORD-101 if an order was discussed, else null\n"
    "- resolution_status: RESOLVED | UNRESOLVED | ESCALATED. RESOLVED means the "
    "request was answered, INCLUDING a policy denial the agent explained (a "
    "denied return is RESOLVED). UNRESOLVED means the question was never "
    "answered or a readable order id was still missing. ESCALATED means the "
    "agent handed the call to a human or promised a human follow-up.\n"
    "- call_summary: 2-3 plain sentences saying what the customer asked and how it "
    "ended. No markdown, and never quote the transcript verbatim."
)

_MISSING = object()

# Intent topic phrases for the no-tool-log fallback summary.
_TOPIC = {
    "ORDER_TRACKING": "order",
    "CANCELLATION": "cancelling an order",
    "RETURN_REFUND": "a return or refund",
    "GENERAL_QUERY": "a product or policy question",
}


def _known_order_id(value: Any) -> str | None:
    """A tool-supplied id counts only when the DB knows it (never guesses)."""
    if value is None:
        return None
    from .tools import ORDERS

    found = normalize_order_id(str(value))
    return found if found and found in ORDERS else None


def _order_id_from_tools(tool_log: list[dict]) -> str | None:
    """Authoritative order id: what the TOOLS were called with (and what they
    returned), not what the transcript happens to contain."""
    for entry in tool_log:
        args = entry.get("args") or {}
        found = _known_order_id(args.get("order_id"))
        if found:
            return found
        result = entry.get("result") or {}
        found = _known_order_id(result.get("order_id")) or _known_order_id(
            result.get("requested")
        )
        if found:
            return found
        order = result.get("order")
        if isinstance(order, dict) and order.get("id"):
            found = _known_order_id(order.get("id"))
            if found:
                return found
    return None


def _intent_from_tools(tool_log: list[dict], keyword_intent: str) -> str:
    """Tool evidence beats keyword guessing: a cancel_order call IS a
    cancellation request. Return/refund is decided by the customer's own words
    (_INTENT_RULES already ranks those above tracking)."""
    for entry in tool_log:
        if entry.get("name") == "cancel_order":
            return "CANCELLATION"
    return keyword_intent


def _resolution_status(
    tool_log: list[dict], agent_lines: list[str], intent: str
) -> str:
    """Deterministic status (the LLM's answer is validated against the same
    rules in _coerce only for presence, not re-derived here):
    - escalation cue in an agent line           -> ESCALATED
    - no agent reply at all                     -> UNRESOLVED
    - order id still missing / NOT_FOUND /      -> UNRESOLVED
      awaiting a confirmation when the call ended
    - explained policy denial or a completed    -> RESOLVED
      tool action (agent replied)
    """
    for line in agent_lines:
        if _ESCALATION_RE.search(line):
            return "ESCALATED"
    if not agent_lines:
        return "UNRESOLVED"
    if not tool_log:
        return "RESOLVED"
    last = tool_log[-1]
    name = last.get("name")
    result = last.get("result") or {}
    error = result.get("error")
    if name == "cancel_order":
        if result.get("cancelled") is True:
            return "RESOLVED"
        if error == "INELIGIBLE":
            # the agent's job here is to state the denial - answered = resolved
            return "RESOLVED"
        return "UNRESOLVED"  # NOT_CONFIRMED (awaiting yes) / NOT_FOUND / no id
    if name == "get_order_details":
        if error in ("NOT_FOUND", "NO_ORDER_ID"):
            return "UNRESOLVED"  # call ended before a usable id came back
        flags = result.get("flags") or {}
        if intent == "RETURN_REFUND" and flags.get("return_eligible") is False:
            return "RESOLVED"  # explained denial
        if intent == "CANCELLATION" and flags.get("cancellable") is False:
            return "RESOLVED"
        return "RESOLVED"
    return "RESOLVED"


def _subject(order_id: str | None, order: dict | None) -> str:
    product = (order or {}).get("product")
    if order_id and product:
        return f"{order_id} ({product})"
    return order_id or "their order"


def _summary_from_tools(tool_log: list[dict], intent: str, order_id: str | None) -> str | None:
    """Build call_summary from the decisive tool outcome + policy text -
    never from transcript lines. Returns None when there is nothing to say."""
    if not tool_log:
        return None
    last = tool_log[-1]
    name = last.get("name")
    args = last.get("args") or {}
    result = last.get("result") or {}
    order = result.get("order") if isinstance(result.get("order"), dict) else None
    oid = order_id or _known_order_id(args.get("order_id")) or _known_order_id(
        result.get("order_id")
    )
    subject = _subject(oid, order)

    if name == "cancel_order":
        if result.get("cancelled") is True:
            return f"Customer asked to cancel {subject}. The order was cancelled."
        if result.get("error") == "INELIGIBLE":
            reason = str(result.get("reason") or "outside the cancellation policy")
            return f"Customer asked to cancel {subject}. Cancellation declined: {reason}"
        if result.get("error") == "NOT_CONFIRMED":
            return (
                f"Customer asked to cancel {subject}; confirmation was still "
                "pending when the call ended."
            )
        if result.get("error") == "NO_ORDER_ID":
            return "Customer asked to cancel an order without a readable id; a repeat of the id was still needed."
        return f"Customer asked to cancel an order id that was not found; a readable id was still needed."

    if name == "get_order_details":
        if result.get("found"):
            status = (order or {}).get("status")
            flags = result.get("flags") or {}
            if intent == "RETURN_REFUND" and flags.get("return_eligible") is False:
                reason = str(flags.get("return_reason") or "outside the return window")
                return f"Customer asked to return {subject}. Return declined: {reason}"
            if intent == "CANCELLATION" and flags.get("cancellable") is False:
                reason = str(flags.get("cancel_reason") or "outside the cancellation policy")
                return f"Customer asked to cancel {subject}. Cancellation declined: {reason}"
            if status:
                return f"Customer asked about {subject}. Order status: {status}."
            return f"Customer asked about {subject}."
        if result.get("error") == "NO_ORDER_ID":
            return "Customer asked about an order without a readable id; a repeat of the id was still needed."
        requested = result.get("requested") or oid or "an order id"
        return f"Customer asked about {requested}, which was not found; a readable id was still needed."

    if name == "get_policy_info":
        topic = result.get("topic") or args.get("topic") or "the applicable"
        return f"Customer asked about {topic} policy; the published policy was applied."

    if name == "end_call":
        return "The customer had no further questions; Aria wrapped the call up."

    return None


def _summary_from_facts(intent: str, order_id: str | None, agent_lines: list[str]) -> str:
    """No tool evidence: still facts, never transcript lines."""
    topic = _TOPIC.get(intent, "a product or policy question")
    if order_id and intent == "ORDER_TRACKING":
        topic = f"order {order_id}"
    elif order_id and intent == "CANCELLATION":
        topic = f"cancelling {order_id}"
    if not agent_lines:
        return f"Customer asked about {topic}; no agent reply was recorded."
    return f"Customer asked about {topic}; Aria answered from the published policy."


def fallback_summary(
    transcript: list[dict], tool_log: list[dict] | None = None
) -> dict:
    tool_log = list(tool_log or [])
    customer_lines = [m["text"] for m in transcript if m.get("role") == "customer" and m.get("text")]
    agent_lines = [m["text"] for m in transcript if m.get("role") == "agent" and m.get("text")]
    haystack = " ".join(customer_lines).lower()

    keyword_intent = "GENERAL_QUERY"
    for name, needles in _INTENT_RULES:
        if any(n in haystack for n in needles):
            keyword_intent = name
            break
    intent = _intent_from_tools(tool_log, keyword_intent)

    order_id = _order_id_from_tools(tool_log)
    if order_id is None:
        from .tools import ORDERS

        for line in customer_lines + agent_lines:
            found = normalize_order_id(line)
            if found and found in ORDERS:  # known DB ids only — avoids "₹3,000" -> ORD-3000
                order_id = found
                break

    status = _resolution_status(tool_log, agent_lines, intent)

    call_summary = _summary_from_tools(tool_log, intent, order_id)
    if call_summary is None:
        call_summary = _summary_from_facts(intent, order_id, agent_lines)
    if status == "ESCALATED" and "escalat" not in call_summary.lower():
        call_summary = f"{call_summary} The call was escalated to a human."
    if len(call_summary) > 300:
        call_summary = call_summary[:297] + "..."

    return {
        "customer_intent": intent,
        "order_id": order_id,
        "resolution_status": status,
        "call_summary": call_summary,
    }


def _coerce(parsed: dict, transcript: list[dict], tool_log: list[dict] | None = None) -> dict:
    fb = fallback_summary(transcript, tool_log)
    out: dict[str, Any] = dict(parsed)  # preserve extras the model added

    ci = parsed.get("customer_intent")
    out["customer_intent"] = (
        str(ci).strip().upper().replace(" ", "_") if ci else fb["customer_intent"]
    )

    oid = parsed.get("order_id", _MISSING)
    if oid is _MISSING:
        out["order_id"] = fb["order_id"]
    elif oid is None:
        out["order_id"] = None
    else:
        normalized = normalize_order_id(str(oid))
        out["order_id"] = normalized or str(oid).strip().upper()

    rs = parsed.get("resolution_status")
    out["resolution_status"] = (
        str(rs).strip().upper().replace(" ", "_") if rs else fb["resolution_status"]
    )
    if out["resolution_status"] not in ("RESOLVED", "UNRESOLVED", "ESCALATED"):
        out["resolution_status"] = fb["resolution_status"]

    cs = parsed.get("call_summary")
    out["call_summary"] = str(cs).strip() if cs and str(cs).strip() else fb["call_summary"]

    for key in SUMMARY_KEYS:
        if key not in out:
            out[key] = fb[key]
    return out


def _parse(text: str) -> dict | None:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def build_summary(
    llm: Any, transcript: list[dict], tool_log: list[dict] | None = None
) -> dict:
    tool_log = list(tool_log or [])
    rendered = "\n".join(
        f"[{'CUSTOMER' if m.get('role') == 'customer' else 'ARIA'}] {m.get('text', '')}"
        for m in transcript
    )
    if tool_log:
        rendered += "\n\nTool calls made during the call:\n" + json.dumps(
            tool_log, ensure_ascii=False, default=str
        )
    try:
        raw = await llm.complete(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": rendered or "(empty call)"},
            ]
        )
    except Exception as exc:
        # The reason the LLM path was NOT used - always logged, never silent.
        logger.warning(
            "summary LLM failed (%s: %s) - using structured fallback",
            type(exc).__name__,
            exc,
        )
        return fallback_summary(transcript, tool_log)
    parsed = _parse(raw)
    if parsed is None:
        excerpt = (raw or "")[:200]
        logger.warning(
            "summary LLM returned unparseable JSON (%r) - using structured fallback",
            excerpt,
        )
        return fallback_summary(transcript, tool_log)
    return _coerce(parsed, transcript, tool_log)
