# Manus Claw Computer Panel (VNC + Tool Log + Interactive Terminal) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks are **sequential and dependent** — later tasks build on files earlier tasks change. Never dispatch implementers in parallel.

**Goal:** Add a right-side panel to Manus Claw's chat page (`ClawPage.vue`), mirroring the Manus Agent's "Computer" panel: a live VNC view of the agent's browser, a live log of tool calls, and an interactive terminal the user can type into ("take control").

**Architecture:** Two independent capabilities layered onto Claw's existing headless container: (A) an opt-in graphical stack (Xvfb + headed Chrome via OpenClaw's own `browser` tool + x11vnc + websockify), proxied to the frontend exactly like the Manus Agent's sandbox VNC (`backend/app/interfaces/api/ws_routes.py::vnc_ws`, `frontend/src/components/VNCViewer.vue`); (B) OpenClaw's native, already-built gateway features — the `session.tool` event stream and the Operator Terminal RPCs (`terminal.open/input/resize/close` + `terminal.data/exit`) — bridged through `claw/manus-claw/`'s existing HTTP/SSE layer to the Manus backend and frontend.

**Tech Stack:** Docker (Xvfb/x11vnc/websockify), Node.js (`claw/manus-claw/` plugin — the gateway bridge), FastAPI WebSocket proxy routes (Python), Vue 3 + `@novnc/novnc` + `@xterm/xterm` (frontend, reusing existing Computer-panel components where possible).

## Global Constraints

- **Never modify** `frontend/src/pages/ChatPage.vue`, `frontend/src/components/ComputerPanel.vue`, `ComputerPanelContent.vue`, `VNCViewer.vue`, `TakeOverView.vue`, `toolViews/BrowserToolView.vue`, `toolViews/ShellToolView.vue` in a way that changes Manus Agent behavior — read them for reference/reuse, copy patterns into new Claw-specific files, do not repurpose the originals to also serve Claw unless a task explicitly says to add a generic parameter (and even then, default behavior for the Manus Agent must stay byte-identical).
- **Opt-in flag**: the graphical stack (Xvfb/Chrome/x11vnc/websockify) is gated behind a new env var `CLAW_BROWSER_GUI` (default `"false"`), exactly the precedent set by `CLAW_DOCKER_IN_DOCKER`. The tool-log + terminal capability (no GUI) is **not** gated — it's always on once wired, since it's lightweight (no extra Chrome/Xvfb process).
- **VNC auth model**: match the Manus Agent exactly — no VNC password (`-nopw`), no server-side VNC protocol parsing, auth happens entirely at the Manus backend's WebSocket layer (Cookie/Bearer via `resolve_ws_user`, already used by every other Claw WS route in `ws_routes.py`). `x11vnc` must run with `-shared` so both the read-only panel view and an interactive takeover view can attach to the same session concurrently, exactly like the sandbox.
- **No new Python dependencies** — the VNC proxy route reuses the exact `websockets` binary-forwarding pattern already in `ws_routes.py::vnc_ws` (lines 645-713); the terminal proxy route follows the same shape.
- **Frontend conventions**: `<script setup lang="ts">`, `@/` path alias, i18n keys added to both `frontend/src/locales/en.ts` and `pt.ts` (this repo's two active locales — check `zh.ts` too and add there for parity if it's still actively maintained, confirm by checking whether recent PRs touched it).
- Run `cd frontend && npm run type-check && npm run lint && npm test` after every frontend task; run backend tests (`cd backend && uv run pytest`) after every backend task, matching this repo's established per-task verification discipline.

---

### Task 1: Fix plugin ownership bug + confirm gateway pre-conditions

**Files:**
- Modify: `claw/entrypoint.sh`

**Interfaces:**
- Produces: a `manus-claw` plugin directory that OpenClaw's loader trusts (root-owned), and a written record (in the task report) of the exact `session.tool` event payload shape and the plugin's gateway connection operator scope — later tasks depend on these facts, not assumptions.

