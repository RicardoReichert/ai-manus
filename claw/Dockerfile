FROM ubuntu:24.04

# Avoid interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Base tools needed to add apt repositories and install everything below.
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    gnupg \
    git \
    sudo \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Python — for the agent's "run a script" path (apt, matching the pattern
# sandbox/Dockerfile already uses for its own Python install).
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Node.js 24 — OpenClaw's own documented runtime requirement (its official
# image is built FROM node:24-bookworm-slim). Installed via NodeSource,
# same mechanism sandbox/Dockerfile already uses for its Node 20 install.
# ---------------------------------------------------------------------------
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_24.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Docker Engine (CLI + dockerd + containerd) — for Docker-in-Docker. Only
# ever started when CLAW_DOCKER_IN_DOCKER=true (see entrypoint.sh); its own
# nested daemon, never the host's socket. Installed via Docker's official
# apt repository, per Docker's documented Ubuntu install steps.
# ---------------------------------------------------------------------------
RUN install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y docker-ce docker-ce-cli containerd.io && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# OpenClaw itself — installed the same way any user installs it outside
# Docker (`npm i -g openclaw`), rather than inheriting the prebuilt upstream
# image. Version pinned deliberately: no floating "latest" dependency on a
# third-party registry, and updates become a conscious version bump here.
# ---------------------------------------------------------------------------
RUN npm i -g openclaw@2026.7.1-2

# Create the `node` user that runs the actual gateway process (dockerd
# needs root; see entrypoint.sh). No specific uid is required — this image
# no longer inherits the official OpenClaw image's volume/uid conventions,
# so all that matters is self-consistency between this Dockerfile's chown
# below and entrypoint.sh's `sudo -u node`. ubuntu:24.04 already ships a
# built-in `ubuntu` user at uid 1000, so pick the next uid rather than
# fight over it.
RUN userdel -r ubuntu 2>/dev/null; \
    useradd -m -d /home/node -s /bin/bash node && \
    echo "node ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/node

# Setup manus-claw plugin in stock extensions and openclaw user dir
RUN mkdir -p /app/extensions/manus-claw /home/node/.openclaw/extensions/manus-claw
COPY manus-claw/ /app/extensions/manus-claw/
COPY manus-claw/ /home/node/.openclaw/extensions/manus-claw/
RUN cd /app/extensions/manus-claw && npm install --production
RUN cd /home/node/.openclaw/extensions/manus-claw && npm install --production
RUN chown -R node:node /app/extensions /home/node/.openclaw

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Deliberately stays root (unlike the upstream image, which drops to `node`
# at build time): dockerd needs root to start when Docker-in-Docker is
# enabled. entrypoint.sh itself drops to the `node` user for the actual
# `openclaw gateway` process — dockerd is the only thing that runs as root.

# Expose manus-claw HTTP server port and OpenClaw gateway port
EXPOSE 18788
EXPOSE 18789

# Environment variables with defaults
ENV CLAW_TTL_SECONDS=0
ENV CLAW_SHUTDOWN_GRACE_SECONDS=30
ENV MANUS_API_BASE_URL=""
ENV MANUS_API_KEY=""
ENV OPENCLAW_GATEWAY_TOKEN=""
ENV CLAW_DOCKER_IN_DOCKER=false

ENTRYPOINT ["/entrypoint.sh"]
