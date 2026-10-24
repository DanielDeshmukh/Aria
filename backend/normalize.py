"""Normalize STT-garbled order IDs ("O R D one oh one", "or d 101") to ORD-###.

This is the most likely thing to break in a live demo, so the mapping is
deliberately conservative: letters are kept, only unambiguous spoken digit
words are expanded (standalone "o" is NOT zero — it collides with "ORD").
"""

from __future__ import annotations

import re

SPOKEN_DIGITS: dict[str, str] = {
    "zero": "0",
    "oh": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}

_TOKEN_RE = re.compile(r"[a-z]+|\d+")
_ORDER_RE = re.compile(r"ord(\d{3,})")
_BARE_NUM_RE = re.compile(r"(\d{3,})")


def normalize_order_id(raw: str | None) -> str | None:
    if not raw:
        return None
    tokens = _TOKEN_RE.findall(raw.lower())
    parts: list[str] = []
    for tok in tokens:
        if tok.isdigit():
            parts.append(tok)
        elif tok in SPOKEN_DIGITS:
            parts.append(SPOKEN_DIGITS[tok])
        else:
            parts.append(tok)
    joined = "".join(parts)
    m = _ORDER_RE.search(joined)
    if m:
        return f"ORD-{m.group(1)}"
    m = _BARE_NUM_RE.search(joined)
    if m:
        return f"ORD-{m.group(1)}"
    return None
