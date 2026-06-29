# Tasks: k3s Migration

**Input**: Design documents from `specs/007-k3s-migration/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Not requested — no test tasks generated.

**Organization**: Tasks grouped by user story to enable independent delivery of each milestone.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared-file dependencies)
- **[Story]**: Which user story (US1–US4) from spec.md this task belongs to

---

## Phase 1: Setup (Directory Structure)

**Purpose**: Create the `k8s/` directory skeleton so all manifest tasks can proceed.

- [x] T001 Create `k8s/` directory tree with subdirectories: `k8s/configmaps/`, `k8s/infrastructure/`, `k8s/backends/`, `k8s/frontends/`, `k8s/ingress/`, `k8s/monitoring/`

---

## Phase 2: Foundational (Shared ConfigMaps + Namespace)

**Purpose**: Namespace and ConfigMaps that are consumed by multiple user stories — must exist before any Deployment or StatefulSet is applied.

**⚠️ CRITICAL**: All Phase 4 (US2) manifest tasks depend on this phase being complete.

- [x] T002 Create Namespace manifest declaring `dark-factory` namespace in `k8s/namespace.yaml`
- [x] T003 [P] Create postgres-init ConfigMap wrapping `infra/postgres/init/01_create_databases.sql` in `k8s/configmaps/postgres-init.yaml` (mounted by postgres StatefulSet initContainer)
- [x] T004 [P] Create Keycloak ConfigMaps — `realm-export.json` and `substitute-env.sh` from `infra/keycloak/` — in `k8s/configmaps/keycloak-realm.yaml`
- [x] T005 [P] Create oauth2-proxy ConfigMap wrapping `infra/oauth2-proxy/config.cfg` in `k8s/configmaps/oauth2-proxy-config.yaml`
- [x] T006 [P] Create agent-registry ConfigMap wrapping `development/agents/registry.yaml` in `k8s/configmaps/agent-registry.yaml` (read-only mount for agent-dispatcher)

**Checkpoint**: Namespace and all ConfigMaps ready — Phase 4 manifest work can begin in parallel.

---

## Phase 3: User Story 1 — Cluster Provisioned and Healthy (Priority: P1) 🎯 MVP

**Goal**: A single idempotent script provisions k3s, Helm, NGINX Ingress Controller, and cert-manager on a fresh Ubuntu 26.04 VPS, and verifies the cluster is healthy before exiting.

**Independent Test**: Run `bash infra/scripts/setup-k3s.sh` on a fresh VPS; verify `kubectl get nodes` shows `Ready`, NGINX Ingress Controller pods are running, cert-manager pods are running, and re-running the script a second time exits 0 with no errors.

- [x] T007 [US1] Write idempotent VPS setup script `infra/scripts/setup-k3s.sh` — installs k3s with `--disable traefik`, installs Helm 3, installs NGINX Ingress Controller via `helm install ingress-nginx ingress-nginx/ingress-nginx`, installs cert-manager via `helm install cert-manager jetstack/cert-manager --set crds.enabled=true`, configures `~/.kube/config` for deploy user, runs `kubectl get nodes` health check and exits non-zero on failure; every install step is guarded with an existence check for idempotency
- [x] T008 [US1] Create cert-manager ClusterIssuer manifest with two issuers — `letsencrypt-staging` (ACME staging server, for initial testing) and `letsencrypt-prod` (production Let's Encrypt) — using HTTP-01 challenge in `k8s/ingress/cluster-issuer.yaml`

**Checkpoint**: VPS can be provisioned from scratch by running one script. cert-manager is ready for TLS automation.

---

## Phase 4: User Story 2 — Full Application Stack Deployed to k3s (Priority: P1)

**Goal**: All infrastructure services (PostgreSQL, MongoDB, Keycloak, oauth2-proxy) and all application services (6 backends, 2 frontends) are declared as Kubernetes resources, deploy successfully to the `dark-factory` namespace, and communicate using the same DNS names as Docker Compose.

**Independent Test**: `kubectl apply -f k8s/` on a provisioned cluster with `dark-factory-secrets` populated; all pods reach `Running` state; `https://studio.dark-factory.local` and `https://tickets.dark-factory.local` serve the correct frontends over HTTPS.

