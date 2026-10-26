"""Pipeline edge behaviors (T12): provider failures, one-shot session,
message-order guards, canned-line rules.

All waits are bounded — a regression fails with an event dump, never a hang.
"""

from __future__ import annotations

import asyncio

import pytest

import backend.session as session_mod
from backend.session import REPEAT, STILL_THERE, CallSession
from backend.tests._fakes import EventBox, FakeLLM, FakeSTT, FakeTTS, wait_until


def make(llm: FakeLLM | None = None, stt: FakeSTT | None = None, tts: FakeTTS | None = None):
    box = EventBox()
    stt = stt if stt is not None else FakeSTT()
    llm = llm if llm is not None else FakeLLM()
    tts = tts if tts is not None else FakeTTS()
    session = CallSession(stt=stt, llm=llm, tts=tts, send=box.send)
    return session, box, stt, llm, tts


async def to_listening(session, box) -> None:
    await session.handle({"type": "start"})
    await session.handle({"type": "playback_done"})


def count(box, text: str) -> int:
    return sum(1 for m in box.of("transcript") if m.get("text") == text)


def test_greeting_stats_first_audio_ms_present_and_non_negative() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await session.handle({"type": "start"})
        stats = box.of("stats")
        assert stats, "greeting must emit a stats event"
        assert "first_audio_ms" in stats[0]
        assert stats[0]["first_audio_ms"] >= 0

    asyncio.run(scenario())


def test_stt_start_failure_sends_named_error_and_ends() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            stt=FakeSTT(start_error=RuntimeError("socket refused"))
        )
        await session.handle({"type": "start"})
        assert box.of("error") == [
            {"type": "error", "message": "speech-to-text unavailable: RuntimeError"}
        ]
        assert box.states()[-1] == "ended"
        assert box.of("audio") == []  # greeting never attempted
        assert stt.started is False
        assert stt.closed is True  # cleanup ran
        await session.handle({"type": "start"})
        assert box.of("error")[-1]["message"] == "session already ended"
        assert len(box.of("error")) == 2  # one-shot after failure too

    asyncio.run(scenario())


def test_tts_greeting_failure_ends_session_with_named_error() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make(tts=FakeTTS(fail=True))
        await session.handle({"type": "start"})
        assert box.of("error") == [
            {"type": "error", "message": "text-to-speech unavailable: RuntimeError"}
        ]
        assert box.states()[-1] == "ended"
        assert stt.started is True  # STT was up before the greeting
        assert stt.closed is True  # then cleaned up
        assert box.of("audio") == []

    asyncio.run(scenario())


def test_llm_failure_during_turn_ends_session() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(rounds=[("error", "groq 500")])
        )
        await to_listening(session, box)
        await stt.emit_final("where is my order ORD-101")
        await wait_until(lambda: box.of("error"), what="llm error event")
        assert box.of("error")[0]["message"] == (
            "language model unavailable: RuntimeError"
        )
        assert box.states()[-1] == "ended"
        assert stt.closed is True
        before = len(box.of("transcript"))
        await stt.emit_final("anyone there")  # post-end transcript ignored
        assert len(box.of("transcript")) == before
        await session.handle({"type": "start"})
        assert box.of("error")[-1]["message"] == "session already ended"

    asyncio.run(scenario())


def test_start_after_end_rejected_without_new_greeting() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await session.handle({"type": "start"})
        await session.handle({"type": "end"})
        audio_before = len(box.of("audio"))
        await session.handle({"type": "start"})
        assert box.of("error")[-1]["message"] == "session already ended"
        assert len(box.of("audio")) == audio_before
        assert len(box.of("summary")) == 1

    asyncio.run(scenario())


def test_playback_done_while_thinking_is_ignored() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(rounds=[("hang",)])
        )
        await to_listening(session, box)
        await stt.emit_final("tell me about my order")
        await wait_until(
            lambda: box.states()[-1] == "thinking", what="thinking state"
        )
        await session.handle({"type": "playback_done"})
        assert box.states()[-1] == "thinking"

    asyncio.run(scenario())


def test_repeat_canned_line_fires_repeatedly_without_llm() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await to_listening(session, box)
        await stt.emit_final("sor y w at", 0.2)
        await wait_until(
            lambda: count(box, REPEAT) >= 1, what="first repeat"
        )
        await stt.emit_final("w at now", 0.3)
        await wait_until(
            lambda: count(box, REPEAT) >= 2, what="second repeat"
        )
        assert llm.chat_calls == 0
        assert box.of("tool") == []

    asyncio.run(scenario())


def test_still_there_fires_once_then_again_after_customer_speaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_mod, "SILENCE_SECONDS", 0.05)

    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await to_listening(session, box)
        await wait_until(
            lambda: count(box, STILL_THERE) >= 1,
            what="first still-there",
            timeout=2.0,
        )
        await session.handle({"type": "playback_done"})
        await asyncio.sleep(0.15)
        assert count(box, STILL_THERE) == 1  # one-shot until customer speaks

        await stt.emit_final("hello are you there", 0.9)
        await wait_until(
            lambda: llm.chat_calls == 1, what="customer turn consumed"
        )
        # the re-armed nudge waits SPEECH_FRESH_SECONDS (3 s) of quiet after
        # the customer's final — that guard is the issue-4 fix
        await wait_until(
            lambda: count(box, STILL_THERE) >= 2,
            what="still-there re-armed after customer speech",
            timeout=4.0,
        )

    asyncio.run(scenario())
