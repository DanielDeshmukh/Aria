from backend import tools
from backend.policy import POLICY_TEXT

NOT_FOUND_MSG = (
    "I couldn't locate an order with that number, could you please repeat or verify "
    "the ID?"
)


def test_get_order_details_ord_101_with_flags() -> None:
    result = tools.dispatch("get_order_details", {"order_id": "ORD-101"})
    assert result["found"] is True
    assert result["order"]["status"] == "Out for Delivery"
    flags = result["flags"]
    assert flags["cancellable"] is False
    assert flags["return_eligible"] is False
    assert flags["cod_available"] is True
    assert flags["shipping_band"] == "free"


def test_get_order_details_normalizes_spoken_forms() -> None:
    for spoken in ("or d one oh one", "ORD 101", "ord-one-oh-one", "one oh one"):
        result = tools.dispatch("get_order_details", {"order_id": spoken})
        assert result["found"] is True, f"{spoken!r} not found"
        assert result["order"]["id"] == "ORD-101"


def test_get_order_details_unknown_id_returns_exact_pdf_phrase() -> None:
    result = tools.dispatch("get_order_details", {"order_id": "ORD-999"})
    assert result["found"] is False
    assert result["error"] == "NOT_FOUND"
    assert result["message"] == NOT_FOUND_MSG


def test_non_id_phrases_get_no_order_id_guard_not_not_found() -> None:
    for raw in ("banana", "just now", "Order", "?"):
        result = tools.dispatch("get_order_details", {"order_id": raw})
        assert result["found"] is False, raw
        assert result["error"] == "NO_ORDER_ID", raw
        assert result["needs_id"] is True, raw
        assert "ask the customer" in result["message"]


def test_flags_per_order_match_pdf_scenarios() -> None:
    o102 = tools.dispatch("get_order_details", {"order_id": "ORD-102"})
    assert o102["flags"]["return_eligible"] is False
    assert o102["flags"]["shipping_band"] == "ambiguous"
    assert o102["flags"]["cancellable"] is False

    o103 = tools.dispatch("get_order_details", {"order_id": "ORD-103"})
    assert o103["flags"]["cancellable"] is True
    assert o103["flags"]["return_eligible"] is False
    assert o103["flags"]["cod_available"] is True


def test_get_policy_info_returns_verbatim_text() -> None:
    for topic in ("shipping", "returns", "cancellation", "cod", "brand"):
        result = tools.dispatch("get_policy_info", {"topic": topic})
        assert result["topic"] == topic
        assert result["policy_text"] == POLICY_TEXT[topic]


def test_get_policy_info_unknown_topic() -> None:
    result = tools.dispatch("get_policy_info", {"topic": "warranty"})
    assert result["error"] == "UNKNOWN_TOPIC"


def test_end_call() -> None:
    assert tools.dispatch("end_call", {}) == {"ok": True}


def test_unknown_tool_name() -> None:
    assert tools.dispatch("launch_rocket", {}) == {"error": "UNKNOWN_TOOL"}


def test_tool_schemas_shape() -> None:
    names = [t["function"]["name"] for t in tools.TOOL_SCHEMAS]
    assert names == ["get_order_details", "cancel_order", "get_policy_info", "end_call"]
    for t in tools.TOOL_SCHEMAS:
        assert t["type"] == "function"
        assert "parameters" in t["function"]
    params = tools.TOOL_SCHEMAS[0]["function"]["parameters"]
    assert params["required"] == ["order_id"]
    cancel_params = tools.TOOL_SCHEMAS[1]["function"]["parameters"]
    assert cancel_params["required"] == ["order_id", "confirmed"]
    assert cancel_params["properties"]["confirmed"]["type"] == "boolean"


def test_cancel_order_requires_confirmed_true() -> None:
    """The confirmation gate lives in code: confirmed=false refuses with a
    read-back instruction even though ORD-103 is eligible."""
    result = tools.dispatch(
        "cancel_order", {"order_id": "ORD-103", "confirmed": False}
    )
    assert result["cancelled"] is False
    assert result["error"] == "NOT_CONFIRMED"
    assert result["order_id"] == "ORD-103"
    assert "read back" in result["message"].lower()
    assert "explicit yes" in result["message"].lower()
    # dispatch must treat non-boolean truthy values as NOT confirmed
    result = tools.dispatch("cancel_order", {"order_id": "ORD-103", "confirmed": "true"})
    assert result["cancelled"] is False
    assert result["error"] == "NOT_CONFIRMED"


def test_cancel_order_happy_path_ord_103() -> None:
    result = tools.dispatch(
        "cancel_order", {"order_id": "ORD-103", "confirmed": True}
    )
    assert result["cancelled"] is True
    assert result["order_id"] == "ORD-103"
    assert result["status"] == "Cancelled"
    assert "ORD-103" in result["message"]
    # mock database stays read-only
    assert tools.ORDERS["ORD-103"]["status"] == "Processing"


def test_cancel_order_ineligible_ord_101_refusal_note() -> None:
    result = tools.dispatch(
        "cancel_order", {"order_id": "ORD-101", "confirmed": True}
    )
    assert result["cancelled"] is False
    assert result["error"] == "INELIGIBLE"
    assert "refuse delivery" in result["reason"]
    assert result["order"]["status"] == "Out for Delivery"


def test_cancel_order_ineligible_ord_102_delivered() -> None:
    result = tools.dispatch(
        "cancel_order", {"order_id": "ORD-102", "confirmed": True}
    )
    assert result["cancelled"] is False
    assert result["error"] == "INELIGIBLE"
    assert "Delivered" in result["reason"]


def test_cancel_order_unknown_id() -> None:
    result = tools.dispatch(
        "cancel_order", {"order_id": "ORD-999", "confirmed": True}
    )
    assert result["cancelled"] is False
    assert result["error"] == "NOT_FOUND"
    assert result["message"] == NOT_FOUND_MSG


def test_cancel_order_no_readable_id() -> None:
    result = tools.dispatch("cancel_order", {"order_id": "just now", "confirmed": True})
    assert result["cancelled"] is False
    assert result["error"] == "NO_ORDER_ID"
    assert result["needs_id"] is True
    assert "ask the customer" in result["message"].lower()


def test_cancel_order_confirmed_false_probes_eligibility() -> None:
    """Issue 2: confirmed=false is the eligibility probe — an ineligible order
    comes back INELIGIBLE with the policy reason (never NOT_CONFIRMED), so the
    model can deny before ever asking the customer to confirm."""
    for oid, status in (("ORD-101", "Out for Delivery"), ("ORD-102", "Delivered")):
        result = tools.dispatch("cancel_order", {"order_id": oid, "confirmed": False})
        assert result["cancelled"] is False
        assert result["error"] == "INELIGIBLE"
        assert result["cancellable"] is False
        assert result["reason"]
        assert result["order"]["status"] == status
    result = tools.dispatch("cancel_order", {"order_id": "ORD-103", "confirmed": False})
    assert result["error"] == "NOT_CONFIRMED"