- [ ] **Step 1:** In `claw/entrypoint.sh`, immediately after the existing line `chown -R node:node "${CONFIG_DIR}"` (around line 115), add a line that restores root ownership specifically for the plugin extensions directory, e.g.:
  ```bash
  chown -R node:node "${CONFIG_DIR}"
  # OpenClaw's plugin loader only trusts root-owned plugin directories —
  # the blanket chown above (needed so the `node` user can write config)
  # otherwise flags manus-claw as "blocked plugin candidate: suspicious
  # ownership" (confirmed live via `openclaw sandbox explain`).
  chown -R root:root "${CONFIG_DIR}/extensions"
  ```
  Read the surrounding ~20 lines of `entrypoint.sh` first to place this correctly relative to when the extensions directory actually exists (it's written earlier in the script — confirm the exact line before this chown, and confirm nothing after this point in the script needs to further write into `extensions` as the `node` user, which would break again).
- [ ] **Step 2:** Rebuild the Claw image and bring up the dev container: `cd /home/coegi/ai-manus && ./dev.sh build claw && ./dev.sh up -d claw`.
- [ ] **Step 3:** Verify the fix: `docker exec ai-manus-claw-1 sh -c "HOME=/home/node openclaw sandbox explain"` — confirm the `Config warnings` section no longer mentions `manus-claw` / `suspicious ownership`. If it still does, the chown ordering is wrong — investigate and fix before proceeding (do not move to later tasks with this warning still present, since Task 5's terminal RPCs depend on the plugin being trusted).
- [ ] **Step 4:** Confirm sandbox mode is still `mode: off` in the same output (should be unaffected by this change, just re-confirm).
- [ ] **Step 5:** Investigate the real `session.tool` event shape. Read `claw/manus-claw/src/gateway-bridge.js` in full first to understand how it currently subscribes to gateway events (`_handleAgentEvent`, the `stream` field switch). Then, with a live Claw session, either (a) add a temporary `console.log(JSON.stringify(payload))` inside `_handleAgentEvent` for any `stream` value not already handled, rebuild, trigger a Claw chat message that causes a tool call (e.g. ask it to run a shell command), and read `docker logs ai-manus-claw-1` to capture the real payload — or (b) if you can locate the emitting code in `/usr/lib/node_modules/openclaw/dist/*.js` inside the container (grep for `'session.tool'` or `session\.tool`), read it directly to get the exact field names without needing a live trigger. Either way, **remove any temporary debug logging before finishing this task** — this step is investigation only, not a permanent change.
- [ ] **Step 6:** Investigate the plugin's gateway connection scope. Read whatever file in `claw/manus-claw/src/` establishes the plugin's own connection/session to the OpenClaw gateway (likely `gateway-bridge.js` itself, or a connection-setup file it imports). Determine whether that connection already authenticates as an `operator` role with `operator.admin` scope (or how it would need to, e.g. via `gateway.terminal.enabled: true` plus the plugin's existing trusted in-process registration). Write down what you find — Task 5 needs it to know whether new pairing/config is required.
- [ ] **Step 7:** Write a report to `.superpowers/sdd/2026-08-07-claw-computer-panel/task-1-report.md` (the SDD workspace path — create the directory if this is the very first task) with: the exact `session.tool` payload shape (field names, example JSON), the plugin's confirmed operator scope, and confirmation the ownership fix holds. This report is required reading for Tasks 4 and 5.
- [ ] **Step 8:** Commit: `git add claw/entrypoint.sh && git commit -m "fix(claw): restore root ownership of the plugin extensions dir so OpenClaw trusts it"`

---

### Task 2: Graphical stack in the Claw container (opt-in)

**Files:**
- Modify: `claw/Dockerfile`
- Modify: `claw/entrypoint.sh`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/infrastructure/external/claw/docker_claw_runtime.py`
- Modify: `docker-compose-development.yml`

**Interfaces:**
- Consumes: Task 1's confirmation that the container/plugin setup is sound.
- Produces: a Claw container that, when `CLAW_BROWSER_GUI=true`, runs Xvfb on `:1`, exposes a websockify VNC-over-WS endpoint on port 5901, and configures OpenClaw's `browser` tool to render into that display. Later tasks (backend VNC proxy, frontend VNC view) depend on this port/URL existing.

- [ ] **Step 1:** Read `sandbox/Dockerfile` in full to see the exact apt packages and versions used for `xvfb`, `x11vnc`, `websockify` there (reuse the same versions/install pattern for consistency, don't invent a different one).
- [ ] **Step 2:** In `claw/Dockerfile`, add `xvfb`, `x11vnc`, and `websockify` to the apt-get install list (alongside the existing curl/git/sudo/python3 etc. — read the current Dockerfile first to find the right install block). Do **not** add a separate Chromium package — confirm first whether OpenClaw's `browser` tool plugin already bundles/downloads its own Chromium via Playwright (check `node_modules/playwright-core` inside the already-built image, or the `openclaw browser doctor` output) before deciding; only add a system Chromium package if the OpenClaw-managed one genuinely isn't sufficient, and note that decision in the task report.
- [ ] **Step 3:** In `claw/entrypoint.sh`, add a new conditional block (mirroring the existing `CLAW_DOCKER_IN_DOCKER` dockerd block in both structure and shutdown-handler integration — read that block first and copy its shape) that, when `CLAW_BROWSER_GUI=true`:
  1. Starts `Xvfb :1 -screen 0 1280x1024x24 &` and records its PID.
  2. Waits briefly / polls for the display to be ready (mirror how the DinD block waits for `docker version` to succeed, adapt to `xdpyinfo -display :1` or similar).
  3. Starts `x11vnc -display :1 -nopw -shared -listen 0.0.0.0 -forever -rfbport 5900 &` and records its PID.
  4. Starts `websockify 0.0.0.0:5901 localhost:5900 &` and records its PID.
  5. Adds all three PIDs to the existing shutdown-handler's kill list (read how `DOCKERD_PID` is handled there and follow the same pattern).
  Set `DISPLAY=:1` in the environment before starting `openclaw gateway` (the `sudo -H -u node openclaw gateway &` line) so any browser process OpenClaw's `browser` tool launches inherits it and renders into Xvfb.
- [ ] **Step 4:** In the `openclaw.json` generation block in `entrypoint.sh` (read it first to find the exact JSON structure being built), add:
  - `browser: { enabled: true, headless: <"false" if CLAW_BROWSER_GUI else "true"> }` (as a real JSON boolean, not a string — check how other booleans are injected in this script, e.g. how `CLAW_DOCKER_IN_DOCKER` becomes a JSON value).
  - `tools: { alsoAllow: ["browser"] }` (merge with any existing `tools` key rather than overwriting it — check first if one exists).
  - `gateway: { terminal: { enabled: true } }` — unconditional, not tied to `CLAW_BROWSER_GUI`.
- [ ] **Step 5:** `backend/app/core/config.py`: add `claw_browser_gui: bool = False` (follow the exact pattern of the existing `claw_docker_in_docker: bool = False` setting — same docstring style).
- [ ] **Step 6:** `backend/app/infrastructure/external/claw/docker_claw_runtime.py`: in `create()`'s `container_config["environment"]` dict, add `"CLAW_BROWSER_GUI": "true" if self.settings.claw_browser_gui else "false"` (same pattern as the existing `CLAW_DOCKER_IN_DOCKER` line right above it). This flag does **not** need `privileged: True` (Xvfb/x11vnc/websockify need no special container privileges, unlike DinD's nested dockerd) — do not add privileged mode for this flag.
- [ ] **Step 7:** `docker-compose-development.yml`: add `CLAW_BROWSER_GUI=${CLAW_BROWSER_GUI:-true}` to the `claw` service's environment (default true in **dev only**, matching how `CLAW_DOCKER_IN_DOCKER` defaults true in dev — read that exact line and mirror it).
- [ ] **Step 8:** Rebuild (`./dev.sh build claw && ./dev.sh up -d claw`) and verify: `docker exec ai-manus-claw-1 sh -c "ps aux | grep -E 'Xvfb|x11vnc|websockify'"` shows all three running. `docker exec ai-manus-claw-1 sh -c "netstat -tlnp 2>/dev/null | grep 5901"` (or `ss -tlnp`) confirms websockify is listening.
- [ ] **Step 9:** Commit: `git add claw/Dockerfile claw/entrypoint.sh backend/app/core/config.py backend/app/infrastructure/external/claw/docker_claw_runtime.py docker-compose-development.yml && git commit -m "feat(claw): opt-in graphical stack (Xvfb+x11vnc+websockify) for live browser VNC"`

---

### Task 3: Expose Claw's VNC URL through the backend service layer

**Files:**
- Modify: `backend/app/domain/services/claw_domain_service.py`
- Modify: `backend/app/application/services/claw_service.py`
- Read for the pattern: `backend/app/infrastructure/external/sandbox/docker_sandbox.py` (the `self._vnc_url = f"ws://{self.ip}:5901"` line), `backend/app/application/services/agent_service.py::get_vnc_url` (lines ~383-400)

**Interfaces:**
- Consumes: Task 2's container now listening on port 5901 when `CLAW_BROWSER_GUI` is on.
- Produces: `claw_service.get_vnc_url(session_id: str, user_id: str) -> str`, returning `f"ws://{session.container_ip}:5901"`. Task 5 (backend WS proxy route) calls this directly.

- [ ] **Step 1:** Read `backend/app/domain/services/claw_domain_service.py` in full to find where `session.container_ip` is set (`docker_domain_service.py:145` per earlier investigation) and how the Claw HTTP `base_url` is currently constructed from it (there should be an existing pattern building `f"http://{container_ip}:<port>"` for the gateway's own HTTP API — find and reuse that exact style).
- [ ] **Step 2:** Add a method (domain service or directly in `claw_service.py`, whichever layer the existing `base_url` construction already lives in — follow that precedent) `get_vnc_url(session_id: str, user_id: str) -> str` that: looks up the session (raising/returning appropriately if not found or not owned by `user_id`, matching how other Claw session lookups in this file handle ownership), and returns `f"ws://{session.container_ip}:5901"`.
- [ ] **Step 3:** If `FixedClawRuntime` (dev shared-container mode) is also in scope for this feature (check `backend/app/infrastructure/external/claw/fixed_claw_runtime.py` — does it also expose a container IP the same way, or does it use a fixed hostname like `CLAW_ADDRESS=claw`?), make sure `get_vnc_url` works for both runtimes. If `FixedClawRuntime` uses a fixed DNS name instead of a per-container IP, use that hostname instead of `container_ip` when running in that mode — read `claw_domain_service.py`'s existing runtime-selection logic to see how it already branches between the two runtimes for other operations, and follow the same branch structure.
- [ ] **Step 4:** Write a unit test `backend/tests/test_claw_vnc_url.py` (new file) mocking the session repository, covering: returns the expected `ws://` URL for a valid owned session; raises/returns an error for a session not owned by the caller (mirror the auth-check test style already used in `backend/tests/test_claw_shared_container_model_resolution.py` from earlier in this session, if that file still exists — read it for the mocking convention).
- [ ] **Step 5:** Run `cd backend && set -a && source ../.env && set +a && uv run pytest tests/test_claw_vnc_url.py -v` — confirm passing, then the full suite to confirm baseline unchanged (16 pre-existing unrelated failures is the known baseline from earlier this session — confirm that count hasn't changed).
- [ ] **Step 6:** Commit: `git add backend/app/domain/services/claw_domain_service.py backend/app/application/services/claw_service.py backend/tests/test_claw_vnc_url.py && git commit -m "feat(claw): expose get_vnc_url on the Claw service layer"`

---

### Task 4: Backend WebSocket proxy route for Claw VNC

**Files:**
- Modify: `backend/app/interfaces/api/ws_routes.py`

**Interfaces:**
- Consumes: Task 3's `claw_service.get_vnc_url()`.
- Produces: `@router.websocket("/claw/vnc/{session_id}")`, the exact URL the frontend's Claw VNC viewer (Task 9) will connect to.

- [ ] **Step 1:** Read the existing `vnc_ws` route (lines 645-713 of `ws_routes.py`, already in this plan's context above) and the existing `/claw/{session_id}` chat route directly above it (for the Claw-specific auth/session-lookup pattern — it uses `claw_service` rather than `agent_service`).
- [ ] **Step 2:** Add a new route `@router.websocket("/claw/vnc/{session_id}")` that follows `vnc_ws`'s exact structure (auth via `resolve_ws_user`, accept with `subprotocol="binary"`, open an outbound `websockets.connect()` to the target, two concurrent forward tasks raced with `asyncio.wait(..., FIRST_COMPLETED)`, same error handling/close codes) but: looks up the session via `claw_service` (confirming ownership the same way the existing `/claw/{session_id}` route does, not via `agent_service`), and gets the target URL via `claw_service.get_vnc_url(session_id, user.id)` from Task 3 instead of `agent_service.get_vnc_url`.
- [ ] **Step 3:** Do not duplicate the forwarding logic as a copy-pasted pair of closures if it can reasonably be shared — but only extract a shared helper if doing so is a clean, obvious refactor; if the existing `vnc_ws` closures are tightly coupled to its own local variable names, a second near-identical pair of closures in the new route is acceptable (note this either way in the report — do not force an awkward abstraction under time pressure).
- [ ] **Step 4:** Manual verification (no unit test for a raw WS byte-forwarding proxy — mirror the fact that `vnc_ws` itself has no dedicated test in this codebase): with `CLAW_BROWSER_GUI=true` and a running Claw session, use a WS client (e.g. a short Python script with `websockets`, or the browser via Task 9 once it exists) to connect to `ws://localhost:8000/api/v1/ws/claw/vnc/{session_id}` and confirm bytes flow both ways without immediate close. If Task 9 isn't done yet, defer full end-to-end verification to this plan's final Verification section and just confirm the route accepts a connection and doesn't error on the Python side for now.
- [ ] **Step 5:** Commit: `git add backend/app/interfaces/api/ws_routes.py && git commit -m "feat(claw): backend VNC proxy route for Claw sessions"`

---

### Task 5: Operator Terminal + tool-event bridge in the Claw plugin

**Files:**
- Modify: `claw/manus-claw/src/gateway-bridge.js`
- Modify: `claw/manus-claw/src/http-server.js`

**Interfaces:**
- Consumes: Task 1's report — **corrected finding, read carefully**: there
  is no literal `session.tool` stream on manus-claw's own connection.
  Tool events for its own agent runs arrive as ordinary `event:'agent'`
  messages (the same envelope `assistant`/`lifecycle` already use) with
  `payload.stream === 'tool'` — phases `start`/`update`/`result`, fields
  `name`, `toolCallId`, `args`/`partialResult`/`result`, `isError`,
  `meta`. Also confirmed: `gateway-client.js` already connects with
  `role:'operator'`, `scopes:['operator.admin','operator.read','operator.write']`,
  `caps:['tool-events']` — **already sufficient for the terminal RPCs
  below, no new pairing/config needed.**
- Produces: (a) a new SSE event `{"type": "tool", ...}` on the existing `/chat` stream, carrying tool-call data; (b) new HTTP/WS endpoints `POST /terminal/open` and a WS (or equivalent bidirectional) endpoint for `terminal.input`/`terminal.resize` in, `terminal.data`/`terminal.exit` out. Task 6 (backend terminal proxy route) and the tool-event passthrough in Task 7 depend on these exact shapes.

- [ ] **Step 1:** Read Task 1's report file first for the full evidence behind the corrected `stream:'tool'` finding above (it includes real captured JSON) — this task's Step 3 must match that real shape, not the plan's original `session.tool` assumption.
- [ ] **Step 2:** Read `claw/manus-claw/src/gateway-bridge.js` in full (already partially described in this plan's Context section: `_handleAgentEvent` currently only handles `stream === 'assistant'` and `stream === 'lifecycle'`, lines ~99-156). This is the exact same switch to extend — `stream === 'tool'` is a third branch alongside the existing two, not a separate subscription mechanism.
- [ ] **Step 3:** Add a branch handling `stream === 'tool'` that extracts `name`/`toolCallId`/`args`/`partialResult`/`result`/`isError`/`meta` per the phase (`start`/`update`/`result`) and forwards it to whatever mechanism `http-server.js` uses to push SSE events (read `_handleChat`/the SSE-writing code in `http-server.js` to find the existing pattern for `chunk`/`file`/`done`/`error` events and follow it exactly), emitting `{"type": "tool", "phase": ..., "name": ..., "toolCallId": ..., ...}` (adapt exact field names/shape to Task 1's captured JSON, not this summary).
- [ ] **Step 4:** In `claw/manus-claw/src/http-server.js`, add `POST /terminal/open`: calls the gateway's `terminal.open` operator RPC using the same already-authenticated `gateway-client.js` connection (confirmed sufficient scope per Task 1 — no re-pairing step needed) for the current agent/session, returns the resulting terminal session id to the caller.
- [ ] **Step 5:** Add a WS endpoint (e.g. `/terminal/{terminalSessionId}`) that: on client message, calls `terminal.input`/`terminal.resize` RPCs with the client's payload; on `terminal.data`/`terminal.exit` events from the gateway (scoped to this terminal session), forwards them out to the connected WS client. Handle `terminal.exit` by closing the WS cleanly.
- [ ] **Step 6:** Manual verification: rebuild the Claw image, start a session, `curl -X POST http://localhost:<claw-port>/terminal/open` (or via `docker exec` from inside the container hitting `localhost`) and confirm a terminal session id comes back, not an error. If a WS testing tool is available, connect and send a trivial command (e.g. `echo hi\n`), confirm `terminal.data` output arrives.
- [ ] **Step 7:** Write a report to `.superpowers/sdd/2026-08-07-claw-computer-panel/task-5-report.md` documenting the exact request/response shapes of the new endpoints — Task 6 needs this to build an accurate backend proxy.
- [ ] **Step 8:** Commit: `git add claw/manus-claw/src/gateway-bridge.js claw/manus-claw/src/http-server.js && git commit -m "feat(claw-plugin): bridge session.tool events and Operator Terminal RPCs to HTTP/SSE"`

---

### Task 6: Backend WebSocket proxy route for the Claw terminal

**Files:**
- Modify: `backend/app/interfaces/api/ws_routes.py`
- Modify: `backend/app/infrastructure/external/claw/http_claw_client.py` (or wherever the Claw base URL / HTTP client living for this session is constructed — check `claw_service.py` first)

**Interfaces:**
- Consumes: Task 5's report (exact request/response shapes of `/terminal/open` and the terminal WS endpoint).
- Produces: `@router.websocket("/claw/terminal/{session_id}")`, the endpoint Task 10 (frontend terminal component) connects to.

- [ ] **Step 1:** Read Task 5's report file for the exact shapes to proxy against.
- [ ] **Step 2:** Add `@router.websocket("/claw/terminal/{session_id}")` in `ws_routes.py`: auth via `resolve_ws_user` + Claw session ownership check (same pattern as Task 4's VNC route), then on connect calls the Claw container's `POST /terminal/open` (via httpx, following the existing pattern used elsewhere in this file for calling into the Claw container's HTTP API — e.g. the `/workspace` POST call visible in the `_process_files` closure read during Task 4), then opens a WS connection to the Claw container's terminal WS endpoint from Task 5 and proxies bidirectionally (JSON messages this time, not raw binary — adapt the forwarding loop's `receive_bytes`/`send_bytes` calls to `receive_json`/`send_json` or `receive_text`/`send_text` matching whatever Task 5's endpoint actually uses).
- [ ] **Step 3:** Manual verification: with a running Claw session, connect a WS test client to `ws://localhost:8000/api/v1/ws/claw/terminal/{session_id}`, send an input message, confirm output comes back.
- [ ] **Step 4:** Commit: `git add backend/app/interfaces/api/ws_routes.py && git commit -m "feat(claw): backend proxy route for the Claw operator terminal"`

---

### Task 7: Forward tool events through the existing Claw chat SSE consumer

**Files:**
- Modify: `backend/app/infrastructure/external/claw/http_claw_client.py`
- Modify: `backend/app/interfaces/api/ws_routes.py` (the existing `/claw/{session_id}` route's event-forwarding logic — the `_write_events` closure referenced near line 605 in this plan's Context)

**Interfaces:**
- Consumes: Task 5's new `{"type": "tool", ...}` SSE event.
- Produces: the same tool events reaching the frontend over the existing `/ws/claw/{session_id}` WS connection, alongside `text`/`done`/`error`/`file`.

- [ ] **Step 1:** Read `HttpClawClient.chat_stream()` in full (`backend/app/infrastructure/external/claw/http_claw_client.py`, lines ~14-33 per earlier investigation) — it currently parses SSE `data:` lines into raw dicts; confirm it doesn't filter out unrecognized `type` values (if it does, that filter needs to allow `"tool"` through).
- [ ] **Step 2:** Read `HttpClawClient.get_history()` (lines ~71-79) — it explicitly discards tool-call intermediate steps today ("Skip empty assistant messages (tool-call intermediate steps)"). Decide (and document in the report) whether history replay should now include tool events too, or whether tool events are intentionally live-only (not persisted/replayed on reconnect) — the plan's default assumption is **live-only** (matching how `terminal_update`/`file_update` work for the Manus Agent, which are also not part of history replay per `useAgentEvents.ts`), but confirm this is a reasonable, working choice rather than an oversight before finalizing.
- [ ] **Step 3:** In the `/claw/{session_id}` WS route's `_write_events` closure, confirm `type: "tool"` frames pass through to the client unchanged (likely no code change needed here if the closure already forwards whatever `chat_stream()` yields — verify by reading it, only add code if something actively strips unknown types).
- [ ] **Step 4:** Run the backend test suite to confirm no regression.
- [ ] **Step 5:** Commit if any code changed: `git add -A && git commit -m "feat(claw): pass tool events through the Claw chat stream"` (skip if Step 3 found no change was needed — note that in the report instead).

---

### Task 8: Frontend API additions (`claw.ts`)

**Files:**
- Modify: `frontend/src/api/claw.ts`

**Interfaces:**
- Consumes: Task 4's VNC route path, Task 6's terminal route path, Task 7's `tool` event type.
- Produces: `getClawVncUrl(sessionId: string): string`, an extended `ClawEvent` union including a `tool` variant, and a minimal terminal WS client class Task 10 will use.

- [ ] **Step 1:** Read `frontend/src/api/claw.ts` in full (already partially described: `ClawEvent` type at lines ~18-29, `ClawWebSocket` class connecting to `/ws/claw/{sessionId}`). Also read `frontend/src/api/agent.ts::getVNCUrl` (lines ~229-232) for the exact URL-construction pattern to mirror.
- [ ] **Step 2:** Add `getClawVncUrl(sessionId: string): string` returning `` `${wsBase}/ws/claw/vnc/${sessionId}` `` using the same `BASE_URL`-derived `wsBase` construction as `getVNCUrl`.
- [ ] **Step 3:** Extend the `ClawEvent` union with a `tool` variant carrying whatever fields Task 5/7 actually produce (read Task 5's report for the exact shape — do not invent fields).
- [ ] **Step 4:** Add a small `ClawTerminalClient` class (or function-based composable, matching this file's existing style — check whether `ClawWebSocket` is a class or composable-style and follow suit) that connects to `` `${wsBase}/ws/claw/terminal/${sessionId}` ``, exposes a way to send input/resize, and an event callback for incoming data/exit — keep this minimal, it doesn't need `ChatWebSocket`'s full reconnect/backoff sophistication (a terminal session is short-lived and tied to the panel being open; simple connect/disconnect is enough, note this scope decision in the report rather than over-building).
- [ ] **Step 5:** Add sibling spec `frontend/src/api/__tests__/claw.spec.ts` if one doesn't already exist (check first), covering `getClawVncUrl`'s URL construction at minimum (follow this repo's established mocking conventions from earlier work this session, e.g. `frontend/src/api/__tests__/config.spec.ts` if it exists from the recent test-suite plan).
- [ ] **Step 6:** Run `cd frontend && npm test -- claw.spec && npm run type-check && npm run lint`.
- [ ] **Step 7:** Commit: `git add frontend/src/api/claw.ts frontend/src/api/__tests__/claw.spec.ts && git commit -m "feat(claw): frontend API additions for VNC URL, tool events, terminal client"`

---

### Task 9: Claw Computer Panel shell + reused browser VNC view

**Files:**
- Create: `frontend/src/components/ClawComputerPanel.vue`
- Create: `frontend/src/components/ClawComputerPanelContent.vue`

**Interfaces:**
- Consumes: Task 8's `getClawVncUrl`.
- Produces: a panel component exposing `showPanel()`/`hidePanel()` (mirroring `ComputerPanel.vue`'s `showComputerPanel`/`hideComputerPanel` via `defineExpose`), rendering a live VNC view when shown. Task 13 (ClawPage.vue integration) drives this via template ref.

- [ ] **Step 1:** Read `frontend/src/components/ComputerPanel.vue` and `ComputerPanelContent.vue` in full — these are the exact components to adapt, not reinvent. Read `frontend/src/components/toolViews/BrowserToolView.vue` and `frontend/src/components/VNCViewer.vue` too.
- [ ] **Step 2:** Create `ClawComputerPanel.vue` as a trimmed-down adaptation of `ComputerPanel.vue`: same `isShow`/sidebar-vs-dialog-teleport structure, but simpler content model (no `toolHistory` timeline/scrubber needed yet — Claw doesn't have a tool-history concept wired up to this panel; a live-only view is enough for this task, historical scrubbing is out of scope unless a later task explicitly adds it). Expose `showPanel()`/`hidePanel()` via `defineExpose`.
- [ ] **Step 3:** Create `ClawComputerPanelContent.vue`: header (simple "Manus Claw's screen" label + close button — no tool-name/verb display needed since there's no `toolInfo` concept here yet), and a `VNCViewer` instance (reused directly, imported from `../VNCViewer.vue` — it already only needs `sessionId`/`enabled`/`viewOnly` props and calls `getVNCUrl` internally... check whether `VNCViewer.vue` hardcodes the import of `getVNCUrl` from `agent.ts` or accepts the URL/fetcher as a prop. If hardcoded, this task must add an optional prop (e.g. `urlResolver?: (sessionId: string) => string`, defaulting to the existing `getVNCUrl` so Manus Agent behavior is unchanged) rather than duplicating `VNCViewer.vue` — read it carefully before deciding, and prefer the minimal-diff option that doesn't touch existing default behavior.
- [ ] **Step 4:** Add necessary i18n keys (e.g. "Manus Claw's screen") to `frontend/src/locales/en.ts` and `pt.ts` (and `zh.ts` if still maintained — check recent commits touching locales to decide).
- [ ] **Step 5:** Run `cd frontend && npm run type-check && npm run lint`.
- [ ] **Step 6:** Commit: `git add frontend/src/components/ClawComputerPanel.vue frontend/src/components/ClawComputerPanelContent.vue frontend/src/components/VNCViewer.vue frontend/src/locales/en.ts frontend/src/locales/pt.ts && git commit -m "feat(claw): Computer-panel shell reusing VNCViewer for live browser view"`

---

### Task 10: Interactive terminal view

**Files:**
- Create: `frontend/src/components/ClawTerminalView.vue`

**Interfaces:**
- Consumes: Task 8's `ClawTerminalClient`.
- Produces: an interactive (not read-only) xterm.js terminal component, addable as a second tab/mode inside `ClawComputerPanelContent.vue`.

- [ ] **Step 1:** Read `frontend/src/components/toolViews/ShellToolView.vue` in full for the xterm.js setup pattern (`@xterm/xterm` + `@xterm/addon-fit`, `disableStdin: true` at line ~167) — this new component is the interactive counterpart: same xterm.js setup, but `disableStdin: false` (or omitted, since `false` is the default) and wired to actually send keystrokes.
- [ ] **Step 2:** Create `ClawTerminalView.vue`: on mount, instantiate xterm.js, connect Task 8's `ClawTerminalClient`, call its "open terminal" method; wire `term.onData(data => client.sendInput(data))` for keystrokes, and the client's data-callback to `term.write(chunk)` (incremental writes here, not `ShellToolView`'s full clear-and-redraw — a real PTY sends incremental output, don't rebuild the buffer-replace approach that only made sense for the snapshot-based shell tool view). Use `@xterm/addon-fit` for sizing and call the client's resize method on window/container resize (check if `ShellToolView.vue` already handles resize observation you can copy).
- [ ] **Step 3:** Handle terminal exit (from the client's exit callback) by showing a simple "session ended" state, not an error.
- [ ] **Step 4:** Wire this into `ClawComputerPanelContent.vue` from Task 9 as a second view mode alongside the VNC view (a simple toggle/tab — "Screen" vs "Terminal" — matching this repo's existing tab/toggle visual conventions from `ComputerPanelContent.vue`'s side/dialog toggle button for styling consistency).
- [ ] **Step 5:** Add i18n keys for the tab labels and exit state message.
- [ ] **Step 6:** Run `cd frontend && npm run type-check && npm run lint`.
- [ ] **Step 7:** Commit: `git add frontend/src/components/ClawTerminalView.vue frontend/src/components/ClawComputerPanelContent.vue frontend/src/locales/en.ts frontend/src/locales/pt.ts && git commit -m "feat(claw): interactive terminal view (take-control equivalent)"`

---

### Task 11: Take-control wiring for the VNC view

**Files:**
- Modify: `frontend/src/components/ClawComputerPanelContent.vue`
- Read for the pattern: `frontend/src/components/TakeOverView.vue`, `frontend/src/components/toolViews/BrowserToolView.vue`'s `takeOver()` (lines ~59-64)

**Interfaces:**
- Consumes: Task 9's panel, Task 8's `getClawVncUrl`.
- Produces: a "take control" affordance on the VNC view that opens a second, interactive (`viewOnly=false`) `VNCViewer` against the same Claw session — no new global overlay component required if the existing panel can just swap its own `VNCViewer` instance's `viewOnly` prop, but if the Manus Agent's pattern (a separate full-screen overlay via `eventBus.emit('ui:takeover', ...)`) is cleaner to reuse, do that instead — read `TakeOverView.vue` and decide which is the better fit, documenting the choice in the report.

- [ ] **Step 1:** Read `TakeOverView.vue`, `MainLayout.vue`'s mounting of it, and `BrowserToolView.vue`'s take-control button.
- [ ] **Step 2:** Decide and implement one of: (a) reuse `TakeOverView.vue` as-is by making its `eventBus.emit('ui:takeover', {sessionId, active})` payload work for a Claw session too — check whether `TakeOverView.vue`'s internal `VNCViewer` call is hardcoded to `getVNCUrl` from `agent.ts`; if so, this needs the same optional-resolver-prop treatment as Task 9 did for the panel's own `VNCViewer`, OR (b) add a simple in-panel toggle inside `ClawComputerPanelContent.vue` that flips the panel's own `VNCViewer`'s `viewOnly` prop directly (simpler, no global overlay, but loses the "full-screen immersive" feel the Manus Agent has). Prefer (a) for consistency with the existing product pattern unless it requires disproportionate changes to `TakeOverView.vue`, in which case (b) is an acceptable, documented fallback.
- [ ] **Step 3:** Add a visible "Take control" button/affordance in `ClawComputerPanelContent.vue`'s screen-view mode.
- [ ] **Step 4:** Add i18n keys.
- [ ] **Step 5:** Run `cd frontend && npm run type-check && npm run lint`.
- [ ] **Step 6:** Commit: `git add -A && git commit -m "feat(claw): take-control affordance for the live VNC view"`

---

### Task 12: Tool-call log rendering

**Files:**
- Modify: `frontend/src/components/ClawComputerPanelContent.vue` (or a new small sub-component if the panel is getting large — implementer's judgment, note the choice)

**Interfaces:**
- Consumes: Task 7/8's `tool`-typed `ClawEvent`.
- Produces: a simple, live-scrolling list of tool calls (name + short arg summary + status), visible as a third mode/section in the panel — this is explicitly **not** required to be as rich as the Manus Agent's per-tool-type view components (`BrowserToolView`/`FileToolView`/etc.) for this task; a flat log list is the acceptable scope here, richer per-tool rendering is a natural future follow-up, not required now.

- [ ] **Step 1:** Read how `ClawPage.vue` currently accumulates/displays the message list from `ClawWebSocket` events, to follow the same reactive-array-append pattern for tool events.
- [ ] **Step 2:** Add a `toolLog` reactive array in `ClawPage.vue` (or wherever session state already lives for this page), appended to whenever a `tool`-typed event arrives via the existing `handleWSEvent` (Task 13 formalizes this wiring — this task can stub the append logic and Task 13 connects it end-to-end, or do both here if it's a small enough change to do together; implementer's judgment on the cleanest split, note it in the report).
- [ ] **Step 3:** Render `toolLog` as a simple scrolling list in the panel (tool name, one-line arg summary, status icon/color) — no timeline scrubber needed.
- [ ] **Step 4:** Run `cd frontend && npm run type-check && npm run lint`.
- [ ] **Step 5:** Commit: `git add -A && git commit -m "feat(claw): live tool-call log in the Computer panel"`

---

### Task 13: Wire the panel into ClawPage.vue

**Files:**
- Modify: `frontend/src/pages/ClawPage.vue`

**Interfaces:**
- Consumes: Tasks 9-12's panel component and its exposed methods.
- Produces: the finished feature — panel visible as a right-side column, opening live on tool activity, closable, with working take-control.

- [ ] **Step 1:** Read `frontend/src/pages/ClawPage.vue` in full, and `frontend/src/pages/ChatPage.vue`'s equivalent wiring (`toolHistory`, `showComputerPanel` calls in the WS event handler, the `<ComputerPanel ref=.../>` placement as a sibling of the chat column — already described in this plan's Context section) as the pattern to mirror.
- [ ] **Step 2:** Add `<ClawComputerPanel ref="clawComputerPanel" .../>` as a second top-level child inside the same `SimpleBar` wrapper that currently has only the chat column as its single child (confirmed in earlier investigation: `SimpleBar`'s `[&_.simplebar-content]:flex-row` makes this automatically lay out side-by-side, no extra flex/grid wrapper needed).
- [ ] **Step 3:** Extend `handleWSEvent` (or wherever `ClawEvent`s are currently switched on) to handle the `tool` type: append to the tool log (Task 12) and call `clawComputerPanel.value?.showPanel()` if not already shown (mirroring `ChatPage.vue`'s auto-open-on-tool-activity behavior).
- [ ] **Step 4:** Add a manual open/close affordance too (e.g. a button in the header, for when there's no live tool activity but the user wants to check the terminal) — check how `ChatPage.vue`/`ComputerPanelContent.vue` expose a manual "Use application" entry point and mirror that pattern's spirit, simplified.
- [ ] **Step 5:** Full manual verification (this is the plan's real acceptance test, not unit tests): follow this plan's top-level Verification section end to end.
- [ ] **Step 6:** Run `cd frontend && npm run type-check && npm run lint && npm test` — confirm zero regressions in the full suite (baseline: the count established by the frontend-test-suite work earlier this session).
- [ ] **Step 7:** Commit: `git add frontend/src/pages/ClawPage.vue && git commit -m "feat(claw): wire the Computer panel into ClawPage.vue"`

---

### Task 14: Documentation

**Files:**
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: nothing code-level; documents the finished feature and its flags.

- [ ] **Step 1:** Read the existing `AGENTS.md` section documenting `CLAW_DOCKER_IN_DOCKER` (added earlier this session) as the style/depth template.
- [ ] **Step 2:** Add an equivalent paragraph for `CLAW_BROWSER_GUI`: what it does, the resource-cost tradeoff (extra Xvfb+Chrome+VNC process per session when enabled), and that it's dev-default-on / prod-opt-in, matching `CLAW_DOCKER_IN_DOCKER`'s framing.
- [ ] **Step 3:** Briefly document the new `gateway.terminal.enabled` capability and what it exposes (operator-terminal-backed interactive terminal in the Claw panel), and the fact that `session.tool` events now surface tool activity in the UI.
- [ ] **Step 4:** Commit: `git add AGENTS.md && git commit -m "docs: document Claw Computer panel (VNC, terminal, tool log) and CLAW_BROWSER_GUI"`

---

## Verification (after all tasks)

1. `docker exec ai-manus-claw-1 sh -c "ps aux | grep -E 'Xvfb|x11vnc|websockify'"` — all three running with `CLAW_BROWSER_GUI=true`.
2. `docker exec ai-manus-claw-1 sh -c "HOME=/home/node openclaw sandbox explain"` — no `manus-claw` ownership warning.
3. Live in the browser: create a new Manus Claw session, ask the agent to browse a website. Confirm the Computer panel opens automatically and shows the live browser screen (cursor/page changes visible in near-real-time, not static screenshots).
4. Live: open the terminal tab in the panel, type a command (e.g. `ls`), confirm real-time output.
5. Live: click "take control" during agent browsing activity, confirm you can interact (click/type) without the agent's own session breaking.
6. Live: check the tool-call log shows entries as the agent works.
7. `cd frontend && npm run type-check && npm run lint && npm test` — clean, matching the established baseline.
8. `cd backend && set -a && source ../.env && set +a && uv run pytest` — 16 pre-existing unrelated failures only, no new ones.
9. Final whole-branch review per `superpowers:subagent-driven-development`, given the size and cross-cutting nature of this change (Docker image, Node.js gateway bridge, 2 new backend WS routes, ~6 new/modified frontend components).
