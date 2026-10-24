# Aria Repo Restructure + FastAPI Scaffold — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `D:\Vs Code\VS code\Aria` into the plan-doc repo layout (`backend/` + `frontend/` + root `Dockerfile`/`README.md`/`.env.example`) with a FastAPI service that serves the built planning site, ready for Hugging Face Spaces.

**Architecture:** Move the existing Vite app verbatim into `frontend/`. A new FastAPI app in `backend/main.py` exposes `/api/health` and a GET catch-all that serves `frontend/dist` files (falling back to `index.html` so the client-side clean routes like `/lens` keep working). A multi-stage Dockerfile builds the frontend with Node and serves it from Uvicorn on port 7860.

**Tech Stack:** React 19 + Vite 7 + Tailwind v4 (existing, unchanged) · FastAPI + Uvicorn · pytest + httpx (TestClient) · Docker (node:22-alpine → python:3.11-slim) · git

**Spec:** `datastraw-aria-voice-agent-plan.md` §5 (stack + Docker/HF rules), §10 (repo structure). **Out of scope (next plan):** voice pipeline, tools, policy engine, all other §10 backend files, HF push.

## Global Constraints

- Repo root stays `D:\Vs Code\VS code\Aria`; layout must end up matching plan.md §10 for the files in scope
- Frontend behavior must not regress: `npx tsc --noEmit` and `npm run build` green from `frontend/`; `/lens` deep links and theme toggle still work
- `Dockerfile` at repo root; app listens on **7860**; README front matter exactly `sdk: docker`, `app_port: 7860`
- API keys server-side only: `.env` gitignored, never committed; `.env.example` committed
- Python ≥ 3.11, Node ≥ 22 (Docker uses `node:22-alpine`)
- `python -m pytest` from repo root must pass
- No new UI features or theme changes in this plan

## File Structure

| Action | Path | Responsibility |
|---|---|---|
| Move | `src/`, `index.html`, `vite.config.ts`, `tsconfig.json`, `package.json`, `package-lock.json` → `frontend/` | existing site, unchanged |
| Create | `backend/__init__.py`, `backend/main.py` | FastAPI app: health + static SPA serving |
| Create | `backend/tests/__init__.py`, `test_health.py`, `test_spa.py` | TDD coverage |
| Create | `requirements.txt`, `requirements-dev.txt` | runtime / dev deps |
| Create | `.gitignore`, `.dockerignore`, `Dockerfile` | hygiene + HF deploy |
| Create | `README.md` (root, HF front matter), `.env.example` | docs + key contract |
| Delete | `dist/` (stale root build), `vite-preview.log` | cruft |

---

### Task 1: Git baseline + hygiene

**Files:** Create `.gitignore`; delete `vite-preview.log`, root `dist/`

**Interfaces:** Produces: initialized repo, ignore rules (`node_modules/`, `dist/`, `.env`, `.playwright-mcp/`, `*.log`) that every later commit relies on.

- [ ] **Step 1: Check tooling**

Run: `git --version; python --version; node --version`
Expected: git ≥ 2.x, Python ≥ 3.11, Node ≥ 22 (if git identity is unset, run `git config --global user.name "..."` / `user.email "..."` first)

- [ ] **Step 2: Create `.gitignore`**

```
node_modules/
dist/
.venv/
__pycache__/
*.pyc
.pytest_cache/
.env
.playwright-mcp/
*.log
```

- [ ] **Step 3: Delete cruft**

```powershell
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
Remove-Item vite-preview.log -ErrorAction SilentlyContinue
```

- [ ] **Step 4: Init and commit**

```powershell
git init
git add -A
git commit -m "chore: baseline planning site with gitignore"
```
Expected: commit succeeds; `git status` clean; no `node_modules`/logs tracked.

---

### Task 2: Move frontend into `frontend/`

**Files:** Move 6 root items → `frontend/`

**Interfaces:** Produces: self-contained `frontend/` package (same scripts: `dev`, `build`, `preview`); root no longer contains `src`/`package.json`.

