# AGENTS.md

> Canonical guide for AI coding agents working on the **AI Manus** codebase.

---

## Project Overview

AI Manus is a general-purpose AI Agent system, comprising four services:

| Service | Stack | Port (dev) | Entry Point |
|---|---|---|---|
| **Frontend** | Vue 3 + TypeScript, Vite 4, Tailwind CSS | 5173 | `frontend/src/main.ts` |
| **Backend** | Python 3.12, FastAPI, LangChain, Beanie/Motor | 8000 | `backend/app/main.py` |
| **Sandbox** | Python 3.10, FastAPI, Xvfb/Chrome/VNC | 8080 (API), 5900 (VNC) | `sandbox/app/main.py` |
| **Mockserver** | Python, FastAPI | 8090 | `mockserver/main.py` |

Infrastructure: **MongoDB 7.0**, **Redis 7.0**, **Docker** (sandbox orchestration).

---

## Directory Structure

```
ai-manus/
├── frontend/          # Vue 3 SPA (Vite, TypeScript, Tailwind)
├── backend/           # FastAPI backend (DDD layout)
│   └── app/
│       ├── domain/           # Models, services, tools, agents, repositories
│       ├── application/      # Application services (auth, agent, file, token, email)
│       ├── infrastructure/   # External integrations (search, browser, sandbox, DB, cache)
│       ├── interfaces/       # API routes, schemas, error handlers, dependencies
│       ├── core/             # Config (config.py)
│       └── main.py
├── sandbox/           # Sandbox service (shell, file, supervisor APIs)
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

**Operator terminal and tool-event surfacing**: The Claw panel exposes two capabilities. First, `gateway.terminal.enabled`
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

Config: `backend/pytest.ini` (`asyncio_mode = auto`, markers: `file_api`, `e2e`).

### Agent Harness E2E + Evals

```bash
# API e2e over the real stack (self-skips if the stack is down)
./dev.sh up -d
cd backend && uv run pytest -m e2e

# Browser e2e (Playwright drives the real UI at localhost:5173)
cd frontend && npx playwright install chromium   # once
cd frontend && npm run test:e2e

