# Architecture Review: 005-github-actions-cicd — GitHub Actions CI/CD Pipeline

**Reviewer**: Software Architect Agent  
**Date**: 2026-06-25  
**Ticket**: GITH-005-0005  
**Artifacts reviewed**: spec.md, plan.md, research.md, data-model.md, contracts/ci-cd-workflow.md, contracts/detect-changes.md, contracts/manual-rollback-workflow.md, quickstart.md  
**Codebase verified**: ✅ (Dockerfiles, docker-compose.yml, service main.py health endpoints)

---

## Executive Summary

The design is **architecturally sound and ready for implementation**. All critical decisions
in plan.md, research.md, and the contracts are consistent with each other and with the
codebase. Three findings require attention before or during implementation:

| # | Severity | Finding |
|---|----------|---------|
| F1 | **CRITICAL** | agent-dispatcher health path mismatch: compose uses `/api/health`, but deploy contract says `/health` |
| F2 | **MEDIUM** | wait-healthy.sh port/path map must be service-specific — generic `/health` on a fixed port will fail agent-dispatcher |
| F3 | **LOW** | Dockerfile prerequisite state: T001–T004 already resolved in codebase; only T004 (ticket-manager entrypoint.sh) needs verification |

No architectural violations found against the project constitution.

---

## Findings

### F1 — CRITICAL: agent-dispatcher health path mismatch

**Evidence**:
- `infra/docker-compose.yml` line 332 healthcheck: `http://localhost:8000/api/health`
- `services/agent-dispatcher/src/main.py` line 84: route is `@app.get("/api/health")`
- `specs/005-github-actions-cicd/contracts/ci-cd-workflow.md` deploy job step 6 says `wait-healthy.sh {changed_services}` — polls `/health` endpoint
- `specs/005-github-actions-cicd/quickstart.md` Scenario 1 step 4 says `waits for /health to return 200`

**Risk**: If `wait-healthy.sh` polls `/health` for agent-dispatcher, it will get 404 and
report the service unhealthy, triggering an automatic rollback even on a successful deploy.

**Required fix**: `wait-healthy.sh` must use a per-service health path table, not a
hardcoded `/health`. Either:
- Option A (preferred): `wait-healthy.sh` accepts `service:port:path` tuples as arguments
- Option B: internal lookup map in `wait-healthy.sh` keyed by compose service name

The ServiceBuildPath table in `data-model.md` should be extended with a `health_path`
column. Implementation owner: devops (affects T010).

**Correction for contracts/ci-cd-workflow.md step 6**: change to:  
`wait-healthy.sh {changed_services}` — polls service-specific health path per internal table.

---

### F2 — MEDIUM: wait-healthy.sh must carry per-service port and health path

The deploy job health poll (contracts/ci-cd-workflow.md) uses SSH + `curl` against
`localhost:{port}`. Port values come from the compose internal port `8000` (all services
listen on 8000 internally; host port mapping only applies on local dev via override file).

On VPS production (without the override file), services communicate via Docker internal
network names, not host ports. The health poll must use internal Docker DNS
(`http://container-name:8000/path`) OR use `docker compose exec` to run curl inside
the container.

**Recommended approach**: VPS-side polling via `docker compose exec {service} curl --fail --silent http://localhost:8000{health_path}`. This avoids needing exposed host ports and works regardless of compose override configuration.

**Correction required in T010 implementation**: the 90-second health poll loop must use
`docker compose exec` (or equivalent docker network curl), not `curl localhost:{port}`.

---

### F3 — LOW: Dockerfile prerequisite state (T001–T005)

**Verified codebase state as of 2026-06-25**:

| Task | File | Documented Violation | Actual State |
|------|------|---------------------|--------------|
| T001 | `services/orchestrator/Dockerfile` | `alembic upgrade head &&` in CMD | ✅ Already clean — `CMD ["uvicorn", ...]` |
| T002 | `services/agent-dispatcher/Dockerfile` | `alembic upgrade head &&` in CMD | ✅ Already clean — `CMD ["uvicorn", ...]` |
| T003 | `services/user-input-manager/backend/Dockerfile` | `alembic upgrade head &&` in CMD | ✅ Already clean — `CMD ["uvicorn", ...]` |
| T004 | `services/ticket-manager/backend/entrypoint.sh` | alembic call in entrypoint | ✅ Already clean — `exec uvicorn src.main:app --host 0.0.0.0 --port 8000` only |
| T005 | `services/agent-tools/Dockerfile` + healthcheck | uvicorn sidecar CMD / HTTP healthcheck | ✅ Already resolved — CMD is `["python", "-m", "src.server"]`; healthcheck is `pgrep -f 'src.server'` |