### Infrastructure StatefulSets

- [x] T009 [P] [US2] Create PostgreSQL StatefulSet and ClusterIP Service in `k8s/infrastructure/postgres-statefulset.yaml` and `k8s/infrastructure/postgres-service.yaml` — image `postgres:16-alpine`, PVC `postgres-data` (10Gi, `local-path`), initContainer mounts `postgres-init` ConfigMap to `/docker-entrypoint-initdb.d/`, `envFrom` references `dark-factory-secrets`, exec liveness probe `pg_isready -U $POSTGRES_USER`, Service name `postgres` port 5432
- [x] T010 [P] [US2] Create MongoDB StatefulSet and ClusterIP Service in `k8s/infrastructure/mongo-statefulset.yaml` and `k8s/infrastructure/mongo-service.yaml` — image `mongo:7-jammy`, PVC `mongo-data` (20Gi, `local-path`), exec liveness probe `mongosh --eval "db.adminCommand('ping')"`, Service name `mongo` port 27017

### Infrastructure Deployments

- [x] T011 [US2] Create Keycloak Deployment and ClusterIP Service in `k8s/infrastructure/keycloak-deployment.yaml` and `k8s/infrastructure/keycloak-service.yaml` — image `quay.io/keycloak/keycloak:25.0`, initContainer waits for `postgres:5432` using `pg_isready`, volume mounts `keycloak-realm` ConfigMap to `/opt/keycloak/data/import-src/` and `substitute-env.sh` to `/entrypoint/substitute-env.sh`, entrypoint runs substitute-env.sh then `kc.sh start --import-realm`, `envFrom` references `dark-factory-secrets`, HTTP readiness probe `GET /health/ready:8080`, Service name `keycloak` port 8080
- [x] T012 [P] [US2] Create oauth2-proxy Deployment and ClusterIP Service in `k8s/infrastructure/oauth2-proxy-deployment.yaml` and `k8s/infrastructure/oauth2-proxy-service.yaml` — image `quay.io/oauth2-proxy/oauth2-proxy:v7.7.1`, volume mounts `oauth2-proxy-config` ConfigMap to `/etc/oauth2_proxy/config.cfg`, `envFrom` references `dark-factory-secrets`, HTTP readiness probe `GET /ping:4180`, Service name `oauth2-proxy` port 4180

### Backend Deployments (× 6)

All backend Deployments share: `envFrom: secretRef: dark-factory-secrets`, `imagePullSecrets: ghcr-pull-secret`, image tag placeholder `ghcr.io/OWNER/SERVICE:REPLACE_SHA`, HTTP readiness probe (initialDelaySeconds=10, periodSeconds=5) and liveness probe (initialDelaySeconds=30, periodSeconds=10, failureThreshold=3).

- [x] T013 [P] [US2] Create user-input-manager Deployment and ClusterIP Service in `k8s/backends/user-input-manager-deployment.yaml` and `k8s/backends/user-input-manager-service.yaml` — port 8000, readiness/liveness probe path `/api/health`, Service name `user-input-manager`
- [x] T014 [P] [US2] Create ticket-manager Deployment and ClusterIP Service in `k8s/backends/ticket-manager-deployment.yaml` and `k8s/backends/ticket-manager-service.yaml` — port 8000, readiness/liveness probe path `/api/health`, Service name `ticket-manager`
- [x] T015 [P] [US2] Create orchestrator Deployment and ClusterIP Service in `k8s/backends/orchestrator-deployment.yaml` and `k8s/backends/orchestrator-service.yaml` — port 8000, readiness/liveness probe path `/health`, Service name `orchestrator`
- [x] T016 [P] [US2] Create context-distiller Deployment and ClusterIP Service in `k8s/backends/context-distiller-deployment.yaml` and `k8s/backends/context-distiller-service.yaml` — port 8000, readiness/liveness probe path `/health`, Service name `context-distiller`
- [x] T017 [P] [US2] Create agent-tools Deployment and ClusterIP Service in `k8s/backends/agent-tools-deployment.yaml` and `k8s/backends/agent-tools-service.yaml` — port 8000, readiness/liveness probe path `/health`, Service name `agent-tools`
- [x] T018 [P] [US2] Create agent-dispatcher Deployment and ClusterIP Service in `k8s/backends/agent-dispatcher-deployment.yaml` and `k8s/backends/agent-dispatcher-service.yaml` — port 8000, readiness/liveness probe path `/health`, additionally mounts `agent-registry` ConfigMap to `/app/development/agents/registry.yaml` as readOnly, Service name `agent-dispatcher`

