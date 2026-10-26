"""CallSession behavior tests — async scenarios driven through asyncio.run.

Every wait is bounded by wait_until/asyncio.wait_for, so a broken state
machine fails with a dump instead of hanging the suite.
"""

from __future__ import annotations

import asyncio
import base64
import logging
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


# ------------------------------------------------------- fragment coalescing
def test_complete_final_starts_turn_immediately() -> None:
    """A finished sentence (terminal punctuation) must never wait for the
    coalescing hold."""

    async def scenario() -> None:
        session, box, stt, llm, tts = make(FakeLLM(rounds=[("text", "Sure.")]))
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("Where is my order?")
        await wait_until(
            lambda: llm.chat_calls == 1, what="immediate turn", timeout=0.4
        )
        assert session.messages[-1]["content"] == "Where is my order?"

    asyncio.run(scenario())


def test_split_finals_join_before_the_llm_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bug 2: endpointing cuts "Can you tell me where my order" /
    "one zero one is?" — the LLM must see ONE joined message. The interim
    between the finals re-arms the hold so the second final still arrives
    inside the join window."""
    monkeypatch.setattr(session_mod, "FRAGMENT_HOLD_SECONDS", 0.5)

    async def scenario() -> None:
        session, box, stt, llm, tts = make(FakeLLM(rounds=[("text", "One moment.")]))
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("Can you tell me where my order")  # ends dangling
        await asyncio.sleep(0.1)
        assert llm.chat_calls == 0  # held, not sent half-done
        await asyncio.sleep(0.35)  # t≈0.45, still inside the original hold
        await stt.emit_interim("Can you tell me where my order one zero one is")
        await asyncio.sleep(0.15)  # t≈0.60 — PAST the original 0.5 s deadline
        assert llm.chat_calls == 0, "interim must re-arm the hold window"
        await stt.emit_final("one zero one is?")
        await wait_until(lambda: llm.chat_calls == 1, what="joined turn", timeout=1.5)
        assert session.messages[-1]["content"] == (
            "Can you tell me where my order one zero one is?"
        )

    asyncio.run(scenario())


def test_incomplete_final_fires_after_the_hold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No second fragment coming: the held final goes to the LLM by itself
    after FRAGMENT_HOLD_SECONDS — never a permanent stall."""
    monkeypatch.setattr(session_mod, "FRAGMENT_HOLD_SECONDS", 0.3)

    async def scenario() -> None:
        session, box, stt, llm, tts = make(FakeLLM(rounds=[("text", "Checking.")]))
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("where is my order")
        await asyncio.sleep(0.1)
        assert llm.chat_calls == 0  # still holding
        await wait_until(lambda: llm.chat_calls == 1, what="hold fires", timeout=1.5)
        assert session.messages[-1]["content"] == "where is my order"

    asyncio.run(scenario())


def test_short_but_ready_finals_are_not_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Digits/ids and yes/no answers are complete answers — under 3 words is
    no reason to delay them; only genuinely dangling fragments wait."""
    monkeypatch.setattr(session_mod, "FRAGMENT_HOLD_SECONDS", 0.3)

    async def scenario() -> None:
        session, box, stt, llm, tts = make(FakeLLM(rounds=[("text", "OK.")]))
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("101")  # order id -> immediate
        await wait_until(lambda: llm.chat_calls == 1, what="digit final", timeout=0.4)
        await stt.emit_final("hello there")  # 2 words, no answer -> held
        await asyncio.sleep(0.1)
        assert llm.chat_calls == 1, "2-word fragment must be held"
        await wait_until(lambda: llm.chat_calls == 2, what="held fragment fires", timeout=1.5)

    asyncio.run(scenario())


def test_refined_final_replaces_held_prefix() -> None:
    """Deepgram restates a fragment longer instead of splitting it: the newer
    final starts with the held text and must replace it, not double it."""

    async def scenario() -> None:
        session, box, stt, llm, tts = make(FakeLLM(rounds=[("text", "Checking.")]))
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("where is my order")
        await asyncio.sleep(0.05)
        await stt.emit_final("where is my order ORD-101")  # prefix refinement
        await wait_until(lambda: llm.chat_calls == 1, what="refined turn", timeout=1.5)
        assert session.messages[-1]["content"] == "where is my order ORD-101"

    asyncio.run(scenario())


# --------------------------------------------- nudge freshness (bug 2c)
def test_nudge_blocked_by_gate_dropped_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A gate-dropped final (low confidence -> canned repeat) still counts as
    STT activity: the nudge must stay away for SPEECH_FRESH_SECONDS."""
    monkeypatch.setattr(session_mod, "SILENCE_SECONDS", 0.2)

    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("sor y w at", 0.2)  # dropped -> canned repeat
        await wait_until(
            lambda: any(m.get("text") == REPEAT for m in box.of("transcript")),
            what="canned repeat",
        )
        await session.handle({"type": "playback_done"})  # repeat drained
        await asyncio.sleep(0.35)  # > SILENCE 0.2, << SPEECH_FRESH 3.0
        assert not any(
            m.get("text") == STILL_THERE for m in box.of("transcript")
        ), "nudge fired within the fresh window of a gate-dropped final"
        assert llm.chat_calls == 0

    asyncio.run(scenario())


