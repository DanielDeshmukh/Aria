from backend.policy import (
    cancellation,
    cod_available,
    parse_value,
    return_eligibility,
    shipping_for,
)
from backend.data.orders import load_orders

ORDERS = load_orders()


def test_parse_value_strips_symbol_and_commas() -> None:
    assert parse_value("₹699") == 699
    assert parse_value("₹1,499") == 1499
    assert parse_value("₹499") == 499


def test_return_ord_102_not_eligible_after_window() -> None:
    r = return_eligibility(ORDERS["ORD-102"])
    assert r["return_eligible"] is False
    assert "14 days" in r["return_reason"]
    assert "7 days" in r["return_reason"]


def test_return_ord_101_not_delivered() -> None:
    r = return_eligibility(ORDERS["ORD-101"])
    assert r["return_eligible"] is False
    assert "Out for Delivery" in r["return_reason"]


def test_return_within_window_eligible() -> None:
    order = {**ORDERS["ORD-102"], "delivered_days_ago": 3}
    r = return_eligibility(order)
    assert r["return_eligible"] is True
    assert "3 days" in r["return_reason"]


def test_cancellation_ord_103_processing_is_eligible() -> None:
    c = cancellation(ORDERS["ORD-103"])
    assert c["cancellable"] is True
    assert "Processing" in c["cancel_reason"]


def test_cancellation_ord_101_out_for_delivery_denied_with_doorstep_option() -> None:
    c = cancellation(ORDERS["ORD-101"])
    assert c["cancellable"] is False
    assert "refuse delivery" in c["cancel_reason"]


def test_cancellation_ord_102_delivered_not_applicable() -> None:
    c = cancellation(ORDERS["ORD-102"])
    assert c["cancellable"] is False


def test_cancellation_shipped_denied_with_doorstep_option() -> None:
    c = cancellation({**ORDERS["ORD-103"], "status": "Shipped"})
    assert c["cancellable"] is False
    assert "refuse delivery" in c["cancel_reason"]


def test_cod_limit() -> None:
    assert cod_available(699)["cod_available"] is True
    assert cod_available(2500)["cod_available"] is True
    low = cod_available(3000)
    assert low["cod_available"] is False
    assert "2,500" in low["cod_reason"]


def test_shipping_bands() -> None:
    assert shipping_for(699)["shipping_band"] == "free"
    assert shipping_for(300)["shipping_band"] == "flat_50"


def test_shipping_exactly_499_is_ambiguous_and_invents_nothing() -> None:
    s = shipping_for(499)
    assert s["shipping_band"] == "ambiguous"
    text = s["shipping_text"]
    assert "above" in text and "below" in text
    assert "₹499" in text
    assert "cannot" in text
    assert "₹50 for this order" not in text
