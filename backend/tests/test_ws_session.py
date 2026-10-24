"""CallSession behavior tests — async scenarios driven through asyncio.run.

Every wait is bounded by wait_until/asyncio.wait_for, so a broken state
machine fails with a dump instead of hanging the suite.
"""

from __future__ import annotations

import asyncio
import base64

import pytest

import backend.session as session_mod
from backend.session import GREETING, REPEAT, STILL_THERE, CallSession
from backend.summary import SUMMARY_KEYS
from backend.tests._fakes import EventBox, FakeLLM, FakeSTT, FakeTTS, wait_until

FAKE_AUDIO_B64 = base64.b64encode(b"RIFF-FAKE-AUDIO").decode("ascii")


def make(llm: FakeLLM | None = None):
    stt, box = FakeSTT(), EventBox()
    llm = llm if llm is not None else FakeLLM()
    tts = FakeTTS()
    session = CallSession(stt=stt, llm=llm, tts=tts, send=box.send)
    return session, box, stt, llm, tts


async def to_listening(session, box, stt, llm, tts):
    await session.handle({"type": "start"})
    await session.handle({"type": "playback_done"})
    return session, box, stt, llm, tts


def test_greeting_sequence_and_playback_done() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await session.handle({"type": "start"})
        assert stt.started
        assert box.states() == ["connecting", "speaking"]
        agents = [m for m in box.of("transcript") if m["role"] == "agent"]
        assert agents and agents[0]["text"] == GREETING
        assert len(box.of("stats")) == 1
        audio = box.of("audio")
        assert len(audio) == 1
        assert audio[0]["data"] == FAKE_AUDIO_B64
        await session.handle({"type": "playback_done"})
        assert box.states()[-1] == "listening"
        await session.handle({"type": "start"})
        assert box.of("error")[0]["message"] == "session already started"

    asyncio.run(scenario())


def test_order_lookup_turn_with_real_tool() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(
                rounds=[
                    ("tool", "get_order_details", {"order_id": "ORD-101"}),
                    (
                        "text",
                        "Your order is out for delivery and should arrive by 6 PM today.",
                    ),
                ]
            )
        )
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("where is my order ORD-101")
        await wait_until(lambda: box.of("tool"), what="tool event")
        tool = box.of("tool")[0]
        assert tool["name"] == "get_order_details"
        assert tool["args"] == {"order_id": "ORD-101"}
        assert tool["result"]["found"] is True
        assert tool["result"]["order"]["id"] == "ORD-101"
        assert tool["result"]["order"]["status"] == "Out for Delivery"
        await wait_until(
            lambda: len(box.of("audio")) >= 2 and box.states()[-1] == "speaking",
            what="reply audio",
        )
        assert "thinking" in box.states()
        assert len(box.of("stats")) == 2
        assert [m["role"] for m in session.transcript] == ["agent", "customer", "agent"]
        assert llm.chat_calls == 1

    asyncio.run(scenario())


def test_unknown_order_returns_not_found_message() -> None:
    from backend.tools import NOT_FOUND_MESSAGE

    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(
                rounds=[
                    ("tool", "get_order_details", {"order_id": "ORD-999"}),
                    ("text", NOT_FOUND_MESSAGE),
                ]
            )
        )
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("where is my order ORD-999")
        await wait_until(lambda: box.of("tool"), what="tool event")
        result = box.of("tool")[0]["result"]
        assert result["found"] is False
        assert result["message"] == NOT_FOUND_MESSAGE
        await wait_until(
            lambda: len(box.of("audio")) >= 2, what="not-found reply audio"
        )

    asyncio.run(scenario())


def test_missing_order_id_skips_tools() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(rounds=[("text", "Could you please share your order ID?")])
        )
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("let me check my order please")
        await wait_until(
            lambda: any(
                "share your order ID" in m.get("text", "")
                for m in box.of("transcript")
                if m["role"] == "agent"
            ),
            what="missing-id reply",
        )
        assert box.of("tool") == []
        assert llm.chat_calls == 1

    asyncio.run(scenario())


def test_low_confidence_canned_repeat_no_llm() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("sor y w at", 0.2)
        await wait_until(
            lambda: any(
                m.get("text") == REPEAT for m in box.of("transcript")
            ),
            what="canned repeat",
        )
        assert llm.chat_calls == 0
        assert box.of("tool") == []
        assert session.transcript[1] == {
            "role": "customer",
            "text": "sor y w at",
        }

    asyncio.run(scenario())


def test_silence_asks_still_there_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_mod, "SILENCE_SECONDS", 0.05)

    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await to_listening(session, box, stt, llm, tts)
        await wait_until(
            lambda: any(
                m.get("text") == STILL_THERE for m in box.of("transcript")
            ),
            what="still-there line",
            timeout=2.0,
        )
        await session.handle({"type": "playback_done"})
        await asyncio.sleep(0.2)
        count = sum(
            1 for m in box.of("transcript") if m.get("text") == STILL_THERE
        )
        assert count == 1
        assert llm.chat_calls == 0

    asyncio.run(scenario())


def test_barge_in_cancels_in_flight_turn() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(
                rounds=[
                    ("text", "Let me check that for you right away."),
                    ("hang",),
                ]
            )
        )
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("where is my order")
        await wait_until(
            lambda: len(box.of("audio")) >= 2 and box.states()[-1] == "speaking",
            what="reply started",
        )
        await stt.emit_speech_start()
        await wait_until(
            lambda: box.of("barge_in") and box.states()[-1] == "listening",
            what="barge-in",
        )
        assert llm.cancelled is True
        assert llm.chat_calls == 1

    asyncio.run(scenario())


def test_end_sends_summary_then_ended() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(
                rounds=[
                    ("text", "Your order is out for delivery and should arrive by 6 PM today.")
                ]
            )
        )
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("where is my order ORD-101")
        await wait_until(
            lambda: len(box.of("audio")) >= 2 and box.states()[-1] == "speaking",
            what="reply",
        )
        await session.handle({"type": "end"})
        summaries = box.of("summary")
        assert len(summaries) == 1
        assert [m["role"] for m in summaries[0]["transcript"]] == [
            "agent",
            "customer",
            "agent",
        ]
        assert set(SUMMARY_KEYS) <= set(summaries[0]["summary"])
        assert summaries[0]["summary"]["order_id"] == "ORD-101"
        assert box.states()[-1] == "ended"
        assert stt.closed
        await session.handle({"type": "end"})
        assert len(box.of("summary")) == 1
        await session.handle({"type": "start"})
        assert box.of("error")

    asyncio.run(scenario())


def test_interims_throttled_and_empty_reply_falls_back_to_listening() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await to_listening(session, box, stt, llm, tts)
        for i in range(5):
            await stt.emit_interim(f"hello worl {i}")
            await asyncio.sleep(0.01)
        interims = [m for m in box.of("transcript") if not m["final"]]
        assert 1 <= len(interims) <= 2
        assert all(m["role"] == "customer" for m in interims)
        assert [m for m in session.transcript if m["role"] == "customer"] == []
        await stt.emit_final("hello there")
        await wait_until(
            lambda: llm.chat_calls == 1 and box.states()[-1] == "listening",
            what="empty reply -> listening",
        )
        assert len(box.of("audio")) == 1  # greeting only

    asyncio.run(scenario())


def test_messages_before_start_are_ignored() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await session.handle({"type": "audio", "data": "AAAA"})
        await session.handle({"type": "playback_done"})
        await session.handle({"type": "bogus"})
        assert box.events == []
        assert stt.audio == []
        assert stt.started is False

    asyncio.run(scenario())
