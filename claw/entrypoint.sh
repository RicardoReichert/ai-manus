#!/bin/bash
set -e

# If arguments are provided, run them instead of the gateway. This makes the
# compose "prevent claw from starting" override (entrypoint/command:
# /bin/sh -c "exit 0") work even with compose implementations that pass the
# override as container args to the image entrypoint instead of replacing it.
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

CONFIG_DIR="/home/node/.openclaw"
CONFIG_FILE="${CONFIG_DIR}/openclaw.json"
mkdir -p "${CONFIG_DIR}/workspace"

# Generate a secure gateway token if not provided
if [ -z "${OPENCLAW_GATEWAY_TOKEN}" ]; then
    OPENCLAW_GATEWAY_TOKEN=$(openssl rand -hex 24 2>/dev/null || node -e "console.log(require('crypto').randomBytes(24).toString('hex'))")
    export OPENCLAW_GATEWAY_TOKEN
fi

# Clean up MANUS_API_BASE_URL so appending /v1 does not produce /v1/v1
MANUS_BASE="${MANUS_API_BASE_URL:-http://backend:8000}"
MANUS_BASE="${MANUS_BASE%/v1}"
MANUS_BASE="${MANUS_BASE%/}"

echo "[entrypoint] Gateway token: ${OPENCLAW_GATEWAY_TOKEN}"
echo "[entrypoint] Manus API base URL: ${MANUS_BASE}/v1"

# CLAW_BROWSER_GUI controls whether the browser tool renders headless or
# into the Xvfb display started below, and gets baked into openclaw.json as
# a real JSON boolean (same technique as CLAW_DOCKER_IN_DOCKER's block
# further down, which only guards *whether* dockerd starts, not any JSON
# value — here the flag also selects between two JSON literals).
if [ "${CLAW_BROWSER_GUI}" = "true" ]; then
    BROWSER_HEADLESS="false"
else
    BROWSER_HEADLESS="true"
fi

# Write openclaw.json configuration
cat > "${CONFIG_FILE}" << EOF
{
  "meta": {
    "lastTouchedVersion": "2026.2.13"
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "manus-proxy/default"
      },
      "workspace": "/home/node/.openclaw/workspace",
      "compaction": {
        "mode": "safeguard"
      },
      "maxConcurrent": 4
    }
  },
  "browser": {
    "enabled": true,
    "headless": ${BROWSER_HEADLESS}
  },
  "tools": {
    "alsoAllow": ["browser"]
  },
  "gateway": {
    "port": 18789,
    "mode": "local",
    "bind": "lan",
    "auth": {
      "mode": "token",
      "token": "${OPENCLAW_GATEWAY_TOKEN}"
    },
    "terminal": {
      "enabled": true
    }
  },
  "plugins": {
    "load": {
      "paths": [
        "/home/node/.openclaw/extensions"
      ]
    },
    "entries": {
      "manus-claw": {
        "enabled": true,
        "config": {
          "gateway": {
            "url": "ws://127.0.0.1:18789",
            "token": "${OPENCLAW_GATEWAY_TOKEN}",
            "agentId": "main"
          },
          "server": {
            "port": 18788,
            "host": "0.0.0.0"
          },
          "retry": {
            "baseMs": 1000,
            "maxMs": 60000,
            "maxAttempts": 0
          },
          "log": {
            "enabled": true,
            "verbose": false
          }
        }
      }
    }
  },
  "models": {
    "mode": "merge",
    "providers": {
      "manus-proxy": {
        "baseUrl": "${MANUS_BASE}/v1",
        "apiKey": "${MANUS_API_KEY}",
        "api": "openai-completions",
        "models": [
          {
            "id": "default",
            "name": "default",
            "contextWindow": 128000,
            "maxTokens": 8192
          }
        ]
      }
    }
  }
}
EOF

echo "[entrypoint] Configuration written to ${CONFIG_FILE}"

