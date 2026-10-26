"""Text-mode harness: run the §8 scenarios against the real LLM + tools.

Usage:
    python -m backend.scripts.text_harness                # all text scenarios
    python -m backend.scripts.text_harness --only COD     # filter by substring
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time

from backend.llm import GroqLLM
from backend.prompts import SYSTEM_PROMPT
from backend.scenarios import SCENARIOS, VOICE_ONLY
from backend.tools import TOOL_SCHEMAS, dispatch

DEVANAGARI = re.compile(r"[\u0900-\u097F]")
HINDISH = re.compile(
    r"\b(aapka|aapki|aapne|bataiye|boliye|kijiye|karungi|hoon|raha|rahi|"
    r"nahi|haan|theek|lijiye|kahan|kaise|kya|mera|hai)\b",
    re.I,
)


def language_drift(say: str, reply: str) -> str | None:
    """Issue 1: an English scenario must never get a Hindi/Hinglish reply.
    Returns a description of the drift, or None when the language is right."""
    if DEVANAGARI.search(reply) and not DEVANAGARI.search(say):
        return "Devanagari reply to an English scenario"
    if HINDISH.search(reply) and not HINDISH.search(say):
        return "Hinglish markers in a reply to an English scenario"
    return None


async def run_scenario(llm: GroqLLM, say: str) -> tuple[list[tuple[str, dict]], str, float]:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": say},
    ]
    tools_seen: list[tuple[str, dict]] = []

    def execute(name: str, args: dict) -> dict:
        tools_seen.append((name, args))
        return dispatch(name, args)

    start = time.monotonic()
    reply = ""
    async for event in llm.chat(messages, TOOL_SCHEMAS, execute):
        if event["type"] == "text":
            reply += event["delta"]
    return tools_seen, reply, (time.monotonic() - start) * 1000


async def main(only: str | None) -> None:
    llm = GroqLLM()
    drifts: list[str] = []
    for say, expected in SCENARIOS:
        if say in VOICE_ONLY:
            print(f"\n--- SAY: {say}\n    (voice-only scenario — run it in the live runbook)")
            continue
        if only and only.lower() not in say.lower():
            continue
        try:
            tools_seen, reply, ms = await asyncio.wait_for(run_scenario(llm, say), timeout=45)
        except Exception as exc:
            print(f"\n--- SAY: {say}\n    ERROR: {type(exc).__name__}: {exc}")
            continue
        tools_txt = ", ".join(f"{n}({a})" for n, a in tools_seen) or "(none)"
        print(f"\n--- SAY: {say}")
        print(f"    TOOLS: {tools_txt}")
        print(f"    REPLY ({ms:.0f} ms): {reply.strip()}")
        print(f"    EXPECTED: {expected}")
        drift = language_drift(say, reply)
        if drift:
            drifts.append(f"{say!r}: {drift} -> {reply.strip()!r}")
            print(f"    LANGUAGE-DRIFT: {drift}")
    if drifts:
        print("\nLANGUAGE DRIFT DETECTED (English scenarios must stay English):")
        for line in drifts:
            print(f"  {line}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default=None, help="substring filter")
    args = parser.parse_args()
    asyncio.run(main(args.only))
