"""Normalize STT-garbled order IDs ("O R D one oh one", "or d 101",
"ORD-one hundred three", "nine ninety nine") to ORD-###.

This is the most likely thing to break in a live demo, so the mapping is
deliberately conservative: only unambiguous number phrases become digits
(standalone "o" is NOT zero — it collides with "ORD"), adjacent number
runs never merge ("one hundred two two weeks" must not become 1022), and
an id needs at least three digits, so fragments like "ORD two" return None.
"""

from __future__ import annotations

import re
import unicodedata

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

DECADE_WORDS: dict[str, int] = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

_TOKEN_RE = re.compile(r"[a-z]+|\d+")
_ORDER_RE = re.compile(r"ord(\d{3,})")
_BARE_NUM_RE = re.compile(r"(\d{3,})")
_INTERIOR_O_RE = re.compile(r"(?<=\d)o(?=\d)")  # smart_format "ORD1O1" -> 101
_RUN_JOIN = "x"  # letter between adjacent number runs: "ord102x2" keeps 102


def _is_number_token(tok: str) -> bool:
    return (
        tok.isdigit()
        or tok in SPOKEN_DIGITS
        or tok in DECADE_WORDS
        or tok in ("hundred", "and")
    )


def _simple_value(toks: list[str]) -> int | None:
    if all(t.isdigit() or t in SPOKEN_DIGITS for t in toks):
        return int("".join(t if t.isdigit() else SPOKEN_DIGITS[t] for t in toks))
    if (
        len(toks) in (2, 3)
        and toks[0] in SPOKEN_DIGITS
        and toks[1] in DECADE_WORDS
        and (len(toks) == 2 or toks[2] in SPOKEN_DIGITS)
    ):
        units = int(SPOKEN_DIGITS[toks[2]]) if len(toks) == 3 else 0
        return int(SPOKEN_DIGITS[toks[0]]) * 100 + DECADE_WORDS[toks[1]] + units
    if len(toks) == 2 and toks[0] in DECADE_WORDS and toks[1] in SPOKEN_DIGITS:
        return DECADE_WORDS[toks[0]] + int(SPOKEN_DIGITS[toks[1]])
    return None


def _hundred_rest_value(rest: list[str]) -> int | None:
    if not rest:
        return 0
    if len(rest) == 1:
        if rest[0] in DECADE_WORDS:  # "one hundred twenty" -> 120
            return DECADE_WORDS[rest[0]]
        return _simple_value(rest)
    if len(rest) == 2:
        if rest[0] in DECADE_WORDS:  # "one hundred twenty five" -> 125
            return _simple_value(rest)
        if rest[0] in ("zero", "oh"):  # digit reading: "zero one" -> 01
            return int("0" + SPOKEN_DIGITS[rest[1]])
        if all(t.isdigit() for t in rest):
            return int("".join(rest))
        return None  # spillover like "two two weeks" — caller retries prefix
    return None


def _run_value(toks: list[str]) -> int | None:
    toks = [t for t in toks if t != "and"]
    if not toks:
        return None
    literals = [t for t in toks if t.isdigit() and len(t) >= 3]
    if literals:
        return int(max(literals, key=len))
    if "hundred" in toks:
        i = toks.index("hundred")
        head, rest = toks[:i], toks[i + 1 :]
        if not head:
            return None
        hv = _simple_value(head)
        if hv is None:
            return None
        rv = _hundred_rest_value(rest)
        if rv is None:
            return None
        return hv * 100 + rv
    return _simple_value(toks)


def has_foreign_script(text: str) -> bool:
    """True when `text` contains letters outside Latin or Devanagari.

    Live repro of the language=multi mis-detection: a short English line
    ("thank you") came back as Telugu finals and was acted on. Any letter
    whose Unicode name is neither LATIN nor DEVANAGARI flags the final, so
    the session treats it as unclear and asks to repeat instead. Symbols,
    digits and punctuation never flag (so "₹499", "…" and "ORD-101" pass),
    and Devanagari stays allowed so Hinglish output still passes under any
    language setting.
    """
    for ch in text:
        if not unicodedata.category(ch).startswith("L"):
            continue
        name = unicodedata.name(ch, "")
        if "LATIN" not in name and "DEVANAGARI" not in name:
            return True
    return False


def normalize_order_id(raw: str | None) -> str | None:
    if not raw:
        return None
    tokens = _TOKEN_RE.findall(raw.lower())
    parts: list[str] = []
    i = 0
    prev_number = False
    while i < len(tokens):
        if _is_number_token(tokens[i]):
            j = i
            while j < len(tokens) and _is_number_token(tokens[j]):
                j += 1
            for k in range(j - i, 0, -1):  # longest parseable prefix wins
                value = _run_value(tokens[i : i + k])
                if value is not None:
                    if prev_number:
                        parts.append(_RUN_JOIN)
                    parts.append(str(value))
                    prev_number = True
                    i += k
                    break
            else:
                parts.append(tokens[i])
                prev_number = False
                i += 1
            continue
        parts.append(tokens[i])
        prev_number = False
        i += 1
    joined = "".join(parts)
    joined = _INTERIOR_O_RE.sub("0", joined)
    m = _ORDER_RE.search(joined)
    if m:
        return f"ORD-{m.group(1)}"
    m = _BARE_NUM_RE.search(joined)
    if m:
        return f"ORD-{m.group(1)}"
    return None
