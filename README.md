---
title: Aria Voice Agent
sdk: docker
app_port: 7860
---

# Aria — AI Voice Customer-Support Agent for Aura Skincare

[![CI](https://github.com/DanielDeshmukh/Aria/actions/workflows/ci.yml/badge.svg)](https://github.com/DanielDeshmukh/Aria/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%20%E2%80%93%203.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.162%2B-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-7-646CFF?logo=vite&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind-4-38B2AC?logo=tailwindcss&logoColor=white)

Browser-based AI voice customer-support agent for the **Datastraw AI + Tech
internship assignment**. This repository currently ships the **Phase 1
master-plan website** (React + Vite + Tailwind) served by **FastAPI**; the
voice pipeline (Deepgram STT → Groq LLM with tools → Sarvam TTS) lands next.

> **Testing policy:** no code or command block reaches this repository before
> it has been executed. Every snippet below was run on Windows 11
> (PowerShell, Python 3.13, Node 24) and/or Linux (Docker, Python 3.11,
> Node 22) before being documented, and [CI](.github/workflows/ci.yml)
> re-runs typecheck + build + the full test suite on every push.

## Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Tech stack](#3-tech-stack)
4. [Repository structure](#4-repository-structure)
5. [Prerequisites](#5-prerequisites)
6. [Quick start](#6-quick-start)
7. [Testing & CI](#7-testing--ci)
8. [HTTP API](#8-http-api)
9. [Client-side routing notes](#9-client-side-routing-notes)
10. [Environment variables](#10-environment-variables)
11. [Docker](#11-docker)
12. [Deploy to Hugging Face Spaces](#12-deploy-to-hugging-face-spaces)
13. [Troubleshooting](#13-troubleshooting)
14. [Assignment documents](#14-assignment-documents)

---

## 1. Overview

Aria answers Aura Skincare customers' questions (products, routines, orders,
discounts, complaints) in a natural voice conversation. The full assignment
spec, test script and 4-day schedule live in
[`datastraw-aria-voice-agent-plan.md`](./datastraw-aria-voice-agent-plan.md).

| Phase | Deliverable | Status |
|---|---|---|
| **1** | Interactive master-plan site + FastAPI scaffold + Docker/HF deployment layout | ✅ shipped (this repo) |
| 2 | Voice session: WebSocket, streaming STT → LLM → TTS with tool calling | ⏳ next |
| 3 | Tools, guardrails, call summary + owner dashboard | ⏳ |
| 4 | Hugging Face Space launch, demo assets, final submission | ⏳ |

## 2. Architecture

```
                     ┌──────────────────────────────────────────────┐
  browser  ────────► │  FastAPI (uvicorn, port 7860)                │
   (Phase 1:         │                                              │
    static site)     │  GET /api/health      → liveness probe       │
                     │  GET /*               → frontend/dist       │
                     │                         (index.html fallback)│
                     │                                              │
   (Phase 2:         │  WS  /ws/call         → voice session  ⏳    │
    voice call)      │       │                                      │
                     │       ├─► Deepgram  (streaming STT)     ⏳    │
                     │       ├─► Groq      (LLM + tool calls)  ⏳    │
                     │       └─► Sarvam    (Bulbul v4 Flash TTS)⏳   │
                     └──────────────────────────────────────────────┘
```

* **Phase 1 (today):** FastAPI serves the single-file production build of the
  planning site. Clean routes such as `/lens` or `/requirements` deep-link
  because unknown paths fall back to `index.html` and the client router
  scrolls to the matching section (see [§9](#9-client-side-routing-notes)).
* **Phase 2 (next):** the same process upgrades a request to a WebSocket for
  duplex audio; all provider API keys stay **server-side** (see
  [§10](#10-environment-variables)).

## 3. Tech stack

| Layer | Technology | Version tested | Role |
|---|---|---|---|
| UI | React | 19.2.6 | planning-site components |
| Build | Vite (`vite-plugin-singlefile`) | 7.3.2 | one-file production build |
| Styling | Tailwind CSS | 4.1.17 | design tokens, light/dark themes |
| Animation | Framer Motion | ^14.6 | scroll reveals, marquee |
| Icons | lucide-react | ^1.61 | icon set |
| Language | TypeScript (strict) | 5.9.3 | type safety, CI typecheck |
| API | FastAPI + Starlette | 0.162.0 | static serving, future voice API |
| Server | Uvicorn (`[standard]`) | 0.54.0 | ASGI server |
| Tests | pytest + FastAPI TestClient (httpx) | 9.1.1 | TDD suite |
| Runtime | Python / Node | 3.11–3.13 / 22+ | verified on both (Windows + Docker/CI) |
| Container | Multi-stage Docker (node:22-alpine → python:3.11-slim) | — | HF Spaces deploy on port 7860 |

## 4. Repository structure

```
Aria/
├── backend/                 # FastAPI service (server-side only)
│   ├── main.py              #   app, /api/health, SPA catch-all
│   └── tests/               #   TDD suite: health + SPA serving
├── frontend/                # React planning site (Vite + Tailwind)
│   ├── src/
│   │   ├── components/      #   Nav, Hero, Lens, Requirements, …
│   │   ├── routes.ts        #   clean-route scroll routing
│   │   └── index.css        #   @theme tokens, light/dark palettes
│   ├── index.html           #   no-flash theme bootstrap script
│   └── dist/                #   production build (generated, gitignored)
├── .github/workflows/ci.yml # CI: typecheck + build + pytest on every push
├── Dockerfile               # multi-stage: Node builds, Python serves
├── .dockerignore            #   keeps node_modules/.env/.venv out of the image
├── .env.example             #   DEEPGRAM/GROQ/SARVAM key template (no values)
├── requirements.txt         # runtime: fastapi, uvicorn[standard]
├── requirements-dev.txt     # + pytest, httpx
├── README.md                # this file
└── datastraw-aria-voice-agent-plan.md   # full assignment plan
```

## 5. Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| Git | 2.x | version control, HF pushes |
| Node.js + npm | 22+ (tested on 22 and 24) | frontend install/build/dev |
| Python | 3.11–3.13 (tested on 3.11 and 3.13) | backend, tests |
| Docker (optional) | any recent | container build & HF Spaces |

## 6. Quick start

### 6.1 Frontend only (hot reload)

```bash
cd frontend
npm install
npm run dev        # → http://localhost:5173
```

### 6.2 Full stack — FastAPI serving the built site (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

cd frontend; npm run build; cd ..      # produces frontend/dist

uvicorn backend.main:app --reload      # → http://localhost:8000
```

### 6.3 Full stack on macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

cd frontend && npm run build && cd ..

uvicorn backend.main:app --reload      # → http://localhost:8000
```

Smoke-check either server:

```bash
curl http://localhost:8000/api/health   # {"status":"ok","service":"aria"}
curl -I http://localhost:8000/lens      # HTTP/1.1 200 OK (SPA fallback)
```

### 6.4 Run it as a container

See [§11](#11-docker) — the exact build/run/probe sequence was executed as part
of Task 6.

## 7. Testing & CI

**Rule of the repo: nothing lands untested.** Feature work follows TDD
(red → green → refactor), and `.github/workflows/ci.yml` re-verifies
everything on every push to `main` and on every pull request.

What CI runs (the same steps were executed locally before this file was
committed):

```bash
cd frontend
npm ci                  # lockfile-exact install
npx tsc --noEmit        # typecheck
npm run build           # production build (dist/ must exist)
cd ..
pip install -r requirements-dev.txt
python -m pytest -v     # 4 tests: health + SPA serving + fallback + API routing
```

Run the suite any time from the repo root (SPA tests auto-skip if
`frontend/dist` has not been built yet):

```powershell
python -m pytest -v
```

Current suite:

| Test | Asserts |
|---|---|
| `test_health_returns_ok` | `GET /api/health` → `{"status":"ok","service":"aria"}` |
| `test_root_serves_index_html` | `GET /` → HTML with the app mount point |
| `test_clean_route_falls_back_to_index` | `GET /lens` → `200` HTML fallback |
| `test_api_route_is_not_swallowed_by_catch_all` | `/api/*` stays under the catch-all |

## 8. HTTP API

| Method & route | Purpose |
|---|---|
| `GET /api/health` | Liveness probe — used by CI, Docker smoke tests and HF |
| `GET /` | Serves `frontend/dist/index.html` |
| `GET /<asset>` | Serves a real file from `frontend/dist` when it exists |
| `GET /<unknown>` | Falls back to `index.html` (client-side clean routes) |
| `WS /ws/call` | **Planned (Phase 2)** — duplex voice session |

Path traversal is blocked: the catch-all resolves every candidate path and
rejects anything outside `frontend/dist`.

## 9. Client-side routing notes

* `frontend/src/routes.ts` owns navigation: clicks are intercepted and pushed
  via `history.pushState`, then the target section is scrolled smoothly with
  `scroll-margin-top: 86px` so section headings clear the sticky nav.
* Deep links (`/lens`, `/requirements`, …) are re-applied on load — after
  fonts and layout settle — unless the user has already scrolled (their
  scroll wins).
* Legacy `/#section` URLs are converted to clean `/section` paths in place.
* Because FastAPI unknown-paths fall back to `index.html`, these URLs work on
  a cold reload and in production, not just in the Vite dev server.

## 10. Environment variables

Copy the template once:

```powershell
Copy-Item .env.example .env
```

| Key | Phase | Used by | Where it lives |
|---|---|---|---|
| `DEEPGRAM_API_KEY` | 2 | streaming speech-to-text | server only |
| `GROQ_API_KEY` | 2 | LLM with tool calling | server only |
| `SARVAM_API_KEY` | 2 | Sarvam Bulbul v4 Flash TTS | server only |

`.env` is git-ignored and excluded from the Docker build context. Keys must
**never** reach the browser — on Hugging Face they go in
**Settings ▸ Secrets**, locally in `.env`.

## 11. Docker

Multi-stage build: `node:22-alpine` compiles the frontend, `python:3.11-slim`
runs Uvicorn on **port 7860** (the port HF Spaces expects).

```powershell
docker build -t aria-voice-agent .
docker run -d --name aria-smoke -p 7860:7860 aria-voice-agent

Invoke-RestMethod http://localhost:7860/api/health   # {"status":"ok",…}
(Invoke-WebRequest http://localhost:7860/lens).StatusCode   # 200

docker stop aria-smoke; docker rm aria-smoke
```

macOS/Linux equivalent: `curl http://localhost:7860/api/health`.

## 12. Deploy to Hugging Face Spaces

1. Create a Space with **SDK: Docker**, hardware **CPU Basic (free)**.
2. Add this repository as a second remote and push:

   ```bash
   git remote add hf https://huggingface.co/spaces/DanielDeshmukh/aria-voice-agent
   git branch -M main
   git push hf main
   ```

3. Space → **Settings ▸ Variables and secrets**: add the three keys from
   [§10](#10-environment-variables).
4. HF builds the `Dockerfile` remotely; the README front matter
   (`sdk: docker`, `app_port: 7860`) points the Space at it.
5. Free Spaces sleep after ~48 h idle — wake it before demos.

> `git remote add hf` is verified; `git push hf main` executes at deploy time
> (requires your Hugging Face token — `hf auth login` or Space write token).

## 13. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `npm ci` fails with `EPERM … *.node` | Vite dev server has the file locked | Stop the dev server (port 5173), run `npm ci`, restart |
| pytest reports `SKIPPED` on SPA tests | `frontend/dist` missing | `cd frontend && npm run build` |
| `ModuleNotFoundError: backend.main` | running pytest outside the repo root | run `python -m pytest` from the repository root |
| `Address already in use` :5173/:8000/:7860 | stale dev/uvicorn/docker process | stop the listener (Windows: `Get-NetTCPConnection -LocalPort 5173`) or pick another `--port` |
| pip `ResolutionImpossible` during Docker build | old pip 24 resolver + registry timeouts | image already runs `pip install --upgrade pip` first — rebuild |
| Theme flashes light on reload | JS disabled or localStorage cleared | bootstrap script in `index.html` defaults correctly; report a bug if seen |

## 14. Assignment documents

* [`datastraw-aria-voice-agent-plan.md`](./datastraw-aria-voice-agent-plan.md)
  — full plan: requirements, architecture, 4-day schedule, test script.
* [`docs/superpowers/plans/2026-10-24-aria-restructure-fastapi.md`](./docs/superpowers/plans/2026-10-24-aria-restructure-fastapi.md)
  — the TDD task plan this Phase 1 restructure was executed from.
