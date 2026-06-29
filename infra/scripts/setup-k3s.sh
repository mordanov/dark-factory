#!/bin/bash
# Idempotent k3s cluster setup for Ubuntu 26.04 VPS.
# Installs: k3s (no Traefik), Helm 3, NGINX Ingress Controller, cert-manager,
#           Kubernetes Dashboard (with RBAC and Ingress).
# Safe to run multiple times — each step checks before acting.
#
# Usage: bash setup-k3s.sh --dashboard-password <password>
#        (re-execs itself with sudo if not already root)
#
set -euo pipefail

[ "$(id -u)" -ne 0 ] && exec sudo bash "$0" "$@"

INGRESS_NGINX_VERSION="4.11.3"
CERT_MANAGER_VERSION="v1.16.2"
HEADLAMP_VERSION="0.43.0"
KUBECONFIG_PATH="/etc/rancher/k3s/k3s.yaml"
DASHBOARD_PASSWORD=""

log() { echo "[setup-k3s] $*"; }
die() { echo "[setup-k3s] ERROR: $*" >&2; exit 1; }

# ── Parse arguments ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dashboard-password)
      DASHBOARD_PASSWORD="$2"
      shift 2
      ;;
    *)
      die "Unknown argument: $1. Usage: bash setup-k3s.sh --dashboard-password <password>"
      ;;
  esac
done

[ -z "$DASHBOARD_PASSWORD" ] && die "--dashboard-password is required"

# ── 1. Install k3s (no Traefik) ───────────────────────────────────────────────
if command -v k3s &>/dev/null && k3s kubectl get nodes &>/dev/null 2>&1; then
  log "k3s already installed and running — skipping install"
else
  log "Installing k3s (--disable traefik)..."
  curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable traefik" sh -
  log "Waiting for k3s to be ready..."
  timeout 120 bash -c 'until k3s kubectl get nodes 2>/dev/null | grep -q " Ready"; do sleep 3; done'
  log "k3s node is Ready"
fi

export KUBECONFIG="$KUBECONFIG_PATH"

# ── 2. Install Helm 3 ─────────────────────────────────────────────────────────
if command -v helm &>/dev/null; then
  log "Helm already installed: $(helm version --short)"
else
  log "Installing Helm 3..."
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
  log "Helm installed: $(helm version --short)"
fi

# ── 3. Add Helm repositories ──────────────────────────────────────────────────
helm_repo_add() {
  local name="$1" url="$2"
  if helm repo list 2>/dev/null | grep -q "^${name}[[:space:]]"; then
    log "Helm repo '${name}' already registered — skipping add"
  else
    log "Adding Helm repo '${name}' (${url})..."
    helm repo add "${name}" "${url}"
  fi
  helm repo update "${name}"
}

helm_repo_add ingress-nginx    https://kubernetes.github.io/ingress-nginx
helm_repo_add jetstack         https://charts.jetstack.io
helm_repo_add headlamp             https://kubernetes-sigs.github.io/headlamp/

# ── 4. Install NGINX Ingress Controller ───────────────────────────────────────
if helm status ingress-nginx -n ingress-nginx &>/dev/null 2>&1; then
  log "NGINX Ingress Controller already installed — skipping"
else
  log "Installing NGINX Ingress Controller v${INGRESS_NGINX_VERSION}..."
  helm install ingress-nginx ingress-nginx/ingress-nginx \
    --namespace ingress-nginx \
    --create-namespace \
    --version "${INGRESS_NGINX_VERSION}" \
    --set controller.service.type=LoadBalancer \
    --wait --timeout 120s
  log "NGINX Ingress Controller installed"
fi

# ── 5. Install cert-manager ───────────────────────────────────────────────────
if helm status cert-manager -n cert-manager &>/dev/null 2>&1; then
  log "cert-manager already installed — skipping"
else
  log "Installing cert-manager ${CERT_MANAGER_VERSION}..."
  helm install cert-manager jetstack/cert-manager \
    --namespace cert-manager \
    --create-namespace \
    --version "${CERT_MANAGER_VERSION}" \
    --set crds.enabled=true \
    --wait --timeout 120s
  log "cert-manager installed"
