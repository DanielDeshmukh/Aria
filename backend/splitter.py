"""Sentence splitter for streaming TTS: LLM token deltas are accumulated here
and released at sentence boundaries so each sentence reaches TTS immediately."""

from __future__ import annotations

_TERMINAL = ".!?…"
_CLOSERS = "'\"”’"
_ABBREV = {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "no", "fig"}


def _is_abbrev_period(buffer: str, i: int) -> bool:
    """True when the '.' at i ends a known abbreviation (letter.period boundary)."""
    j = i
    while j > 0 and buffer[j - 1].isalpha():
        j -= 1
    return buffer[j:i].lower() in _ABBREV


def split_sentences(buffer: str) -> tuple[list[str], str]:
    """Split off complete sentences; return (sentences, remainder).

    A terminator is only a boundary when followed by whitespace or end of
    buffer. digit.digit ("₹499.00") and letter.period-letter ("Mr. Sharma")
    never split. Trailing "..." stays attached to its sentence.
    """
    sentences: list[str] = []
    start = 0
    i = 0
    n = len(buffer)
    while i < n:
        ch = buffer[i]
        if ch in _TERMINAL:
            if (
                ch == "."
                and i > 0
                and i + 1 < n
                and buffer[i - 1].isdigit()
                and buffer[i + 1].isdigit()
            ):
                i += 1
                continue
            if ch == "." and _is_abbrev_period(buffer, i):
                i += 1
                continue
            if (
                ch == "."
                and i > 0
                and i + 1 < n
                and buffer[i - 1].isalpha()
                and buffer[i + 1].isalpha()
            ):
                i += 1
                continue
            j = i
            while j < n and buffer[j] in _TERMINAL + _CLOSERS:
                j += 1
            if j >= n or buffer[j].isspace():
                sentence = buffer[start:j].strip()
                if sentence:
                    sentences.append(sentence)
                while j < n and buffer[j].isspace():
                    j += 1
                start = j
                i = j
                continue
            i += 1
            continue
        i += 1
    return sentences, buffer[start:]
