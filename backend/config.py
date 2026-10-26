"""Single accessor for secrets and runtime configuration.

Rules:
- Real key values are loaded here from .env and nowhere else.
- Key fields use repr=False so they can never leak via print/log/pytest repr.
- Error paths use missing_keys() which returns NAMES only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")
load_dotenv()

_KEY_ENV_NAMES = ("DEEPGRAM_API_KEY", "GROQ_API_KEY", "SARVAM_API_KEY")


@dataclass(frozen=True)
class Settings:
    deepgram_api_key: str = field(repr=False, default="")
    groq_api_key: str = field(repr=False, default="")
    sarvam_api_key: str = field(repr=False, default="")
    groq_model: str = "openai/gpt-oss-120b"
    # Fallback model when the primary is rate-limited/unavailable: a smaller
    # Groq model with tool calling (llm.py walks the chain on failure).
    groq_fallback_model: str = "openai/gpt-oss-20b"
    # Model for the END-OF-CALL summary request. Empty = the fallback model -
    # deliberately NOT the primary, whose TPM budget the live call itself just
    # consumed (15:39 incident: chat burned ~7k tokens, summary 429'd on the
    # primary). Set GROQ_SUMMARY_MODEL to override.
    groq_summary_model: str = ""
    sarvam_voice: str = ""  # female Indian-English persona, set after T11 probe
    # Deepgram language: multi is the default because en-IN dead-drops
    # Hinglish utterances (measured: 0 finals for "Mera order kahan hai?",
    # while multi returns conf 1.0). multi's mis-detection risk (short lines
    # in e.g. Telugu script) is handled by normalize.has_foreign_script —
    # those finals become a canned "please repeat", never an LLM turn.
    # Flip to en-IN for English-only deployments via STT_LANGUAGE.
    stt_language: str = "multi"

    def missing_keys(self) -> list[str]:
        """Names (never values) of required keys that are unset."""
        present = {
            "DEEPGRAM_API_KEY": self.deepgram_api_key,
            "GROQ_API_KEY": self.groq_api_key,
            "SARVAM_API_KEY": self.sarvam_api_key,
        }
        return [name for name, value in present.items() if not value]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        deepgram_api_key=os.getenv("DEEPGRAM_API_KEY", "").strip(),
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        sarvam_api_key=os.getenv("SARVAM_API_KEY", "").strip(),
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip(),
        groq_fallback_model=(
            os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b").strip()
            or "openai/gpt-oss-20b"
        ),
        groq_summary_model=os.getenv("GROQ_SUMMARY_MODEL", "").strip(),
        sarvam_voice=os.getenv("SARVAM_VOICE", "").strip(),
        stt_language=os.getenv("STT_LANGUAGE", "multi").strip() or "multi",
    )


def require_keys() -> None:
    """Raise RuntimeError listing missing key NAMES (never values)."""
    missing = get_settings().missing_keys()
    if missing:
        raise RuntimeError(
            "Missing API keys in .env: " + ", ".join(missing)
            + " — copy .env.example and fill them in."
        )
