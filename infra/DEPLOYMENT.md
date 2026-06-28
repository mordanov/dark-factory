# Deployment Guide — Dark Factory

> **Migration note (feature 007-k3s-migration):** This project has been migrated from Docker
> Compose + VPS SSH to **k3s (Kubernetes)**. The Docker Compose sections below are preserved
> for reference. The k3s deployment procedure starts at [k3s Deployment](#k3s-deployment).

---

## k3s Deployment

### GitHub Actions Secrets

After the k3s migration, replace the three VPS SSH secrets with two k8s secrets:

**Add these secrets:**

| Secret | Value | How to generate |
|--------|-------|----------------|
| `KUBECONFIG` | base64-encoded kubeconfig | `cat ~/.kube/dark-factory-k3s.yaml \| base64` |
| `GHCR_TOKEN` | GitHub PAT with `write:packages` scope | GitHub → Settings → Developer Settings → PATs |

**Remove these secrets (no longer used):**

| Secret | Reason |
|--------|--------|
| `VPS_HOST` | SSH deploy replaced by kubectl |
| `VPS_USER` | SSH deploy replaced by kubectl |
| `VPS_SSH_KEY` | SSH deploy replaced by kubectl |

> **Constitution note:** This change supersedes Principles XXII (VPS-only builds) and XXVI
> (3-secret CI rule). A container registry is architecturally required for Kubernetes.
> See `specs/007-k3s-migration/plan.md` — Constitution Check section.

---

### First-Time k3s Cluster Setup

```bash
# 1. Copy and run setup script on VPS
scp infra/scripts/setup-k3s.sh <user>@<vps-ip>:~/
ssh <user>@<vps-ip> "bash setup-k3s.sh"

# 2. Copy kubeconfig to local machine
scp <user>@<vps-ip>:/etc/rancher/k3s/k3s.yaml ~/.kube/dark-factory-k3s.yaml
sed -i 's/127.0.0.1/<vps-public-ip>/g' ~/.kube/dark-factory-k3s.yaml
export KUBECONFIG=~/.kube/dark-factory-k3s.yaml

# 3. Create namespace and secrets (run once, manually — NEVER in CI)
kubectl create namespace dark-factory

kubectl create secret generic dark-factory-secrets \
  --from-env-file=infra/.env \
  -n dark-factory

kubectl create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<ghcr-token> \
  -n dark-factory
```

### Building and Pushing Initial Images

```bash
export OWNER=<github-repository-owner>
export SHA=$(git rev-parse HEAD)

for SERVICE in user-input-manager ticket-manager orchestrator context-distiller agent-tools agent-dispatcher uim-frontend tm-frontend; do
  docker build -t ghcr.io/$OWNER/$SERVICE:$SHA services/$SERVICE/
  docker push ghcr.io/$OWNER/$SERVICE:$SHA
done
```

Substitute image tags in manifests:
```bash
find k8s/ -name '*.yaml' -exec sed -i "s|REPLACE_SHA|$SHA|g; s|OWNER|$OWNER|g" {} \;
```

The `agent-registry` ConfigMap must be populated from the live registry.yaml:
```bash
kubectl create configmap agent-registry \
  --from-file=registry.yaml=development/agents/registry.yaml \
  -n dark-factory --dry-run=client -o yaml | kubectl apply -f -
```

### Apply Manifests

```bash
kubectl apply -f k8s/
```

### Run Database Migrations (first deploy)

```bash
for SERVICE in user-input-manager ticket-manager orchestrator context-distiller agent-dispatcher; do
  kubectl run alembic-$SERVICE \
    --image=ghcr.io/$OWNER/$SERVICE:$SHA \
    --rm --restart=Never -n dark-factory \
    --env-from=secret/dark-factory-secrets \
    -- alembic upgrade head
done
```

### cert-manager ClusterIssuers

```bash
# Apply ClusterIssuers (update email address in k8s/ingress/cluster-issuer.yaml first)
kubectl apply -f k8s/ingress/cluster-issuer.yaml

# Verify cert-manager obtained certificates after Ingress is applied
kubectl describe certificate dark-factory-tls -n dark-factory
```

### DNS Requirements

Before applying the Ingress, create DNS A records pointing to the VPS public IP:

| Hostname | Target |
|----------|--------|
| `studio.dark-factory.local` | VPS public IP |
| `tickets.dark-factory.local` | VPS public IP |
| `grafana.dark-factory.local` | VPS public IP |

### Verify Health

```bash
kubectl get pods -n dark-factory
kubectl rollout status deployment/user-input-manager -n dark-factory
kubectl rollout status deployment/keycloak -n dark-factory
kubectl rollout status statefulset/postgres -n dark-factory
kubectl rollout status statefulset/mongo -n dark-factory
```

### Rollback (manual)

```bash
kubectl rollout undo deployment/<service-name> -n dark-factory

# Rollback to a specific revision:
kubectl rollout history deployment/<service-name> -n dark-factory
kubectl rollout undo deployment/<service-name> --to-revision=<n> -n dark-factory
```

---

## How the k3s CI/CD Pipeline Works (updated)

Every push to `main` triggers `.github/workflows/ci-cd.yml`:

1. **detect** — identifies which services changed (unchanged)
2. **validate** — ruff + docker build for changed services (unchanged)
3. **test** — pytest/vitest with SQLite + AUTH_MODE=local (unchanged)
4. **deploy** — for each changed service:
   - Writes `KUBECONFIG` secret to `~/.kube/config`
   - Logs in to GHCR with `GHCR_TOKEN`
   - Builds and pushes image to `ghcr.io/<owner>/<service>:<sha>`
   - For DB-backed services: runs `kubectl run --rm` Alembic migration
   - `kubectl set image` to update the Deployment
   - `kubectl rollout status --timeout=120s`
   - On failure: `kubectl rollout undo` + pipeline exits 1

---

## Observability (optional)

Install after core stack is verified:

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace \
  -f k8s/monitoring/values-prometheus.yaml

kubectl apply -f k8s/monitoring/service-monitors.yaml
kubectl apply -f k8s/monitoring/grafana-ingress.yaml
```

Create Grafana basic-auth secret before applying grafana-ingress:
```bash
kubectl create secret generic grafana-basic-auth \
  --from-literal=auth="$(htpasswd -nb admin <your-password>)" \
  -n monitoring
```

---

## Legacy: Docker Compose Deployment (pre-k3s)

> The sections below document the original VPS + Docker Compose deployment.
> They are retained for reference during the migration period.

### GitHub Actions Secrets (legacy)

Configure exactly three secrets in **Repository → Settings → Secrets → Actions**:

| Secret | Value |
|--------|-------|
| `VPS_HOST` | IP address of the Hetzner VPS |
| `VPS_USER` | SSH username (e.g. `ubuntu`) |
| `VPS_SSH_KEY` | Private SSH key (PEM format, e.g. `~/.ssh/id_ed25519`) |

**Nothing else.** No database passwords, API keys, Keycloak secrets, or application credentials belong here. All application configuration is sourced from `.env` on the VPS at runtime.

---

## First-Time VPS Setup

Run the idempotent setup script from the VPS as `root` or with `sudo`, passing the repository URL:

```bash
sudo bash /app/dark-factory/infra/scripts/setup-vps.sh https://github.com/your-org/dark-factory.git
```

If the repo is not yet present, clone it first:

```bash
git clone https://github.com/your-org/dark-factory.git /app/dark-factory
sudo bash /app/dark-factory/infra/scripts/setup-vps.sh https://github.com/your-org/dark-factory.git
```

> **Initial deployment note:** The pipeline uses `git diff HEAD^ HEAD` to detect changes. On the very first push to `main` (no parent commit), no changed services are detected and the pipeline does nothing. The **first deployment must be performed manually** via SSH before the pipeline takes over subsequent pushes:
> ```bash
> cd /app/dark-factory
> docker compose -f infra/docker-compose.yml build
> docker compose -f infra/docker-compose.yml run --rm <service> alembic upgrade head  # for each backend
> docker compose -f infra/docker-compose.yml up -d
> ```

The script:
- Installs Docker (official Docker apt repo) if not already installed
- Adds the deploy user to the `docker` group
- Verifies Docker Compose v2 is available
- Clones the repo to `/app/dark-factory/` if not present
- Prints a reminder to place the `.env` file

---

## Placing the Production `.env` File

The production environment file must be placed at `/app/dark-factory/infra/.env` before the first pipeline run. It is never committed to git or stored in GitHub.

```bash
# Copy your production .env to the VPS:
scp your-production.env ubuntu@<VPS_HOST>:/app/dark-factory/infra/.env
```

Use `infra/.env.example` as the reference for required variables.

---

## How the CI/CD Pipeline Works

Every push to `main` triggers `.github/workflows/ci-cd.yml`:

1. **detect** — identifies which services changed using path-based diff
2. **validate** — runs `ruff check` + `ruff format --check` for Python services; attempts `docker build` for all changed services (no VPS contact)
3. **test** — runs `pytest --cov --cov-fail-under=80` (backends) or `vitest` (frontends) with in-memory SQLite + AUTH_MODE=local
4. **deploy** — SSHs to the VPS and:
   - `git pull origin main`
   - Snapshots current images (`:rollback-TIMESTAMP`)
   - Builds new images on the VPS
   - Runs `alembic upgrade head` for each migration-enabled service
   - Restarts containers
   - Polls `/health` for up to 90 seconds per service
   - Auto-restores previous images if health check times out

Deployments are serialised: a second `git push` during an active deploy queues and waits (GitHub Actions concurrency group `production`).

---

## Optional: SSL/HTTPS Setup with Certbot

SSL is set up manually after HTTP is confirmed working. The certbot service is included in Docker Compose under the `certbot` profile and does **not** start with a normal `docker compose up`.

```bash
# On the VPS, after HTTP traffic is working:
docker compose -f infra/docker-compose.yml --profile certbot run --rm certbot \
  certonly --webroot --webroot-path=/var/www/certbot \
  -d studio.dark-factory.com -d tickets.dark-factory.com \
  --email admin@dark-factory.com --agree-tos
```

After the certificate is issued:
1. Uncomment the SSL server blocks in `infra/nginx/nginx.conf.template`
2. Restart nginx: `docker compose -f infra/docker-compose.yml restart nginx`

### Certbot Auto-Renewal (cron)

Add to root crontab on the VPS (`sudo crontab -e`):

```cron
0 3 * * * docker compose -f /app/dark-factory/infra/docker-compose.yml --profile certbot run --rm certbot renew --quiet && docker compose -f /app/dark-factory/infra/docker-compose.yml restart nginx
```

---

## Manual Rollback Procedure

Use when a defect is discovered after the automated health check window has passed.

1. Navigate to **Actions → Manual Rollback** in GitHub
2. Click **Run workflow**
3. Select the affected service (or `all`)
4. Enter a reason (required — appears in the audit log)
5. Click **Run workflow**

The workflow restores the most recent `:rollback-*` snapshot for the selected service(s) and restarts the container(s). Completion time: under 2 minutes for a single service.

### Rollback Snapshot Retention

The pipeline retains the **3 most recent rollback tags** per service. Older tags are deleted automatically during each deployment. If a snapshot has been garbage-collected, the manual rollback logs a warning for that service and continues with any remaining services in an `all` rollback.

### Audit Trail

Every manual rollback run records:
- **Actor**: GitHub username who triggered the workflow
- **Timestamp**: `github.run_started_at` (UTC)
- **Service**: selected service name
- **Reason**: operator-provided text
- **Run URL**: permanent link to the workflow run

The job log is the authoritative audit record. GitHub retains workflow logs for 90 days by default.

---

## Troubleshooting

### VPS unreachable during deploy

The `deploy` job fails with an SSH connection error. Validate and test results are preserved in the run log. No partial deployment occurs — old containers remain running.

### Migration succeeded but new container crashes

The pipeline auto-rolls back the container image. However, the migration is already applied to the database schema. To recover:
1. Trigger a manual rollback via the GitHub Actions UI to restore the container image
2. Assess whether the schema migration needs a manual down migration (`alembic downgrade -1`)

### Health check endpoint not available

Services without a `/health` endpoint (agent-tools, uim-frontend, tm-frontend, nginx) are treated as healthy immediately after container start. They are not monitored during the 90-second window.

### Check pipeline status from CLI

```bash
gh run list --limit 5
gh run watch
```
