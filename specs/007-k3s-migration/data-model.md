# Data Model: k3s Migration

**Feature**: 007-k3s-migration | **Date**: 2026-06-28

This document describes the Kubernetes resource topology — the "data model" for the infrastructure migration. Service application data models are unchanged.

---

## Namespace

| Resource | Name | Purpose |
|----------|------|---------|
| Namespace | `dark-factory` | All application resources |
| Namespace | `monitoring` | kube-prometheus-stack |

---

## Secrets

| Resource | Name | Namespace | Contents |
|----------|------|-----------|----------|
| Secret | `dark-factory-secrets` | `dark-factory` | All credentials from `infra/.env` (see contracts/k8s-secret-schema.md) |
| Secret | `ghcr-pull-secret` | `dark-factory` | GHCR imagePullSecret (`docker-registry` type) |

---

## ConfigMaps

| Resource | Name | Namespace | Source File | Consumed By |
|----------|------|-----------|-------------|-------------|
| ConfigMap | `postgres-init-sql` | `dark-factory` | `infra/postgres/init/01_create_databases.sql` | `postgres` StatefulSet initContainer |
| ConfigMap | `keycloak-realm-export` | `dark-factory` | `infra/keycloak/realm-export.json` | `keycloak` Deployment |
| ConfigMap | `keycloak-substitute-env` | `dark-factory` | `infra/keycloak/substitute-env.sh` | `keycloak` Deployment |
| ConfigMap | `oauth2-proxy-config` | `dark-factory` | `infra/oauth2-proxy/config.cfg` | `oauth2-proxy` Deployment |
| ConfigMap | `agent-registry` | `dark-factory` | `development/agents/registry.yaml` | `agent-dispatcher` Deployment (read-only mount) |

---

## StatefulSets (persistent infrastructure)

### postgres

| Field | Value |
|-------|-------|
| Image | `postgres:16-alpine` |
| Replicas | 1 |
| Service name | `postgres` |
| Port | 5432 |
| Storage | PVC `postgres-data`, 10Gi, `local-path` |
| InitContainer | copies `postgres-init-sql` ConfigMap to `/docker-entrypoint-initdb.d/` |
| Env from | `dark-factory-secrets` (POSTGRES_USER, POSTGRES_PASSWORD) |
| Health probe | `pg_isready -U $POSTGRES_USER` (exec) |

### mongo

| Field | Value |
|-------|-------|
| Image | `mongo:7-jammy` |
| Replicas | 1 |
| Service name | `mongo` |
| Port | 27017 |
| Storage | PVC `mongo-data`, 20Gi, `local-path` |
| Health probe | `mongosh --eval "db.adminCommand('ping')"` (exec) |

---

## Deployments (stateless services)

### keycloak

| Field | Value |
|-------|-------|
| Image | `quay.io/keycloak/keycloak:25.0` |
| Replicas | 1 |
| Service name | `keycloak` |
| Port | 8080 |
| InitContainer | waits for `postgres:5432` to accept connections |
| Volume mounts | `keycloak-realm-export` → `/opt/keycloak/data/import-src/`, `keycloak-substitute-env` → `/entrypoint/substitute-env.sh` |
| Entrypoint | runs `substitute-env.sh` then `kc.sh start --import-realm` |
| Env from | `dark-factory-secrets` (KC_DB_USERNAME, KC_DB_PASSWORD, KC_BOOTSTRAP_ADMIN_*, KC_HOSTNAME) |
| Health probe | HTTP GET `/health/ready` on port 8080 |

### oauth2-proxy

| Field | Value |
|-------|-------|
| Image | `quay.io/oauth2-proxy/oauth2-proxy:v7.7.1` |
| Replicas | 1 |
| Service name | `oauth2-proxy` |
| Port | 4180 |
| Volume mounts | `oauth2-proxy-config` → `/etc/oauth2_proxy/config.cfg` |
| Env from | `dark-factory-secrets` (OAUTH2_PROXY_CLIENT_SECRET, OAUTH2_PROXY_COOKIE_SECRET) |
| Health probe | HTTP GET `/ping` on port 4180 |

### Backend services (× 6)

All share the same pattern. Image tag is `ghcr.io/<owner>/<service>:<sha>`.

| Service | Internal DNS | Port | Health path | DB env keys | Special mounts |
|---------|-------------|------|-------------|------------|----------------|
| `user-input-manager` | `user-input-manager` | 8000 | `/api/health` | UIM_DB_USER, UIM_DB_PASSWORD | — |
| `ticket-manager` | `ticket-manager` | 8000 | `/api/health` | TM_DB_USER, TM_DB_PASSWORD | — |
| `orchestrator` | `orchestrator` | 8000 | `/health` | ORCH_DB_USER, ORCH_DB_PASSWORD | — |
| `context-distiller` | `context-distiller` | 8000 | `/health` | DISTILLER_DB_USER, DISTILLER_DB_PASSWORD | — |
| `agent-tools` | `agent-tools` | 8000 | `/health` | — | — |
| `agent-dispatcher` | `agent-dispatcher` | 8000 | `/health` | DISPATCHER_DB_USER, DISPATCHER_DB_PASSWORD | `agent-registry` ConfigMap → `/app/development/agents/registry.yaml` (readOnly) |

