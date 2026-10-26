from dataclasses import fields

import pytest

from backend import config


def test_all_three_keys_present() -> None:
    filled = config.Settings(
        deepgram_api_key="d", groq_api_key="g", sarvam_api_key="s"
    )
    assert filled.missing_keys() == []


def test_settings_frozen_and_cached() -> None:
    a = config.get_settings()
    b = config.get_settings()
    assert a is b
    with pytest.raises(Exception):
        a.groq_model = "other"  # type: ignore[misc]


def test_key_fields_never_appear_in_repr() -> None:
    text = repr(config.get_settings())
    assert "API_KEY" not in text  # field names hidden too (repr=False)
    for f in fields(config.Settings):
        if f.name.endswith("_key"):
            assert f.repr is False


def test_require_keys_passes_with_filled_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DEEPGRAM_API_KEY", "GROQ_API_KEY", "SARVAM_API_KEY"):
        monkeypatch.setenv(name, "test-key")
    config.get_settings.cache_clear()
    try:
        config.require_keys()  # must not raise when the env is complete
    finally:
        config.get_settings.cache_clear()  # never leak the fake env to other tests


def test_missing_keys_returns_names_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        config,
        "get_settings",
        lambda: config.Settings(
            deepgram_api_key="x", groq_api_key="", sarvam_api_key=""
        ),
    )
    assert config.get_settings().missing_keys() == ["GROQ_API_KEY", "SARVAM_API_KEY"]


def test_fallback_model_default_and_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bug 1: the second model in the LLM chain is env-configurable."""
    config.get_settings.cache_clear()
    try:
        assert config.Settings().groq_fallback_model == "openai/gpt-oss-20b"
        monkeypatch.setenv("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile")
        config.get_settings.cache_clear()
        assert config.get_settings().groq_fallback_model == (
            "llama-3.3-70b-versatile"
        )
        monkeypatch.setenv("GROQ_FALLBACK_MODEL", "   ")  # blank -> default back
        config.get_settings.cache_clear()
        assert config.get_settings().groq_fallback_model == "openai/gpt-oss-20b"
    finally:
        config.get_settings.cache_clear()  # never leak the fake env to other tests


def test_summary_model_env_override_and_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """GROQ_SUMMARY_MODEL picks the end-of-call summary model; empty/blank
    means the chain defaults to the fallback model (never the live-chat
    primary, whose TPM budget the call itself just spent)."""
    config.get_settings.cache_clear()
    try:
        assert config.Settings().groq_summary_model == ""  # -> fallback model
        monkeypatch.setenv("GROQ_SUMMARY_MODEL", "acme/summary-1")
        config.get_settings.cache_clear()
        assert config.get_settings().groq_summary_model == "acme/summary-1"
        monkeypatch.setenv("GROQ_SUMMARY_MODEL", "   ")  # blank -> fallback again
        config.get_settings.cache_clear()
        assert config.get_settings().groq_summary_model == ""
    finally:
        config.get_settings.cache_clear()  # never leak the fake env to other tests
