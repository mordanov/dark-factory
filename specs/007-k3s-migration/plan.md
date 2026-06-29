# Implementation Plan: k3s Migration

**Branch**: `007-k3s-migration` | **Date**: 2026-06-28 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/007-k3s-migration/spec.md`

## Summary

Migrate the Dark Factory platform from Docker Compose + VPS SSH deployment to k3s (lightweight Kubernetes) on Ubuntu 26.04. The migration produces four concrete deliverables: a VPS setup script (`infra/scripts/setup-k3s.sh`), a full set of Kubernetes manifests (`k8s/`), an updated CI/CD deploy stage in `.github/workflows/ci-cd.yml`, and a kube-prometheus-stack observability installation. All six backend service names, environment variable names, and inter-service DNS names are preserved to minimise service-level changes.

## Technical Context

**Language/Version**: Bash (setup script), YAML (Kubernetes manifests, GitHub Actions), Python 3.12 (existing services, unchanged)
**Primary Dependencies**: k3s (latest stable), Helm 3, NGINX Ingress Controller (`ingress-nginx`), cert-manager, kube-prometheus-stack, kubectl, Alembic 1.14.0 (existing)
**Storage**: PersistentVolumeClaims (k3s local-path provisioner) for PostgreSQL and MongoDB
**Testing**: `kubectl rollout status`, `kubectl get nodes`, Prometheus scrape target health
**Target Platform**: Ubuntu 26.04 VPS (single-node k3s cluster)
**Project Type**: Infrastructure migration (platform / DevOps)
**Performance Goals**: VPS setup completes in <10 min; full stack healthy in <5 min after `kubectl apply`; CI/CD deploy per-service in <5 min
**Constraints**: All internal service names preserved (postgres, mongo, keycloak, etc.); zero env var renames; existing detect/test pipeline stages unchanged
**Scale/Scope**: Single-node k3s; ~15 Deployments/StatefulSets; ~35 YAML manifest files; 1 setup script; updated CI/CD workflow

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principles that apply unchanged

| Principle | Applicability |
|-----------|---------------|
| I. Services remain independently deployable | Each service gets its own Deployment; no cross-service coupling introduced |
| II–XXI. Application-level principles (auth, DB, FSM, etc.) | Unchanged — these govern service code, not infrastructure topology |
| XXIV. Migrations before container restart | Upheld: Alembic Jobs run before `kubectl rollout` in CI/CD |

### Constitution conflicts — intentional supersession

This migration deliberately replaces the Docker Compose + VPS SSH deployment model. Three principles were codified for that model and must be superseded:

| Principle | Current rule | Conflict | Justification |
|-----------|-------------|----------|---------------|
| **XXII. Build on VPS, Not in CI** | Images built on VPS over SSH; no registry | k3s nodes pull images; they cannot access locally-built images on the host FS | A container registry is architecturally required for Kubernetes. GHCR is the natural choice given GitHub Actions. This principle is fully superseded for k3s. |
| **XXVI. VPS-Only Secrets** | Only VPS_HOST, VPS_USER, VPS_SSH_KEY in CI | k3s deploy needs KUBECONFIG (cluster access) and GHCR_TOKEN (registry push) | The 3-secret rule was specific to SSH-based VPS deploy. k3s requires kubeconfig-based access. New rule: KUBECONFIG + GHCR_TOKEN replace VPS_HOST + VPS_USER + VPS_SSH_KEY. Net secret count increases from 3 to 2 (VPS SSH secrets are removed entirely). |
| **DoD items 36–49** (CI/CD pipeline) | docker compose, SSH, 90s healthcheck poll, auto-rollback via image tags | All replaced by kubectl-native equivalents | `kubectl rollout status --timeout=120s` replaces the 90s health poll; `kubectl rollout undo` replaces manual image tag rollback; `docker build on VPS` replaced by `docker build + push to GHCR in CI`. |

**These supersessions require a constitution amendment (Principles XXII and XXVI) after this feature ships.**

### Non-negotiable constraints that remain in force

- Services MUST never share a database (unchanged — StatefulSet topology mirrors Compose)
- Passwords/secrets MUST NOT be hardcoded in committed manifest files (enforced via `dark-factory-secrets` Secret)
- `AUTH_MODE=local` MUST NEVER appear in production manifests (enforced)
- Migrations run before container restart, never at startup (enforced in CI/CD Job ordering)
- `agent-tools` CMD remains `python -m src.server` (unchanged)

## Project Structure

### Documentation (this feature)

```text
specs/007-k3s-migration/
├── plan.md              # This file
├── research.md          # Phase 0: k3s, Helm, cert-manager decisions
├── data-model.md        # Phase 1: k8s resource topology and PVC sizing
├── quickstart.md        # Phase 1: How to provision and deploy from scratch
├── contracts/
│   ├── k8s-secret-schema.md     # Required secret keys
│   ├── ingress-routing.md       # Hostname → service mapping
│   └── cicd-deploy-contract.md  # Updated deploy stage interface
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
infra/
├── scripts/
│   └── setup-k3s.sh          # NEW: idempotent k3s + Helm + ingress + cert-manager setup

