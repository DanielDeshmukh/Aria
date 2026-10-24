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


def test_garbage_order_id_returns_not_found_not_crash() -> None:
    result = tools.dispatch("get_order_details", {"order_id": "banana"})
    assert result["found"] is False
    assert result["error"] == "NOT_FOUND"


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
    assert names == ["get_order_details", "get_policy_info", "end_call"]
    for t in tools.TOOL_SCHEMAS:
        assert t["type"] == "function"
        assert "parameters" in t["function"]
    params = tools.TOOL_SCHEMAS[0]["function"]["parameters"]
    assert params["required"] == ["order_id"]