# ------------------------------------------------ closing offer (bug 2d)
def test_closing_offer_ends_quietly_after_longer_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After Aria's closing offer the customer gets CLOSING_IDLE_SECONDS, and
    the call then ends quietly - summary + ended, never a nudge."""
    monkeypatch.setattr(session_mod, "SILENCE_SECONDS", 0.1)
    monkeypatch.setattr(session_mod, "CLOSING_IDLE_SECONDS", 0.5)
    monkeypatch.setattr(session_mod, "SPEECH_FRESH_SECONDS", 0.05)

    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(
                rounds=[("text", "Is there anything else I can help you with?")]
            )
        )
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("thanks that is everything")
        await wait_until(
            lambda: any(
                "anything else" in (m.get("text") or "")
                for m in box.of("transcript")
            ),
            what="closing offer spoken",
        )
        assert session._closing_offer is True
        await session.handle({"type": "playback_done"})
        await asyncio.sleep(0.25)  # the SHORT window (0.1 s) would have nudged
        assert not any(
            m.get("text") == STILL_THERE for m in box.of("transcript")
        ), "nudge fired inside the longer closing window"
        await wait_until(
            lambda: box.states()[-1] == "ended",
            what="quiet end after the closing window",
            timeout=2.0,
        )
        assert not any(
            m.get("text") == STILL_THERE for m in box.of("transcript")
        ), "the quiet end must never speak STILL_THERE"
        assert len(box.of("summary")) == 1

    asyncio.run(scenario())


def test_closing_flag_clears_on_new_customer_final() -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make(
            FakeLLM(
                rounds=[("text", "Anything else I can help you with?")],
                advance=True,
            )
        )
        await to_listening(session, box, stt, llm, tts)
        await stt.emit_final("one more thing please")
        await wait_until(
            lambda: any(
                "Anything else" in (m.get("text") or "")
                for m in box.of("transcript")
            ),
            what="closing offer spoken",
        )
        await session.handle({"type": "playback_done"})
        assert session._closing_offer is True
        await stt.emit_final("actually no thank you")
        await wait_until(
            lambda: session._closing_offer is False and llm.chat_calls == 2,
            what="closing flag cleared and the second turn ran",
        )

    asyncio.run(scenario())


# ------------------------------------------------------ STT logging (2a)
def test_stt_final_and_gate_decision_logged_with_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await to_listening(session, box, stt, llm, tts)
        with caplog.at_level(logging.INFO, logger="backend.session"):
            await stt.emit_final("sor y w at", 0.2)
            await wait_until(
                lambda: any(m.get("text") == REPEAT for m in box.of("transcript")),
                what="canned repeat",
            )

    asyncio.run(scenario())
    messages = [r.getMessage() for r in caplog.records]
    assert any(
        "stt final" in m and "sor y w at" in m and "conf=0.2" in m
        for m in messages
    ), messages
    assert any(
        "stt gate" in m and "low confidence" in m for m in messages
    ), messages


def test_empty_final_gate_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Empty finals were invisible before (silent early return) - they must
    show up in the log with their reason."""

    async def scenario() -> None:
        session, box, stt, llm, tts = make()
        await to_listening(session, box, stt, llm, tts)
        with caplog.at_level(logging.INFO, logger="backend.session"):
            await stt.emit_final("")  # Deepgram silence chatter
            await asyncio.sleep(0.05)

    asyncio.run(scenario())
    messages = [r.getMessage() for r in caplog.records]
    assert any("empty final ignored" in m for m in messages), messages
