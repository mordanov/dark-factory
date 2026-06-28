# Research: k3s Migration

**Feature**: 007-k3s-migration | **Date**: 2026-06-28

## Decision Log

### 1. k3s vs. Full Kubernetes Distribution

**Decision**: k3s (Rancher/SUSE, latest stable)
**Rationale**: k3s is a CNCF-certified, production-grade Kubernetes distribution packaged as a single binary. It ships with a built-in local-path provisioner (needed for PVCs on a single-node VPS), uses containerd (no external Docker daemon dependency), and disables Traefik by default when `--disable traefik` is passed. Resource overhead is ~512 MB RAM vs ~2+ GB for a full kubeadm cluster — critical for a Hetzner VPS.
**Alternatives considered**:
- `minikube`: Dev-only; lacks production readiness and automatic node bootstrapping.
- `kubeadm`: Production-grade but requires manual etcd management and significant setup complexity for a single-node cluster.
- `microk8s`: Ubuntu-native Snap package; snap confinement creates friction with custom ingress and cert-manager.

### 2. Ingress Controller

**Decision**: NGINX Ingress Controller (`ingress-nginx`, Helm chart `ingress-nginx/ingress-nginx`)
**Rationale**: Direct functional replacement for the existing nginx container. Supports `auth_request` annotations for oauth2-proxy validation on `/api/*` routes (preserving Principle IX semantics at the Ingress level). Widely supported, stable, and the upstream Helm chart handles LoadBalancer/NodePort service creation on k3s automatically.
**Alternatives considered**:
- Traefik (disabled by `--disable traefik` per requirement): would require rewriting the auth middleware chain.
- Caddy ingress: less mature ecosystem for Kubernetes; no direct auth_request equivalent.

### 3. Certificate Management

**Decision**: cert-manager (Jetstack, Helm chart `cert-manager/cert-manager`) with two ClusterIssuers: `letsencrypt-staging` (initial testing) and `letsencrypt-prod` (production)
**Rationale**: cert-manager is the de facto standard for automated TLS in Kubernetes. It replaces the `certbot` Docker Compose profile (Principle XXVII: certbot is `profiles: [certbot]` only). The `ClusterIssuer` resource integrates directly with the NGINX Ingress Controller via the `cert-manager.io/cluster-issuer` annotation on Ingress objects.
**Alternatives considered**:
- Manual cert provisioning via certbot on the node: loses automation; requires cron and manual kubeconfig secret management.
- Traefik's built-in ACME: Traefik is explicitly disabled.

### 4. Container Registry

**Decision**: GitHub Container Registry (GHCR) — `ghcr.io/${{ github.repository_owner }}/<service>:<sha>`
**Rationale**: GHCR is free for public images and included in GitHub Actions environments. No additional SaaS account needed. k3s can be configured to pull from GHCR with a single `imagePullSecret`. This supersedes Principle XXII (VPS-only builds) — a registry is architecturally required for Kubernetes image distribution.
**Alternatives considered**:
- Docker Hub: rate limiting on pulls; paid tier for private images.
- Self-hosted registry on the VPS: adds operational burden; another service to maintain; single point of failure.
- `docker save | docker load` into k3s containerd: bypasses k3s image management; breaks `kubectl rollout undo`; not viable.

### 5. Secret Management

**Decision**: Single Kubernetes Secret `dark-factory-secrets` in the `dark-factory` namespace; populated from `infra/.env` variables; applied via `kubectl create secret generic --from-env-file` (run manually on the VPS with kubeconfig access; never in CI)
**Rationale**: Mirrors the existing VPS-only secret principle (Principle XXVI): the secret is populated by the operator, not CI. CI has `KUBECONFIG` and `GHCR_TOKEN`; the production credentials live in the cluster Secret, not GitHub Actions.
**Alternatives considered**:
- HashiCorp Vault: significant operational overhead for a single-node cluster.
- Sealed Secrets: encrypted secrets in git are acceptable but adds tooling complexity.
- External Secrets Operator with a cloud provider: over-engineered for single-VPS deployment.

