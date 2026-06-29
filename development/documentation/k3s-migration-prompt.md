# Migrating Dark Factory from Docker Compose to k3s on Ubuntu 26.04 VPS

I'm migrating the **Dark Factory** platform from Docker Compose to k3s (lightweight Kubernetes).
Below is the full context extracted from my actual `docker-compose.yml` and GitHub Actions
`ci-cd.yml`. Please use this to produce concrete, ready-to-run output — not generic templates.

---

## Stack Summary

**Infrastructure services:**
- `keycloak:25.0` — identity/auth, depends on postgres, imports a realm at boot via a custom
  entrypoint script and `realm-export.json`
- `oauth2-proxy:v7.7.1` — sits in front of services, depends on keycloak
- `postgres:16-alpine` — single instance serving **6 separate databases**
  (`df_user_input`, `df_ticket_manager`, `df_orchestrator`, `df_distiller`, `df_dispatcher`,
  `keycloak`), initialized via `postgres/init/01_create_databases.sql`
- `mongo:7-jammy` — used by orchestrator and context-distiller
- `nginx` — reverse proxy with Let's Encrypt TLS, routes by hostname
  (`studio.dark-factory.local`, `tickets.dark-factory.local`)
- `certbot` — optional certbot profile for SSL renewal

**Backend services (Python/FastAPI, port 8000 each, health at `/health` or `/api/health`):**
- `user-input-manager` — PostgreSQL + Keycloak + OpenAI
- `ticket-manager` — PostgreSQL + Keycloak
- `orchestrator` — PostgreSQL + MongoDB + Keycloak + OpenAI
- `context-distiller` — PostgreSQL + MongoDB + Keycloak + OpenAI
- `agent-tools` — Keycloak only (no DB)
- `agent-dispatcher` — PostgreSQL + Keycloak + OpenAI, mounts
  `development/agents/registry.yaml` read-only

**Frontend services (Nginx static, port 80):**
- `uim-frontend`
- `tm-frontend`

**Networking:** all services on an `internal` bridge; only `nginx` is on `external` (port 80 host).

**Volumes:** `postgres_data`, `mongo_data`, `letsencrypt`, `certbot_www`

**Current CI/CD:** GitHub Actions — 4 stages:
1. **detect** — bash script detects which of 9 services changed
2. **validate** — ruff lint/format + Docker build per changed service
3. **test** — pytest (≥80% coverage) for Python backends; Vitest for frontends
4. **deploy** — SSH into VPS → `git pull` → `docker build` on VPS → Alembic migrations →
   `docker compose up -d` → 90-second health poll → auto-rollback on failure

---

## What I Need

### 1. VPS Setup Script

A single idempotent `setup-k3s.sh` for Ubuntu 26.04 that:
- Installs k3s (latest stable), **without Traefik** (`--disable traefik`) — we bring our own
  ingress
- Installs Helm 3
- Installs NGINX Ingress Controller via Helm (to replace the current nginx container)
- Installs cert-manager via Helm (to replace certbot)
- Configures `~/.kube/config` for the deploy user
- Verifies the cluster is healthy (`kubectl get nodes`) before exiting

### 2. Docker Compose → k3s Manifests

Convert the full stack into Kubernetes manifests under a `k8s/` directory.
Key requirements:

- Use a single `Namespace`: `dark-factory`
- **Secrets:** create a `dark-factory-secrets` Secret from all `.env` variables
  (all the `KC_*`, `POSTGRES_*`, `UIM_DB_*`, `OPENAI_API_KEY`, etc.)
- **Postgres:** single `StatefulSet` with a `PersistentVolumeClaim`; the init SQL script
  (`01_create_databases.sql`) must be mounted via a `ConfigMap`
- **MongoDB:** `StatefulSet` with a `PVC`
- **Keycloak:** `Deployment`; the realm-import entrypoint logic and `realm-export.json` +
  `substitute-env.sh` must be preserved — mount them via `ConfigMap`; must wait for postgres
  via an `initContainer`
- **oauth2-proxy:** `Deployment`; mount `config.cfg` via `ConfigMap`
- **6 backend services:** `Deployment` each, with `/health` or `/api/health` readiness
  and liveness probes; `agent-dispatcher` needs the `registry.yaml` as a `ConfigMap` volume
