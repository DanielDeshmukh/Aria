from backend.normalize import normalize_order_id

CASES = {
    "O R D one oh one": "ORD-101",
    "ord 101": "ORD-101",
    "or d 101": "ORD-101",
    "ORD-101!": "ORD-101",
    "one zero one": "ORD-101",
    "where is my order ORD-102": "ORD-102",
    "O.R.D. 1 0 1": "ORD-101",
    "ord-103": "ORD-103",
    "ORD102": "ORD-102",
    "o r d one oh three": "ORD-103",
    "999": "ORD-999",
    "ORD-999": "ORD-999",
}


def test_known_spoken_forms() -> None:
    for raw, expected in CASES.items():
        assert normalize_order_id(raw) == expected, f"{raw!r} -> {normalize_order_id(raw)!r}"


def test_no_id_returns_none() -> None:
    assert normalize_order_id("hello") is None
    assert normalize_order_id("") is None
    assert normalize_order_id("   ") is None


def test_none_input_returns_none() -> None:
    assert normalize_order_id(None) is None  # type: ignore[arg-type]


def test_does_not_map_standalone_o_as_zero() -> None:
    # "O" inside ORD must stay a letter, not become digit 0
    assert normalize_order_id("O R D 101") == "ORD-101"


def test_four_digit_ids_keep_all_digits() -> None:
    assert normalize_order_id("ORD-1001") == "ORD-1001"
