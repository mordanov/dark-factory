# Quickstart: k3s Migration

**Feature**: 007-k3s-migration

This guide walks through provisioning a fresh VPS, deploying the full Dark Factory stack to k3s, and verifying it is healthy.

## Prerequisites

- Ubuntu 26.04 VPS with a public IP address
- SSH access as a user with passwordless sudo
- DNS A records pointing `studio.dark-factory.local`, `tickets.dark-factory.local`, and `grafana.dark-factory.local` to the VPS IP
- `infra/.env` file with all production credentials (see `specs/007-k3s-migration/contracts/k8s-secret-schema.md`)
- `kubectl` installed on your local machine
- GHCR token with `write:packages` scope (for CI/CD; not needed for manual deploy)

---

## Step 1: Provision the VPS

Copy the setup script to the VPS and run it:

```bash
scp infra/scripts/setup-k3s.sh <user>@<vps-ip>:~/
ssh <user>@<vps-ip> "bash setup-k3s.sh"
```

The script installs k3s, Helm 3, NGINX Ingress Controller, and cert-manager. It exits non-zero if the cluster is not healthy. Expected runtime: ~5–8 minutes.

Verify from the VPS:
```bash
kubectl get nodes
# NAME   STATUS   ROLES                  AGE   VERSION
# vps    Ready    control-plane,master   2m    v1.x.x+k3s1
```

Copy the kubeconfig to your local machine:
```bash
scp <user>@<vps-ip>:/etc/rancher/k3s/k3s.yaml ~/.kube/dark-factory-k3s.yaml
# Replace 127.0.0.1 with the VPS public IP:
sed -i '' 's/127.0.0.1/<vps-public-ip>/g' ~/.kube/dark-factory-k3s.yaml   # macOS
# sed -i 's/127.0.0.1/<vps-public-ip>/g' ~/.kube/dark-factory-k3s.yaml  # Linux
export KUBECONFIG=~/.kube/dark-factory-k3s.yaml
```

---

## Step 2: Create the Namespace and Secret

```bash
kubectl create namespace dark-factory

# Populate the secret from infra/.env (operator runs this manually — never in CI)
kubectl create secret generic dark-factory-secrets \
  --from-env-file=infra/.env \
  -n dark-factory

# Create imagePullSecret for GHCR
kubectl create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<ghcr-token> \
  -n dark-factory
```

---

## Step 3: Build and Push Initial Images

For the first deploy, build and push all service images from your local machine:

```bash
export OWNER=<github-repository-owner>   # e.g. mordanov
export SHA=$(git rev-parse HEAD)

echo "<ghcr-token>" | docker login ghcr.io -u $OWNER --password-stdin

# Backends (Dockerfile is in backend/ subdirectory)
for SERVICE in user-input-manager ticket-manager orchestrator context-distiller agent-tools agent-dispatcher; do
  docker build -t ghcr.io/$OWNER/$SERVICE:$SHA services/$SERVICE/backend/
  docker push ghcr.io/$OWNER/$SERVICE:$SHA
done

# Frontends
docker build -t ghcr.io/$OWNER/uim-frontend:$SHA services/user-input-manager/frontend/
docker push ghcr.io/$OWNER/uim-frontend:$SHA

docker build -t ghcr.io/$OWNER/tm-frontend:$SHA services/ticket-manager/frontend/
docker push ghcr.io/$OWNER/tm-frontend:$SHA
```

Update the image tags in manifests:
```bash
# macOS
find k8s/ -name '*.yaml' -exec sed -i '' "s|:REPLACE_SHA|:$SHA|g" {} \;
find k8s/ -name '*.yaml' -exec sed -i '' "s|/OWNER/|/$OWNER/|g" {} \;
# Linux
# find k8s/ -name '*.yaml' -exec sed -i "s|:REPLACE_SHA|:$SHA|g" {} \;
# find k8s/ -name '*.yaml' -exec sed -i "s|/OWNER/|/$OWNER/|g" {} \;
```

---

## Step 4: Apply Manifests