### Frontend Deployments

- [x] T019 [P] [US2] Create uim-frontend Deployment and ClusterIP Service in `k8s/frontends/uim-frontend-deployment.yaml` and `k8s/frontends/uim-frontend-service.yaml` — image `ghcr.io/OWNER/uim-frontend:REPLACE_SHA`, `imagePullSecrets: ghcr-pull-secret`, port 80, Service name `uim-frontend`
- [x] T020 [P] [US2] Create tm-frontend Deployment and ClusterIP Service in `k8s/frontends/tm-frontend-deployment.yaml` and `k8s/frontends/tm-frontend-service.yaml` — image `ghcr.io/OWNER/tm-frontend:REPLACE_SHA`, `imagePullSecrets: ghcr-pull-secret`, port 80, Service name `tm-frontend`

### Ingress and Deployment Documentation

- [x] T021 [US2] Create application Ingress in `k8s/ingress/ingress.yaml` — `ingressClassName: nginx`, annotation `cert-manager.io/cluster-issuer: letsencrypt-prod`, routes `studio.dark-factory.local` → `uim-frontend:80` and `tickets.dark-factory.local` → `tm-frontend:80`, annotation `nginx.ingress.kubernetes.io/auth-url: http://oauth2-proxy.dark-factory.svc.cluster.local:4180/oauth2/auth` on `/api/*` path rules, annotation `nginx.ingress.kubernetes.io/auth-response-headers: X-Auth-Request-User,X-Auth-Request-Email,X-Auth-Request-Groups`, TLS secret `dark-factory-tls`
- [x] T022 [US2] Update `infra/DEPLOYMENT.md` — document full provisioning sequence: VPS setup, `kubectl create namespace dark-factory`, `kubectl create secret generic dark-factory-secrets --from-env-file=infra/.env`, `kubectl create secret docker-registry ghcr-pull-secret`, image SHA substitution, `kubectl apply -f k8s/`, Alembic migration commands per service, and kubeconfig copy/export instructions

**Checkpoint**: Full application stack deployable from manifests. `https://studio.dark-factory.local` and `https://tickets.dark-factory.local` accessible and protected by Keycloak.

---

## Phase 5: User Story 3 — Automated CI/CD Deploys via Kubernetes (Priority: P2)

**Goal**: The `deploy` stage in CI/CD builds and pushes Docker images to GHCR, runs Alembic migrations, performs a rolling deployment with `kubectl rollout status`, and automatically rolls back on failure — without any SSH to VPS.

**Independent Test**: Trigger a pipeline push with a change to one backend service; verify a new GHCR image is created, the migration Job completes, `kubectl rollout status` confirms the new pods are up, and a deliberate broken image triggers the rollback path and exits the pipeline with status 1.

- [x] T023 [US3] Rewrite the `deploy` job in `.github/workflows/ci-cd.yml` — remove SSH/`docker compose` steps; add step: write `${{ secrets.KUBECONFIG }}` (base64) to `~/.kube/config`; add step: `docker login ghcr.io`; for each changed service: (a) `docker build -t ghcr.io/${{ github.repository_owner }}/<service>:${{ github.sha }}` from correct service path, (b) `docker push`, (c) if DB-backed service: `kubectl run alembic-<service>-<sha> --image=... --rm --restart=Never -n dark-factory --env-from=secret/dark-factory-secrets -- alembic upgrade head`, (d) `kubectl set image deployment/<service> <container>=ghcr.io/...:<sha> -n dark-factory`, (e) `kubectl rollout status deployment/<service> -n dark-factory --timeout=120s || (kubectl rollout undo deployment/<service> -n dark-factory && exit 1)`; document in `infra/DEPLOYMENT.md`: add `KUBECONFIG` and `GHCR_TOKEN` to GitHub Actions secrets, remove `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`

