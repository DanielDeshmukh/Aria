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
internship assignment**. The repository ships the **Phase 1 master-plan
website** (React + Vite + Tailwind) plus the **backend voice pipeline**: a
FastAPI WebSocket session (`/ws/call`) wiring **Deepgram STT → Groq LLM with
tool calling → Sarvam Bulbul v4 Flash TTS**, with order tools, call guardrails
and a post-call summary. The in-browser call screen is live (mic capture →
WebSocket session → live state badge → audio playback); the transcript,
orders and summary panels are landing next.

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
8. [HTTP & WebSocket API](#8-http--websocket-api)
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
| **1** | Interactive master-plan site + FastAPI scaffold + Docker/HF deployment layout | shipped |
| **2** | Voice session: WebSocket, streaming STT → LLM → TTS with tool calling | backend shipped (`/ws/call`) |
| **3** | Tools, guardrails, call summary | backend shipped · owner dashboard pending |
| — | In-browser call screen: mic capture, WS session, state badge, playback | shipped · transcript/summary panels in progress |
| **4** | Hugging Face Space launch, demo assets, final submission | pending |

## 2. Architecture

```
                     ┌──────────────────────────────────────────────┐
  browser  ────────► │  FastAPI (uvicorn, port 7860)                │
   (Phase 1:         │                                              │
    static site)     │  GET /api/health      → liveness probe       │
                     │  GET /*               → frontend/dist       │
                     │                         (index.html fallback)│
                     │                                              │
   (voice call)      │  WS  /ws/call         → CallSession      done  │
                     │       │                                      │
                     │       ├─► Deepgram  (streaming STT)      done  │
                     │       ├─► Groq      (LLM + tool calls)   done  │
                     │       └─► Sarvam    (Bulbul v4 Flash TTS) done  │
                     └──────────────────────────────────────────────┘
```

* **Static site:** FastAPI serves the single-file production build of the
  planning site. Clean routes such as `/lens` or `/requirements` deep-link
  because unknown paths fall back to `index.html` and the client router
  scrolls to the matching section (see [§9](#9-client-side-routing-notes)).
* **Voice session:** the same process upgrades a request to a WebSocket for
  duplex audio; all provider API keys stay **server-side** (see
  [§10](#10-environment-variables)). The session state machine, provider
  clients, order tools and summary builder live in `backend/` and are covered
  by the hermetic test suite (see [§7](#7-testing--ci)).
* **Call screen:** the hero's Start Call CTA opens `/call`, an in-browser test
  call: AudioWorklet mic capture → 16 kHz PCM16 frames → the same WebSocket,
  with live state badge, first-audio chip and gapless audio playback
  (`frontend/src/call/`).

## 3. Tech stack

| Layer | Technology | Version tested | Role |
|---|---|---|---|
| UI | React | 19.2.6 | planning-site components |
| Build | Vite (`vite-plugin-singlefile`) | 7.3.2 | one-file production build |
| Styling | Tailwind CSS | 4.1.17 | design tokens, light/dark themes |
| Animation | Framer Motion | ^14.6 | scroll reveals, marquee |
| Icons | lucide-react | ^1.61 | icon set |
| Language | TypeScript (strict) | 5.9.3 | type safety, CI typecheck |
| API | FastAPI + Starlette | 0.162.0 | static serving + `WS /ws/call` |
| Server | Uvicorn (`[standard]`) | 0.54.0 | ASGI server |
| Voice protocol | `websockets` | 15.0.1 | Deepgram + Sarvam WS clients |
| LLM client | `openai` SDK (Groq base URL) | ≥1.50 | streaming chat + tool calls |
| Tests | pytest + FastAPI TestClient (httpx) | 9.1.1 | TDD suite (hermetic + live) |
| Runtime | Python / Node | 3.11–3.13 / 22+ | verified on both (Windows + Docker/CI) |
| Container | Multi-stage Docker (node:22-alpine → python:3.11-slim) | — | HF Spaces deploy on port 7860 |

## 4. Repository structure

```
Aria/
├── backend/                 # FastAPI service (server-side only)
│   ├── main.py              #   app, /api/health, SPA fallback, WS /ws/call
│   ├── config.py            #   sole key accessor (repr-safe Settings)
│   ├── session.py           #   CallSession state machine (barge-in,
│   │                        #   silence, canned lines, tools, summary)
│   ├── stt.py               #   Deepgram streaming client + pure parser
│   ├── llm.py               #   Groq streaming chat + tool-call assembly
│   ├── tts.py               #   Sarvam Bulbul WS client (sentence-level)
│   ├── splitter.py          #   stream → sentences for per-sentence TTS
│   ├── tools.py             #   order/policy tools + JSON schemas
│   ├── policy.py            #   returns/cancellation/COD/shipping rules
│   ├── normalize.py         #   order-id normalization ("ord 101" → ORD-101)
│   ├── summary.py           #   4-key post-call summary (LLM + fallback)
│   ├── prompts.py           #   system prompt (verbatim, test-locked)
│   ├── audio_utils.py       #   PCM16 resample/base64 helpers
│   ├── data/orders.json     #   ORD-101..103 fixtures
│   ├── scripts/             #   probe_sarvam (schema probe), text_harness
│   └── tests/               #   100+ hermetic tests + live smoke tests
│                            #   (live ones skip without .env keys)
├── frontend/                # React planning site (Vite + Tailwind)
│   ├── src/
│   │   ├── call/            #   CallApp, useVoiceSession, useMic, playback,
│   │   │                    #   OrdersPanel (ORD-101..103 helper)
│   │   ├── components/      #   Nav, Hero, Lens, Requirements, …
│   │   ├── routes.ts        #   clean-route scroll routing
│   │   └── index.css        #   @theme tokens, light/dark palettes
│   ├── index.html           #   no-flash theme bootstrap script
│   ├── public/              #   pcm-worklet.js (mic → 16 kHz PCM16 frames)
│   └── dist/                #   production build (generated, gitignored)
├── .github/workflows/ci.yml # CI: typecheck + build + pytest on every push
├── Dockerfile               # multi-stage: Node builds, Python serves
├── .dockerignore            #   keeps node_modules/.env/.venv out of the image
├── .env.example             #   DEEPGRAM/GROQ/SARVAM key template (no values)
├── requirements.txt         # runtime: fastapi, uvicorn[standard], websockets, openai
├── requirements-dev.txt     # + pytest, httpx, pytest-timeout
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
python -m pytest -v     # full suite: 100+ tests (see table below)
```

Run the suite any time from the repo root (SPA tests auto-skip if
`frontend/dist` has not been built yet):

```powershell
python -m pytest -v
```

Test suite layout:

| Module | Asserts |
|---|---|
| `test_health` / `test_spa` / `test_orders` | liveness, static serving, SPA fallback + API routing, orders fixtures |
| `test_config` | keys repr-safe, `missing_keys()` names-only, frozen/cached settings |
| `test_policy` / `test_normalize` / `test_tools` | returns/COD/shipping rules, order-id normalization, tool schemas + not-found |
| `test_prompt_verbatim` | system prompt locked verbatim |
| `test_llm_assembly` | streaming text + fragmented tool calls → correct history (`tool_call_id`) |
| `test_summary` | 4-key summary coercion + deterministic fallback |
| `test_splitter` | sentence boundaries: abbreviations, prices, partial tails |
| `test_ws_session` / `test_ws_route` / `test_ws_edges` | state machine: greeting, turns, barge-in, silence, canned lines, provider failures |
| `test_audio_utils` / `test_stt_parse` | resample/base64, Deepgram frame parsing |
| `test_llm_live` / `test_stt_live` / `test_tts_live` / `test_live_voice` | real Groq/Deepgram/Sarvam smoke tests — **live voice E2E: TTS audio → STT → tool turn → summary** — all skip automatically when `.env` keys are absent (CI has none) |

## 8. HTTP & WebSocket API

| Method & route | Purpose |
|---|---|
| `GET /api/health` | Liveness probe — used by CI, Docker smoke tests and HF |
| `GET /` | Serves `frontend/dist/index.html` |
| `GET /<asset>` | Serves a real file from `frontend/dist` when it exists |
| `GET /<unknown>` | Falls back to `index.html` (client-side clean routes) |
| `WS /ws/call` | Duplex voice session (see protocol below) |

Path traversal is blocked: the catch-all resolves every candidate path and
rejects anything outside `frontend/dist`.

### 8.1 Voice session protocol (`WS /ws/call`)

Client → server frames:

| Type | Payload | Meaning |
|---|---|---|
| `start` | — | begin the call: STT opens, Aria greets |
| `audio` | `data`: base64 PCM16, 16 kHz mono | mic frame → Deepgram |
| `playback_done` | — | agent audio finished → listening |
| `end` | — | hang up → post-call summary |

Server → client frames:

| Type | Payload | Meaning |
|---|---|---|
| `state` | `connecting / listening / thinking / speaking / ended` | session state machine |
| `transcript` | `role`, `text`, `final` | rolling transcript (interims throttled) |
| `audio` | `mime` (`audio/l16;rate=16000`), `data` | one synthesized agent sentence |
| `barge_in` | — | customer interrupted the agent (turn cancelled) |
| `tool` | `name`, `args`, `result` | order/policy tool executed |
| `stats` | `first_audio_ms` | turn latency (first sentence audible) |
| `summary` | `transcript`, `summary` | 4-key post-call summary (LLM, deterministic fallback) |
| `error` | `message` | provider failure — message contains names only, never secrets |

Guardrails inside the session: speech during playback triggers barge-in
(cancel + replay from customer speech), 9 s of silence asks "still there?" once
until the customer speaks again, low-confidence finals answer with a canned
repeat line, and the session is one-shot (one call per connection).

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
* `/call` is **not** part of that scroll router: it is a full-page app. The
  click interceptor ignores paths outside the section list, so the hero's
  `href="/call"` navigates natively, and on `/call` the plain `href="/"`
  back link returns to the site (the hook is not mounted there).

## 10. Environment variables

Copy the template once:

```powershell
Copy-Item .env.example .env
```

| Key | Required | Used by | Where it lives |
|---|---|---|---|
| `DEEPGRAM_API_KEY` | yes | streaming speech-to-text | server only |
| `GROQ_API_KEY` | yes | LLM with tool calling | server only |
| `SARVAM_API_KEY` | yes | Sarvam Bulbul v4 Flash TTS | server only |
| `GROQ_MODEL` | no (default `openai/gpt-oss-20b`) | model override | server only |
| `SARVAM_VOICE` | no (default `simran_en_customer`) | TTS persona override | server only |

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