**All Phase 1 Dockerfile tasks are already done in the codebase.** The backend and devops
agents can skip T001–T005 and proceed directly to Phase 2 (T006/T007). The tasks should
be transitioned to DONE or skipped.

This is a positive pre-condition — the pipeline constitution compliance is already in place.

---

## Architecture Validation

### Job Graph — APPROVED

```
push to main
    ↓
detect (git diff HEAD^ HEAD → JSON service array)
    ↓ has_changes == true
validate (matrix: ruff + docker build per service)
    ↓ all matrix jobs pass
test (matrix: pytest/vitest per service, 80% coverage gate)
    ↓ all matrix jobs pass
deploy (single job, concurrency: production, cancel-in-progress: false)
    ↓ snapshot → build → migrate → restart → health poll → [rollback on failure]
```

The sequential job chain with matrix parallelism within validate and test is the correct
design. Using `fromJSON(needs.detect.outputs.services)` for the matrix is the standard
GitHub Actions pattern for dynamic matrices. ✅

### Change Detection Strategy — APPROVED

`git diff --name-only HEAD^ HEAD` with `fetch-depth: 2` in actions/checkout is correct
and sufficient. The `infra/docker-compose.yml` → all-services trigger is properly scoped.
The NONE group (docs, specs, postgres init, .env.example) producing an empty array is
correct — these should not trigger CI work. ✅

One edge case not in the contract but worth noting: first commit to main (no `HEAD^`) will
fail `git diff HEAD^ HEAD`. The `detect-changes.sh` should handle this with:
```bash
git diff --name-only HEAD^ HEAD 2>/dev/null || git diff --name-only HEAD
```
This is a low-probability edge case but should be in the implementation.

### Rollback Snapshot Mechanism — APPROVED

`docker tag` for rollback snapshots is the correct choice for a no-registry VPS setup.
Retaining 3 most-recent rollback tags is operationally sound. Using a timestamp suffix
(`rollback-YYYYMMDDHHMMSS`) allows lexicographic sort to identify the most recent tag,
which `docker images --format '{{.Tag}}' ... | grep rollback | sort -r | head -1` handles
correctly. ✅

**One clarification for implementation**: the snapshot TIMESTAMP must be captured on the
VPS (inside the SSH action), not in the GitHub Actions runner, because the VPS clock
controls the image tags. The pipeline should capture `TIMESTAMP=$(date +%Y%m%d%H%M%S)` in
the first SSH step and reuse it in subsequent steps.

### Concurrency Control — APPROVED

`concurrency: group: production, cancel-in-progress: false` correctly queues rather than
cancels the second pipeline, satisfying FR-015. The group is scoped only to the `deploy`
job (not `validate`/`test`), which allows concurrent validation/testing runs for queued
commits while only serializing the deploy. This is the correct placement. ✅

### Migration-before-restart Pattern — APPROVED

Running `docker compose run --rm {service} alembic upgrade head` as a separate step
before `docker compose up -d` satisfies FR-011/FR-012. The abort-on-failure behavior
(leaving old containers running) is architecturally correct — after a failed migration
the schema is in an indeterminate state and restarting the new container would likely
cause a cascading failure. ✅

**Services requiring migration step** (from data-model.md): uim-backend, tm-backend,
orchestrator, context-distiller, agent-dispatcher. agent-tools, uim-frontend, tm-frontend,
nginx have no migration step. ✅

### Secret Management — APPROVED

Exactly 3 GitHub Actions secrets (VPS_HOST, VPS_USER, VPS_SSH_KEY). All application
secrets (DB passwords, Keycloak secrets, OpenAI key) live in `/app/dark-factory/infra/.env`
on the VPS, placed manually before first deploy, never committed. This satisfies FR-018
and FR-006 (the pipeline reads secrets from the VPS-side .env, not from GitHub). ✅

### Certbot Integration — APPROVED

`profiles: [certbot]` is the correct Docker Compose mechanism to prevent certbot from
starting with the standard `docker compose up`. The shared `letsencrypt` and `certbot_www`
volumes with read-only nginx mounts are architecturally correct. The nginx.conf.template
already has the `/.well-known/acme-challenge/` block. ✅

---

## Implementation Guidance for Agents

### For devops agent

1. **Phase 1 (T001–T005)**: Skip or mark done — all Dockerfile changes are already in
   the codebase. Verify with `git diff main` before creating TM tickets for these.

2. **T006 detect-changes.sh**: Add first-commit guard:
   ```bash
   BASE=${1:-HEAD^}
   CHANGED=$(git diff --name-only "$BASE" HEAD 2>/dev/null || git diff --name-only HEAD)
   ```