# The container now starts as root (dockerd needs root, see below), so
# anything written into the config volume above must be handed back to the
# `node` user before the gateway (which runs as `node`) can use it.
chown -R node:node "${CONFIG_DIR}"
# OpenClaw's plugin loader only trusts root-owned plugin directories —
# the blanket chown above (needed so the `node` user can write config)
# otherwise flags manus-claw as "blocked plugin candidate: suspicious
# ownership" (confirmed live via `openclaw sandbox explain`).
chown -R root:root "${CONFIG_DIR}/extensions"

# ---------------------------------------------------------------------------
# Docker-in-Docker: only when explicitly opted in (CLAW_DOCKER_IN_DOCKER=true,
# set by docker_claw_runtime.py alongside `privileged=True` on the container
# itself — dockerd cannot start without it). This is the container's OWN
# nested daemon and socket, at the default /var/run/docker.sock *inside this
# container* — never the host's. `docker ps` from in here only ever shows
# containers this nested daemon created.
# ---------------------------------------------------------------------------
DOCKERD_PID=""
if [ "${CLAW_DOCKER_IN_DOCKER}" = "true" ]; then
    echo "[entrypoint] CLAW_DOCKER_IN_DOCKER=true, starting nested dockerd (storage-driver=vfs)"
    mkdir -p /var/lib/docker
    # Guard against a stale /var/run/docker.pid: the docker-ce apt package's
    # postinst briefly starts+stops dockerd during image build, and that
    # leftover pid file can get committed into the image layer. At real
    # container boot, an early entrypoint process can coincidentally reuse
    # that same low PID, so dockerd's "is it still running?" check falsely
    # believes a daemon is already up and refuses to start — permanently,
    # since nothing here retries. Always start from a clean pid/socket state.
    rm -f /var/run/docker.pid /var/run/docker.sock
    dockerd --storage-driver=vfs > /var/log/dockerd.log 2>&1 &
    DOCKERD_PID=$!

    DOCKERD_READY=false
    for _ in $(seq 1 30); do
        if docker version >/dev/null 2>&1; then
            DOCKERD_READY=true
            break
        fi
        sleep 1
    done
    if [ "${DOCKERD_READY}" = "true" ]; then
        echo "[entrypoint] Nested dockerd ready (pid ${DOCKERD_PID})"
    else
        echo "[entrypoint] Nested dockerd did not become ready within 30s — continuing without it, see /var/log/dockerd.log"
    fi
fi

# ---------------------------------------------------------------------------
# Browser GUI: only when explicitly opted in (CLAW_BROWSER_GUI=true, set by
# docker_claw_runtime.py). Unlike CLAW_DOCKER_IN_DOCKER this needs no
# container privileges — Xvfb/x11vnc/websockify are plain userspace
# processes. Starts a virtual display, a VNC server pointed at it, and a
# websockify bridge so the frontend can view it over WebSocket on 5901.
# openclaw.json's browser.headless above already reflects this same flag;
# DISPLAY is exported below so any browser process OpenClaw's `browser`
# tool launches renders into this Xvfb display instead of failing to find
# a display or falling back to headless.
# ---------------------------------------------------------------------------
XVFB_PID=""
X11VNC_PID=""
WEBSOCKIFY_PID=""
if [ "${CLAW_BROWSER_GUI}" = "true" ]; then
    echo "[entrypoint] CLAW_BROWSER_GUI=true, starting Xvfb+x11vnc+websockify"
    Xvfb :1 -screen 0 1280x1024x24 &
    XVFB_PID=$!

    XVFB_READY=false
    for _ in $(seq 1 30); do
        if xdpyinfo -display :1 >/dev/null 2>&1; then
            XVFB_READY=true
            break
        fi
        sleep 1
    done
    if [ "${XVFB_READY}" = "true" ]; then
        echo "[entrypoint] Xvfb ready on :1 (pid ${XVFB_PID})"
    else
        echo "[entrypoint] Xvfb did not become ready within 30s — continuing anyway"
    fi

    x11vnc -display :1 -nopw -shared -listen 0.0.0.0 -forever -rfbport 5900 &
    X11VNC_PID=$!
    echo "[entrypoint] x11vnc listening on 5900 (pid ${X11VNC_PID})"

    websockify 0.0.0.0:5901 localhost:5900 &
    WEBSOCKIFY_PID=$!
    echo "[entrypoint] websockify listening on 5901 (pid ${WEBSOCKIFY_PID})"

    export DISPLAY=:1
