# Tasks: GitHub Actions CI/CD Pipeline

**Input**: Design documents from `specs/005-github-actions-cicd/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US4)

---

## Phase 1: Setup — Dockerfile Fixes (Constitution Compliance)

**Purpose**: Remove `alembic upgrade head` from all backend CMDs and fix `agent-tools` CMD.
These are blocking prerequisites: the pipeline MUST NOT run migrations at container startup.
Each task touches a different file and can run in parallel.

**⚠️ CRITICAL**: No pipeline work can begin until this phase is complete — the deploy stage
relies on running migrations as a separate step.

- [ ] T001 [P] Remove `alembic upgrade head` from `services/orchestrator/Dockerfile` CMD — replace `CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 1"]` with `CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]`
- [ ] T002 [P] Remove `alembic upgrade head` from `services/agent-dispatcher/Dockerfile` CMD — replace `CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 1"]` with `CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]`
- [ ] T003 [P] Remove `alembic upgrade head` from `services/user-input-manager/backend/Dockerfile` CMD — replace the multi-line `CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 2"]` with `CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]`
- [ ] T004 [P] Remove `alembic upgrade head` from `services/ticket-manager/backend/entrypoint.sh` — delete the entire `python - <<'EOF' ... asyncio.run(migrate())` block and the `python -m src.core.seed` line; keep only `exec uvicorn src.main:app --host 0.0.0.0 --port 8000`
- [ ] T005 [P] Change `services/agent-tools/Dockerfile` CMD to `["python", "-m", "src.server"]` (MCP stdio only; remove sidecar uvicorn CMD); also update `agent-tools` healthcheck in `infra/docker-compose.yml` from HTTP to process-existence check: `test: ["CMD-SHELL", "pgrep -f 'src.server' || exit 1"]`

**Checkpoint**: All service startup commands are alembic-free. `agent-tools` runs as MCP stdio.

---

## Phase 2: Foundational — Change Detection Scripts

**Purpose**: Core scripts that all CI pipeline stages depend on. Must exist before `ci-cd.yml`
can reference them.

- [ ] T006 Create `.github/scripts/` directory and write `.github/scripts/detect-changes.sh` — executable bash script that: (1) runs `git diff --name-only HEAD^ HEAD`, (2) maps changed paths to service names using the ServiceMap from `data-model.md` (uim-backend, tm-backend, orchestrator, context-distiller, agent-dispatcher, agent-tools, uim-frontend, tm-frontend, nginx), (3) if `infra/docker-compose.yml` changed emits ALL 9 service names, (4) if only docs/specs/.env.example/postgres-init changed emits empty array, (5) deduplicates and writes compact JSON array to stdout, (6) exits 0 always; run `chmod +x .github/scripts/detect-changes.sh`
- [ ] T007 Write `.github/scripts/service-to-path.sh` — executable bash script that accepts a service name argument and echoes two values: the Docker Compose service name and the build context path relative to repo root; implement the ServiceBuildPath table from `data-model.md`; exit 1 for unknown service names; run `chmod +x .github/scripts/service-to-path.sh`

**Checkpoint**: Run `.github/scripts/detect-changes.sh` locally — must emit valid JSON. Test
`.github/scripts/service-to-path.sh tm-backend` — must print `ticket-manager` and
`services/ticket-manager/backend`.

---

## Phase 3: User Story 1 — Automated Validation on Every Push (P1) 🎯 MVP

**Goal**: Every push to `main` runs ruff + docker build for changed services before any VPS
contact. Catches code quality and Dockerfile errors in CI.

**Independent Test**: Push a commit with a ruff violation to `main`. `detect` identifies the
changed service, `validate` runs ruff, pipeline fails before `test` or `deploy` runs.

- [ ] T008 [US1] Create `.github/workflows/ci-cd.yml` with two jobs: (1) `detect` job: `actions/checkout@v4` with `fetch-depth: 2`, runs `.github/scripts/detect-changes.sh`, sets outputs `services` (JSON string) and `has_changes` (`"true"/"false"`); (2) `validate` job: `needs: detect`, `if: needs.detect.outputs.has_changes == 'true'`, `strategy.matrix.service: ${{ fromJSON(needs.detect.outputs.services) }}`, runs on `ubuntu-latest`; steps: checkout, setup Python 3.12 (for Python services), run `ruff check` and `ruff format --check` in the service directory (skip for frontend/nginx), run `docker build --no-cache -f <service-dockerfile> <build-context>` for each service; fail on any error

**Checkpoint**: Push a commit changing only `services/ticket-manager/backend/src/`. Pipeline
runs `detect` → `validate` for `tm-backend` only. No VPS SSH occurs.

---

## Phase 4: User Story 2 — Automated Tests Before Deployment (P2)

**Goal**: After validation passes, run pytest and vitest for each changed service. Block
deployment if any test fails or coverage drops below 80%.

**Independent Test**: Break a pytest test in `services/ticket-manager/backend/tests/`.
After T008's `validate` passes, the `test` job fails and no `deploy` job runs.

