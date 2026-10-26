from backend.normalize import has_foreign_script, normalize_order_id

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
    # live-runbook STT variants (run 2 of the 14-scenario runbook)
    "ORD-one hundred three": "ORD-103",
    "What's the shipping charge on ORD-one Hundred 2?": "ORD-102",
    "ORD-nine ninety nine": "ORD-999",
    "ORD-one 102": "ORD-102",
    "I got ORD-one hundred two two weeks ago": "ORD-102",
    "Cancel ORD-one hundred three": "ORD-103",
    "ORD1O1": "ORD-101",  # Deepgram smart_format final: letter O between digits
    "Where is my order, ORD1O1": "ORD-101",
    # issue 3: the low-confidence gate opens on normalize()d ids — these
    # exact low-confidence utterances must map ("101" got a canned repeat live)
    "101": "ORD-101",
    "ORD 101": "ORD-101",
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


def test_unrecognized_ids_return_none() -> None:
    for raw in ("?", "my product arrived broken, just now", "ORD two", "Can I cancel ORD?"):
        assert normalize_order_id(raw) is None, raw


def test_foreign_script_flags_non_latin_devanagari_letters() -> None:
    # live repro of the language=multi mis-detection: short English lines
    # coming back as Telugu (or other) finals
    assert has_foreign_script("థాంక్యూ") is True  # Telugu "thank you"
    assert has_foreign_script("నాకు ఆర్డర్ కావాలి") is True  # Telugu words
    assert has_foreign_script("спасибо") is True  # Cyrillic
    assert has_foreign_script("ありがとう") is True  # Japanese
    assert has_foreign_script("مرحبا") is True  # Arabic


def test_foreign_script_allows_latin_devanagari_and_symbols() -> None:
    assert has_foreign_script("") is False
    assert has_foreign_script("Thank you so much!") is False
    assert has_foreign_script("Mera order kahan hai?") is False
    assert has_foreign_script("Café résumé — naïve") is False
    assert has_foreign_script("मेरा ऑर्डर कहाँ है?") is False  # Devanagari Hinglish
    assert has_foreign_script("Order ORD-101 is ₹499 · 7 days…") is False
    assert has_foreign_script("don't — it's ORD-102's") is False