3. **T010 deploy job health polling**: Use `docker compose exec` pattern:
   ```bash
   # Per-service health path table in wait-healthy.sh
   declare -A HEALTH_PATHS=(
     ["user-input-manager"]="/health"
     ["ticket-manager"]="/health"
     ["orchestrator"]="/health"
     ["context-distiller"]="/health"
     ["agent-dispatcher"]="/api/health"
     ["nginx"]=""   # no health check
   )
   # Poll via: docker compose exec {compose_svc} curl -sf http://localhost:8000${HEALTH_PATHS[$svc]}
   ```

4. **T010 TIMESTAMP capture**: Capture once on VPS at snapshot time:
   ```bash
   TIMESTAMP=$(date +%Y%m%d%H%M%S)
   # Pass or reuse in same SSH action block for snapshot and restore
   ```

### For backend agent

T001–T005 are already resolved. Proceed to any backend-specific test configuration tasks
if assigned.

### For security-architect agent

FR-018 is structurally sound — 3 secrets only. No app secrets in workflow files.
Key threat surface: the SSH key grants full VPS access; GitHub Actions environment
should be scoped to the `main` branch only (branch protection + environment protection
rules in GitHub settings). This is an operational concern outside the workflow files
themselves but should be documented in DEPLOYMENT.md (T014).

---

## Updated ServiceBuildPath Table (with health paths)

Replaces the table in `data-model.md` — devops should use this for `wait-healthy.sh`:

| Service Name | Compose Service Name | Health Path | Has Migrations |
|---|---|---|---|
| `uim-backend` | `user-input-manager` | `/health` | ✅ |
| `tm-backend` | `ticket-manager` | `/health` | ✅ |
| `orchestrator` | `orchestrator` | `/health` | ✅ |
| `context-distiller` | `context-distiller` | `/health` | ✅ |
| `agent-dispatcher` | `agent-dispatcher` | `/api/health` | ✅ |
| `agent-tools` | `agent-tools` | *(pgrep only — no HTTP)* | ❌ |
| `uim-frontend` | `uim-frontend` | *(nginx wget — no HTTP API)* | ❌ |
| `tm-frontend` | `tm-frontend` | *(nginx wget — no HTTP API)* | ❌ |
| `nginx` | `nginx` | *(no health check)* | ❌ |

---

## Constitution Compliance Check

No violations found. All 28 constitution principles reviewed in plan.md are correctly
assessed. The most critical ones for this feature:

- **XXII (Build on VPS, Not in CI)**: ✅ — deploy job uses SSH to VPS; no `docker push`
- **XXIV (Migrations Before Container Restart)**: ✅ — Dockerfiles clean; pipeline owns migrations
- **XXV (Automatic Rollback on Healthcheck Failure)**: ✅ — 90s poll + docker tag restore
- **XXVI (VPS-Only Secrets)**: ✅ — exactly 3 GitHub secrets
- **XXVII (Validation Gates)**: ✅ — ruff + docker build in validate before any VPS SSH
- **XXVIII (CI Tests Use SQLite + mongomock + AUTH_MODE=local)**: ✅ — test job env vars correct

---

## Well-Architected Pillars

| Pillar | Assessment |
|--------|-----------|
| **Operational Excellence** | Path-based change detection avoids unnecessary work. Sequential gates prevent bad deploys. The 90s rollback window is tight but achievable for HTTP services. |
| **Security** | 3-secret model is minimal and correct. VPS SSH key scope should be locked to main branch via GitHub environment protection (note for T014). |
| **Reliability** | Automatic rollback on health failure is solid. Concurrency queuing prevents race conditions. Migration-abort-on-failure preserves data integrity. |
| **Performance Efficiency** | Matrix parallelism in validate/test is efficient. Single-service detection avoids rebuilding unchanged services. Full-pipeline target of ≤10 min (SC-001) is achievable. |
| **Cost Optimization** | VPS-only build (no container registry) eliminates registry costs. Ubuntu hosted runners are standard pricing. |
| **Sustainability/Maintainability** | All logic in shell scripts (portable, locally testable). Contracts are explicit and versioned. Single-VPS simplicity is appropriate for this scale. |

---

## Gate Assessment

| Gate | Status |
|------|--------|
| Gate A — Design Readiness | ✅ PASS — goals, non-goals, assumptions, ADRs (D001–D011), contracts, data model all documented |
| Gate B — Security Readiness | ✅ PASS — secret model correct; SSH key scope note added for T014 |
| Gate C — Delivery Readiness | ✅ PASS with F1/F2 corrections — tasks are dependency-ordered; T010 needs health path fix before implementation |
| Gate D — Release Readiness | ⚠️ DEFERRED — monitoring, alerting, and runbooks are explicitly out of scope per spec assumptions |

**Architecture is READY FOR IMPLEMENTATION** with F1 and F2 corrections applied to T010.
