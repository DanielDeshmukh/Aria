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