### 6. Alembic Migration Strategy in k3s

**Decision**: `kubectl run --rm` (ephemeral pod using the service image) rather than a `Job` manifest for inline CI/CD runs; a standalone `Job` manifest is not committed to `k8s/` to avoid accidental re-execution on `kubectl apply`
**Rationale**: Alembic migrations must run exactly once per deploy (Principle XXIV: migrations before container restart). Using `kubectl run --rm` gives the CI pipeline direct control over execution order and captures exit codes cleanly. Jobs in `k8s/` would re-execute on every `kubectl apply` unless explicitly managed with completion tracking.
**Alternatives considered**:
- `initContainer` in each backend Deployment: violates Principle XXIV (runs at pod start, not before Deployment update).
- Helm hooks: adds Helm dependency for service deployments that don't otherwise need it.
- `Job` with `ttlSecondsAfterFinished`: workable but requires job name uniqueness per deploy.

### 7. Storage Provisioner for PVCs

**Decision**: k3s built-in `local-path` StorageClass (Rancher `local-path-provisioner`)
**Rationale**: Single-node cluster; no need for distributed storage. local-path provisions `hostPath` volumes under `/var/lib/rancher/k3s/storage/` — equivalent to Docker named volumes. Data survives pod restarts and rescheduling (irrelevant on single-node, but correct semantics).
**Alternatives considered**:
- NFS provisioner: adds complexity; external NFS server required.
- Longhorn: Rancher's distributed storage — overkill for single-node; significant RAM/CPU overhead.

### 8. Observability Stack

**Decision**: `kube-prometheus-stack` Helm chart (`prometheus-community/kube-prometheus-stack`) installed into `monitoring` namespace
**Rationale**: Bundles Prometheus, Alertmanager, Grafana, and the Prometheus Operator with node/pod/container metrics out-of-the-box. Pre-packaged dashboards cover node CPU/memory and pod restarts with zero custom configuration. ServiceMonitor CRDs (from the Operator) provide clean per-service scrape config.
**Postgres exporter**: `prometheus-community/prometheus-postgres-exporter` Helm chart
**Mongo exporter**: `prometheus-community/prometheus-mongodb-exporter` Helm chart
**Alternatives considered**:
- Standalone Prometheus + Grafana: more manual wiring; no Operator; ServiceMonitor not available.
- Datadog/New Relic: paid SaaS; no offline capability.

### 9. CI/CD Rollout Verification and Rollback

**Decision**: `kubectl rollout status deployment/<name> -n dark-factory --timeout=120s` for health verification; `kubectl rollout undo deployment/<name> -n dark-factory` for automatic rollback
**Rationale**: Native Kubernetes rollout management. `kubectl rollout undo` reverts to the previous ReplicaSet revision — no image tag snapshot logic required (replaces the manual snapshot + `docker tag` rollback of Principle XXV).
**Alternatives considered**:
- Custom health polling script: replicates what `kubectl rollout status` already does.
- Argo Rollouts: progressive delivery controller; valuable long-term but out of scope for initial migration.

### 10. Ingress DNS Annotation for oauth2-proxy auth_request

**Decision**: Use NGINX Ingress `auth-url` and `auth-signin` annotations on `/api/*` paths to route requests through oauth2-proxy, preserving the auth semantics of Principle IX
**Rationale**: The current nginx container uses `auth_request /oauth2/auth` directives. The NGINX Ingress Controller supports equivalent behaviour via `nginx.ingress.kubernetes.io/auth-url` and `nginx.ingress.kubernetes.io/auth-snippet` annotations. Frontend routes continue without auth annotations (keycloak-js handles redirects at the browser level).
**Alternatives considered**:
- Placing oauth2-proxy as a sidecar on each backend: large manifest overhead; duplicates proxy per pod.
- Istio service mesh: major operational complexity; out of scope.