All backend Deployments:
- `envFrom`: `secretRef: dark-factory-secrets` (all keys injected)
- `imagePullSecrets`: `ghcr-pull-secret`
- readinessProbe: HTTP GET `<health path>`, initialDelaySeconds=10, periodSeconds=5
- livenessProbe: HTTP GET `<health path>`, initialDelaySeconds=30, periodSeconds=10, failureThreshold=3

### Frontend services (× 2)

| Service | Internal DNS | Port | Image |
|---------|-------------|------|-------|
| `uim-frontend` | `uim-frontend` | 80 | `ghcr.io/<owner>/uim-frontend:<sha>` |
| `tm-frontend` | `tm-frontend` | 80 | `ghcr.io/<owner>/tm-frontend:<sha>` |

---

## Services (ClusterIP)

Every Deployment and StatefulSet above has a corresponding ClusterIP Service. Names match the Docker Compose service names exactly so environment variable values require no changes.

| Service name | Target | Port |
|-------------|--------|------|
| `postgres` | postgres StatefulSet | 5432 |
| `mongo` | mongo StatefulSet | 27017 |
| `keycloak` | keycloak Deployment | 8080 |
| `oauth2-proxy` | oauth2-proxy Deployment | 4180 |
| `user-input-manager` | backend Deployment | 8000 |
| `ticket-manager` | backend Deployment | 8000 |
| `orchestrator` | backend Deployment | 8000 |
| `context-distiller` | backend Deployment | 8000 |
| `agent-tools` | backend Deployment | 8000 |
| `agent-dispatcher` | backend Deployment | 8000 |
| `uim-frontend` | frontend Deployment | 80 |
| `tm-frontend` | frontend Deployment | 80 |

---

## Ingress Resources

### Application Ingress

| Field | Value |
|-------|-------|
| Ingress class | `nginx` |
| Cert-manager annotation | `cert-manager.io/cluster-issuer: letsencrypt-prod` |
| `studio.dark-factory.local` | → `uim-frontend:80` |
| `tickets.dark-factory.local` | → `tm-frontend:80` |
| `/api/*` nginx annotation | `nginx.ingress.kubernetes.io/auth-url: http://oauth2-proxy.dark-factory.svc.cluster.local:4180/oauth2/auth` |
| TLS secret | `dark-factory-tls` (managed by cert-manager) |

### Grafana Ingress

| Field | Value |
|-------|-------|
| Namespace | `monitoring` |
| Host | `grafana.dark-factory.local` |
| Backend | `kube-prometheus-stack-grafana:80` |
| Auth | Basic auth via nginx annotation (`auth-secret`) |
| TLS | cert-manager ClusterIssuer |

---

## cert-manager Resources

| Resource | Name | Type | ACME server |
|----------|------|------|-------------|
| ClusterIssuer | `letsencrypt-staging` | ACME HTTP-01 | `https://acme-staging-v02.api.letsencrypt.org/directory` |
| ClusterIssuer | `letsencrypt-prod` | ACME HTTP-01 | `https://acme-v02.api.letsencrypt.org/directory` |

---

## Monitoring Resources

### ServiceMonitors (× 6 backends)

| ServiceMonitor | Namespace | Selects | Scrape path |
|----------------|-----------|---------|-------------|
| `user-input-manager-monitor` | `dark-factory` | `user-input-manager` Service | `/metrics` |
| `ticket-manager-monitor` | `dark-factory` | `ticket-manager` Service | `/metrics` |
| `orchestrator-monitor` | `dark-factory` | `orchestrator` Service | `/metrics` |
| `context-distiller-monitor` | `dark-factory` | `context-distiller` Service | `/metrics` |
| `agent-tools-monitor` | `dark-factory` | `agent-tools` Service | `/metrics` |
| `agent-dispatcher-monitor` | `dark-factory` | `agent-dispatcher` Service | `/metrics` |

**Note**: If any backend service does not currently expose `/metrics`, a `/metrics` endpoint returning Prometheus-format text must be added before the ServiceMonitor is activated.

### Exporter Deployments (via Helm subchart or standalone)

| Component | Helm chart | Scrape target |
|-----------|-----------|---------------|
| postgres-exporter | `prometheus-community/prometheus-postgres-exporter` | `postgres:5432` |
| mongodb-exporter | `prometheus-community/prometheus-mongodb-exporter` | `mongo:27017` |

---

## PVC Sizing

| PVC | StorageClass | Capacity | Access Mode |
|-----|-------------|----------|-------------|
| `postgres-data` | `local-path` | 10Gi | ReadWriteOnce |
| `mongo-data` | `local-path` | 20Gi | ReadWriteOnce |

*Sizes are defaults for initial deployment; should be adjusted based on actual data growth.*

---

## State Transitions (Deployment lifecycle)

```
New image pushed to GHCR
  → CI: kubectl run alembic migration (ephemeral pod, --rm)
  → CI: kubectl set image deployment/<name> <container>=ghcr.io/<owner>/<name>:<sha>
  → k8s: rolling update starts (maxSurge=1, maxUnavailable=0)
  → CI: kubectl rollout status --timeout=120s
      → SUCCESS: old ReplicaSet scaled to 0
      → FAILURE: CI runs kubectl rollout undo → previous ReplicaSet restored
```
