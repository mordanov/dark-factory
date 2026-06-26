# Research: GitHub Actions CI/CD Pipeline

**Feature**: 005-github-actions-cicd
**Date**: 2026-06-25
**Status**: Complete — all NEEDS CLARIFICATION resolved

## Decision Log

---

### D001: Change detection strategy

**Decision**: `git diff --name-only HEAD^ HEAD` piped through a fixed path-to-service map
in `.github/scripts/detect-changes.sh`, outputting a JSON array of service names.

**Rationale**: Cheapest possible diff — no GitHub API calls, no Actions path-filter steps
that add concurrency complexity. The map is maintained in one script so service ownership
is explicit. Output is JSON so the caller (`ci-cd.yml`) can use `fromJSON()` in matrix jobs.

**Alternatives considered**:
- `dorny/paths-filter` Action — adds third-party dependency; wrapping in a script keeps
  the logic portable (runnable locally for debugging).
- Comparing full tree with `git status` — doesn't isolate per-commit changes in squash-merge
  scenarios.

---

### D002: `detect-changes.sh` full-rebuild trigger

**Decision**: If `infra/docker-compose.yml` appears in the diff, emit ALL service names.
`infra/.env.example` and `infra/postgres/**` changes emit an empty array (no rebuild).

**Rationale**: `docker-compose.yml` owns image build configuration for every service;
any structural change could affect any of them. `.env.example` is documentation-only.
`infra/postgres/**` covers SQL migration scripts that are applied manually or through
database initialization, not through container rebuilds.

**Alternatives considered**:
- Per-compose-key diffing — complex, fragile, overkill for single-VPS.

---

### D003: SSH to VPS — approach

**Decision**: `appleboy/ssh-action@v1` for multi-command SSH blocks. For pre-deployment
snapshot step, a separate `ssh-action` call runs the snapshot script. This keeps deploy
logic on the VPS as shell scripts rather than inline YAML heredocs.

**Rationale**: `appleboy/ssh-action` is the de facto standard for single-VPS SSH in
GitHub Actions. It handles connection retry and multi-line scripts cleanly. Alternative
(`webfactory/ssh-agent` + `ssh -o StrictHostKeyChecking=no`) requires managing the
known_hosts file manually.

**Alternatives considered**:
- Ansible — heavyweight; requires Python + pip on the CI runner.
- Fabric (Python) — second language in the pipeline, no benefit over ssh-action.

---

### D004: Rollback snapshot mechanism

**Decision**: Before each deploy, on VPS:
```sh
for svc in $SERVICES; do
  docker tag dark-factory-${svc}:latest dark-factory-${svc}:rollback-${TIMESTAMP}
done
```
After failed healthcheck, restore via `docker tag dark-factory-${svc}:rollback-${TIMESTAMP} dark-factory-${svc}:latest` and `docker compose up -d`.

Retain 3 most recent rollback tags per service; delete older ones.

**Rationale**: `docker tag` is instant (metadata-only) and requires no registry.
Rollback images are stored on the VPS disk alongside the current images. The TIMESTAMP
is captured once at snapshot time so all services in one deployment share the same tag.

**Alternatives considered**:
- Git-based rollback (re-checkout commit on VPS) — requires git pull, full rebuild;
  too slow for emergency recovery.
- Docker image save/load — exports large tarballs; wasteful when images share base layers.

---

### D005: Health check polling approach

**Decision**: Poll each deployed service's `/health` endpoint with `curl --fail --silent`
every 5 seconds, up to 90 seconds total. Services that have no HTTP health endpoint
(none currently, but handled gracefully) are treated as passed after container start.

Implementation: a VPS-side `wait-healthy.sh` helper called by `ci-cd.yml`'s deploy stage.

**Rationale**: Direct HTTP polling is simpler than parsing `docker compose ps` JSON output
which varies by Docker version. The `/health` endpoint already exists in every service.

**Alternatives considered**:
- `docker compose ps --format json | jq ...` — Docker Compose health status is only
  set when `healthcheck:` is defined in the compose file; all services already have it,
  but the wait-for-healthy loop is still needed.

