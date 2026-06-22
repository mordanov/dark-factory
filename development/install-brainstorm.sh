#!/usr/bin/env bash
# install-brainstorm.sh
# Clones, builds, and registers brainstorm-mcp with Claude Code.
# Usage: bash install-brainstorm.sh [--dir /path/to/install]

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
REPO_URL="https://github.com/TheodorStorm/brainstorm-mcp.git"
DEFAULT_INSTALL_DIR="$HOME/.local/share/brainstorm-mcp"

# Allow overriding the install directory via --dir flag
INSTALL_DIR="$DEFAULT_INSTALL_DIR"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    *)     echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ── Dependency checks ─────────────────────────────────────────────────────────
echo "==> Checking dependencies..."

for cmd in git node npm; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: '$cmd' is not installed or not in PATH." >&2
    exit 1
  fi
done

NODE_MAJOR=$(node -e "process.stdout.write(process.versions.node.split('.')[0])")
if (( NODE_MAJOR < 18 )); then
  echo "ERROR: Node.js >= 18 required (found $(node --version))." >&2
  exit 1
fi

# ── Clone / update ────────────────────────────────────────────────────────────
if [[ -d "$INSTALL_DIR/.git" ]]; then
  echo "==> Repository already exists at $INSTALL_DIR — pulling latest changes..."
  git -C "$INSTALL_DIR" pull --ff-only
else
  echo "==> Cloning brainstorm-mcp into $INSTALL_DIR..."
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── Install & build ───────────────────────────────────────────────────────────
echo "==> Installing npm dependencies..."
npm install

echo "==> Building TypeScript..."
npm run build

# ── Register with Claude Code ─────────────────────────────────────────────────
echo "==> Registering with Claude Code (updating ~/.claude/mcp_config.json)..."
# npm run config writes the correct absolute path to the config file
npm run config

# ── Shell wrapper (optional) ──────────────────────────────────────────────────
SHELL_RC=""
if [[ -f "$HOME/.zshrc" ]]; then
  SHELL_RC="$HOME/.zshrc"
elif [[ -f "$HOME/.bashrc" ]]; then
  SHELL_RC="$HOME/.bashrc"
fi

WRAPPER='
# ── Brainstorm-MCP: Claude Code smart wrapper ────────────────────────────────
claude() {
  if ! command -v claude >/dev/null 2>&1; then
    echo "Error: claude command not found. Please install Claude Code first." >&2
    return 1
  fi
  if [ $# -eq 0 ]; then
    local prompt="CRITICAL: You (Claude Code AI assistant) must check if YOU are a member of any Brainstorm projects. The human user is your supervisor, not a project member. Use mcp__brainstorm__status with working_directory set to the EXACT initial '\''Working directory'\'' path from the <env> block (shown at conversation start - NOT the current PWD). Report: (1) YOUR agent name and role (coordinator/contributor) in each project YOU are a member of, (2) YOUR unread message counts in YOUR inbox, (3) Any handoff messages directed to YOU. If YOU have unread messages, ask the human supervisor if they want you to review them before proceeding with other tasks."
    command claude "$prompt"
  else
    command claude "$@"
  fi
}
# ─────────────────────────────────────────────────────────────────────────────
'

if [[ -n "$SHELL_RC" ]]; then
  if grep -q "Brainstorm-MCP: Claude Code smart wrapper" "$SHELL_RC" 2>/dev/null; then
    echo "==> Shell wrapper already present in $SHELL_RC — skipping."
  else
    echo "==> Adding shell wrapper to $SHELL_RC..."
    printf '%s\n' "$WRAPPER" >> "$SHELL_RC"
    echo "    Run: source $SHELL_RC"
  fi
else
  echo "    NOTE: Could not detect ~/.zshrc or ~/.bashrc."
  echo "    Add the shell wrapper manually (see CLAUDE.md 'Shell Wrapper' section)."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "✅  brainstorm-mcp installed successfully!"
echo "    Install dir : $INSTALL_DIR"
echo "    MCP config  : ~/.claude/mcp_config.json"
echo ""
echo "Next steps:"
echo "  1. source your shell config  (e.g. source ~/.zshrc)"
echo "  2. Open Claude Code in any project directory"
echo "  3. Run the brainstorm team launcher:  bash run-agents.sh"
