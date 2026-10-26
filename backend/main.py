import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from .session import CallSession
from .llm import GroqLLM
from .selftest import run_selftest
from .stt import DeepgramSTT
from .tts import SarvamTTS

# Backend loggers (backend.llm turn reports, session warnings) have no handler
# otherwise — uvicorn/Vercel stdout would swallow them.
if not logging.root.handlers:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )

logger = logging.getLogger(__name__)

app = FastAPI(title="Aria Voice Agent", version="0.1.0")

DIST: Path = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def session_factory(send) -> CallSession:
    """Wired providers for /ws/call. Tests monkeypatch this module attribute."""
    return CallSession(stt=DeepgramSTT(), llm=GroqLLM(), tts=SarvamTTS(), send=send)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "aria"}


@app.get("/api/ws-selftest")
async def ws_selftest() -> dict:
    """Post-deploy reachability probe: outbound WebSocket to Deepgram, WS to
    Sarvam, HTTPS to Groq from inside the function. Returns ok/detail/latency
    names only — never keys or tokens."""
    return await run_selftest()


@app.websocket("/ws/call")
async def ws_call(websocket: WebSocket) -> None:
    await websocket.accept()
    session = session_factory(websocket.send_json)
    try:
        while True:
            await session.handle(await websocket.receive_json())
            if session.ended:
                # summary + state:ended are already flushed by _end; close the
                # socket only AFTER sending them (the endpoint returns, which
                # closes the connection). Buffered repeat "end" clicks are
                # deliberately not read again - _end is idempotent.
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        # Never swallow silently: a swallowed send/close failure was how the
        # production "stuck LISTENING, no summary" bug hid itself.
        logger.exception("ws/call handler failed")
    finally:
        await session.close()


@app.get("/{full_path:path}", include_in_schema=False)
async def spa(full_path: str) -> FileResponse:
    """Serve built frontend files; unknown paths fall back to index.html
    so client-side clean routes (/pipeline …) and hash targets (/#call)
    deep-link correctly."""
    if full_path:
        root = DIST.resolve()
        candidate = (DIST / full_path).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
    index = DIST / "index.html"
    if not index.is_file():
        raise HTTPException(503, "Frontend not built — run: cd frontend && npm run build")
    return FileResponse(index, media_type="text/html")


# Static-file directory for Vercel's FastAPI build: files under frontend/dist
# are promoted to the CDN at build time (app.frontend checks path operations
# first, so the catch-all above keeps serving locally, unchanged). check_dir
# stays False so a fresh clone without `dist/` still imports cleanly in tests.
app.frontend("/", directory="frontend/dist", check_dir=False)
