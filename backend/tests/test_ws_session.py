"""CallSession behavior tests — async scenarios driven through asyncio.run.

Every wait is bounded by wait_until/asyncio.wait_for, so a broken state
machine fails with a dump instead of hanging the suite.
"""

from __future__ import annotations

import asyncio
import base64
import time

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


def test_still_there_fires_despite_empty_finals(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deepgram emits empty finals throughout pure silence (live repro). They
    must not reset the timer — with SILENCE=0.15 and empty finals every 20 ms
    the old code never fired the nudge."""
    monkeypatch.setattr(session_mod, "SILENCE_SECONDS", 0.15)

    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await to_listening(session, box, stt, llm, tts)

        async def chatter() -> None:
            for _ in range(30):
                await stt.emit_final("")
                await asyncio.sleep(0.02)

        chatter_task = asyncio.create_task(chatter())
        await wait_until(
            lambda: any(
                m.get("text") == STILL_THERE for m in box.of("transcript")
            ),
            what="still-there despite empty finals",
            timeout=2.0,
        )
        await chatter_task
        await asyncio.sleep(0.1)
        count = sum(
            1 for m in box.of("transcript") if m.get("text") == STILL_THERE
        )
        assert count == 1

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


def test_interim_barge_in_when_deepgram_omits_speech_started() -> None:
    """Live runbook scenario 8: Deepgram never sends SpeechStarted on our
    config — a real interim while we are speaking must trigger barge-in."""

    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await session.handle({"type": "start"})
        assert box.states()[-1] == "speaking"
        await stt.emit_interim("where is my order ORD-")
        await wait_until(
            lambda: box.of("barge_in") and box.states()[-1] == "listening",
            what="interim barge-in",
        )
        assert session._silence_task is not None
        await stt.emit_interim("where is my order ORD-101")
        assert len(box.of("barge_in")) == 1
        assert box.of("error") == []

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


def test_foreign_script_final_asks_repeat_no_llm() -> None:
    """language=multi mis-detection repro: a Telugu final at conf 0.98 must
    take the canned-repeat path, never an LLM turn."""

    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("థాంక్యూ", 0.98)
        await wait_until(
            lambda: any(m.get("text") == REPEAT for m in box.of("transcript")),
            what="canned repeat for foreign-script final",
        )
        assert llm.chat_calls == 0
        assert box.of("tool") == []
        assert session.transcript[1] == {"role": "customer", "text": "థాంక్యూ"}

    asyncio.run(scenario())


def test_interim_resets_idle_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Interims streaming mid-sentence must restart the countdown — the nudge
    fires only after the customer actually stops talking."""

    monkeypatch.setattr(session_mod, "SILENCE_SECONDS", 0.3)
    # this test targets the interim reset, not the fresh-speech guard (which
    # has its own test) — shrink the guard window so the nudge lands fast
    monkeypatch.setattr(session_mod, "SPEECH_FRESH_SECONDS", 0.05)

    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await to_listening(session, box, stt, llm, tts)
        # talk continuously across the original deadline (0.3 s)
        for i in range(16):
            await stt.emit_interim(f"let me think about that order {i}")
            await asyncio.sleep(0.05)
        assert not any(
            m.get("text") == STILL_THERE for m in box.of("transcript")
        ), "nudge fired while the customer was speaking"
        await wait_until(
            lambda: any(m.get("text") == STILL_THERE for m in box.of("transcript")),
            what="nudge after speech stops",
            timeout=2.0,
        )

    asyncio.run(scenario())


def test_speech_start_resets_idle_timer_while_listening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_mod, "SILENCE_SECONDS", 0.3)
    monkeypatch.setattr(session_mod, "SPEECH_FRESH_SECONDS", 0.05)

    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await to_listening(session, box, stt, llm, tts)
        await asyncio.sleep(0.15)  # half way to the original deadline
        await stt.emit_speech_start()
        await asyncio.sleep(0.18)  # original deadline (0.3) has passed
        assert not any(
            m.get("text") == STILL_THERE for m in box.of("transcript")
        ), "nudge fired although speech-start reset the timer"
        await wait_until(
            lambda: any(m.get("text") == STILL_THERE for m in box.of("transcript")),
            what="nudge after the fresh window",
            timeout=2.0,
        )

    asyncio.run(scenario())


