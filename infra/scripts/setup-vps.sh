#!/usr/bin/env bash
# Idempotent one-time VPS setup script for Dark Factory.
# Safe to re-run: each step checks current state before acting.
# Target: Ubuntu 24.04 LTS with Docker already available via apt or installed by this script.
set -euo pipefail

REPO_URL="${1:?Usage: setup-vps.sh <repo-url>  (e.g. https://github.com/your-org/dark-factory.git)}"
APP_DIR="/app/dark-factory"
DEPLOY_USER="${SUDO_USER:-ubuntu}"

log() { echo "[setup-vps] $*"; }
ok()  { echo "[setup-vps] OK: $*"; }

# ── 1. Install Docker (official repo) ────────────────────────────────────────
if command -v docker >/dev/null 2>&1; then
  ok "Docker already installed: $(docker --version)"
else
  log "Installing Docker via official apt repository..."
  apt-get update -qq
  apt-get install -y --no-install-recommends ca-certificates curl gnupg lsb-release

  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
     https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list

  apt-get update -qq
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
  ok "Docker installed: $(docker --version)"
fi

# ── 2. Add deploy user to docker group ───────────────────────────────────────
if id -nG "$DEPLOY_USER" | grep -qw docker; then
  ok "${DEPLOY_USER} is already in the docker group"
else
  log "Adding ${DEPLOY_USER} to docker group..."
  usermod -aG docker "$DEPLOY_USER"
  ok "${DEPLOY_USER} added to docker group (logout/login required to take effect)"
fi

# ── 3. Verify Docker Compose v2 ───────────────────────────────────────────────
if docker compose version >/dev/null 2>&1; then
  ok "Docker Compose v2: $(docker compose version)"
else
  echo "ERROR: docker compose v2 not available. Check Docker installation." >&2
  exit 1
fi

# ── 4. Create app directory and clone repo ────────────────────────────────────
if [ -d "${APP_DIR}/.git" ]; then
  ok "Repository already present at ${APP_DIR}"
else
  log "Creating ${APP_DIR} and cloning repository..."
  mkdir -p "$(dirname "$APP_DIR")"
  git clone "$REPO_URL" "$APP_DIR"
  chown -R "$DEPLOY_USER":"$DEPLOY_USER" "$APP_DIR"
  ok "Repository cloned to ${APP_DIR}"
fi

# ── 5. Reminder: place .env file ──────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  NEXT STEP: Place the production .env file"
echo ""
echo "  Copy your production environment file to:"
echo "    ${APP_DIR}/infra/.env"
echo ""
echo "  Reference: ${APP_DIR}/infra/.env.example"
echo "============================================================"
echo ""
ok "VPS setup complete."