- [ ] **Step 1: Move files**

```powershell
New-Item -ItemType Directory -Path frontend | Out-Null
Move-Item src, index.html, vite.config.ts, tsconfig.json, package.json, package-lock.json -Destination frontend
```
Configs are self-relative (`baseUrl: "."`, alias `__dirname/src`), so they move unmodified.

- [ ] **Step 2: Install inside frontend**

Run (workdir `frontend`): `npm install`
Expected: lockfile unchanged, `frontend/node_modules` created.

- [ ] **Step 3: Typecheck**

Run (workdir `frontend`): `npx tsc --noEmit`
Expected: no output.

- [ ] **Step 4: Build**

Run (workdir `frontend`): `npm run build`
Expected: `frontend/dist/index.html` (~532 kB, singlefile — only file).

- [ ] **Step 5: Manual smoke**

Run (workdir `frontend`): `npm run dev` → open `http://localhost:5173/`
Expected: site renders, nav shows clean paths (`/lens`), theme toggle works, marquee hover-pause works. Stop the server after.

- [ ] **Step 6: Drop the duplicate install + commit**

```powershell
Remove-Item -Recurse -Force node_modules   # root copy; frontend/ now owns its install
git add -A
git commit -m "chore: move vite app into frontend/"
```

---

### Task 3: FastAPI scaffold with health endpoint (TDD)

**Files:** Create `requirements.txt`, `requirements-dev.txt`, `backend/__init__.py`, `backend/tests/__init__.py`, `backend/tests/test_health.py`, `backend/main.py`

**Interfaces:** Consumes: nothing. Produces: `app` (`fastapi.FastAPI`) exported from `backend.main` — Task 4's tests import it.

- [ ] **Step 1: Dependency files**

`requirements.txt`:
```
fastapi>=0.115
uvicorn[standard]>=0.30
```
`requirements-dev.txt`:
```
-r requirements.txt
pytest>=8
httpx>=0.27
```
(`uvicorn[standard]` already includes the WebSocket stack the voice plan needs later.)

- [ ] **Step 2: Create venv + install**

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -q -r requirements-dev.txt
```
Expected: installs without error.

- [ ] **Step 3: Write the failing test**

Create `backend/__init__.py` and `backend/tests/__init__.py` (empty — makes `python -m pytest` resolve `backend.*` from the repo root), then `backend/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "aria"}
```

- [ ] **Step 4: Run to verify it fails**

Run: `.venv\Scripts\python -m pytest backend/tests/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.main'`.

- [ ] **Step 5: Minimal implementation**

`backend/main.py`:
```python
from fastapi import FastAPI

app = FastAPI(title="Aria Voice Agent", version="0.1.0")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "aria"}
```

- [ ] **Step 6: Run to verify it passes**

Run: `.venv\Scripts\python -m pytest backend/tests/test_health.py -v`
Expected: 1 passed.

- [ ] **Step 7: Commit**

```powershell
git add backend requirements.txt requirements-dev.txt
git commit -m "feat: FastAPI scaffold with /api/health"
```

---

### Task 4: Serve the built frontend + clean-route fallback (TDD)

**Files:** Modify `backend/main.py` (full file below); Create `backend/tests/test_spa.py`

**Interfaces:** Consumes: `app` from Task 3; `frontend/dist` from Task 2. Produces: exported `DIST: Path` (tests + later Docker code rely on it); GET behavior `/*` → file or `index.html`.

- [ ] **Step 1: Build the frontend (dist must exist)**

Run (workdir `frontend`): `npm run build`
Expected: `frontend/dist/index.html` present.

- [ ] **Step 2: Write the failing test**

`backend/tests/test_spa.py`:
```python
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import DIST, app

pytestmark = pytest.mark.skipif(
    not (DIST / "index.html").exists(),
    reason="frontend not built — run: cd frontend && npm run build",
)

client = TestClient(app)


def test_root_serves_index_html() -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert '<div id="root">' in r.text


def test_clean_route_falls_back_to_index() -> None:
    r = client.get("/lens")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_api_route_is_not_swallowed_by_catch_all() -> None:
    assert client.get("/api/health").status_code == 200
```

