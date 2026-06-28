#!/usr/bin/env bash
# First script to run on a fresh VPS — as root.
# Creates a deploy user, grants sudo, and disables root SSH login.
# Run ONCE before setup-vps.sh.
#
# Usage: sudo bash init-server.sh --user <username> --pubkey "<ssh-public-key>"
#
set -euo pipefail

[ "$(id -u)" -ne 0 ] && exec sudo bash "$0" "$@"

DEPLOY_USER=""
PUBKEY=""

log() { echo "[init-server] $*"; }
die() { echo "[init-server] ERROR: $*" >&2; exit 1; }

# ── Parse arguments ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)   DEPLOY_USER="$2"; shift 2 ;;
    --pubkey) PUBKEY="$2";      shift 2 ;;
    *) die "Unknown argument: $1. Usage: bash init-server.sh --user <username> --pubkey \"<ssh-public-key>\"" ;;
  esac
done

[ -z "$DEPLOY_USER" ] && die "--user is required"
[ -z "$PUBKEY" ]      && die "--pubkey is required"

# ── 1. Create deploy user ─────────────────────────────────────────────────────
if id "$DEPLOY_USER" &>/dev/null; then
  log "User '${DEPLOY_USER}' already exists — skipping creation"
else
  log "Creating user '${DEPLOY_USER}'..."
  useradd --create-home --shell /bin/bash "$DEPLOY_USER"
  log "User '${DEPLOY_USER}' created"
fi

# ── 2. Add to sudo group ──────────────────────────────────────────────────────
if id -nG "$DEPLOY_USER" | grep -qw sudo; then
  log "User '${DEPLOY_USER}' already in sudo group — skipping"
else
  log "Adding '${DEPLOY_USER}' to sudo group..."
  usermod -aG sudo "$DEPLOY_USER"
  log "Done"
fi

# ── 3. Install SSH public key ─────────────────────────────────────────────────
AUTHORIZED_KEYS="/home/${DEPLOY_USER}/.ssh/authorized_keys"
if grep -qsF "$PUBKEY" "$AUTHORIZED_KEYS" 2>/dev/null; then
  log "SSH public key already present — skipping"
else
  log "Installing SSH public key for '${DEPLOY_USER}'..."
  mkdir -p "/home/${DEPLOY_USER}/.ssh"
  echo "$PUBKEY" >> "$AUTHORIZED_KEYS"
  chmod 700 "/home/${DEPLOY_USER}/.ssh"
  chmod 600 "$AUTHORIZED_KEYS"
  chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "/home/${DEPLOY_USER}/.ssh"
  log "SSH key installed"
fi

# ── 4. Grant passwordless sudo ───────────────────────────────────────────────
SUDOERS_FILE="/etc/sudoers.d/${DEPLOY_USER}"
if [ -f "$SUDOERS_FILE" ]; then
  log "Passwordless sudo already configured for '${DEPLOY_USER}' — skipping"
else
  log "Granting passwordless sudo to '${DEPLOY_USER}'..."
  echo "${DEPLOY_USER} ALL=(ALL) NOPASSWD:ALL" > "$SUDOERS_FILE"
  chmod 440 "$SUDOERS_FILE"
  log "Passwordless sudo granted"
fi

# ── 5. Disable root SSH login ─────────────────────────────────────────────────
SSHD_CONFIG="/etc/ssh/sshd_config"

# Disable PermitRootLogin
if grep -qE "^PermitRootLogin\s+no" "$SSHD_CONFIG"; then
  log "Root SSH login already disabled — skipping"
else
  log "Disabling root SSH login..."
  sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' "$SSHD_CONFIG"
  log "PermitRootLogin set to no"
fi

# Disable password authentication (key-only)
if grep -qE "^PasswordAuthentication\s+no" "$SSHD_CONFIG"; then
  log "Password authentication already disabled — skipping"
else
  log "Disabling password authentication..."
  sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' "$SSHD_CONFIG"
  log "PasswordAuthentication set to no"
fi

log "Reloading sshd..."
systemctl reload sshd

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Server initialised. Next steps:"
echo ""
echo "  1. Verify you can SSH as '${DEPLOY_USER}' before closing"
echo "     this root session:"
echo "     ssh ${DEPLOY_USER}@<vps-ip>"
echo ""
echo "  2. Then run as '${DEPLOY_USER}':"
echo "     sudo bash setup-vps.sh <repo-url>"
echo "============================================================"
echo ""
log "Done."
