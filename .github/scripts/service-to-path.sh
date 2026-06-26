#!/usr/bin/env bash
# Given a service name, prints two lines:
#   1. Docker Compose service name
#   2. Build context path relative to repo root
# Exits 1 for unknown service names.
set -euo pipefail

SERVICE="${1:-}"

if [ -z "$SERVICE" ]; then
  echo "Usage: service-to-path.sh <service-name>" >&2
  exit 1
fi

case "$SERVICE" in
  uim-backend)       echo "user-input-manager"; echo "services/user-input-manager/backend" ;;
  tm-backend)        echo "ticket-manager";     echo "services/ticket-manager/backend" ;;
  orchestrator)      echo "orchestrator";       echo "services/orchestrator" ;;
  context-distiller) echo "context-distiller";  echo "services/context-distiller" ;;
  agent-dispatcher)  echo "agent-dispatcher";   echo "services/agent-dispatcher" ;;
  agent-tools)       echo "agent-tools";        echo "services/agent-tools" ;;
  uim-frontend)      echo "uim-frontend";       echo "services/user-input-manager/frontend" ;;
  tm-frontend)       echo "tm-frontend";        echo "services/ticket-manager/frontend" ;;
  nginx)             echo "nginx";              echo "infra/nginx" ;;
  *)
    echo "Unknown service: $SERVICE" >&2
    exit 1
    ;;
esac