- [ ] **Step 3: Run to verify it fails**

Run: `.venv\Scripts\python -m pytest backend/tests/test_spa.py -v`
Expected: FAIL with `ImportError: cannot import name 'DIST' from 'backend.main'`.

- [ ] **Step 4: Implement SPA serving**

`backend/main.py` (complete file):
```python
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
        candidate = DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
    index = DIST / "index.html"
    if not index.is_file():
        raise HTTPException(503, "Frontend not built — run: cd frontend && npm run build")
    return FileResponse(index, media_type="text/html")
```
Route order is safe: `/api/health` and FastAPI's own `/docs`, `/openapi.json` are registered before the catch-all; the catch-all is GET-only, so future POST/WS routes are unaffected.

- [ ] **Step 5: Run to verify it passes**

Run: `.venv\Scripts\python -m pytest -v`
Expected: 4 passed (1 health + 3 SPA).

- [ ] **Step 6: Live smoke**

Run: `.venv\Scripts\python -m uvicorn backend.main:app --port 8000` → open `http://localhost:8000/lens`
Expected: page loads scrolled to the Lens section; `http://localhost:8000/api/health` returns JSON. Stop the server.

- [ ] **Step 7: Commit**

```powershell
git add backend
git commit -m "feat: serve built frontend with SPA deep-link fallback"
```

---

### Task 5: README + `.env.example`

> **Amended during execution (same session):** Task 5 expanded to —
> **(a)** add `.github/workflows/ci.yml` (npm ci → `tsc --noEmit` → build → `pytest -v`, Python 3.13 + Node 22) so a CI-passing badge exists and nothing lands untested;
> **(b)** README must be comprehensively documented with badges, and *every*
> code block must be executed before commit (Windows PowerShell verified
> locally; POSIX flow verified in a `python:3.11-slim` container; Docker
> blocks verified in Task 6; `git remote add hf` syntax verified —
> `git push hf main` remains deploy-time);
> **(c)** publish the preserved history to a **new GitHub repo `Aria`**
> (`DanielDeshmukh/Aria`, branch `main`) and confirm the CI badge goes green.
> Task 6 deviation already applied: image runs `pip install --upgrade pip`
> first (real build failed with pip-24 `ResolutionImpossible`).

**Files:** Create `README.md`, `.env.example` at root

**Interfaces:** Consumes: routes from Tasks 3-4, Docker file from Task 6. Produces: HF Space front matter; the key-name contract (`DEEPGRAM_API_KEY`, `GROQ_API_KEY`, `SARVAM_API_KEY`).

- [ ] **Step 1: Create `.env.example`**

```
# Server-side only — never expose to the browser.
# Local: copy to .env (gitignored). Hugging Face: Settings ▸ Secrets.
DEEPGRAM_API_KEY=
GROQ_API_KEY=
SARVAM_API_KEY=
```

- [ ] **Step 2: Create `README.md`**

````markdown
---
title: Aria Voice Agent
sdk: docker
app_port: 7860
---

# Aria — Voice Customer Support Agent for Aura Skincare

Browser-based AI voice customer-support agent for the Datastraw AI + Tech
internship assignment. This repository currently ships the **master-plan
website** (React + Vite + Tailwind) behind a **FastAPI** server; the voice
pipeline (STT → LLM → TTS) lands next — roadmap:
[`datastraw-aria-voice-agent-plan.md`](./datastraw-aria-voice-agent-plan.md).

## Repository structure

```
aria-voice-agent/
├── backend/            # FastAPI (serves built frontend; voice pipeline next)
│   ├── main.py
│   └── tests/
├── frontend/           # React (Vite + Tailwind) master-plan site
│   ├── src/
│   └── index.html
├── Dockerfile          # multi-stage: Node builds, Python serves (port 7860)
├── .env.example
└── README.md
```

## Quick start

**Frontend only**
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

