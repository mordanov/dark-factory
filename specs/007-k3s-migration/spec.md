# Feature Specification: k3s Migration

**Feature Branch**: `007-k3s-migration`
**Created**: 2026-06-28
**Status**: Draft
**Input**: User description: "Migrating Dark Factory from Docker Compose to k3s on Ubuntu 26.04 VPS"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cluster Provisioned and Healthy (Priority: P1)

A platform engineer runs a single script on a fresh Ubuntu 26.04 VPS and ends up with a fully functioning k3s cluster — NGINX Ingress Controller installed, cert-manager ready for TLS, and kubeconfig accessible for the deploy user. No manual steps are required.

**Why this priority**: Everything else depends on a healthy cluster. This is the entry point for all subsequent deployment work and must succeed before any application can run.

**Independent Test**: Run `setup-k3s.sh` against a fresh VPS and verify `kubectl get nodes` shows the node in `Ready` state, Helm charts for ingress and cert-manager are deployed, and no manual follow-up is needed.

**Acceptance Scenarios**:

1. **Given** a fresh Ubuntu 26.04 VPS with root/sudo access, **When** the setup script is executed, **Then** k3s is installed and running, the node is in `Ready` state, Helm 3 is available, NGINX Ingress Controller pods are running, and cert-manager pods are running.
2. **Given** a VPS where the script was already run once, **When** the script is executed again, **Then** it completes without errors and the cluster remains in the same healthy state (idempotent).
3. **Given** the script completes successfully, **When** the deploy user runs any `kubectl` command, **Then** it succeeds without extra configuration.

---

### User Story 2 - Full Application Stack Deployed to k3s (Priority: P1)

A platform engineer applies Kubernetes manifests for the entire Dark Factory stack — all infrastructure services (PostgreSQL, MongoDB, Keycloak, oauth2-proxy) and all application services (6 backends, 2 frontends) — into a single `dark-factory` namespace. All services reach a healthy running state and can communicate with each other using the same service names as in Docker Compose.

**Why this priority**: Without the full application stack running, the platform has no user-facing value. This is the core migration deliverable.

**Independent Test**: Run `kubectl apply -f k8s/` and verify all pods are `Running`, all services are reachable by their internal names, and the application responds to HTTP requests through the ingress.

**Acceptance Scenarios**:

1. **Given** a healthy k3s cluster and a populated Kubernetes Secret with all credentials, **When** `kubectl apply -f k8s/` is run, **Then** all Deployments and StatefulSets reach their desired replica count within a reasonable time.
2. **Given** the stack is deployed, **When** a backend service attempts to connect to `postgres:5432` or `mongo:27017`, **Then** the connection succeeds using the same environment variable names as in Docker Compose.
3. **Given** the stack is deployed, **When** the Keycloak service starts, **Then** it waits for PostgreSQL to be ready via an initContainer, imports the realm configuration, and becomes healthy.
4. **Given** the stack is deployed, **When** a browser navigates to `studio.dark-factory.local` or `tickets.dark-factory.local`, **Then** the correct frontend is served over HTTPS with a valid TLS certificate.
5. **Given** the stack is deployed, **When** a backend service's `/health` or `/api/health` endpoint returns a non-2xx status, **Then** Kubernetes restarts the pod automatically.

---

### User Story 3 - Automated CI/CD Deploys via Kubernetes (Priority: P2)

A developer merges a pull request. GitHub Actions detects which services changed, builds and pushes new Docker images to the container registry, runs database migrations, applies updated manifests, and waits for each changed service to roll out successfully. If a rollout fails, it is automatically undone.

**Why this priority**: Continuous delivery is the operational backbone of the platform. Without it, deploying changes requires manual intervention, but the application can still run once deployed.

**Independent Test**: Trigger the pipeline on a branch with a change to one backend service. Verify a new image is pushed to GHCR, the migration Job runs to completion, `kubectl rollout status` confirms the new pods are running, and the old pods are gone.

**Acceptance Scenarios**:

1. **Given** a code change is pushed, **When** the pipeline runs the deploy stage, **Then** only images for changed services are built and pushed to the registry.
2. **Given** a new image is pushed, **When** the deploy stage runs for a DB-backed service, **Then** Alembic migrations run to completion before the new pods are started.
3. **Given** a rollout is triggered, **When** the new pods become healthy within the timeout, **Then** the pipeline succeeds and old pods are terminated.
4. **Given** a rollout is triggered, **When** the new pods fail to become healthy within the timeout, **Then** the pipeline automatically runs a rollback to the previous revision and exits with a failure status.
5. **Given** the pipeline succeeds, **When** a developer reviews GitHub Actions, **Then** the deploy log shows which services were updated and what image tags were applied.