fi

# Start OpenClaw gateway as a child process, running as the unprivileged
# `node` user (the config file above already has every value it needs
# baked in as literal strings, so the gateway process itself needs no env
# vars — only dockerd above needs root). This script stays PID 1 and acts
# as a watchdog: forward shutdown signals and force-kill if the gateway
# does not exit within the grace period. This guarantees the container
# always exits when the TTL expires (or on docker stop), even if the Node
# process hangs during graceful shutdown.
CLAW_TTL_SECONDS="${CLAW_TTL_SECONDS:-0}"
CLAW_SHUTDOWN_GRACE_SECONDS="${CLAW_SHUTDOWN_GRACE_SECONDS:-30}"

sudo -H -u node openclaw gateway &
GATEWAY_PID=$!

shutdown_gateway() {
    echo "[entrypoint] Shutting down OpenClaw gateway (pid ${GATEWAY_PID})"
    kill -TERM "${GATEWAY_PID}" 2>/dev/null || true
    for _ in $(seq 1 "${CLAW_SHUTDOWN_GRACE_SECONDS}"); do
        if ! kill -0 "${GATEWAY_PID}" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    if kill -0 "${GATEWAY_PID}" 2>/dev/null; then
        echo "[entrypoint] Gateway did not stop within ${CLAW_SHUTDOWN_GRACE_SECONDS}s, force killing"
        kill -KILL "${GATEWAY_PID}" 2>/dev/null || true
    fi
    if [ -n "${DOCKERD_PID}" ]; then
        echo "[entrypoint] Shutting down nested dockerd (pid ${DOCKERD_PID})"
        kill -TERM "${DOCKERD_PID}" 2>/dev/null || true
    fi
    if [ -n "${WEBSOCKIFY_PID}" ]; then
        echo "[entrypoint] Shutting down websockify (pid ${WEBSOCKIFY_PID})"
        kill -TERM "${WEBSOCKIFY_PID}" 2>/dev/null || true
    fi
    if [ -n "${X11VNC_PID}" ]; then
        echo "[entrypoint] Shutting down x11vnc (pid ${X11VNC_PID})"
        kill -TERM "${X11VNC_PID}" 2>/dev/null || true
    fi
    if [ -n "${XVFB_PID}" ]; then
        echo "[entrypoint] Shutting down Xvfb (pid ${XVFB_PID})"
        kill -TERM "${XVFB_PID}" 2>/dev/null || true
    fi
}
trap shutdown_gateway TERM INT

if [ "${CLAW_TTL_SECONDS}" -gt 0 ] 2>/dev/null; then
    echo "[entrypoint] TTL set to ${CLAW_TTL_SECONDS} seconds, will shutdown automatically"
    (
        sleep "${CLAW_TTL_SECONDS}"
        echo "[entrypoint] TTL expired after ${CLAW_TTL_SECONDS} seconds, shutting down"
        kill -TERM $$ 2>/dev/null || true
    ) &
fi

# Wait for the gateway to exit. The first wait may be interrupted by the TERM
# trap; wait again to collect the real exit status after the trap returns.
set +e
wait "${GATEWAY_PID}"
wait "${GATEWAY_PID}" 2>/dev/null
EXIT_CODE=$?
echo "[entrypoint] OpenClaw gateway exited with code ${EXIT_CODE}"
exit "${EXIT_CODE}"