Apply core manifests only — `k8s/monitoring/` is applied separately in Step 7 after kube-prometheus-stack is installed (ServiceMonitor CRDs don't exist yet, and Helm values files aren't k8s manifests):

```bash
kubectl apply -R -f k8s/namespace.yaml
kubectl apply -R -f k8s/configmaps/
kubectl apply -R -f k8s/infrastructure/
kubectl apply -R -f k8s/backends/
kubectl apply -R -f k8s/frontends/
kubectl apply -R -f k8s/ingress/
```

cert-manager will begin certificate provisioning immediately (requires DNS to be live).

---

## Step 5: Run Database Migrations

Requires `$OWNER` and `$SHA` exported in Step 3. Run from your local machine (uses the kubeconfig set in Step 1):

```bash
# If starting a new shell since Step 3:
export OWNER=<github-repository-owner>
export SHA=$(git rev-parse HEAD)

for SERVICE in user-input-manager ticket-manager orchestrator context-distiller agent-dispatcher; do
  POD="alembic-${SERVICE}"

  kubectl run "$POD" \
    --image=ghcr.io/$OWNER/$SERVICE:$SHA \
    --restart=Never -n dark-factory \
    --env-from=secret/dark-factory-secrets \
    --overrides='{"spec":{"imagePullSecrets":[{"name":"ghcr-pull-secret"}]}}' \
    -- alembic upgrade head

  # Wait up to 5 minutes for the pod to finish
  kubectl wait pod "$POD" -n dark-factory \
    --for=jsonpath='{.status.phase}'=Succeeded \
    --timeout=300s \
  || {
    echo "--- logs for failed migration: $SERVICE ---"
    kubectl logs "$POD" -n dark-factory
    kubectl delete pod "$POD" -n dark-factory --ignore-not-found
    exit 1
  }

  kubectl logs "$POD" -n dark-factory
  kubectl delete pod "$POD" -n dark-factory
done
```

---

## Step 6: Verify the Stack

```bash
# All pods should be Running
kubectl get pods -n dark-factory

# Check each service Deployment
kubectl rollout status deployment/user-input-manager -n dark-factory
kubectl rollout status deployment/ticket-manager -n dark-factory
kubectl rollout status deployment/orchestrator -n dark-factory
kubectl rollout status deployment/context-distiller -n dark-factory
kubectl rollout status deployment/agent-tools -n dark-factory
kubectl rollout status deployment/agent-dispatcher -n dark-factory
kubectl rollout status deployment/uim-frontend -n dark-factory
kubectl rollout status deployment/tm-frontend -n dark-factory
kubectl rollout status deployment/keycloak -n dark-factory
kubectl rollout status deployment/oauth2-proxy -n dark-factory

# StatefulSets
kubectl rollout status statefulset/postgres -n dark-factory
kubectl rollout status statefulset/mongo -n dark-factory

# Ingress
kubectl get ingress -n dark-factory
```

Open `https://studio.dark-factory.local` in a browser — you should see the Keycloak login page.

---

## Step 7: Install Observability (optional, after core stack is verified)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace \
  -f k8s/monitoring/values-prometheus.yaml

kubectl apply -f k8s/monitoring/service-monitors.yaml
kubectl apply -f k8s/monitoring/grafana-ingress.yaml
```

Verify Grafana at `https://grafana.dark-factory.local`.

---

## Updating CI/CD Secrets

After the cluster is provisioned:

1. **Add to GitHub Actions secrets**:
   - `KUBECONFIG`: `cat ~/.kube/dark-factory-k3s.yaml | base64`
   - `GHCR_TOKEN`: GitHub PAT with `write:packages`

2. **Remove from GitHub Actions secrets**:
   - `VPS_HOST`
   - `VPS_USER`
   - `VPS_SSH_KEY`

See `specs/007-k3s-migration/contracts/cicd-deploy-contract.md` for the full deploy stage specification.

---

## Rollback (manual)

```bash
kubectl rollout undo deployment/<service-name> -n dark-factory
```

To roll back to a specific revision:
```bash
kubectl rollout history deployment/<service-name> -n dark-factory
kubectl rollout undo deployment/<service-name> --to-revision=<n> -n dark-factory
```