---

### User Story 4 - Observability Dashboard Available (Priority: P3)

A platform engineer accesses Grafana at `grafana.dark-factory.local` and sees pre-built dashboards covering node resource usage, pod restart counts, and HTTP request latency per service. Prometheus is scraping metrics from all backend services, PostgreSQL, and MongoDB.

**Why this priority**: Observability is essential for production operations but does not block the application from running. It can be layered on after the core stack is deployed.

**Independent Test**: Install kube-prometheus-stack, apply ServiceMonitor resources, and verify that all backend services, postgres exporter, and mongo exporter appear as scrape targets in the Prometheus UI. Open Grafana and confirm the pre-configured dashboards display data.

**Acceptance Scenarios**:

1. **Given** the monitoring stack is installed, **When** a platform engineer opens Grafana, **Then** they can log in and see dashboards for node CPU/memory, pod restart counts, and per-service HTTP latency.
2. **Given** the monitoring stack is installed, **When** Prometheus scrapes targets, **Then** all 6 backend services, the PostgreSQL exporter, and the MongoDB exporter show as `UP`.
3. **Given** the Grafana ingress is configured with basic auth, **When** an unauthenticated request is made to `grafana.dark-factory.local`, **Then** it returns a 401 and requires credentials.

---

### Edge Cases

- What happens when the setup script is run on a VPS that already has a conflicting k3s version installed?
- How does the system handle a PostgreSQL initContainer timeout if the database pod is slow to start?
- What happens if a Keycloak realm import fails on first boot — does the pod restart cleanly?
- How does the rollback behave if the migration Job has already applied schema changes before the Deployment fails?
- What happens if cert-manager cannot obtain a TLS certificate (e.g., DNS not yet propagated)?
- How does the ingress behave if both frontends are unavailable — does it return a clear error?

## Requirements *(mandatory)*

### Functional Requirements

**VPS Setup**

- **FR-001**: The setup script MUST install k3s without the Traefik ingress controller.
- **FR-002**: The setup script MUST install Helm 3.
- **FR-003**: The setup script MUST install the NGINX Ingress Controller via Helm.
- **FR-004**: The setup script MUST install cert-manager via Helm.
- **FR-005**: The setup script MUST configure kubeconfig for the deploy user without manual steps.
- **FR-006**: The setup script MUST verify the cluster is healthy before exiting, and exit with a non-zero code if it is not.
- **FR-007**: The setup script MUST be idempotent — running it multiple times on the same VPS must not produce errors or degrade the cluster.

**Kubernetes Manifests**

- **FR-008**: All resources MUST be deployed into a single `dark-factory` Namespace.
- **FR-009**: All credentials and secrets from `infra/.env` MUST be stored in a Kubernetes Secret named `dark-factory-secrets`; no secrets may appear in plaintext in manifest files.
- **FR-010**: PostgreSQL MUST be deployed as a StatefulSet with a PersistentVolumeClaim, and the database initialization SQL script MUST be mounted via a ConfigMap.
- **FR-011**: MongoDB MUST be deployed as a StatefulSet with a PersistentVolumeClaim.
- **FR-012**: Keycloak MUST be deployed as a Deployment; the realm export file and entrypoint script MUST be mounted via ConfigMap; Keycloak MUST wait for PostgreSQL via an initContainer before starting.
- **FR-013**: oauth2-proxy MUST be deployed as a Deployment with its configuration file mounted via a ConfigMap.
- **FR-014**: Each of the 6 backend services MUST be deployed as a Deployment with readiness and liveness probes pointing to their `/health` or `/api/health` endpoint.
- **FR-015**: The `agent-dispatcher` service MUST have `registry.yaml` mounted as a read-only ConfigMap volume.
- **FR-016**: Each of the 2 frontend services MUST be deployed as a Deployment.
- **FR-017**: Internal service discovery MUST use the same service names as Docker Compose (`postgres`, `mongo`, `keycloak`, etc.) so that existing environment variable values require no changes.
- **FR-018**: The Ingress resource MUST route `studio.dark-factory.local` to `uim-frontend` and `tickets.dark-factory.local` to `tm-frontend`, with TLS provided by cert-manager.
- **FR-019**: The `certbot` Docker Compose profile and the `nginx` container MUST have no equivalent in the k8s manifests; their roles are fully replaced by cert-manager and NGINX Ingress Controller respectively.

**CI/CD Pipeline**

