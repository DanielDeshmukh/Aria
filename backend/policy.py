"""Policy engine — every eligibility decision is computed here, in code.

The LLM only paraphrases these results; it never decides them.
POLICY_TEXT holds the PDF's brand/policy wording verbatim (source of truth).
"""

POLICY_TEXT: dict[str, str] = {
    "brand": (
        "Aura Skincare is a premium organic Indian skincare brand focused on "
        "simple, effective skincare products made with thoughtfully selected ingredients."
    ),
    "shipping": (
        "Free delivery on orders above ₹499. Orders below ₹499 have a ₹50 shipping fee. "
        "Standard delivery takes 3–5 business days."
    ),
    "returns": (
        "Returns are accepted within 7 days of delivery for unopened, unused products in "
        "original packaging. Damaged or defective products must be reported within 48 hours "
        "of delivery with photos for replacement."
    ),
    "cancellation": (
        "Orders can be cancelled only while their status is Processing. Once an order is "
        "Shipped or Out for Delivery, it cannot be cancelled (customers may refuse delivery "
        "at doorstep)."
    ),
    "cod": (
        "COD is available for orders up to ₹2,500. Customers can pay by cash or UPI at "
        "the doorstep."
    ),
}

COD_LIMIT = 2500
FREE_SHIPPING_ABOVE = 499
RETURN_WINDOW_DAYS = 7
DAMAGED_REPORT_HOURS = 48

# Enforcement sentence for the assignment's policy-enforcement example
# ("bought ... and have opened it — can I return it?"): the opened/used
# condition is the one eligibility rule no order field can carry, so the
# decision lives here (interpolated verbatim into the system prompt) and the
# LLM only phrases it. Damaged/defective stays on the separate 48-hour path.
OPENED_RETURN_RULE = (
    "Opened, used or unpackaged products cannot be returned — even when the "
    "delivery was within the 7-day window — because returns cover only "
    "unopened, unused products in original packaging. Decline politely: it "
    "falls outside the return policy, and you must never promise a refund. A "
    "product that arrived damaged or defective is handled by the separate "
    "48-hour replacement rule, not this one."
)


def parse_value(value: str) -> int:
    return int(value.replace("₹", "").replace(",", "").strip())


def return_eligibility(order: dict) -> dict:
    if order["status"] != "Delivered":
        return {
            "return_eligible": False,
            "return_reason": (
                f"Order status is {order['status']}, not Delivered — the 7-day return "
                "window starts at delivery."
            ),
        }
    days = order.get("delivered_days_ago")
    if days is None:
        return {
            "return_eligible": False,
            "return_reason": "No delivery date is on record for this order.",
        }
    if days > RETURN_WINDOW_DAYS:
        return {
            "return_eligible": False,
            "return_reason": (
                f"Delivered {days} days ago; returns are accepted within "
                f"{RETURN_WINDOW_DAYS} days of delivery."
            ),
        }
    return {
        "return_eligible": True,
        "condition_required": "unopened, unused, original packaging",
        "return_reason": (
            f"Delivered {days} days ago, within the {RETURN_WINDOW_DAYS}-day window — "
            "valid only if unopened, unused, in original packaging."
        ),
    }


def cancellation(order: dict) -> dict:
    status = order["status"]
    if status == "Processing":
        return {
            "cancellable": True,
            "cancel_reason": "Status is Processing, so the order can still be cancelled.",
        }
    if status in ("Shipped", "Out for Delivery"):
        return {
            "cancellable": False,
            "cancel_reason": (
                f"Order is {status}; once Shipped or Out for Delivery it cannot be "
                "cancelled, but the customer may refuse delivery at the doorstep."
            ),
        }
    if status == "Delivered":
        return {
            "cancellable": False,
            "cancel_reason": "Order is already Delivered, so cancellation no longer applies.",
        }
    return {
        "cancellable": False,
        "cancel_reason": f"Unrecognised status {status}; cancellation cannot be confirmed.",
    }


def cod_available(value: int) -> dict:
    if value <= COD_LIMIT:
        return {
            "cod_available": True,
            "cod_reason": f"COD is available up to ₹{COD_LIMIT:,}; ₹{value:,} is within the limit.",
        }
    return {
        "cod_available": False,
        "cod_reason": f"COD is available up to ₹{COD_LIMIT:,}; ₹{value:,} exceeds the limit.",
    }


def shipping_for(value: int) -> dict:
    if value > FREE_SHIPPING_ABOVE:
        return {
            "shipping_band": "free",
            "shipping_text": "Free delivery on orders above ₹499.",
        }
    if value < FREE_SHIPPING_ABOVE:
        return {
            "shipping_band": "flat_50",
            "shipping_text": "Orders below ₹499 have a ₹50 shipping fee.",
        }
    return {
        "shipping_band": "ambiguous",
        "shipping_text": (
            "The shipping policy covers orders above ₹499 (free delivery) and orders "
            "below ₹499 (₹50 fee). For an order of exactly ₹499 the policy does not "
            "state a charge, so I cannot confirm whether delivery is free — I would not "
            "want to guess."
        ),
    }
