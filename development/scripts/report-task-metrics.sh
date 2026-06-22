#!/usr/bin/env bash
# report-task-metrics.sh
# Records a completed task event to the project-administrator SQLite database.
#
# Usage (from any agent directory):
#   ../scripts/report-task-metrics.sh \
#     --feature-name "auth-app" \
#     --task-id "T001" \
#     --task-description "Implemented login endpoint" \
#     --time-spent-seconds 600 \
#     --tokens-spent 4200 \
#     --model-used "claude-sonnet-4-6" \
#     [--token-source "self-reported"] \
#     [--status "completed"] \
#     [--notes "tokens estimated"]

set -euo pipefail

# ── Defaults ────────────────────────────────────────────────────────────────
FEATURE_NAME=""
TASK_ID=""
TASK_DESCRIPTION=""
TIME_SPENT_SECONDS=0
TOKENS_SPENT=0
MODEL_USED=""
TOKEN_SOURCE="self-reported"
STATUS="completed"
NOTES=""

# ── Argument parsing ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --feature-name)         FEATURE_NAME="$2";         shift 2 ;;
    --task-id)              TASK_ID="$2";               shift 2 ;;
    --task-description)     TASK_DESCRIPTION="$2";      shift 2 ;;
    --time-spent-seconds)   TIME_SPENT_SECONDS="$2";    shift 2 ;;
    --tokens-spent)         TOKENS_SPENT="$2";          shift 2 ;;
    --model-used)           MODEL_USED="$2";            shift 2 ;;
    --token-source)         TOKEN_SOURCE="$2";          shift 2 ;;
    --status)               STATUS="$2";                shift 2 ;;
    --notes)                NOTES="$2";                 shift 2 ;;
    --agent-name)           AGENT_NAME_OVERRIDE="$2";   shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ── Validation ───────────────────────────────────────────────────────────────
if [[ -z "$FEATURE_NAME" ]]; then
  echo "ERROR: --feature-name is required" >&2; exit 1
fi
if [[ -z "$TASK_DESCRIPTION" ]]; then
  echo "ERROR: --task-description is required" >&2; exit 1
fi

# ── Resolve agent name from caller directory ─────────────────────────────────
# If explicitly overridden use that; otherwise derive from the current directory name.
if [[ -n "${AGENT_NAME_OVERRIDE:-}" ]]; then
  AGENT_NAME="$AGENT_NAME_OVERRIDE"
else
  AGENT_NAME="$(basename "$(pwd)")"
fi

# ── Locate agent_metrics.py ──────────────────────────────────────────────────
# The script lives in project-administrator/ relative to the repo root.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
METRICS_PY="$REPO_ROOT/project-administrator/agent_metrics.py"

if [[ ! -f "$METRICS_PY" ]]; then
  echo "ERROR: agent_metrics.py not found at $METRICS_PY" >&2
  exit 1
fi

# ── Write to SQLite ──────────────────────────────────────────────────────────
python3 "$METRICS_PY" insert \
  --agent-name       "$AGENT_NAME" \
  --feature-name     "$FEATURE_NAME" \
  --task-id          "$TASK_ID" \
  --task-description "$TASK_DESCRIPTION" \
  --time-spent-seconds "$TIME_SPENT_SECONDS" \
  --tokens-spent     "$TOKENS_SPENT" \
  --model-used       "$MODEL_USED" \
  --token-source     "$TOKEN_SOURCE" \
  --status           "$STATUS" \
  --notes            "$NOTES"
