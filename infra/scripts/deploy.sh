#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
OWNER=""
SKIP_BUILD=false
SKIP_PUSH=false
SKIP_APPLY=false

usage() {
  echo "Usage: $0 --owner <github-owner> [--skip-build] [--skip-push] [--skip-apply]"
  echo ""
  echo "  --owner       GitHub owner (e.g. mordanov)"
  echo "  --skip-build  Skip docker build steps"
  echo "  --skip-push   Skip docker push steps"
  echo "  --skip-apply  Skip kubectl apply + rollout restart"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --owner) OWNER="$2"; shift 2 ;;
    --skip-build) SKIP_BUILD=true; shift ;;
    --skip-push) SKIP_PUSH=true; shift ;;
    --skip-apply) SKIP_APPLY=true; shift ;;
    *) echo "Unknown flag: $1"; usage ;;
  esac
done

[[ -z "$OWNER" ]] && usage

SHA=$(git -C "$REPO_ROOT" rev-parse HEAD)
REGISTRY="ghcr.io/$OWNER"

log() { echo "[deploy] $*"; }

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

BACKENDS=(
  user-input-manager
  ticket-manager
  orchestrator
  context-distiller
  agent-tools
  agent-dispatcher
)

FRONTENDS=(
  user-input-manager
  ticket-manager
)

if [[ "$SKIP_BUILD" == false ]]; then
  log "Building backend images (SHA=$SHA)..."
  for SVC in "${BACKENDS[@]}"; do
    log "  building $SVC..."
    # Some services have Dockerfile at root, others inside backend/
    if [[ -f "$REPO_ROOT/services/$SVC/backend/Dockerfile" ]]; then
      CTX="$REPO_ROOT/services/$SVC/backend/"
    else
      CTX="$REPO_ROOT/services/$SVC/"
    fi
    docker build -t "$REGISTRY/$SVC:$SHA" "$CTX"
  done

  log "Building frontend images..."
  docker build -t "$REGISTRY/uim-frontend:$SHA" "$REPO_ROOT/services/user-input-manager/frontend/"
  docker build -t "$REGISTRY/tm-frontend:$SHA"  "$REPO_ROOT/services/ticket-manager/frontend/"
fi

# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------

if [[ "$SKIP_PUSH" == false ]]; then
  log "Pushing images..."
  for SVC in "${BACKENDS[@]}"; do
    log "  pushing $SVC..."
    docker push "$REGISTRY/$SVC:$SHA"
  done
  docker push "$REGISTRY/uim-frontend:$SHA"
  docker push "$REGISTRY/tm-frontend:$SHA"
fi

# ---------------------------------------------------------------------------
# Apply manifests with SHA substituted
# ---------------------------------------------------------------------------

if [[ "$SKIP_APPLY" == false ]]; then
  log "Applying manifests (SHA=$SHA, OWNER=$OWNER)..."

  # Work on a temp copy so we don't dirty the repo
  TMPDIR=$(mktemp -d)
  trap 'rm -rf "$TMPDIR"' EXIT

  cp -r "$REPO_ROOT/k8s" "$TMPDIR/"

  # Substitute placeholders AND tagless images
  find "$TMPDIR/k8s" -name '*.yaml' | while read -r f; do
    sed -i "s|:REPLACE_SHA|:$SHA|g"       "$f"
    sed -i "s|/OWNER/|/$OWNER/|g"         "$f"
    # Tag images that have no tag (no colon after the image name)
    sed -i "s|ghcr.io/$OWNER/\([^:]*\)$|ghcr.io/$OWNER/\1:$SHA|g" "$f"
  done

  for DIR in namespace.yaml configmaps infrastructure backends frontends ingress; do
    TARGET="$TMPDIR/k8s/$DIR"
    [[ -e "$TARGET" ]] || continue
    if [[ -f "$TARGET" ]]; then
      kubectl apply -f "$TARGET"
    else
      kubectl apply -R -f "$TARGET"
    fi
  done

  log "Restarting deployments..."
  kubectl rollout restart deployment \
    user-input-manager \
    ticket-manager \
    orchestrator \
    context-distiller \
    agent-tools \
    agent-dispatcher \
    uim-frontend \
    tm-frontend \
    -n dark-factory

  log "Waiting for rollouts..."
  for DEP in user-input-manager ticket-manager orchestrator context-distiller agent-tools agent-dispatcher uim-frontend tm-frontend; do
    kubectl rollout status deployment/"$DEP" -n dark-factory --timeout=120s
  done
fi

log "Done. SHA=$SHA"
