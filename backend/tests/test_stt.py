"""Pinned Deepgram language unit tests — URL assembly and the single config
value (no network). The live Hinglish probe lives in test_stt_hinglish_live."""

from __future__ import annotations

import pytest

from backend import selftest as selftest_mod
from backend.config import get_settings
from backend.stt import DEEPGRAM_WS_URL

KEYTERMS = (
    "keyterm=ORD&",
    "keyterm=ORD-101",
    "keyterm=ORD-102",
    "keyterm=ORD-103",
    "keyterm=sunscreen",
    "keyterm=serum",
    "keyterm=toner",
)


@pytest.fixture(autouse=True)
def _reload_settings() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_default_language_is_multi() -> None:
    # en-IN dead-drops Hinglish (0 finals measured) — multi is guarded by
    # normalize.has_foreign_script, so multi is the safe default
    assert get_settings().stt_language == "multi"


def test_url_pins_language_and_keeps_keyterms() -> None:
    url = DEEPGRAM_WS_URL.format(
        sample_rate=16000, language=get_settings().stt_language
    )
    assert "language=multi" in url
    assert "model=nova-3" in url
    for keyterm in KEYTERMS:
        assert keyterm in url, keyterm


def test_stt_language_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STT_LANGUAGE", "en-IN")
    get_settings.cache_clear()
    assert get_settings().stt_language == "en-IN"
    url = DEEPGRAM_WS_URL.format(
        sample_rate=16000, language=get_settings().stt_language
    )
    assert "language=en-IN" in url


def test_endpointing_not_eager() -> None:
    """Issue 4: endpointing=300 finalized utterances mid-sentence ("Can you
    cancel my"), starving the session of interims; 800 ms waits out natural
    clause pauses (~+0.5 s to finalization, first-audio latency unchanged)."""
    url = DEEPGRAM_WS_URL.format(sample_rate=16000, language="multi")
    assert "endpointing=800" in url
    assert "endpointing=300" not in url


def test_selftest_shares_the_single_language_value() -> None:
    # no second hardcoded language anywhere: the probe formats the same knob
    assert "language={language}" in selftest_mod.DEEPGRAM_WS_URL
    url = selftest_mod.DEEPGRAM_WS_URL.format(
        language=get_settings().stt_language
    )
    assert "language=multi" in url
