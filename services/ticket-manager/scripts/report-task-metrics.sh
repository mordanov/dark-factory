#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
METRICS_TOOL="$REPO_ROOT/project-administrator/agent_metrics.py"
DB_PATH="${METRICS_DB_PATH:-$REPO_ROOT/project-administrator/agent_metrics.sqlite3}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

usage() {
  cat <<'EOF'
Usage:
  report-task-metrics.sh \
    --feature-name <feature> \
    --task-description <text> \
    (--time-spent-seconds <seconds> | --time-spent-minutes <minutes> | --started-at <iso> --finished-at <iso>) \
    --tokens-spent <tokens> \
    --model-used <model> \
    [--task-id <task-id>] \
    [--agent-name <agent>] \
    [--token-source <source>] \
    [--status <status>] \
    [--notes <notes>] \
    [--timestamp <iso>]

Notes:
  - Run this from any role directory; it finds the repository root automatically.
  - Tokens are required. If exact values are unavailable, pass an estimate with --token-source estimated.
  - This writes to project-administrator/agent_metrics.sqlite3 unless METRICS_DB_PATH is set.
EOF
}

infer_agent_name() {
  case "$(basename "$PWD")" in
    product-manager|software-architect|security-architect|frontend|backend|devops|code-reviewer|autotester|project-administrator)
      printf '%s\n' "$(basename "$PWD")"
      ;;
    *)
      printf '%s\n' "unknown-agent"
      ;;
  esac
}

AGENT_NAME="${AGENT_NAME:-$(infer_agent_name)}"
FEATURE_NAME=""
TASK_ID=""
TASK_DESCRIPTION=""
MODEL_USED="${MODEL_USED:-${CLAUDE_MODEL:-}}"
TOKEN_SOURCE="self-reported"
STATUS="completed"
NOTES=""
TIMESTAMP=""
TOKENS_SPENT=""
TIME_SECONDS=""
TIME_MINUTES=""
STARTED_AT=""
FINISHED_AT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent-name)
      AGENT_NAME="$2"
      shift 2
      ;;
    --feature-name)
      FEATURE_NAME="$2"
      shift 2
      ;;
    --task-id)
      TASK_ID="$2"
      shift 2
      ;;
    --task-description)
      TASK_DESCRIPTION="$2"
      shift 2
      ;;
    --model-used)
      MODEL_USED="$2"
      shift 2
      ;;
    --tokens-spent)
      TOKENS_SPENT="$2"
      shift 2
      ;;
    --token-source)
      TOKEN_SOURCE="$2"
      shift 2
      ;;
    --status)
      STATUS="$2"
      shift 2
      ;;
    --notes)
      NOTES="$2"
      shift 2
      ;;
    --timestamp)
      TIMESTAMP="$2"
      shift 2
      ;;
    --time-spent-seconds)
      TIME_SECONDS="$2"
      shift 2
      ;;
    --time-spent-minutes)
      TIME_MINUTES="$2"
      shift 2
      ;;
    --started-at)
      STARTED_AT="$2"
      shift 2
      ;;
    --finished-at)
      FINISHED_AT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$FEATURE_NAME" || -z "$TASK_DESCRIPTION" || -z "$MODEL_USED" || -z "$TOKENS_SPENT" ]]; then
  echo "Missing required arguments." >&2
  usage >&2
  exit 2
fi

if [[ -z "$TIME_SECONDS" && -z "$TIME_MINUTES" && ( -z "$STARTED_AT" || -z "$FINISHED_AT" ) ]]; then
  echo "Provide --time-spent-seconds, --time-spent-minutes, or both --started-at and --finished-at." >&2
  exit 2
fi

if [[ -n "$TIME_SECONDS" && "$TIME_SECONDS" -le 0 ]]; then
  echo "--time-spent-seconds must be greater than 0 for completed work." >&2
  exit 2
fi

if [[ -n "$TIME_MINUTES" ]]; then
  if ! "$PYTHON_BIN" - "$TIME_MINUTES" <<'PY'
import sys
value = float(sys.argv[1])
if value <= 0:
    raise SystemExit(1)
PY
  then
    echo "--time-spent-minutes must be greater than 0 for completed work." >&2
    exit 2
  fi
fi

if [[ "$TOKENS_SPENT" =~ ^- ]]; then
  echo "--tokens-spent must be zero or greater." >&2
  exit 2
fi

if [[ "$TOKEN_SOURCE" == "unknown" && -z "$NOTES" ]]; then
  echo "When --token-source unknown is used, provide --notes explaining why estimation was impossible." >&2
  exit 2
fi

if [[ "$AGENT_NAME" == "unknown-agent" ]]; then
  echo "Could not infer agent name from the current directory. Pass --agent-name explicitly." >&2
  exit 2
fi

if [[ ! -f "$METRICS_TOOL" ]]; then
  echo "Metrics tool not found: $METRICS_TOOL" >&2
  exit 1
fi

FULL_TASK_DESCRIPTION="$TASK_DESCRIPTION"
if [[ -n "$TASK_ID" ]]; then
  FULL_TASK_DESCRIPTION="$TASK_ID: $TASK_DESCRIPTION"
fi

RECORD_ARGS=(
  "$PYTHON_BIN" "$METRICS_TOOL" record
  --db "$DB_PATH"
  --agent-name "$AGENT_NAME"
  --feature-name "$FEATURE_NAME"
  --task-description "$FULL_TASK_DESCRIPTION"
  --model-used "$MODEL_USED"
  --tokens-spent "$TOKENS_SPENT"
  --token-source "$TOKEN_SOURCE"
  --status "$STATUS"
  --notes "$NOTES"
)

if [[ -n "$TIMESTAMP" ]]; then
  RECORD_ARGS+=(--timestamp "$TIMESTAMP")
fi
if [[ -n "$TIME_SECONDS" ]]; then
  RECORD_ARGS+=(--time-spent-seconds "$TIME_SECONDS")
fi
if [[ -n "$TIME_MINUTES" ]]; then
  RECORD_ARGS+=(--time-spent-minutes "$TIME_MINUTES")
fi
if [[ -n "$STARTED_AT" ]]; then
  RECORD_ARGS+=(--started-at "$STARTED_AT")
fi
if [[ -n "$FINISHED_AT" ]]; then
  RECORD_ARGS+=(--finished-at "$FINISHED_AT")
fi

"$PYTHON_BIN" "$METRICS_TOOL" init --db "$DB_PATH" >/dev/null
"${RECORD_ARGS[@]}"

echo "Next step: send the same metrics in a brainstorm task-metrics message to project-administrator for acknowledgement."
