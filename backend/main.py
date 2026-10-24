from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI(title="Aria Voice Agent", version="0.1.0")

DIST: Path = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "aria"}


@app.get("/{full_path:path}", include_in_schema=False)
async def spa(full_path: str) -> FileResponse:
    """Serve built frontend files; unknown paths fall back to index.html
    so client-side clean routes (/lens, /requirements …) deep-link correctly."""
    if full_path:
        root = DIST.resolve()
        candidate = (DIST / full_path).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
    index = DIST / "index.html"
    if not index.is_file():
        raise HTTPException(503, "Frontend not built — run: cd frontend && npm run build")
    return FileResponse(index, media_type="text/html")
