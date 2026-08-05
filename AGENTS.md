# AGENTS.md

> Canonical guide for AI coding agents working on the **AI Manus × Claw** codebase.

---

## Project Overview

AI Manus × Claw is a general-purpose AI Agent system with an integrated [OpenClaw](https://github.com/anthropics/openclaw) AI assistant, comprising five services:

| Service | Stack | Port (dev) | Entry Point |
|---|---|---|---|
| **Frontend** | Vue 3 + TypeScript, Vite 4, Tailwind CSS | 5173 | `frontend/src/main.ts` |
| **Backend** | Python 3.12, FastAPI, LangChain, Beanie/Motor | 8000 | `backend/app/main.py` |
| **Sandbox** | Python 3.10, FastAPI, Xvfb/Chrome/VNC | 8080 (API), 5900 (VNC) | `sandbox/app/main.py` |
| **Claw** | Node.js, OpenClaw Gateway, manus-claw plugin | 18788 | `claw/entrypoint.sh` |
| **Mockserver** | Python, FastAPI | 8090 | `mockserver/main.py` |

Infrastructure: **MongoDB 7.0**, **Redis 7.0**, **Docker** (sandbox & Claw orchestration).

---

## Directory Structure

```
ai-manus/
├── frontend/          # Vue 3 SPA (Vite, TypeScript, Tailwind)
├── backend/           # FastAPI backend (DDD layout)
│   └── app/
│       ├── domain/           # Models, services, tools, agents, repositories
│       ├── application/      # Application services (auth, agent, file, token, email, claw)
│       ├── infrastructure/   # External integrations (search, browser, sandbox, claw, DB, cache)
│       ├── interfaces/       # API routes, schemas, error handlers, dependencies
│       ├── core/             # Config (config.py)
│       └── main.py
├── sandbox/           # Sandbox service (shell, file, supervisor APIs)
├── claw/              # Claw service (OpenClaw Gateway + manus-claw plugin)
│   └── manus-claw/   # Node.js plugin bridging OpenClaw with Manus backend
├── mockserver/        # Mock LLM server for dev/testing
├── docs/              # Docsify documentation site
├── .cursor/skills/    # Cursor agent skills
├── dev.sh             # Shortcut: docker compose -f docker-compose-development.yml ...
├── run.sh             # Shortcut: docker compose -f docker-compose.yml ...
├── build.sh           # docker buildx bake
├── .env.example       # Environment variable template
├── docker-compose.yml                # Production compose
└── docker-compose-development.yml    # Development compose (hot-reload)
```

---

## Development Environment Setup

### Prerequisites

- **Docker 20.10+** and **Docker Compose**
- **uv** (Python package manager) — for running backend/sandbox outside Docker
- **Node.js / npm** — for running frontend outside Docker
- **Python 3.12+** (backend), **Python 3.10+** (sandbox)

### Quick Start (Docker Compose — Recommended)

```bash
cp .env.example .env
# Edit .env — at minimum set API_KEY to any non-empty string
./dev.sh up -d
```

This starts: frontend (5173), backend (8000), sandbox (8080), mockserver (8090), MongoDB (27017), Redis.

### Key `.env` Values for Development

| Variable | Recommended Value | Purpose |
|---|---|---|
| `AUTH_PROVIDER` | `none` | Skip authentication entirely |
| `API_BASE` | `http://mockserver:8090/v1` | Use mock LLM server |
| `API_KEY` | any non-empty string | Required — set to anything with mockserver |
| `SEARCH_PROVIDER` | `bing_web` | No API key needed |
| `SANDBOX_ADDRESS` | `sandbox` | Use single dev sandbox container |
| `LOG_LEVEL` | `DEBUG` | Verbose logging |

### Model Registry (Settings > Models)

Selectable LLMs (OpenAI, Google Gemini, LM Studio, Ollama, OpenRouter, …) live in MongoDB
(`ModelConfigDocument`), managed by an admin through **Settings > Models** — not through a
mounted file. Provider credentials are encrypted at rest with Fernet
(`backend/app/infrastructure/security/secret_box.py`).

| Variable | Required | Purpose |
|---|---|---|
| `MODEL_ENCRYPTION_KEY` | Yes, to store/read any credential | Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. No default — rotating it makes stored credentials unreadable, so an operator must set it deliberately. Local models with no credential (LM Studio, Ollama) work without it. |

**Upgrading an existing deployment** (one that relied on the old `models.json` + `MODEL_NAME`/`API_KEY`
registry): the database starts empty, so run the one-time importer before the model dropdown will
show anything:

```bash
docker compose -f docker-compose-development.yml exec backend uv run python -m scripts.import_models
# --dry-run to preview first
```

It reads `MODELS_CONFIG_PATH` (default `/etc/models.json`, see `models.json.example`) plus the
global `MODEL_NAME`/`MODEL_PROVIDER`/`API_KEY`, and is idempotent — safe to re-run.

**Capabilities and tool profiles.** Registering a model auto-detects capabilities from a built-in
catalog (`infrastructure/external/llm/model_catalog.py`) — known small models (Qwen3-4B, Gemma 4
E4B, Phi-4-Mini) get a reduced tool budget and, when their profile is set to `lean`, browsing is
delegated to an isolated sub-agent (`domain/services/agents/web.py`) instead of exposing the
12-tool browser toolkit directly — the mechanism that keeps small models usable without losing
functionality on large ones. Large/unrecognized hosted models default to full capability
(no behavior change). See `domain/services/tools/profiles.py` for the `full`/`lean` definitions.

**Claw model selection**: `PATCH /api/v1/claw/model` sets which registered model a user's Claw talks
to (`ClawDocument.claw_model_id`); resolved per-request in `openai_routes.py`, so switching needs no
container restart. In **dev mode** (`CLAW_ADDRESS=claw`, single shared container), every user
authenticates with the same fixed `MANUS_API_KEY`, so `claw_service.verify_api_key` always resolves
to a fixed service account rather than the real user — per-user model routing is only exercisable
against a real per-user deployment (`DockerClawRuntime`), not the dev stack.

### Running Services Individually (Without Docker)

**Backend:**
```bash
cd backend
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Requires running MongoDB and Redis. Requires `API_KEY` env var (or `.env` in `backend/`).

**Frontend:**
```bash
cd frontend
npm install
BACKEND_URL=http://localhost:8000 npm run dev
```
The Vite config creates a proxy for `/api` when `BACKEND_URL` is set.

**Sandbox:** Typically Docker-only (requires Xvfb, Chrome, VNC, supervisord).

**Mockserver:**
```bash
cd mockserver
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8090 --reload
```

---

## Testing

### Backend Tests (pytest — integration-style)

Tests live in `backend/tests/` and hit a **running** backend at `http://localhost:8000`.

```bash
# Ensure backend + MongoDB + Redis are running
./dev.sh up -d mongodb redis backend

cd backend
uv run pytest                               # all tests
uv run pytest tests/test_auth_routes.py     # specific file
uv run pytest -m file_api                   # by marker
```

Key test files:
- `tests/test_auth_routes.py` — auth endpoints
- `tests/test_api_file.py` — file upload/download
- `tests/test_sandbox_file.py` — sandbox file operations

Config: `backend/pytest.ini` (`asyncio_mode = auto`, markers: `file_api`).

### Sandbox Tests (pytest)

```bash
./dev.sh up -d sandbox
cd sandbox
uv run pytest
```

### Frontend (Vitest)

```bash
cd frontend
npm run test          # Vitest unit tests (src/**/*.spec.ts)
npm run type-check    # vue-tsc type checking
npm run lint          # ESLint (flat config, eslint.config.js)
npm run build         # production build (catches TS + template errors)
```

For manual UI testing: start full dev stack (`./dev.sh up -d`), open `http://localhost:5173`.

### Mockserver

No tests. Verify with:
```bash
curl -X POST http://localhost:8090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"mock","messages":[{"role":"user","content":"hi"}]}'
```

### Full-Stack Integration Test

1. `./dev.sh up -d` — start all services
2. Open `http://localhost:5173`
3. Login (or bypass with `AUTH_PROVIDER=none`)
4. Create session, send message — mockserver returns canned tool calls
5. Check logs: `./dev.sh logs -f backend`
6. Check VNC at `localhost:5902` for sandbox desktop

---

## Code Conventions

### Backend (Python)

- **DDD architecture**: `domain/` → `application/` → `infrastructure/` → `interfaces/`
- **FastAPI** with **Pydantic v2** models and settings
- **Beanie** ODM for MongoDB documents (`infrastructure/models/documents.py`)
- **Redis** for caching and message queues
- Dependency management: **uv** + `pyproject.toml` (PEP 621)
- No enforced linter/formatter (no Ruff, Black, or Flake8 configured)
- Async-first: use `async def` for route handlers and service methods

### Frontend (TypeScript / Vue)

- **Vue 3 Composition API** with `<script setup lang="ts">`
- **TypeScript** throughout
- **Tailwind CSS** for styling, **reka-ui** component library
- Path alias: `@/` → `src/`
- **vue-i18n** for internationalization (Chinese + English)
- Dependency management: **npm** + `package.json`
- **ESLint** configured (`npm run lint`); no Prettier
- **Vitest** + @vue/test-utils for unit tests (`npm run test`)

### Sandbox (Python)

- **FastAPI** service exposing shell, file, and supervisor APIs
- Runs inside Docker with **supervisord** managing Chrome, Xvfb, VNC, and the API
- Dependency management: **uv** + `pyproject.toml`

---

## CI/CD

Single GitHub Actions workflow: `.github/workflows/docker-build-and-push.yml`

- **Triggers**: push/PR to `main` and `develop`; tags `v*`
- **Builds**: matrix of `frontend`, `backend`, `sandbox` Docker images for `linux/amd64` and `linux/arm64`
- **Pushes** to Docker Hub on non-PR events (requires `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` secrets)
- **No** automated test or lint steps in CI

---

## Cursor Cloud Specific Instructions

### Environment Setup

When running in a Cloud Agent environment:

1. Docker may not be available. If Docker commands fail, focus on running individual services or testing code changes without the full stack.
2. For backend work, install dependencies with `cd backend && uv sync`.
3. For frontend work, install dependencies with `cd frontend && npm install`.
4. Set `AUTH_PROVIDER=none` and `API_KEY=test` in `.env` to bypass auth and LLM requirements.

### Testing Strategy by Change Type

| Change Type | Testing Approach |
|---|---|
| Backend Python logic | `cd backend && uv run pytest` (needs running backend + MongoDB + Redis) |
| Backend API routes | `cd backend && uv run pytest` against running server |
| Frontend Vue/TS | `cd frontend && npm run test && npm run type-check && npm run lint && npm run build` |
| Frontend UI changes | Type-check + build + manual GUI testing via `computerUse` subagent |
| Sandbox changes | `cd sandbox && uv run pytest` |
| Config / env changes | Verify with `./dev.sh up -d` and check service logs |
| Documentation / README | No testing needed |

### Debugging the Backend

The dev compose starts the backend with **debugpy** on port `5678`. Attach a remote Python debugger for step-through debugging.

### Resetting State

- MongoDB data persists in volume `manus-mongodb-data`. Wipe with `./dev.sh down -v`.
- Mockserver tracks response index; restart to reset: `./dev.sh restart mockserver`.

---

## Skills

| Skill File | When to Use |
|---|---|
| `.cursor/skills/starter.md` | Setting up, running, or testing any part of the codebase. Contains detailed API reference, env var tables, and testing workflows. |
| `.cursor/skills/replicate-manus-ui/SKILL.md` | Align frontend UI with manus.im (mine official JS/DOM; Computer / sidebar / Library / Project / Search / chat chrome parity). |
| `.cursor/skills/update-docs/SKILL.md` | Sync compose/env embeds + README demos via `.cursor/skills/update-docs/update_doc.sh` (not docs/demo.md scenarios). |
| `.cursor/skills/demo-videos/SKILL.md` | Recording/uploading README demo MP4s (`tmp/videos` + `gh image` + `docs/demos.yml`; never commit binaries; publish only after user confirmation). |
| `.cursor/skills/release/SKILL.md` | Cutting `vX.Y.Z` GitHub releases (bilingual notes like v2.4.0/v2.5.0; no demo-videos-* releases). |
| `.cursor/skills/debug-claw/SKILL.md` | Debugging OpenClaw / Claw chat, history, uploads, WebSocket, containers. |

Personal (not in repo): `~/.cursor/skills/telegram-screenshots/SKILL.md` — UI screenshots → Telegram Bot MCP, not OpenClaw.