**Checkpoint**: Merging to `main` automatically deploys only changed services via Kubernetes rolling updates with automatic rollback.

---

## Phase 6: User Story 4 — Observability Dashboard (Priority: P3)

**Goal**: kube-prometheus-stack is installed in the `monitoring` namespace; all 6 backend services, the PostgreSQL exporter, and the MongoDB exporter are scraped by Prometheus; Grafana dashboards for node metrics, pod restarts, and HTTP latency are accessible at `grafana.dark-factory.local` behind basic auth.

**Independent Test**: After Helm install and `kubectl apply -f k8s/monitoring/`, all 6 backend service targets plus postgres-exporter and mongo-exporter show as `UP` in the Prometheus UI; Grafana displays data on all three pre-configured dashboards; unauthenticated request to `grafana.dark-factory.local` returns 401.

- [x] T024 [US4] Inspect each of the 6 backend services for a `/metrics` endpoint — for any service that does not expose one, add `prometheus-fastapi-instrumentator` (or equivalent Prometheus client) to that service's `requirements.txt` and wire it up in `src/main.py` following the canonical version rules in `pyproject.toml`
- [x] T025 [P] [US4] Create ServiceMonitor resources for all 6 backend services in `k8s/monitoring/service-monitors.yaml` — each ServiceMonitor selects the corresponding Service by label, sets `namespaceSelector: matchNames: [dark-factory]`, scrape path `/metrics`, port `http`
- [x] T026 [P] [US4] Create Grafana Ingress with basic auth in `k8s/monitoring/grafana-ingress.yaml` — host `grafana.dark-factory.local`, backend `kube-prometheus-stack-grafana:80`, annotations `nginx.ingress.kubernetes.io/auth-type: basic` and `nginx.ingress.kubernetes.io/auth-secret: grafana-basic-auth`, cert-manager TLS annotation, TLS secret `grafana-tls`
- [x] T027 [US4] Create kube-prometheus-stack Helm values in `k8s/monitoring/values-prometheus.yaml` — enable `grafana.enabled: true`, set Grafana admin credentials via secret reference, include `prometheus-postgres-exporter` subchart with `DATA_SOURCE_NAME` pointing to `postgres.dark-factory.svc.cluster.local:5432`, include `prometheus-mongodb-exporter` subchart pointing to `mongo.dark-factory.svc.cluster.local:27017`, enable default dashboards for node CPU/memory (`nodeExporter.enabled: true`) and kube-state-metrics pod restarts

**Checkpoint**: Prometheus scrapes all targets; Grafana dashboards show live data; `grafana.dark-factory.local` requires login.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Verification, documentation completeness, and final consistency pass.

- [x] T028 [P] Validate all k8s manifests with `kubectl apply --dry-run=client --validate=true -f k8s/ -n dark-factory` to catch YAML syntax errors and invalid field names before running against a real cluster
- [ ] T029 Run the full `quickstart.md` procedure on a test VPS from scratch — confirm each step succeeds as written and update any instructions that are incorrect or missing

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (directory structure)
- **US1 (Phase 3)**: Independent of Phase 2 — `setup-k3s.sh` and `cluster-issuer.yaml` have no ConfigMap dependencies
- **US2 (Phase 4)**: Depends on Phase 2 (ConfigMaps must exist); T011 (Keycloak) requires T009 (postgres) to be defined first for the initContainer reference
- **US3 (Phase 5)**: Depends on US1 + US2 — CI/CD pipeline deploys what the manifests define
- **US4 (Phase 6)**: Depends on US2 — ServiceMonitors reference Services created in US2; T024 (metrics endpoints) must precede T025 (ServiceMonitors)
- **Polish (Phase 7)**: Depends on all prior phases complete

