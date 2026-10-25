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
    groq_model: str = "qwen/qwen3.8-27b"
    sarvam_voice: str = ""  # female Indian-English persona, set after T11 probe

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
        groq_model=os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b").strip(),
        sarvam_voice=os.getenv("SARVAM_VOICE", "").strip(),
    )


def require_keys() -> None:
    """Raise RuntimeError listing missing key NAMES (never values)."""
    missing = get_settings().missing_keys()
    if missing:
        raise RuntimeError(
            "Missing API keys in .env: " + ", ".join(missing)
            + " — copy .env.example and fill them in."
        )
