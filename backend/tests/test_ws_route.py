"""Route-level /ws/call tests: factory injection + dispatch + teardown.

starlette's WebSocketTestSession.__exit__ waits for the app task to finish,
so side-effect assertions after the with-block are deterministic without
receiving a single message (no hang risk).
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

import backend.main as main_mod
from backend.session import GREETING, CallSession
from backend.summary import SUMMARY_KEYS
from backend.tests._fakes import FakeLLM, FakeSTT, FakeTTS

FAKE_AUDIO_B64 = base64.b64encode(b"RIFF-FAKE-AUDIO").decode("ascii")


def _patch_factory(monkeypatch: pytest.MonkeyPatch):
    stt, llm, tts = FakeSTT(), FakeLLM(), FakeTTS()
    monkeypatch.setattr(
        main_mod,
        "session_factory",
        lambda send: CallSession(stt=stt, llm=llm, tts=tts, send=send),
    )
    return stt, llm, tts


@pytest.mark.timeout(10)
def test_ws_call_route_greeting_summary_end(monkeypatch: pytest.MonkeyPatch) -> None:
    stt, llm, tts = _patch_factory(monkeypatch)
    with TestClient(main_mod.app).websocket_connect("/ws/call") as ws:
        ws.send_json({"type": "start"})
        first = [ws.receive_json() for _ in range(5)]
        assert [m["type"] for m in first] == [
            "state",
            "transcript",
            "stats",
            "state",
            "audio",
        ]
        assert first[0] == {"type": "state", "state": "connecting"}
        assert first[1]["text"] == GREETING
        assert first[4]["data"] == FAKE_AUDIO_B64
        ws.send_json({"type": "end"})
        summary_ev = ws.receive_json()
        ended_ev = ws.receive_json()
        assert summary_ev["type"] == "summary"
        assert set(SUMMARY_KEYS) <= set(summary_ev["summary"])
        assert ended_ev == {"type": "state", "state": "ended"}
        assert stt.closed


@pytest.mark.timeout(10)
def test_ws_call_route_disconnect_closes_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stt, llm, tts = _patch_factory(monkeypatch)
    with TestClient(main_mod.app).websocket_connect("/ws/call") as ws:
        ws.send_json({"type": "start"})
    assert stt.started and stt.closed
    assert tts.synthed == [GREETING]
    assert llm.complete_calls == 0
