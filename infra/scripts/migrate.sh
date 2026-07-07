#!/usr/bin/env bash
# Run Alembic migrations for one or all backend services.
# Usage:
#   ./infra/scripts/migrate.sh --owner <github-owner>
#   ./infra/scripts/migrate.sh --owner <github-owner> --service orchestrator
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

OWNER=""
SERVICES=()

usage() {
  echo "Usage: $0 --owner <github-owner> [--service <name>]"
  echo ""
  echo "  --owner    GitHub owner (e.g. mordanov)"
  echo "  --service  Migrate only this service (can be repeated). Omit for all."
  echo "             Valid: user-input-manager ticket-manager orchestrator"
  echo "                    context-distiller agent-dispatcher"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --owner)   OWNER="$2"; shift 2 ;;
    --service) SERVICES+=("$2"); shift 2 ;;
    *) echo "Unknown flag: $1"; usage ;;
  esac
done

[[ -z "$OWNER" ]] && usage

REGISTRY="ghcr.io/$OWNER"
SHA=$(kubectl get deployment/orchestrator -n dark-factory -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null | cut -d: -f2 || git -C "$REPO_ROOT" rev-parse HEAD)

log() { echo "[migrate] $*"; }

secret_val() {
  kubectl get secret dark-factory-secrets -n dark-factory \
    -o jsonpath="{.data.$1}" | base64 -d
}

declare -A DB_USER_KEY=(
  [user-input-manager]=UIM_DB_USER
  [ticket-manager]=TM_DB_USER
  [orchestrator]=ORCH_DB_USER
  [context-distiller]=DISTILLER_DB_USER
  [agent-dispatcher]=DISPATCHER_DB_USER
)
declare -A DB_PASS_KEY=(
  [user-input-manager]=UIM_DB_PASSWORD
  [ticket-manager]=TM_DB_PASSWORD
  [orchestrator]=ORCH_DB_PASSWORD
  [context-distiller]=DISTILLER_DB_PASSWORD
  [agent-dispatcher]=DISPATCHER_DB_PASSWORD
)
declare -A DB_NAME=(
  [user-input-manager]=df_user_input
  [ticket-manager]=df_ticket_manager
  [orchestrator]=df_orchestrator
  [context-distiller]=df_distiller
  [agent-dispatcher]=df_dispatcher
)

ALL_SERVICES=(user-input-manager ticket-manager orchestrator context-distiller agent-dispatcher)

if [[ ${#SERVICES[@]} -eq 0 ]]; then
  SERVICES=("${ALL_SERVICES[@]}")
fi

for SERVICE in "${SERVICES[@]}"; do
  if [[ -z "${DB_USER_KEY[$SERVICE]+_}" ]]; then
    echo "[migrate] Unknown service: $SERVICE"; usage
  fi

  POD="alembic-${SERVICE}"
  IMG="$REGISTRY/$SERVICE:$SHA"

  # Resolve image: prefer what's currently running in the deployment
  RUNNING_IMG=$(kubectl get deployment/"$SERVICE" -n dark-factory \
    -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "")
  [[ -n "$RUNNING_IMG" ]] && IMG="$RUNNING_IMG"

  log "Running migrations for $SERVICE (image: $IMG)..."

  # Clean up any previous failed pod
  kubectl delete pod "$POD" -n dark-factory --ignore-not-found

  U=$(secret_val "${DB_USER_KEY[$SERVICE]}")
  P=$(secret_val "${DB_PASS_KEY[$SERVICE]}")
  DB_URL="postgresql+asyncpg://$U:$P@postgres:5432/${DB_NAME[$SERVICE]}"

  # Write manifest to temp file to avoid shell quoting issues with special chars
  TMPFILE=$(mktemp /tmp/alembic-XXXXXX.yaml)
  trap 'rm -f "$TMPFILE"' EXIT

  cat > "$TMPFILE" <<MANIFEST
apiVersion: v1
kind: Pod
metadata:
  name: ${POD}
  namespace: dark-factory
spec:
  restartPolicy: Never
  imagePullSecrets:
    - name: ghcr-pull-secret
  containers:
    - name: ${POD}
      image: ${IMG}
      command: ["alembic", "upgrade", "head"]
      envFrom:
        - secretRef:
            name: dark-factory-secrets
      env:
        - name: DATABASE_URL
          value: "${DB_URL}"
MANIFEST

  kubectl apply -f "$TMPFILE"
  rm -f "$TMPFILE"
  trap - EXIT

  log "Waiting for $SERVICE migration pod to complete..."
  kubectl wait pod "$POD" -n dark-factory \
    --for=jsonpath='{.status.phase}'=Succeeded \
    --timeout=300s \
  || {
    echo "--- migration failed for $SERVICE ---"
    kubectl logs "$POD" -n dark-factory
    kubectl delete pod "$POD" -n dark-factory --ignore-not-found
    exit 1
  }

  kubectl logs "$POD" -n dark-factory
  kubectl delete pod "$POD" -n dark-factory
  log "$SERVICE migrations done."
done

log "All migrations complete."
