from backend.data.orders import load_orders

DB_FIELDS = (
    "id",
    "customer",
    "product",
    "value",
    "status",
    "carrier",
    "tracking",
    "delivered_days_ago",
    "ordered_hours_ago",
    "notes",
)


def test_three_orders_with_exact_ids() -> None:
    orders = load_orders()
    assert set(orders) == {"ORD-101", "ORD-102", "ORD-103"}


def test_all_db_fields_present_on_every_order() -> None:
    for order in load_orders().values():
        assert tuple(order) == DB_FIELDS


def test_ord_102_values_match_pdf() -> None:
    o = load_orders()["ORD-102"]
    assert o["customer"] == "Rahul Verma"
    assert o["product"] == "Hydrating Sunscreen SPF 50"
    assert o["value"] == "₹499"
    assert o["status"] == "Delivered"
    assert o["carrier"] == "Delhivery"
    assert o["tracking"] == "DL-441029"
    assert o["delivered_days_ago"] == 14
    assert o["notes"] == "Delivered 14 days ago"


def test_ord_101_and_103_values_match_pdf() -> None:
    orders = load_orders()
    o101 = orders["ORD-101"]
    assert o101["customer"] == "Priya Sharma"
    assert o101["product"] == "Vitamin C Serum (30ml)"
    assert o101["value"] == "₹699"
    assert o101["status"] == "Out for Delivery"
    assert o101["carrier"] == "BlueDart"
    assert o101["tracking"] == "BD-982103"
    assert o101["delivered_days_ago"] is None
    assert o101["ordered_hours_ago"] is None

    o103 = orders["ORD-103"]
    assert o103["customer"] == "Ananya Patel"
    assert o103["product"] == "Green Tea Face Wash + Toner"
    assert o103["value"] == "₹850"
    assert o103["status"] == "Processing"
    assert o103["carrier"] is None
    assert o103["tracking"] is None
    assert o103["ordered_hours_ago"] == 3
