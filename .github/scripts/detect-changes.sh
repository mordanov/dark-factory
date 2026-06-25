#!/usr/bin/env bash
# Outputs a JSON array of service names affected by the last commit.
# Exits 0 always. Exits 1 if git is unavailable or not in a repo.
set -euo pipefail

BASE_COMMIT="${1:-HEAD^}"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Error: not inside a git repository" >&2
  exit 1
fi

ALL_SERVICES='["uim-backend","tm-backend","orchestrator","context-distiller","agent-dispatcher","agent-tools","uim-frontend","tm-frontend","nginx"]'

CHANGED=$(git diff --name-only "${BASE_COMMIT}" HEAD 2>/dev/null || true)

if [ -z "$CHANGED" ]; then
  echo "[]"
  exit 0
fi

# If infra/docker-compose.yml changed → full rebuild of all services
if echo "$CHANGED" | grep -q "^infra/docker-compose\.yml$"; then
  echo "$ALL_SERVICES"
  exit 0
fi

declare -A seen

add_service() {
  local svc="$1"
  seen["$svc"]=1
}

while IFS= read -r path; do
  case "$path" in
    services/user-input-manager/backend/*)  add_service "uim-backend" ;;
    services/ticket-manager/backend/*)      add_service "tm-backend" ;;
    services/orchestrator/*)                add_service "orchestrator" ;;
    services/context-distiller/*)           add_service "context-distiller" ;;
    services/agent-dispatcher/*)            add_service "agent-dispatcher" ;;
    services/agent-tools/*)                 add_service "agent-tools" ;;
    services/user-input-manager/frontend/*) add_service "uim-frontend" ;;
    services/ticket-manager/frontend/*)     add_service "tm-frontend" ;;
    infra/nginx/*)                          add_service "nginx" ;;
    # docs/specs/.env.example/postgres-init → no rebuild
    infra/.env.example)                     ;;
    infra/postgres/*)                       ;;
    specs/*)                                ;;
    *.md)                                   ;;
  esac
done <<< "$CHANGED"

# Build JSON array from associative array keys
result="["
first=true
for svc in "${!seen[@]}"; do
  if [ "$first" = true ]; then
    result="${result}\"${svc}\""
    first=false
  else
    result="${result},\"${svc}\""
  fi
done
result="${result}]"

echo "$result"
exit 0