def test_silence_never_fires_on_fresh_speech(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hard guard inside _silence_fire: even if a reset was missed, a fire
    requires SPEECH_FRESH_SECONDS of quiet since the last speech signal."""

    monkeypatch.setattr(session_mod, "SILENCE_SECONDS", 0.1)

    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await to_listening(session, box, stt, llm, tts)
        await asyncio.sleep(0.05)
        session._last_user_speech_at = time.monotonic()  # spoke right now
        await asyncio.sleep(0.08)  # deadline passes; guard must re-arm
        assert not any(
            m.get("text") == STILL_THERE for m in box.of("transcript")
        ), "nudge fired within the fresh-speech window"
        assert session._silence_task is not None, "guard must re-arm, not drop"
        session._last_user_speech_at = time.monotonic() - 999  # quiet for ages
        await wait_until(
            lambda: any(m.get("text") == STILL_THERE for m in box.of("transcript")),
            what="nudge once speech ages out",
            timeout=2.0,
        )

    asyncio.run(scenario())


def test_cancel_order_tool_turn_confirmed() -> None:
    """Session plumbing: the cancel_order tool event executes through
    _execute_tool and its structured result rides the tool event."""

    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(
                rounds=[
                    ("tool", "cancel_order", {"order_id": "ORD-103", "confirmed": True}),
                    ("text", "Done — ORD-103 is cancelled."),
                ]
            )
        )
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("cancel my order 103")
        await wait_until(lambda: box.of("tool"), what="cancel tool event")
        tool = box.of("tool")[0]
        assert tool["name"] == "cancel_order"
        assert tool["args"] == {"order_id": "ORD-103", "confirmed": True}
        assert tool["result"]["cancelled"] is True
        assert tool["result"]["order_id"] == "ORD-103"
        await wait_until(
            lambda: any(
                "ORD-103 is cancelled" in m.get("text", "")
                for m in box.of("transcript")
                if m["role"] == "agent"
            ),
            what="cancellation reply",
        )

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "said,tool_id",
    [
        ("101", "101"),
        ("one zero one", "one zero one"),
        ("ORD 101", "ORD 101"),
    ],
)
def test_low_confidence_order_id_accepted(said: str, tool_id: str) -> None:
    """Issue 3: digit-like ids often land below LOW_CONFIDENCE ("101" got a
    canned repeat live) — the gate opens on them and the tool normalizes the
    spoken form again."""

    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(
                rounds=[
                    ("tool", "get_order_details", {"order_id": tool_id}),
                    ("text", "Your order ORD-101 is out for delivery."),
                ]
            )
        )
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final(said, 0.3)
        await wait_until(lambda: box.of("tool"), what="tool after low-conf id")
        assert box.of("tool")[0]["result"]["found"] is True
        assert not any(m.get("text") == REPEAT for m in box.of("transcript"))
        assert llm.chat_calls == 1

    asyncio.run(scenario())


def test_low_confidence_yes_after_readback_accepted() -> None:
    """Issue 3 extension: the read-back "yes" is often a soft murmur below
    LOW_CONFIDENCE — accepted only because Aria's last question was a yes/no
    confirmation (the cancel read-back)."""

    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(
                advance=True,
                rounds=[
                    (
                        "text",
                        "ORD-103 is Processing — would you like me to cancel it?",
                    ),
                    ("tool", "cancel_order", {"order_id": "ORD-103", "confirmed": True}),
                    ("text", "Done — ORD-103 is cancelled."),
                ],
            )
        )
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("cancel my order ORD-103")
        await wait_until(
            lambda: any(
                "cancel it?" in m.get("text", "")
                for m in box.of("transcript")
                if m["role"] == "agent"
            ),
            what="read-back question",
        )
        await stt.emit_final("yes", 0.3)
        await wait_until(lambda: box.of("tool"), what="confirmed cancel")
        tool = box.of("tool")[0]
        assert tool["args"] == {"order_id": "ORD-103", "confirmed": True}
        assert tool["result"]["cancelled"] is True
        assert not any(m.get("text") == REPEAT for m in box.of("transcript"))
        assert llm.chat_calls == 2

    asyncio.run(scenario())


def test_low_confidence_orphan_yes_still_repeats() -> None:
    """The gate stays shut without a yes/no question behind it: a stray
    low-confidence "yes" (e.g. right after the greeting) never reaches the LLM."""

    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("yes", 0.3)
        await wait_until(
            lambda: any(m.get("text") == REPEAT for m in box.of("transcript")),
            what="canned repeat for orphan yes",
        )
        assert llm.chat_calls == 0

    asyncio.run(scenario())


def test_nudge_never_fires_within_fresh_window_after_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue 4: endpointing can cut a final mid-sentence — the nudge must stay
    at least SPEECH_FRESH_SECONDS after the last non-empty transcript fragment,
    even when the silence window is tiny. Empty finals are different (they are
    the silence chatter and must not reset — see the empty-finals test above)."""
    monkeypatch.setattr(session_mod, "SILENCE_SECONDS", 0.3)

    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("can you cancel my")  # mid-sentence final
        await asyncio.sleep(2.4)
        assert not any(
            m.get("text") == STILL_THERE for m in box.of("transcript")
        ), "nudge fired within the fresh-speech window of the last final"
        await wait_until(
            lambda: any(m.get("text") == STILL_THERE for m in box.of("transcript")),
            what="nudge after the fresh window",
            timeout=2.5,
        )

    asyncio.run(scenario())
