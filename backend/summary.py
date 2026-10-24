"""Post-call summary: LLM-produced JSON with a deterministic fallback, so the
4 required keys are always present even if the model misbehaves."""

from __future__ import annotations

import json
import re
from typing import Any

from .normalize import normalize_order_id

SUMMARY_KEYS = ("customer_intent", "order_id", "resolution_status", "call_summary")

_INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("CANCELLATION", ("cancel", "cancell")),
    ("RETURN_REFUND", ("return", "refund", "damaged", "broken", "defective")),
    ("GENERAL_QUERY", ("cod", "shipping", "ingredient", "price", "discount")),
    ("ORDER_TRACKING", ("order", "delivery", "delivered", "status", "where", "track", "kahan")),
]

_SYSTEM = (
    "You produce the final JSON summary of a customer-support call. "
    "Respond with ONE JSON object and nothing else, with exactly these keys:\n"
    "- customer_intent: UPPER_SNAKE_CASE (e.g. ORDER_TRACKING, CANCELLATION, "
    "RETURN_REFUND, GENERAL_QUERY)\n"
    "- order_id: a string like ORD-101 if an order was discussed, else null\n"
    "- resolution_status: RESOLVED | UNRESOLVED | DECLINED\n"
    "- call_summary: 2-3 plain sentences saying what the customer asked and how it "
    "ended. No markdown."
)

_MISSING = object()


def fallback_summary(transcript: list[dict]) -> dict:
    customer_lines = [m["text"] for m in transcript if m.get("role") == "customer" and m.get("text")]
    agent_lines = [m["text"] for m in transcript if m.get("role") == "agent" and m.get("text")]
    haystack = " ".join(customer_lines).lower()

    intent = "GENERAL_QUERY"
    for name, needles in _INTENT_RULES:
        if any(n in haystack for n in needles):
            intent = name
            break

    order_id: str | None = None
    from .tools import ORDERS

    for line in customer_lines + agent_lines:
        found = normalize_order_id(line)
        if found and found in ORDERS:  # known DB ids only — avoids "₹3,000" -> ORD-3000
            order_id = found
            break

    status = "RESOLVED" if agent_lines else "UNRESOLVED"

    first = customer_lines[0] if customer_lines else "the customer opened the call"
    last = agent_lines[-1] if agent_lines else "no agent reply was recorded"
    call_summary = f"Customer said: {first} Aria replied: {last}"
    if len(call_summary) > 300:
        call_summary = call_summary[:297] + "..."

    return {
        "customer_intent": intent,
        "order_id": order_id,
        "resolution_status": status,
        "call_summary": call_summary,
    }


def _coerce(parsed: dict, transcript: list[dict]) -> dict:
    fb = fallback_summary(transcript)
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


async def build_summary(llm: Any, transcript: list[dict]) -> dict:
    rendered = "\n".join(
        f"[{'CUSTOMER' if m.get('role') == 'customer' else 'ARIA'}] {m.get('text', '')}"
        for m in transcript
    )
    try:
        raw = await llm.complete(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": rendered or "(empty call)"},
            ]
        )
        parsed = _parse(raw)
    except Exception:
        return fallback_summary(transcript)
    if parsed is None:
        return fallback_summary(transcript)
    return _coerce(parsed, transcript)