- **2 frontend services:** `Deployment` each
- **Ingress:** replace nginx container with an `Ingress` resource routing
  `studio.dark-factory.local` → `uim-frontend` and `tickets.dark-factory.local` → `tm-frontend`;
  TLS via cert-manager `ClusterIssuer`
- **Certbot:** replaced entirely by cert-manager — no k8s manifest needed, just cert-manager
  config

Inter-service DNS: use k8s `Service` names within the namespace
(e.g. `http://keycloak:8080`, `postgres:5432`, `mongo:27017`) — same names as Docker Compose
so env vars need minimal changes.

### 3. CI/CD Pipeline Updates

Update the existing 4-stage GitHub Actions pipeline (`ci-cd.yml`). Keep the detect / validate /
test stages unchanged. Update only **Stage 4 (deploy)**:

- Remove the SSH + `docker compose` deploy logic
- Add a step that writes `${{ secrets.KUBECONFIG }}` to `~/.kube/config`
- For each changed service, build the Docker image and **push to a registry**
  (assume `ghcr.io/${{ github.repository_owner }}/<service>:${{ github.sha }}`)
- Update the image tag in the relevant `Deployment` manifest using `kubectl set image`
  or `kustomize`
- Run Alembic migrations via `kubectl run --rm` or a `Job` for the 5 DB-backed Python services
- Apply manifests: `kubectl apply -f k8s/`
- Replace the 90-second health poll with `kubectl rollout status deployment/<name> -n
  dark-factory --timeout=120s` for each changed service
- Replace the manual rollback logic with `kubectl rollout undo deployment/<name>`
  on failure
- Store `KUBECONFIG` and `GHCR_TOKEN` as GitHub Actions secrets (document which secrets
  to add and remove)

### 4. Observability Dashboard

- Install **kube-prometheus-stack** via Helm into a `monitoring` namespace
- Pre-configure dashboards for: node CPU/memory, pod restarts, HTTP request latency per service
- Expose Grafana via an `Ingress` at `grafana.dark-factory.local` with basic auth
- Add a `ServiceMonitor` for each backend service (they already expose `/health`;
  add `/metrics` if not present)
- Include Prometheus scrape config for postgres and mongo exporters

---

## Secrets Reference

All secrets currently come from `infra/.env`. Here is the full list to migrate into a
Kubernetes Secret:

```
# Postgres
POSTGRES_USER, POSTGRES_PASSWORD
UIM_DB_USER, UIM_DB_PASSWORD
TM_DB_USER, TM_DB_PASSWORD
ORCH_DB_USER, ORCH_DB_PASSWORD
DISTILLER_DB_USER, DISTILLER_DB_PASSWORD
DISPATCHER_DB_USER, DISPATCHER_DB_PASSWORD

# Keycloak
KC_DB_USERNAME, KC_DB_PASSWORD
KC_BOOTSTRAP_ADMIN_USERNAME, KC_BOOTSTRAP_ADMIN_PASSWORD
KC_BOOTSTRAP_ADMIN_EMAIL
KC_HOSTNAME
OAUTH2_PROXY_CLIENT_SECRET, OAUTH2_PROXY_COOKIE_SECRET
KC_ORCHESTRATOR_CLIENT_SECRET, KC_DISTILLER_CLIENT_SECRET
KC_DISPATCHER_CLIENT_SECRET, KC_AGENT_TOOLS_CLIENT_SECRET
KC_UIM_CLIENT_SECRET, KC_TM_CLIENT_SECRET

# App / AI
OPENAI_API_KEY, OPENAI_BASE_URL
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

# Frontend URLs
UIM_FRONTEND_URL, TM_FRONTEND_URL
UIM_HOST, TM_HOST
```

---

## Notes

- All 6 Python backend services use **Alembic** for DB migrations — this must run before
  `kubectl rollout` in the deploy stage
- The `certbot` Docker Compose profile is fully replaced by cert-manager
- The `nginx` container is fully replaced by the NGINX Ingress Controller
- Keep the existing `detect-changes.sh` and `service-to-path.sh` helper scripts — only
  the deploy job needs rewriting
