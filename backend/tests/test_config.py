from dataclasses import fields

import pytest

from backend import config


def test_all_three_keys_present() -> None:
    assert config.get_settings().missing_keys() == []


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


def test_require_keys_passes_with_filled_env() -> None:
    config.require_keys()  # must not raise when .env is complete


def test_missing_keys_returns_names_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        config,
        "get_settings",
        lambda: config.Settings(
            deepgram_api_key="x", groq_api_key="", sarvam_api_key=""
        ),
    )
    assert config.get_settings().missing_keys() == ["GROQ_API_KEY", "SARVAM_API_KEY"]