**Backend serving the built site** (Windows PowerShell shown; activate a venv first)
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
cd frontend; npm run build; cd ..
uvicorn backend.main:app --reload   # http://localhost:8000
```

**Tests** (from the repo root; SPA tests skip until the frontend is built)
```bash
python -m pytest
```

## API

| Route | Purpose |
|---|---|
| `GET /api/health` | liveness probe |
| `GET /*` | serves the built frontend; unknown paths fall back to `index.html` so clean routes (`/lens`, `/requirements`, …) deep-link |

## Environment variables (server-side only)

| Key | Used by |
|---|---|
| `DEEPGRAM_API_KEY` | streaming STT |
| `GROQ_API_KEY` | LLM with tool calling |
| `SARVAM_API_KEY` | Sarvam Bulbul v4 Flash TTS |

Copy `.env.example` → `.env` locally; on Hugging Face set them in
**Settings ▸ Secrets**. Keys must never reach the browser.

## Docker

```bash
docker build -t aria-voice-agent .
docker run -p 7860:7860 aria-voice-agent   # http://localhost:7860
```

## Deploy to Hugging Face Spaces

1. Create a Space with SDK **Docker**, hardware **CPU Basic (free)**.
2. `git remote add hf https://huggingface.co/spaces/Daniel2503/<space-name>` then `git push hf main` (GitHub stays the public source remote).
3. Set the three secrets above.
4. Free Spaces sleep after 48h idle — wake it before demos.

## Roadmap

Requirements, architecture, the 4-day schedule and the full test script live
in [`datastraw-aria-voice-agent-plan.md`](./datastraw-aria-voice-agent-plan.md).
````

- [ ] **Step 3: Verify**

Run: `Get-Content README.md -TotalCount 4`
Expected: first line is `---`, then `title: Aria Voice Agent`, `sdk: docker`, `app_port: 7860`.

- [ ] **Step 4: Commit**

```powershell
git add README.md .env.example
git commit -m "docs: README with HF front matter and .env.example"
```

---

### Task 6: Multi-stage Dockerfile + smoke test

**Files:** Create `Dockerfile`, `.dockerignore` at root

**Interfaces:** Consumes: `frontend/` build (Task 2), `backend/` + `requirements.txt` (Tasks 3-4). Produces: OCI image serving on `0.0.0.0:7860`.

- [ ] **Step 1: Check Docker**

Run: `docker --version`
Expected: Docker Desktop running. If unavailable, still create the files, commit, and mark the run-smoke step **deferred to deploy** (HF builds remotely).

- [ ] **Step 2: Create `.dockerignore`**

```
node_modules
frontend/node_modules
frontend/dist
dist
.venv
.git
.playwright-mcp
__pycache__
*.log
```

- [ ] **Step 3: Create `Dockerfile`**

```dockerfile
# stage 1 — build the frontend
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# stage 2 — serve with FastAPI
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist
EXPOSE 7860
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
```

- [ ] **Step 4: Build and smoke test**

```powershell
docker build -t aria-voice-agent .
docker run -d --name aria-smoke -p 7860:7860 aria-voice-agent
Invoke-RestMethod http://localhost:7860/api/health    # expect: status ok
(Invoke-WebRequest http://localhost:7860/lens).StatusCode   # expect: 200
docker stop aria-smoke; docker rm aria-smoke
```
Expected: both probes succeed; container stops cleanly.

- [ ] **Step 5: Commit**

```powershell
git add Dockerfile .dockerignore
git commit -m "feat: multi-stage Dockerfile for HF Spaces (port 7860)"
```

---

## Self-review notes (done)

- **Spec coverage:** §10 layout (in-scope files) ✓ · §5 Docker/port/HF front matter ✓ · §5 "keys server-side" ✓ · remaining §10 files + voice pipeline explicitly deferred by scope choice ✓
- **Type/interface consistency:** `app` and `DIST` names match across Tasks 3-6 ✓ · test imports match `main.py` exports ✓
- **Windows reality:** PowerShell commands, `.venv\Scripts`, `node:22-alpine` for Vite 7 ✓