# Offline behavioral evals (deterministic, no services needed; exit 1 on failure)
cd backend && uv run python -m evals.run
```

API e2e (`backend/tests/test_e2e_plan_act.py`) drives the chat WebSocket directly; browser e2e (`frontend/e2e/plan-act.spec.ts`) drives the rendered UI as a user. Both replay mockserver scenarios switched via `POST localhost:8090/mock/scenario`. Evals (`backend/evals/`) score PlanActFlow behavior (completion, LLM-call budget, replans, self-repairs, rejections). See `.cursor/skills/harness/SKILL.md`.

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

## AI Coding Loop

The standard working loop for AI agents making changes in this repo:

1. **Scope** — identify the change type and read the matching skill first (see Skills table; harness changes → `.cursor/skills/harness/SKILL.md`, UI parity → `replicate-manus-ui`, docs → `update-docs`).
2. **Implement** — follow Code Conventions; match surrounding style; keep layer boundaries (`domain` ← `infrastructure`, wired in `interfaces/dependencies.py`).
3. **Verify** — run the test pyramid for the affected layers (see Testing Strategy by Change Type). Delegate to the `test-pyramid` subagent to run all layers and get a per-layer failure report.
4. **Guard** — for changes under `backend/app/domain/services` or `domain/models`, run the `harness-reviewer` subagent (read-only) to check the diff against harness invariants and required companion updates. For Manus UI parity work, run the `ui-parity-auditor` subagent before claiming a surface is aligned.
5. **Sync** — update companions in the same change: tests (`backend/tests/`, shared fakes in `tests/harness.py`), eval scenarios (`backend/evals/scenarios.py`), skill docs (invariants in the harness skill), and doc embeds via `.cursor/skills/update-docs/update_doc.sh`.
6. **Ship** — one logical change per commit; verify lint/type-check for frontend changes (`npm run type-check && npm run lint`).

### Subagents (`.cursor/agents/`)

| Subagent | Mode | Use |
|---|---|---|
| `test-pyramid` | read/write | Runs all four automated verification layers (unit → evals → API e2e → browser e2e) and reports per-layer results with failure diagnosis. Use after harness/test/scenario/chat-UI changes. |
| `harness-reviewer` | read-only | Reviews a diff against the harness invariants and the companion-update checklist (tests/evals/skill/mock scenarios). Use before committing `domain/services` changes. |
| `ui-parity-auditor` | read-only | Audits Manus-parity frontend changes against mined official class trees and the 直接抄 rules (`replicate-manus-ui` skill). Use before claiming a surface is aligned; mining itself still needs the user's logged-in Chrome. |

Cursor loads these from `.cursor/agents/*.md` (also compatible with `.claude/agents/`). Invoke explicitly with `/test-pyramid` / `/harness-reviewer`, or let the agent delegate automatically.

### Autonomy Stack (unattended-by-design)

**Lifecycle**: every stage from task intake to regression repair is wired so no human sits in the loop:

| Stage | Automation |
|---|---|
| Task intake | **Features**: file an issue with the `Agent task` template (`.github/ISSUE_TEMPLATE/agent-task.yml`, goal + acceptance criteria, auto-labeled `agent-task`) → a Cursor automation on the label (or an `@cursor` comment) dispatches a Cloud Agent, whose PR closes the issue. Ad-hoc: `@cursor` on any issue/PR, Slack, cursor.com/agents, or the Cloud Agents API |
| Develop | AI Coding Loop (above) + skills; agent commits and opens the PR itself |
| Verify (inner) | L1 `stop` hook — the turn cannot end red |
| Review | L2 guard subagents + platform review bots on the PR |
| Merge gate | L3 CI (`tests.yml`): offline tests + evals, frontend checks, secret scan, docs-drift, full e2e (API + browser + sandbox); branch protection makes green mandatory |
| Dependencies | Dependabot (`.github/dependabot.yml`) opens weekly upgrade PRs for uv (backend/sandbox), npm, pip, Docker base images, and Actions; L3 green + auto-merge lands them unattended |
| Release | `docker-build-and-push.yml` publishes images on merge to `main` and tags (`release` skill covers versioned notes) |

Reproducibility: `backend/uv.lock`, `sandbox/uv.lock` and `frontend/package-lock.json` are committed; CI installs with `uv sync --frozen` / `npm ci`; Dependabot keeps them fresh. Doc embeds are generated (`update_doc.sh`) and drift-gated in CI.

**Remaining human touchpoints** (by design, one-time or judgment-only):
- One-time GitHub setup: branch protection requiring the `Tests` jobs, enabling auto-merge, allowing Actions to create issues; optional Cursor automations for issue → agent dispatch.
- Judgment calls: merging (or enabling auto-merge per PR), product/UX decisions, mining manus.im dumps (needs a logged-in browser), and rotating secrets.

Four gate layers remove the human from the verify-fix loop; each outer layer backstops the inner ones:

| Layer | Mechanism | What it enforces |
|---|---|---|
| L1 — session gate | `.cursor/hooks.json` `stop` hook → `.cursor/hooks/verify_on_stop.py` | The agent cannot end a turn while backend offline tests/evals or frontend unit tests fail for areas touched by **unpushed** work (uncommitted + commits ahead of `@{upstream}`). Once pushed, CI owns verification and the gate passes in milliseconds. Failures come back as an auto follow-up with the failure tail (max 3 loops). Fail-open on missing env — environment problems must not trap the agent. |
| L2 — guard subagents | `.cursor/agents/` (`test-pyramid`, `harness-reviewer`, `ui-parity-auditor`) | Heavy verification (e2e layers) and semantic review (invariants, UI parity) on demand, per the AI Coding Loop. |
| L3 — CI hard gate | `.github/workflows/tests.yml` | Every push/PR to `main`/`develop` runs backend offline tests + evals, frontend unit/type-check/lint/build, gitleaks secret scan, docs-drift, and full-stack e2e (API + browser + sandbox API tests) against the dev compose stack. |
| L4 — platform | Branch protection + review bots (one-time human setup on GitHub/Cursor) | PRs merge only when L3 is green; automated review comments feed back into agent runs. |

Offline test selection is exclusion-based (`--ignore` the three server-dependent files + `-m "not e2e"`) and must stay in sync across the hook, the `test-pyramid` subagent, and CI.

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
| Agent harness (`domain/services` flows/agents/prompts/tools) | Offline: `uv run pytest tests/test_plan_act_flow.py tests/test_context_engineering.py tests/test_single_loop_manus.py` + `uv run python -m evals.run`; full stack: `uv run pytest -m e2e` + `cd frontend && npm run test:e2e` |
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
| `.cursor/skills/harness/SKILL.md` | Changing the agent framework (`backend/app/domain/services`: flows, agents, prompts, tools, events). File map, invariants, extension recipes, offline test harness (`backend/tests/harness.py`) and mockserver scenarios. |
| `.cursor/skills/manus-official-cdp/SKILL.md` | Logged-in manus.im over Chrome CDP via Default-profile `session_id` (inject / verify / geo `/unavailable`); use before replicate-manus-ui capture. |
| `.cursor/skills/replicate-manus-ui/SKILL.md` | Align frontend UI with manus.im (mine official JS/DOM; Computer / sidebar / Library / Project / Search / chat chrome parity). |
| `.cursor/skills/update-docs/SKILL.md` | Sync compose/env embeds + README demos via `.cursor/skills/update-docs/update_doc.sh` (not docs/demo.md scenarios). |
| `.cursor/skills/demo-videos/SKILL.md` | Recording/uploading README demo MP4s (`tmp/videos` + `gh image` + `docs/demos.yml`; never commit binaries; publish only after user confirmation). |
| `.cursor/skills/release/SKILL.md` | Cutting `vX.Y.Z` GitHub releases (bilingual notes like v2.4.0/v2.5.0; no demo-videos-* releases). |

Personal (not in repo): `~/.cursor/skills/telegram-screenshots/SKILL.md` — UI screenshots → Telegram Bot MCP.