- [ ] T009 [US2] Add `test` job to `.github/workflows/ci-cd.yml` — `needs: validate`, `if: needs.detect.outputs.has_changes == 'true'`, same service matrix; for Python backend services: setup Python 3.12, `pip install -r requirements.txt`, run `pytest --cov --cov-fail-under=80` with env vars `AUTH_MODE=local`, `TEST_JWT_SECRET=ci-test-secret`, `DATABASE_URL=sqlite+aiosqlite:///:memory:`, `MONGO_URL=mongomock://localhost` (for orchestrator, context-distiller), `OPENAI_API_KEY=test-key`, `OPENAI_BASE_URL=http://localhost:9999`; for frontend services (uim-frontend, tm-frontend): setup Node.js 20, `npm ci`, `npm run test -- --run --coverage`; skip for nginx/agent-tools (no test suite)

**Checkpoint**: Push a commit that breaks a test — `test` job fails, pipeline exits red, no
deploy occurs. Fix the test, push again — pipeline goes green through `test`.

---

## Phase 5: User Story 3 — Automated Deployment with Safe Rollback (P3)

**Goal**: After validation and tests pass, deploy changed services to VPS via SSH. Migrate
databases before restarting containers. Auto-rollback on healthcheck failure.

**Independent Test**: Push a commit that introduces a startup crash. `validate` and `test`
pass. `deploy` starts, service crashes, healthcheck times out after 90s, pipeline
automatically restores previous image and exits 1. VPS continues running old version.

- [ ] T010 [US3] Add `deploy` job to `.github/workflows/ci-cd.yml` — `needs: test`, `if: needs.detect.outputs.has_changes == 'true'`, concurrency `group: production, cancel-in-progress: false`; uses `appleboy/ssh-action@v1` with `secrets.VPS_HOST`, `secrets.VPS_USER`, `secrets.VPS_SSH_KEY`; steps: (1) git pull on VPS, (2) snapshot: `docker tag dark-factory-{service}:latest dark-factory-{service}:rollback-$(date +%Y%m%d%H%M%S)` for each service in matrix, retain only 3 most recent rollback tags (delete older), (3) `docker compose -f infra/docker-compose.yml build {compose-service}`, (4) for each migration-enabled service (uim-backend/tm-backend/orchestrator/context-distiller/agent-dispatcher): `docker compose -f infra/docker-compose.yml run --rm {compose-service} alembic upgrade head` — abort entire deploy on failure leaving old containers running, (5) `docker compose -f infra/docker-compose.yml up -d {compose-service}`, (6) health poll loop: `curl --fail --silent http://localhost:{port}/health` every 5s up to 90s, (7) on poll timeout: restore snapshot tags + `docker compose up -d` + exit 1
- [ ] T011 [US3] Add certbot service to `infra/docker-compose.yml` with `profiles: [certbot]` — image: `certbot/certbot`, volumes: `letsencrypt:/etc/letsencrypt` and `certbot_www:/var/www/certbot`; add both volumes to the top-level `volumes:` section; add `letsencrypt` volume as read-only mount to nginx service at `/etc/letsencrypt:ro` and `certbot_www` at `/var/www/certbot:ro` (nginx.conf.template already has the /.well-known block)
- [ ] T012 [US3] Write `infra/scripts/setup-vps.sh` — idempotent bash script (safe to re-run) that: installs Docker via apt-get official repo (if not already installed), adds `ubuntu` user to `docker` group (if not already member), creates `/app/dark-factory/` directory, clones the repo if not present, verifies `docker compose version` is v2+, prints reminder to place `.env` at `/app/dark-factory/infra/.env`; mark executable with `chmod +x`

**Checkpoint**: Verify certbot service is NOT started by `docker compose -f infra/docker-compose.yml up` (it requires `--profile certbot`). Trigger a manual deploy test via pushing a non-breaking change. Monitor the GitHub Actions deploy log to confirm snapshot → build → migrate → restart → healthcheck sequence.

---

## Phase 6: User Story 4 — Emergency Manual Rollback (P4)

**Goal**: An operator can trigger a rollback for any service via GitHub Actions UI with an
audit trail capturing actor, timestamp, and reason.

**Independent Test**: In GitHub Actions UI, trigger `manual-rollback` with service=`tm-backend`
and reason=`test rollback`. Verify the workflow run log shows actor, reason, and that the
VPS restores the most recent rollback snapshot for `ticket-manager`.

- [ ] T013 [US4] Write `.github/workflows/manual-rollback.yml` — `on: workflow_dispatch` with inputs: `service` (choice: uim-backend, tm-backend, orchestrator, context-distiller, agent-dispatcher, agent-tools, uim-frontend, tm-frontend, nginx, all) and `reason` (string, required); single job `rollback`: logs `Rollback triggered by ${{ github.actor }} at ${{ github.run_started_at }} | Service: ${{ inputs.service }} | Reason: ${{ inputs.reason }}`; uses `appleboy/ssh-action@v1` to SSH to VPS; for each target service finds most recent `rollback-*` tag via `docker images --format '{{.Tag}}' dark-factory-{service} | grep rollback | sort -r | head -1`, restores with `docker tag dark-factory-{service}:{rollback-tag} dark-factory-{service}:latest` + `docker compose -f infra/docker-compose.yml up -d {compose-service}`; logs warning and continues if no rollback tag found; exits 1 if any service restoration fails