k8s/                           # NEW: full Kubernetes manifest tree
├── namespace.yaml
├── configmaps/
│   ├── postgres-init.yaml          # 01_create_databases.sql
│   ├── keycloak-realm.yaml         # realm-export.json + substitute-env.sh
│   ├── oauth2-proxy-config.yaml    # config.cfg
│   └── agent-registry.yaml         # development/agents/registry.yaml
├── infrastructure/
│   ├── postgres-statefulset.yaml
│   ├── postgres-service.yaml
│   ├── mongo-statefulset.yaml
│   ├── mongo-service.yaml
│   ├── keycloak-deployment.yaml
│   ├── keycloak-service.yaml
│   ├── oauth2-proxy-deployment.yaml
│   └── oauth2-proxy-service.yaml
├── backends/
│   ├── {service}-deployment.yaml   # × 6 (user-input-manager, ticket-manager,
│   └── {service}-service.yaml      #   orchestrator, context-distiller,
│                                   #   agent-tools, agent-dispatcher)
├── frontends/
│   ├── uim-frontend-deployment.yaml
│   ├── uim-frontend-service.yaml
│   ├── tm-frontend-deployment.yaml
│   └── tm-frontend-service.yaml
├── ingress/
│   ├── cluster-issuer.yaml         # cert-manager ClusterIssuer (staging + prod)
│   └── ingress.yaml                # Routes studio.* and tickets.*
└── monitoring/
    ├── service-monitors.yaml       # ServiceMonitor × 6 backends
    └── grafana-ingress.yaml        # grafana.dark-factory.local

.github/workflows/
└── ci-cd.yml                  # MODIFIED: deploy stage only

infra/DEPLOYMENT.md            # UPDATED: k3s setup, secrets doc, migration notes
```

**Structure decision**: New `k8s/` tree at the monorepo root alongside `infra/`. The existing `infra/` directory retains the Docker Compose files (for local development continuity during the migration) and gains `scripts/setup-k3s.sh`. Monitoring manifests live under `k8s/monitoring/` so `kubectl apply -f k8s/` installs everything in one pass.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| GHCR container registry (supersedes Principle XXII) | k3s pods pull images from a registry; they cannot access locally-built Docker images on the node filesystem | Building on VPS and importing via `docker save/load` into k3s is possible but fragile; it bypasses all k3s image management and breaks `kubectl rollout undo` which requires a registry tag |
| KUBECONFIG + GHCR_TOKEN in CI (supersedes Principle XXVI) | `kubectl` requires kubeconfig; `docker push ghcr.io` requires a PAT | Storing kubeconfig on VPS and SSH-ing to run kubectl defeats the purpose of k3s; no simpler auth path exists for GHCR |