fi

# ── 6. Install Headlamp ───────────────────────────────────────────────────────
if helm status headlamp -n headlamp &>/dev/null 2>&1; then
  log "Headlamp already installed — skipping"
else
  log "Installing Headlamp v${HEADLAMP_VERSION}..."
  helm install headlamp headlamp/headlamp \
    --namespace headlamp \
    --create-namespace \
    --version "${HEADLAMP_VERSION}" \
    --set ingress.enabled=false \
    --set service.type=ClusterIP \
    --wait --timeout 120s
  log "Headlamp installed"
fi

# ── 7. Configure kubeconfig for current user ─────────────────────────────────
DEST_KUBECONFIG="${HOME}/.kube/config"
mkdir -p "${HOME}/.kube"
if [ -f "$DEST_KUBECONFIG" ]; then
  log "kubeconfig already exists at ${DEST_KUBECONFIG} — skipping copy"
else
  sudo cp "$KUBECONFIG_PATH" "$DEST_KUBECONFIG"
  sudo chown "$(id -u):$(id -g)" "$DEST_KUBECONFIG"
  chmod 600 "$DEST_KUBECONFIG"
  log "kubeconfig written to ${DEST_KUBECONFIG}"
fi

# ── 8. Apply Headlamp Ingress ─────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MONITORING_MANIFESTS="${REPO_ROOT}/k8s/monitoring"

if [ ! -d "$MONITORING_MANIFESTS" ]; then
  die "Cannot find k8s/monitoring/ at ${MONITORING_MANIFESTS}. Run from a checkout of the repo."
fi

log "Applying Headlamp Ingress..."
kubectl apply -f "${MONITORING_MANIFESTS}/headlamp-ingress.yaml"

# ── 9. Create Headlamp basic-auth secret ──────────────────────────────────────
if kubectl get secret headlamp-basic-auth -n headlamp &>/dev/null 2>&1; then
  log "headlamp-basic-auth secret already exists — skipping"
else
  if ! command -v htpasswd &>/dev/null; then
    die "htpasswd not found. Install it with: apt-get install -y apache2-utils"
  fi
  log "Creating headlamp-basic-auth secret..."
  kubectl create secret generic headlamp-basic-auth \
    --from-literal=auth="$(htpasswd -nb admin "${DASHBOARD_PASSWORD}")" \
    -n headlamp
  log "headlamp-basic-auth secret created"
fi

# ── 10. Health check ───────────────────────────────────────────────────────────
log "Verifying cluster health..."
NODE_STATUS=$(kubectl get nodes --no-headers 2>/dev/null | awk '{print $2}' | head -1)
if [ "$NODE_STATUS" != "Ready" ]; then
  die "Node is not Ready (status: ${NODE_STATUS:-unknown}). Check: kubectl get nodes"
fi

INGRESS_PODS=$(kubectl get pods -n ingress-nginx --no-headers 2>/dev/null | grep -c "Running" || true)
if [ "$INGRESS_PODS" -eq 0 ]; then
  die "No NGINX Ingress Controller pods running. Check: kubectl get pods -n ingress-nginx"
fi

CERTMGR_PODS=$(kubectl get pods -n cert-manager --no-headers 2>/dev/null | grep -c "Running" || true)
if [ "$CERTMGR_PODS" -eq 0 ]; then
  die "No cert-manager pods running. Check: kubectl get pods -n cert-manager"
fi

log "Cluster is healthy:"
kubectl get nodes
log ""
log "Setup complete. Next steps:"
log "  1. Copy kubeconfig to local machine:"
log "     scp <user>@<vps-ip>:${DEST_KUBECONFIG} ~/.kube/dark-factory-k3s.yaml"
log "     sed -i 's/127.0.0.1/<vps-public-ip>/g' ~/.kube/dark-factory-k3s.yaml"
log "  2. Open https://k8s.dark-factory.local — Headlamp will prompt for a token."
log "     Generate one with:"
log "     kubectl create token headlamp -n headlamp --duration=8760h"
log "  3. Follow: specs/007-k3s-migration/quickstart.md"