### User Story Dependencies

- **US1 (P1)**: Can start immediately after Phase 1 — no dependencies on other stories
- **US2 (P1)**: Requires Phase 2 (ConfigMaps) — T011 (Keycloak) requires T009 (postgres) defined; all other US2 tasks are independent of each other
- **US3 (P2)**: Requires US1 + US2 complete — CI/CD deploys to the cluster provisioned by US1 using manifests from US2
- **US4 (P3)**: Requires US2 complete — T024 modifies service code; T025/T026/T027 reference namespace and Services from US2

### Within Each User Story

- Models (ConfigMaps, StatefulSets) before services that depend on them
- T009/T010 (databases) are independent of each other — run in parallel
- T011 (Keycloak) depends on T009 being defined (postgres initContainer reference)
- T012–T020 (all other Deployments) are mutually independent — run in parallel
- T021 (Ingress) can be written in parallel with T013–T020 but references their Service names — apply last
- T024 (add /metrics) must complete before T025 (ServiceMonitors reference those endpoints)

### Parallel Opportunities

- **Phase 2**: T003, T004, T005, T006 all target different files — all 4 can run simultaneously
- **Phase 3**: T007 and T008 target different files — run in parallel
- **Phase 4**: T009 and T010 run in parallel; T012–T020 all run in parallel with each other; T011 can overlap once T009 YAML is written (not applied)
- **Phase 6**: T025 and T026 target different files — run in parallel

---

## Parallel Example: User Story 2

```bash
# Database infrastructure (can run simultaneously):
Task T009: "Create PostgreSQL StatefulSet + Service in k8s/infrastructure/"
Task T010: "Create MongoDB StatefulSet + Service in k8s/infrastructure/"

# All backend Deployments + frontend Deployments (can run simultaneously):
Task T012: "Create oauth2-proxy Deployment + Service"
Task T013: "Create user-input-manager Deployment + Service"
Task T014: "Create ticket-manager Deployment + Service"
Task T015: "Create orchestrator Deployment + Service"
Task T016: "Create context-distiller Deployment + Service"
Task T017: "Create agent-tools Deployment + Service"
Task T018: "Create agent-dispatcher Deployment + Service"
Task T019: "Create uim-frontend Deployment + Service"
Task T020: "Create tm-frontend Deployment + Service"

# T011 (Keycloak) written alongside T012–T020 but referencing T009's postgres Service
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Create k8s/ directory structure
2. Complete Phase 3 (US1): Write `setup-k3s.sh` + `cluster-issuer.yaml`
3. **STOP and VALIDATE**: Run setup script on a test VPS; verify cluster is `Ready`

### Incremental Delivery

1. Phase 1 + Phase 2 → directory structure and ConfigMaps ready
2. Phase 3 (US1) → cluster provisionable from one script (MVP!)
3. Phase 4 (US2) → full application stack deployed via `kubectl apply -f k8s/`
4. Phase 5 (US3) → automated CI/CD pipeline with GHCR + kubectl rollout
5. Phase 6 (US4) → observability dashboards added without touching application code

Each phase delivers independently verifiable value before the next begins.

### Single-Developer Strategy

Recommended execution order (maximum parallelism within each phase):

1. T001 → T002
2. T003 + T004 + T005 + T006 (parallel)
3. T007 + T008 (parallel)
4. T009 + T010 (parallel) → T011; T012–T020 (parallel)
5. T021 → T022
6. T023
7. T024 → T025 + T026 (parallel) → T027
8. T028 + T029

---

## Notes

- [P] tasks write to different files with no shared-file dependencies — safe to run concurrently
- [Story] label maps each task to a user story for delivery traceability
- Image tag placeholder `REPLACE_SHA` in manifests is substituted during CI/CD or manual deploy (see quickstart.md)
- `agent-tools` has no database — skip Alembic step in T023 for this service (Principle XXVII)
- Constitution amendment for Principles XXII and XXVI is required after this feature ships — document in `infra/DEPLOYMENT.md`
- Each user story can be demo'd independently before moving to the next