---

### D006: Concurrency control

**Decision**: GitHub Actions `concurrency` group on the deploy job:
```yaml
concurrency:
  group: production
  cancel-in-progress: false
```

**Rationale**: `cancel-in-progress: false` queues the second run rather than cancelling it,
so both pushes eventually deploy. This matches FR-015 exactly.

**Alternatives considered**:
- `cancel-in-progress: true` — drops the second deployment; a fast-follow commit would
  never reach production without a manual re-trigger.

---

### D007: CI test stack

**Decision**: Each Python backend uses `pytest` with `AUTH_MODE=local` and `TEST_JWT_SECRET`
set in the workflow env. SQLite via `aiosqlite` (already in orchestrator requirements; verify
other services). MongoDB services use `mongomock-motor`. External HTTP calls mocked via
`respx` or `unittest.mock.AsyncMock`.

**Rationale**: All 6 `conftest.py` files already exist and several already have `AUTH_MODE`
test support (confirmed via grep). No new test infrastructure to invent.

**Current state — alembic-in-CMD violations that MUST be removed as part of this feature
(constitution XXIV):**

| Service | Violation location |
|---------|-------------------|
| `services/orchestrator/Dockerfile` | CMD runs `alembic upgrade head &&` |
| `services/agent-dispatcher/Dockerfile` | CMD runs `alembic upgrade head &&` |
| `services/user-input-manager/backend/Dockerfile` | CMD runs `alembic upgrade head &&` |
| `services/ticket-manager/backend/entrypoint.sh` | entrypoint runs `alembic upgrade head` |

**agent-tools CMD violation (constitution item 49):**
Current CMD: `uvicorn src.sidecar:app --host 0.0.0.0 --port 8000`
Required CMD: `python -m src.server`

---

### D008: Frontend test invocation in CI

**Decision**: `npm ci && npm run test -- --run` (Vitest non-interactive mode) inside the
changed frontend service directory. Coverage enforced via `--coverage` flag and Vitest's
`coverageThreshold` in `vite.config.ts` (already configured per constitution VII).

**Rationale**: Both frontends already use Vitest. `--run` prevents interactive watch mode
hanging the CI job.

---

### D009: Certbot in docker-compose.yml

**Decision**: Add certbot service to `infra/docker-compose.yml` with `profiles: [certbot]`.
Mount Let's Encrypt volume shared with nginx.

**Rationale**: `nginx.conf.template` already has `/.well-known/acme-challenge/` and
commented SSL blocks. Certbot just needs to be wired in with the `profiles:` guard so
it never starts accidentally.

**Current state**: `infra/docker-compose.yml` has no certbot service — needs to be added.
`nginx.conf.template` is already SSL-ready.

---

### D010: VPS setup script scope

**Decision**: `infra/scripts/setup-vps.sh` covers: Docker install, user `ubuntu` added to
`docker` group, repo clone at `/app/dark-factory/`, `.env` placement reminder, SSH key
deployment from GitHub Secrets guide. Written as an **idempotent** script (safe to re-run).

**Rationale**: The script is for human-assisted first-time setup, not automated; idempotency
prevents re-runs from breaking a partially configured VPS.

---

### D011: service-to-path.sh necessity

**Decision**: Separate `service-to-path.sh` alongside `detect-changes.sh`. `detect-changes.sh`
maps file paths → service names (for change detection); `service-to-path.sh` maps service
names → VPS build paths (for SSH deploy commands).

**Rationale**: These are inverse operations. Keeping them separate makes each independently
testable and avoids a single bloated mapping script.

---

## Pre-existing CI/CD infrastructure

`.github/workflows/infra-checks.yml` already exists and handles:
- `AUTH_MODE=local` guard on `infra/docker-compose.yml`
- `docker-compose.yml` YAML syntax validation

The new `ci-cd.yml` MUST NOT duplicate these checks. The infra-checks workflow continues
independently (runs on infra/ path changes, not on every push to main).