**Checkpoint**: Manually trigger the workflow from the Actions UI. Verify the job log shows
the audit info and the VPS service is restarted with the rollback image.

---

## Phase 7: Polish & Documentation

**Purpose**: Operator documentation and end-to-end validation.

- [ ] T014 Write `infra/DEPLOYMENT.md` — operator guide covering: (1) GitHub Actions secrets table (VPS_HOST, VPS_USER, VPS_SSH_KEY — nothing else), (2) first-time VPS setup steps using `infra/scripts/setup-vps.sh`, (3) `.env` placement at `/app/dark-factory/infra/.env`, (4) certbot SSL certificate procedure using `--profile certbot`, (5) nginx SSL activation steps (uncomment SSL blocks in nginx.conf.template), (6) manual rollback procedure via GitHub Actions UI, (7) rollback snapshot retention policy (3 most recent per service), (8) certbot renewal cron job example
- [ ] T015 Validate against quickstart.md scenarios 1–6: run through each scenario (doc-only push, single service push, full rebuild push, test failure blocking deploy, certbot not starting with normal up, manual rollback trigger) and confirm pipeline behaviour matches expected outcomes documented in `specs/005-github-actions-cicd/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Dockerfiles)**: No dependencies — start immediately; all 5 tasks are parallel
- **Phase 2 (Scripts)**: Can start alongside Phase 1 (different files); T007 must follow T006
- **Phase 3 (US1 validate job)**: Depends on Phase 2 complete (needs detect-changes.sh)
- **Phase 4 (US2 test job)**: Depends on Phase 3 (modifies same ci-cd.yml file)
- **Phase 5 (US3 deploy job)**: Depends on Phase 4 (modifies same ci-cd.yml file); T011/T012 parallel with T010
- **Phase 6 (US4 rollback)**: Depends on Phase 5 (VPS infrastructure must be in place)
- **Phase 7 (Polish)**: Depends on all story phases complete

### User Story Dependencies

- **US1 (validate)**: Needs Foundational phase (Scripts) complete. T008 creates ci-cd.yml
- **US2 (test)**: Needs US1 complete. T009 modifies existing ci-cd.yml
- **US3 (deploy)**: Needs US2 complete. T010 modifies existing ci-cd.yml; T011/T012 independent
- **US4 (rollback)**: Needs US3 deploy infrastructure. T013 is a new file (parallel with T015)

### Parallel Opportunities

```bash
# Phase 1 — all 5 can run simultaneously (different files):
T001  # services/orchestrator/Dockerfile
T002  # services/agent-dispatcher/Dockerfile
T003  # services/user-input-manager/backend/Dockerfile
T004  # services/ticket-manager/backend/entrypoint.sh
T005  # services/agent-tools/Dockerfile + infra/docker-compose.yml healthcheck

# Phase 2 — T006 then T007 (T007 depends on directory existing):
T006 → T007

# Phase 5 — T011 and T012 can run while T010 is being developed:
T010 (deploy job in ci-cd.yml) ← sequential with T008/T009
T011 (certbot in docker-compose.yml)  ← parallel with T010
T012 (setup-vps.sh)                   ← parallel with T010
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Dockerfile fixes (unblocks safe deployment)
2. Complete Phase 2: detect-changes.sh + service-to-path.sh
3. Complete Phase 3: T008 — ci-cd.yml with detect + validate
4. **STOP and VALIDATE**: Push a test commit, confirm validate job runs for changed service only
5. CI validation is live — PRs now get ruff + docker build checks

### Incremental Delivery

1. Phase 1 + Phase 2 → safe-start services + detection scripts ready
2. Phase 3 (T008) → automated validation on every push ← **MVP**
3. Phase 4 (T009) → automated tests gate deployment
4. Phase 5 (T010–T012) → fully automated deploy with rollback
5. Phase 6 (T013) → emergency rollback via UI
6. Phase 7 (T014–T015) → fully documented and validated

### Parallel Team Strategy

With multiple agents:

1. All agents start Phase 1 in parallel (5 different Dockerfiles)
2. Agent A: T006 → T007 (scripts), then T008 (US1 validate)
3. Agent B: T011 (certbot) + T012 (setup-vps.sh) in parallel with Agent A's work
4. Sequential: T009 (US2 test) → T010 (US3 deploy) — must follow in order on same file
5. Agent C: T013 (manual-rollback.yml) once VPS infra is in place

---

## Notes

- Tasks T001–T005 are one-line Dockerfile changes — fast and safe
- T006/T007 shell scripts must be `chmod +x` to be executable in CI
- T008, T009, T010 all modify `ci-cd.yml` sequentially — never in parallel
- T011 modifies `docker-compose.yml` — verify certbot service has `profiles: [certbot]` before commit
- The `agent-tools` healthcheck change in T005 affects `infra/docker-compose.yml` — coordinate with T011 if running in parallel (same file)
- After T010: add `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` to GitHub Actions Secrets before first live run
- T015 is a validation task, not implementation — run after all other tasks complete
