#!/usr/bin/env bash
# Idempotent one-time VPS preparation script for Dark Factory (k3s deployment).
# Run this first on a fresh Ubuntu 26.04 VPS, then run setup-k3s.sh.
# Safe to re-run: each step checks current state before acting.
#
# Usage: sudo bash setup-vps.sh <repo-url> [--app-dir <path>]
#   repo-url   HTTPS clone URL, e.g. https://github.com/your-org/dark-factory.git
#   --app-dir  Installation directory (default: /app/dark-factory)
#
set -euo pipefail

REPO_URL="${1:?Usage: sudo bash setup-vps.sh <repo-url> [--app-dir <path>]}"
APP_DIR="/app/dark-factory"
DEPLOY_USER="${SUDO_USER:-ubuntu}"

shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-dir) APP_DIR="$2"; shift 2 ;;
    *) echo "[setup-vps] ERROR: Unknown argument: $1" >&2; exit 1 ;;
  esac
done

log() { echo "[setup-vps] $*"; }
ok()  { echo "[setup-vps] OK: $*"; }

# ── 1. Install system prerequisites ──────────────────────────────────────────
log "Installing system prerequisites..."
apt-get update -qq
apt-get install -y --no-install-recommends \
  curl \
  git \
  apache2-utils \
  openssl \
  ca-certificates
ok "System prerequisites installed"

# ── 2. Clone repository ───────────────────────────────────────────────────────
if [ -d "${APP_DIR}/.git" ]; then
  ok "Repository already present at ${APP_DIR}"
else
  log "Cloning repository to ${APP_DIR}..."
  mkdir -p "$(dirname "$APP_DIR")"
  git clone "$REPO_URL" "$APP_DIR"
  chown -R "$DEPLOY_USER":"$DEPLOY_USER" "$APP_DIR"
  ok "Repository cloned to ${APP_DIR}"
fi

# ── 3. Next steps ─────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  VPS preparation complete. Next steps:"
echo ""
echo "  1. Place the production .env file:"
echo "     ${APP_DIR}/infra/.env"
echo "     (reference: ${APP_DIR}/infra/.env.example)"
echo ""
echo "  2. Run the k3s cluster setup:"
echo "     sudo bash ${APP_DIR}/infra/scripts/setup-k3s.sh \\"
echo "       --dashboard-password <your-dashboard-password>"
echo "============================================================"
echo ""
ok "Done."
