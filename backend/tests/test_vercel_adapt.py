"""Vercel adaptation tests — additive only.

Covers the Phase 1 pieces: hosting-limit call deadlines (270 s warning, 295 s
graceful force-end, only when VERCEL is set), the /api/ws-selftest route shape
(ok/detail/ms per probe, never secrets), and the deploy config files.
Existing suites must pass unchanged.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

import backend.session as session_mod
import backend.selftest as selftest_mod
from backend.main import app
from backend.summary import SUMMARY_KEYS
from backend.tests._fakes import EventBox, FakeLLM, FakeSTT, FakeTTS, wait_until

ROOT = Path(__file__).resolve().parents[2]
client = TestClient(app)


def make():
    stt, box = FakeSTT(), EventBox()
    session = session_mod.CallSession(
        stt=stt, llm=FakeLLM(), tts=FakeTTS(), send=box.send
    )
    return session, box


def test_call_ending_soon_then_graceful_force_end(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(session_mod, "CALL_ENDING_SOON_SECONDS", 0.05)
    monkeypatch.setattr(session_mod, "CALL_FORCE_END_SECONDS", 0.15)

    async def scenario() -> None:
        session, box = make()
        await session.handle({"type": "start"})
        await wait_until(
            lambda: box.of("call_ending_soon"), what="call_ending_soon event"
        )
        warn = box.of("call_ending_soon")[0]
        assert isinstance(warn["seconds_left"], int)
        await wait_until(lambda: box.of("summary"), what="force-end summary")
        assert len(box.of("summary")) == 1
        assert box.states()[-1] == "ended"
        assert set(SUMMARY_KEYS) <= set(box.of("summary")[0]["summary"])
        await session.close()

    asyncio.run(scenario())


def test_deadlines_cancelled_when_session_ends(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(session_mod, "CALL_ENDING_SOON_SECONDS", 0.05)
    monkeypatch.setattr(session_mod, "CALL_FORCE_END_SECONDS", 0.15)

    async def scenario() -> None:
        session, box = make()
        await session.handle({"type": "start"})
        await session.handle({"type": "end"})
        await asyncio.sleep(0.3)  # past both deadlines — they must be cancelled
        assert box.of("call_ending_soon") == []
        assert len(box.of("summary")) == 1
        await session.close()

    asyncio.run(scenario())


def test_deadlines_absent_without_vercel_env(monkeypatch) -> None:
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr(session_mod, "CALL_ENDING_SOON_SECONDS", 0.03)
    monkeypatch.setattr(session_mod, "CALL_FORCE_END_SECONDS", 0.06)

    async def scenario() -> None:
        session, box = make()
        await session.handle({"type": "start"})
        await asyncio.sleep(0.2)  # far past both values — but not on Vercel
        assert box.of("call_ending_soon") == []
        assert box.of("summary") == []
        assert "ended" not in box.states()
        await session.close()

    asyncio.run(scenario())


def test_selftest_route_reports_shape_without_secrets(monkeypatch) -> None:
    async def ok_deepgram():
        return True, "ok"

    async def boom_sarvam():
        raise RuntimeError("boom with a secret-looking string")

    async def groq_unauthorized():
        return False, "HTTP 401"

    monkeypatch.setattr(selftest_mod, "_probe_deepgram_ws", ok_deepgram)
    monkeypatch.setattr(selftest_mod, "_probe_sarvam_ws", boom_sarvam)
    monkeypatch.setattr(selftest_mod, "_probe_groq_https", groq_unauthorized)

    r = client.get("/api/ws-selftest")
    assert r.status_code == 200
    result = r.json()
    assert set(result) == {"deepgram_ws", "sarvam_ws", "groq_https", "ok"}
    assert result["deepgram_ws"]["ok"] is True
    assert result["deepgram_ws"]["detail"] == "ok"
    assert result["deepgram_ws"]["ms"] >= 0
    assert result["sarvam_ws"]["ok"] is False
    assert result["sarvam_ws"]["detail"] == "RuntimeError"  # type name only
    assert result["groq_https"] == {
        "ok": False,
        "detail": "HTTP 401",
        "ms": result["groq_https"]["ms"],
    }
    assert result["ok"] is False
    # exception text and key values must never leak into the response
    assert "boom" not in r.text


def test_selftest_all_ok(monkeypatch) -> None:
    async def ok():
        return True, "ok"

    monkeypatch.setattr(selftest_mod, "_probe_deepgram_ws", ok)
    monkeypatch.setattr(selftest_mod, "_probe_sarvam_ws", ok)
    monkeypatch.setattr(selftest_mod, "_probe_groq_https", ok)

    r = client.get("/api/ws-selftest")
    assert r.status_code == 200
    result = r.json()
    assert result["ok"] is True
    for key in ("deepgram_ws", "sarvam_ws", "groq_https"):
        assert result[key]["ok"] is True
        assert result[key]["detail"] == "ok"


def test_vercel_json_configuration() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert config["fluid"] is True  # WebSockets require Fluid compute
    assert config["regions"] == ["bom1"]  # Mumbai
    entry = config["functions"]["main.py"]
    assert entry["maxDuration"] == 300  # Hobby maximum
    assert "npm run build" in config["buildCommand"]


def test_vercelignore_excludes_env_and_local_clutter() -> None:
    lines = [
        line.strip()
        for line in (ROOT / ".vercelignore").read_text(encoding="utf-8").splitlines()
    ]
    for required in (".env", ".venv", "**/__pycache__", "**/node_modules"):
        assert required in lines


def test_root_main_shim_exports_backend_app() -> None:
    import main as root_main

    assert root_main.app is app
