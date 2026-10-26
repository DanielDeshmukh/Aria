"""Tools exposed to the LLM.

Everything that decides eligibility is computed by backend.policy — tools only
fetch data and attach computed flags, so the model can never invent policy.
"""

from __future__ import annotations

import time

from .data.orders import ORDERS, get_order  # ORDERS re-exported for summary.py and tests
from .normalize import normalize_order_id
from . import policy

# Server-side cost of the last get_order_details call (id normalization +
# repository lookup + policy verdict), in milliseconds. session.py copies it
# into the per-turn stats event as tool_lookup_ms.
LAST_LOOKUP_MS: float | None = None


def last_lookup_ms() -> float | None:
    return LAST_LOOKUP_MS


def _ms_since(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0

NOT_FOUND_MESSAGE = (
    "I couldn't locate an order with that number, could you please repeat or verify "
    "the ID?"
)

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_order_details",
            "description": (
                "Look up an Aura Skincare order by order id (e.g. ORD-101). Handles "
                "spoken/garbled ids. Returns order fields plus computed eligibility "
                "flags, or a structured NOT_FOUND result."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Order id, spoken forms allowed (ORD-101, 101, ORD 101)",
                    }
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_order",
            "description": (
                "Cancel an order that is still Processing. Check eligibility "
                "FIRST (get_order_details flags.cancellable, or call with "
                "confirmed=false to preview); if it is not cancellable return "
                "the INELIGIBLE reason to the customer without asking for "
                "confirmation. Call with confirmed=true only after reading "
                "back the order id and product and getting an explicit yes. "
                "Returns structured NOT_CONFIRMED, NOT_FOUND or INELIGIBLE "
                "results instead of cancelling; never mutates data beyond "
                "this."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Order id, spoken forms allowed (ORD-101, 101, ORD 101)",
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": (
                            "true ONLY after the customer explicitly confirmed the "
                            "read-back; false previews eligibility without cancelling"
                        ),
                    },
                },
                "required": ["order_id", "confirmed"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_policy_info",
            "description": "Fetch the exact Aura Skincare policy text on a topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "enum": ["shipping", "returns", "cancellation", "cod", "brand", "discounts"],
                    }
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_call",
            "description": "Wrap the call up politely once the customer has no more questions.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def get_order_details(order_id: str) -> dict:
    global LAST_LOOKUP_MS
    started = time.perf_counter()
    normalized = normalize_order_id(order_id)
    if normalized is None:
        # Runbook scenarios 9/11: the model called with "Order"/"just now".
        # A non-id must never come back as NOT_FOUND — steer the reply to
        # ask the customer to say the order id again instead.
        LAST_LOOKUP_MS = _ms_since(started)
        return {
            "found": False,
            "error": "NO_ORDER_ID",
            "requested": order_id,
            "needs_id": True,
            "message": (
                "No readable order id was given. Do NOT say the order couldn't be "
                "found — ask the customer to say the order id again."
            ),
        }
    order = get_order(normalized)
    if order is None:
        LAST_LOOKUP_MS = _ms_since(started)
        return {
            "found": False,
            "error": "NOT_FOUND",
            "requested": order_id,
            "message": NOT_FOUND_MESSAGE,
        }
    value = policy.parse_value(order["value"])
    flags = {
        **policy.return_eligibility(order),
        **policy.cancellation(order),
        **policy.cod_available(value),
        **policy.shipping_for(value),
    }
    LAST_LOOKUP_MS = _ms_since(started)
    return {"found": True, "order": order, "flags": flags}


def cancel_order(order_id: str, confirmed: bool) -> dict:
    """Confirm-gated cancellation: eligibility comes from policy, and the tool
    refuses unless the customer explicitly confirmed (confirmed=True). The
    mock database is never mutated — the result is structured data only."""
    normalized = normalize_order_id(order_id)
    if normalized is None:
        return {
            "cancelled": False,
            "error": "NO_ORDER_ID",
            "requested": order_id,
            "needs_id": True,
            "message": (
                "No readable order id was given. Ask the customer to say the "
                "order id again."
            ),
        }
    order = get_order(normalized)
    if order is None:
        return {
            "cancelled": False,
            "error": "NOT_FOUND",
            "requested": order_id,
            "message": NOT_FOUND_MESSAGE,
        }
    verdict = policy.cancellation(order)
    if not verdict["cancellable"]:
        # ORD-101's reason carries the refuse-at-the-doorstep note; ORD-102
        # gets the already-delivered reason — both straight from policy.py.
        return {
            "cancelled": False,
            "error": "INELIGIBLE",
            "order_id": normalized,
            "order": order,
            "cancellable": False,
            "reason": verdict["cancel_reason"],
        }
    if not confirmed:
        return {
            "cancelled": False,
            "error": "NOT_CONFIRMED",
            "order_id": normalized,
            "message": (
                "The customer has not confirmed yet. Read back the order id and "
                "product, get an explicit yes, then call again with confirmed=true."
            ),
        }
    return {
        "cancelled": True,
        "order_id": normalized,
        "order": order,
        "status": "Cancelled",
        "message": f"Order {normalized} is cancelled.",
    }


def get_policy_info(topic: str) -> dict:
    if topic not in policy.POLICY_TEXT:
        return {"error": "UNKNOWN_TOPIC", "available": sorted(policy.POLICY_TEXT)}
    return {"topic": topic, "policy_text": policy.POLICY_TEXT[topic]}


def end_call() -> dict:
    return {"ok": True}


def dispatch(name: str, args: dict) -> dict:
    if name == "get_order_details":
        return get_order_details(str(args.get("order_id", "")))
    if name == "cancel_order":
        # `is True` so a truthy string ("false") can never pass the gate.
        return cancel_order(str(args.get("order_id", "")), args.get("confirmed") is True)
    if name == "get_policy_info":
        return get_policy_info(str(args.get("topic", "")))
    if name == "end_call":
        return end_call()
    return {"error": "UNKNOWN_TOOL"}
