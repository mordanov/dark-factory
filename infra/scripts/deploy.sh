#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------
OWNER=""
SERVICES=()
SKIP_BUILD=false
SKIP_PUSH=false
SKIP_APPLY=false

usage() {
  echo "Usage: $0 --owner <github-owner> [--service <name>] [--skip-build] [--skip-push] [--skip-apply]"
  echo ""
  echo "  --owner       GitHub owner (e.g. mordanov)"
  echo "  --service     Deploy only this service (can be repeated). Omit to deploy all."
  echo "                Backend names: user-input-manager ticket-manager orchestrator"
  echo "                               context-distiller agent-tools agent-dispatcher"
  echo "                Frontend names: uim-frontend tm-frontend"
  echo "  --skip-build  Skip docker build steps"
  echo "  --skip-push   Skip docker push steps"
  echo "  --skip-apply  Skip kubectl apply + rollout restart"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --owner)   OWNER="$2"; shift 2 ;;
    --service) SERVICES+=("$2"); shift 2 ;;
    --skip-build) SKIP_BUILD=true; shift ;;
    --skip-push)  SKIP_PUSH=true; shift ;;
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

ALL_BACKENDS=(
  user-input-manager
  ticket-manager
  orchestrator
  context-distiller
  agent-tools
  agent-dispatcher
)
ALL_FRONTENDS=(uim-frontend tm-frontend)
# Map frontend image name → source dir
declare -A FRONTEND_SRC=(
  [uim-frontend]="services/user-input-manager/frontend/"
  [tm-frontend]="services/ticket-manager/frontend/"
)

# If --service was given, scope work to those services only
if [[ ${#SERVICES[@]} -eq 0 ]]; then
  BUILD_BACKENDS=("${ALL_BACKENDS[@]}")
  BUILD_FRONTENDS=("${ALL_FRONTENDS[@]}")
  DEPLOY_SERVICES=("${ALL_BACKENDS[@]}" "${ALL_FRONTENDS[@]}")
else
  BUILD_BACKENDS=()
  BUILD_FRONTENDS=()
  DEPLOY_SERVICES=()
  for SVC in "${SERVICES[@]}"; do
    # Check if it's a known backend or frontend
    is_backend=false
    for b in "${ALL_BACKENDS[@]}"; do [[ "$b" == "$SVC" ]] && is_backend=true; done
    is_frontend=false
    for f in "${ALL_FRONTENDS[@]}"; do [[ "$f" == "$SVC" ]] && is_frontend=true; done

    if $is_backend; then
      BUILD_BACKENDS+=("$SVC")
      DEPLOY_SERVICES+=("$SVC")
    elif $is_frontend; then
      BUILD_FRONTENDS+=("$SVC")
      DEPLOY_SERVICES+=("$SVC")
    else
      echo "[deploy] Unknown service: $SVC"; usage
    fi
  done
fi

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

if [[ "$SKIP_BUILD" == false ]]; then
  if [[ ${#BUILD_BACKENDS[@]} -gt 0 ]]; then
    log "Building backend images (SHA=$SHA)..."
    for SVC in "${BUILD_BACKENDS[@]}"; do
      log "  building $SVC..."
      if [[ -f "$REPO_ROOT/services/$SVC/backend/Dockerfile" ]]; then
        CTX="$REPO_ROOT/services/$SVC/backend/"
      else
        CTX="$REPO_ROOT/services/$SVC/"
      fi
      docker build -t "$REGISTRY/$SVC:$SHA" "$CTX"
    done
  fi

  if [[ ${#BUILD_FRONTENDS[@]} -gt 0 ]]; then
    log "Building frontend images..."
    KEYCLOAK_URL="${VITE_KEYCLOAK_URL:-https://dqaifactory.ru}"
    for SVC in "${BUILD_FRONTENDS[@]}"; do
      log "  building $SVC..."
      case "$SVC" in
        uim-frontend) KC_CLIENT_ID=uim-frontend ;;
        tm-frontend)  KC_CLIENT_ID=tm-frontend ;;
        *)            KC_CLIENT_ID=$SVC ;;
      esac
      docker build \
        --build-arg "VITE_KEYCLOAK_URL=$KEYCLOAK_URL" \
        --build-arg "VITE_KEYCLOAK_REALM=dark-factory" \
        --build-arg "VITE_KEYCLOAK_CLIENT_ID=$KC_CLIENT_ID" \
        -t "$REGISTRY/$SVC:$SHA" \
        "$REPO_ROOT/${FRONTEND_SRC[$SVC]}"
    done
  fi
fi

# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------

if [[ "$SKIP_PUSH" == false ]]; then
  log "Pushing images..."
  for SVC in "${BUILD_BACKENDS[@]:-}"; do
    [[ -z "$SVC" ]] && continue
    log "  pushing $SVC..."
    docker push "$REGISTRY/$SVC:$SHA"
  done
  for SVC in "${BUILD_FRONTENDS[@]:-}"; do
    [[ -z "$SVC" ]] && continue
    log "  pushing $SVC..."
    docker push "$REGISTRY/$SVC:$SHA"
  done
fi

# ---------------------------------------------------------------------------
# Apply manifests with SHA substituted
# ---------------------------------------------------------------------------

if [[ "$SKIP_APPLY" == false ]]; then
  log "Applying manifests (SHA=$SHA, OWNER=$OWNER)..."

  TMPDIR=$(mktemp -d)
  trap 'rm -rf "$TMPDIR"' EXIT

  cp -r "$REPO_ROOT/k8s" "$TMPDIR/"

  find "$TMPDIR/k8s" -name '*.yaml' | while read -r f; do
    sed -i "s|:REPLACE_SHA|:$SHA|g"       "$f"
    sed -i "s|/OWNER/|/$OWNER/|g"         "$f"
    sed -i "s|ghcr.io/$OWNER/\([^:]*\)$|ghcr.io/$OWNER/\1:$SHA|g" "$f"
  done

  # Regenerate agent-registry ConfigMap from source file
  kubectl create configmap agent-registry \
    --from-file=registry.yaml="$REPO_ROOT/development/agents/registry.yaml" \
    -n dark-factory --dry-run=client -o yaml \
    > "$TMPDIR/k8s/configmaps/agent-registry.yaml"

  if [[ ${#SERVICES[@]} -eq 0 ]]; then
    # Full apply
    for DIR in namespace.yaml configmaps infrastructure backends frontends ingress; do
      TARGET="$TMPDIR/k8s/$DIR"
      [[ -e "$TARGET" ]] || continue
      if [[ -f "$TARGET" ]]; then
        kubectl apply -f "$TARGET"
      else
        kubectl apply -R -f "$TARGET"
      fi
    done
  else
    # Apply only the specific deployment manifest(s)
    for SVC in "${DEPLOY_SERVICES[@]}"; do
      for MANIFEST in "$TMPDIR/k8s/backends/${SVC}-deployment.yaml" \
                      "$TMPDIR/k8s/frontends/${SVC}-deployment.yaml"; do
        [[ -f "$MANIFEST" ]] && kubectl apply -f "$MANIFEST"
      done
    done
  fi

  log "Restarting deployments: ${DEPLOY_SERVICES[*]}"
  kubectl rollout restart deployment "${DEPLOY_SERVICES[@]}" -n dark-factory

  log "Waiting for rollouts..."
  for DEP in "${DEPLOY_SERVICES[@]}"; do
    kubectl rollout status deployment/"$DEP" -n dark-factory --timeout=120s
  done
fi

log "Done. SHA=$SHA"
