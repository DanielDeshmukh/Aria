"""Pipeline edge behaviors (T12): provider failures, one-shot session,
message-order guards, canned-line rules.

All waits are bounded — a regression fails with an event dump, never a hang.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

import backend.session as session_mod
from backend.session import LLM_TROUBLE, REPEAT, STILL_THERE, CallSession
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


def test_llm_failure_during_turn_graceful_recovery() -> None:
    """Bug 1 (session side): once the whole model chain gives up, the call
    must NOT die — Aria speaks the graceful apology, state returns to
    listening, no error event is ever sent, and the next turn still reaches
    the LLM."""

    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(rounds=[("error", "groq 500")])
        )
        await to_listening(session, box)
        await stt.emit_final("where is my order ORD-101")
        await wait_until(
            lambda: count(box, LLM_TROUBLE) >= 1, what="graceful LLM_TROUBLE line"
        )
        assert box.of("error") == []  # no error banner, ever
        assert box.states()[-1] != "ended"
        assert stt.closed is False  # providers stay up
        # playback_done -> listening, then a second final reaches the LLM again
        await session.handle({"type": "playback_done"})
        await wait_until(lambda: box.states()[-1] == "listening", what="listening again")
        await stt.emit_final("hello are you there")
        await wait_until(lambda: llm.chat_calls == 2, what="second llm turn")
        assert box.of("error") == []
        assert box.states()[-1] != "ended"
        # end still works (clean shutdown, no extra errors)
        await session.handle({"type": "end"})
        assert box.of("error") == []

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


# ------------------------------------------------- playback timing (bug 2b)
def test_playback_done_ignored_while_turn_producing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The client drains its queue BETWEEN two sentences while the server is
    still producing: that drain must never start the idle countdown."""

    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(rounds=[("text", "First sentence."), ("hang",)])
        )
        await to_listening(session, box)
        with caplog.at_level(logging.INFO, logger="backend.session"):
            await stt.emit_final("tell me about my order")
            await wait_until(
                lambda: box.states()[-1] == "speaking" and box.of("audio"),
                what="reply audio mid-turn",
            )
            await session.handle({"type": "playback_done"})
            # no transition and no countdown while the turn is producing
            assert box.states()[-1] == "speaking"
            assert session._silence_task is None
        await session.handle({"type": "end"})
        assert len(box.of("summary")) == 1

    asyncio.run(scenario())
    messages = [r.getMessage() for r in caplog.records]
    assert any("playback_done: deferred" in m for m in messages), messages


def test_estimate_starts_countdown_without_playback_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No playback_done ever arrives: the playback-duration estimate must
    start the idle countdown - never server send-finish alone."""
    monkeypatch.setattr(session_mod, "PLAYBACK_MARGIN_SECONDS", 0.1)
    monkeypatch.setattr(session_mod, "SILENCE_SECONDS", 0.3)
    monkeypatch.setattr(session_mod, "SPEECH_FRESH_SECONDS", 0.05)

    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(rounds=[("text", "Sure, checking that now.")])
        )
        await to_listening(session, box)
        await stt.emit_final("where is my order")
        await wait_until(
            lambda: box.states()[-1] == "speaking" and box.of("audio"),
            what="reply audio",
        )
        # deliberately NO playback_done from the client
        await wait_until(
            lambda: box.states()[-1] == "listening"
            and session._silence_task is not None,
            what="estimate moved us to listening and armed the countdown",
            timeout=2.0,
        )
        await wait_until(
            lambda: any(
                m.get("text") == STILL_THERE for m in box.of("transcript")
            ),
            what="nudge after the estimated playback window",
            timeout=2.0,
        )

    asyncio.run(scenario())


def test_pcm_bytes_per_second_from_tts_config_and_fallback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Sample rate/format come from the real TTS output config; 16 kHz only
    when it is truly unknown - and that fallback is logged."""

    class Configured:
        mime = "audio/l16;rate=22050"

    assert session_mod._pcm_bytes_per_second(Configured) == 44100.0

    class WithAttr:
        sample_rate = 16000
        mime = "application/octet-stream"

    assert session_mod._pcm_bytes_per_second(WithAttr) == 32000.0

    class Bare:
        mime = "audio/wav"

    with caplog.at_level(logging.INFO, logger="backend.session"):
        assert session_mod._pcm_bytes_per_second(Bare) == 32000.0
    assert any(
        "assuming 16000" in r.getMessage() for r in caplog.records
    ), [r.getMessage() for r in caplog.records]