- **FR-020**: The deploy stage MUST write the `KUBECONFIG` secret to the runner's kubeconfig before any `kubectl` commands are executed.
- **FR-021**: For each changed service, the deploy stage MUST build a Docker image tagged with the commit SHA and push it to `ghcr.io/<owner>/<service>:<sha>`.
- **FR-022**: For each changed DB-backed Python service, the deploy stage MUST run Alembic migrations to completion before triggering a rollout of the new image.
- **FR-023**: The deploy stage MUST update the image tag in the relevant Deployment and wait for `kubectl rollout status` to confirm success within 120 seconds.
- **FR-024**: If a rollout fails or times out, the deploy stage MUST automatically execute a rollback and exit the pipeline with a failure status.
- **FR-025**: The detect, validate, and test stages MUST remain unchanged.
- **FR-026**: The `KUBECONFIG` and `GHCR_TOKEN` secrets MUST be documented, along with which existing secrets can be removed.

**Observability**

- **FR-027**: The kube-prometheus-stack MUST be installed into a `monitoring` Namespace via Helm.
- **FR-028**: A ServiceMonitor MUST be created for each of the 6 backend services.
- **FR-029**: Prometheus scrape configuration MUST include postgres and mongo exporters.
- **FR-030**: Grafana MUST be accessible at `grafana.dark-factory.local` via an Ingress with basic auth enforced.
- **FR-031**: Grafana MUST include pre-configured dashboards for node CPU/memory, pod restart counts, and HTTP request latency per service.

### Key Entities

- **Namespace**: `dark-factory` — logical isolation boundary for all application resources.
- **Secret (`dark-factory-secrets`)**: Holds all credentials from `infra/.env`; consumed by Deployments and StatefulSets as environment variables.
- **StatefulSet**: Used for stateful infrastructure (PostgreSQL, MongoDB) requiring stable storage and identity.
- **Deployment**: Used for all stateless services (backends, frontends, Keycloak, oauth2-proxy).
- **ConfigMap**: Holds non-secret configuration files (init SQL, realm export, oauth2-proxy config, registry.yaml).
- **PersistentVolumeClaim**: Provides durable storage for PostgreSQL and MongoDB data.
- **Ingress**: Routes external traffic by hostname; backed by NGINX Ingress Controller.
- **ClusterIssuer**: cert-manager resource that automates TLS certificate provisioning.
- **ServiceMonitor**: Prometheus Operator resource that defines how a service's metrics endpoint is scraped.
- **Job**: Short-lived workload used to run Alembic database migrations during CI/CD deploys.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The VPS setup script completes successfully on a fresh Ubuntu 26.04 instance in under 10 minutes, leaving the cluster in a `Ready` state with no manual follow-up required.
- **SC-002**: The full application stack (all 8 services plus infrastructure) reaches a healthy running state within 5 minutes of `kubectl apply -f k8s/` on a provisioned cluster.
- **SC-003**: All inter-service connections succeed using the same hostnames and environment variable names as the Docker Compose deployment — zero environment variable renames required for any service.
- **SC-004**: A CI/CD deployment of a single changed service completes end-to-end (image build, migration, rollout, health confirmation) in under 5 minutes.
- **SC-005**: A failed rollout triggers an automatic rollback within 30 seconds of the 120-second timeout expiring, with no manual intervention.
- **SC-006**: The setup script is fully idempotent — running it three consecutive times on the same VPS produces zero errors and leaves the cluster unchanged after the first run.
- **SC-007**: All 6 backend services, the PostgreSQL exporter, and the MongoDB exporter appear as `UP` scrape targets in Prometheus within 2 minutes of the monitoring stack being installed.
- **SC-008**: Zero secrets appear in plaintext in any manifest file or CI/CD pipeline log.

## Assumptions

- The target VPS runs Ubuntu 26.04 LTS and the deploy user has passwordless sudo access.
- A domain or local DNS is configured so that `studio.dark-factory.local`, `tickets.dark-factory.local`, and `grafana.dark-factory.local` resolve to the VPS IP.
- A container registry (GHCR) is accessible from both the GitHub Actions runner and the k3s cluster, and the cluster has credentials to pull images.
- All 6 Python backend services already expose a `/health` or `/api/health` endpoint; adding a `/metrics` endpoint for Prometheus is in scope only if not already present.
- The existing `detect-changes.sh` and `service-to-path.sh` helper scripts are not modified — only the deploy job is rewritten.
- Alembic migration commands are already defined per service; the CI/CD change only determines how they are invoked (via a Kubernetes Job or `kubectl run --rm`).
- A single-node k3s cluster is acceptable for the initial migration; high-availability multi-node setup is out of scope.
- The `infra/.env` file format is used as the authoritative source for the Kubernetes Secret — the migration does not change any credential values, only how they are stored and accessed.
- cert-manager will use Let's Encrypt for production TLS; a staging issuer will also be provided for initial testing.
