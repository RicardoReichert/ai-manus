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

**Claw sessions and model selection**: a user may own several Claw sessions (`/api/v1/claw/sessions`,
`ClawSessionDocument`/`claw_sessions` collection — replaces the old 1:1-per-user `Claw`/`claws`
collection). A session picks its model **at creation** (mandatory) and that model is pinned while its
container is live; the only way to change it is `POST /claw/sessions/{id}/restart`, which kills the
current container and starts a fresh one on the new model. Each session gets its own Docker volume
(`ClawSession.volume_name`, mounted at `/home/node/.openclaw` by `DockerClawRuntime.create()`), which
is what makes OpenClaw's own native conversational memory survive that restart — verified directly:
a second model, on a freshly-created container reusing the same volume, correctly recalled
information only ever told to the first, now-destroyed container's model. Expiry (TTL) only stops the
container; the session record and its volume persist until the user explicitly deletes the session
(`DELETE /claw/sessions/{id}`, which also removes the volume — the one operation that actually
discards a session's memory). `openai_routes.py::_resolve_llm_target` resolves the model per-request
from the session that owns the Bearer api_key (now per-session, not per-user), so a restart needs no
config regeneration. In **dev mode** (`CLAW_ADDRESS=claw`, single shared `FixedClawRuntime` container),
every session authenticates with the same fixed `MANUS_API_KEY`, so `claw_service.verify_api_key`
always resolves to a fixed service account rather than the real user — per-session model routing is
only exercisable against a real per-user deployment (`DockerClawRuntime`), not the dev stack; the
volume-per-session mechanism is likewise a `DockerClawRuntime`-only concern (`FixedClawRuntime`'s
`create`/`destroy`/`destroy_volume` are all no-ops, matching its single-shared-container design).

**Python and Docker-in-Docker inside Claw**: `claw/Dockerfile` builds on `ubuntu:24.04` (not the
prebuilt `ghcr.io/openclaw/openclaw` image) with `openclaw` installed via `npm i -g openclaw@<pinned
version>` — the same way any user installs it outside Docker. Python 3 is installed unconditionally
(`python3`/`pip`/`venv`), so OpenClaw's own built-in `exec` tool can already run `.py` scripts with no
plugin changes. Docker Engine (CLI + `dockerd`) is also installed in the image, but only *started* when
`CLAW_DOCKER_IN_DOCKER=true` (`Settings.claw_docker_in_docker`, default `False`) — `DockerClawRuntime`
then also sets `privileged=True` on the container, since `dockerd` needs it to create its own nested
namespaces/cgroups. `entrypoint.sh` starts this nested `dockerd` (storage driver `vfs`) as root, waits
for it, then drops to the unprivileged `node` user to run `openclaw gateway` itself via `sudo -u node`.
**This is the container's own isolated daemon at its own `/var/run/docker.sock` — the host's socket is
never mounted into Claw**, matching OpenClaw's own documented guidance to never give an agent sandbox
the host's Docker socket. Once enabled, no `manus-claw` plugin change is needed: the existing `exec`
tool just finds `docker` on `PATH` and uses it. Known limitation: the nested daemon's `/var/lib/docker`
is not on a persistent volume, so images pulled inside Claw are lost on container restart/TTL expiry —
acceptable for one-off task execution, revisit with a dedicated volume if that turns out to matter.
`privileged: true` is a real container-privilege increase (not host-root like a socket mount, but a
materially larger kernel-facing surface than the default container) — keep it opt-in per deployment.

**Graphical display and VNC in Claw (`CLAW_BROWSER_GUI`)**: The Claw container includes an optional graphical stack
— Xvfb (virtual frame buffer), x11vnc (VNC server), and websockify (WebSocket-to-VNC proxy) — gated by `CLAW_BROWSER_GUI` env var
(`Settings.claw_browser_gui`, default `True` in dev, `False` in production). The `browser` tool itself is enabled
unconditionally in `openclaw.json` (`browser.enabled: true`, `tools.alsoAllow: ["browser"]`) regardless of this flag —
`CLAW_BROWSER_GUI` only toggles `browser.headless` (`false` when on, `true` when off) and whether the Xvfb/x11vnc/websockify
processes start at all. When enabled, each Claw session starts its own display server and a headed (visible, non-headless)
Chrome browser, surfaced to the UI via the Computer panel (live VNC view of the browser, terminal tab, tool-call log, operator
takeover). This trades off memory and CPU per session (roughly 200–400 MB baseline Xvfb + Chrome process overhead) for
immediate visual feedback on agent browsing activity and the ability to manually intervene without breaking the agent's
session. In dev, it's on by default to make agent interaction visible; in production, operators opt-in with
`CLAW_BROWSER_GUI=true` only when interactive debugging is needed, keeping the default footprint lean. Note the Xvfb/x11vnc/
x11-utils and system Chromium packages are baked into the Claw image unconditionally at build time (paid in image size by
every deployment, whether or not the flag is ever turned on) — only their *use* at runtime is gated. No `manus-claw` plugin
changes are required: the plugin reuses OpenClaw's own built-in browser execution, and the graphical layer is orthogonal —
the agent's tool execution works the same way regardless, just with or without a live display behind it.

**Operator terminal and tool-event surfacing**: The Claw panel now exposes two new capabilities. First, `gateway.terminal.enabled`
(a setting in the OpenClaw Gateway config) activates an operator-terminal-backed interactive terminal within the panel, allowing users
to execute shell commands in the agent's environment in real-time — useful for debugging or querying tool state mid-execution.
Second, the backend now surfaces `session.tool` events through the Claw WebSocket (`/api/v1/ws/claw/{session_id}`, distinct from
the Manus Agent's `/api/v1/ws/chat`), piping tool-call activity to the Computer panel's tool-call log: users see each tool
invocation (name, input, output) as the agent executes, making it easy to spot stuck steps or unexpected tool behavior without
hunting through server logs.

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
