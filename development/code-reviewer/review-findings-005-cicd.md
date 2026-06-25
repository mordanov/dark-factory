# Code Review: 005-github-actions-cicd

**Reviewed by**: code-reviewer agent  
**Date**: 2026-06-25  
**Scope**: T001–T015 — Dockerfile fixes, change detection scripts, CI/CD workflow (ci-cd.yml), docker-compose certbot (T011), setup-vps.sh (T012), manual-rollback.yml (T013), DEPLOYMENT.md (T014)

---

## Code Review Result

### Decision
**CHANGES REQUESTED**

### Scope Reviewed
- `services/orchestrator/Dockerfile` (T001)
- `services/agent-dispatcher/Dockerfile` (T002)
- `services/user-input-manager/backend/Dockerfile` (T003)
- `services/ticket-manager/backend/entrypoint.sh` (T004)
- `services/agent-tools/Dockerfile` + healthcheck in `infra/docker-compose.yml` (T005)
- `.github/scripts/detect-changes.sh` (T006)
- `.github/scripts/service-to-path.sh` (T007)
- `.github/workflows/ci-cd.yml` — detect/validate/test/deploy (T008–T010)
- `infra/docker-compose.yml` — certbot service + volumes + nginx mounts (T011)
- `infra/scripts/setup-vps.sh` (T012)
- `.github/workflows/manual-rollback.yml` (T013)
- `infra/DEPLOYMENT.md` (T014)

### Summary
Phase 1 (Dockerfile fixes) and foundational scripts are clean and correct. The CI/CD workflow is impressively well-structured: GitHub Actions are pinned to full commit SHAs, service name allowlist validation prevents injection, and the detect→validate→test→deploy flow satisfies all FR-001 through FR-020 requirements. Two **Blockers** are present in the deploy script that will cause rollback failures in production. These must be fixed before merge.

---

## Blockers

### Blocker 1: Image name mismatch in snapshot/rollback logic

**Location:** `.github/workflows/ci-cd.yml:278–285`, `:353–358`; `.github/workflows/manual-rollback.yml:84–94`

**Issue:** The snapshot and rollback logic constructs image names as `dark-factory-${SVC}` where `$SVC` is the pipeline service name (`tm-backend`, `uim-backend`). Docker Compose v2, when no `image:` field is specified in the service definition, names built images as `{project_name}-{compose_service_name}:latest`. Running `docker compose -f infra/docker-compose.yml build ticket-manager` from `/app/dark-factory/` produces `dark-factory-ticket-manager:latest` — **not** `dark-factory-tm-backend:latest`.

Affected services (pipeline name ≠ compose service name):
- `uim-backend` → compose builds `dark-factory-user-input-manager:latest`
- `tm-backend` → compose builds `dark-factory-ticket-manager:latest`

All other pipeline names match their compose service names (`orchestrator`, `context-distiller`, `agent-dispatcher`, `agent-tools`, `uim-frontend`, `tm-frontend`, `nginx`).

**Impact:** For `uim-backend` and `tm-backend`, `docker image inspect "dark-factory-${SVC}:latest"` returns "not found" on every deploy — snapshots are never created. On any failure, rollback cannot restore these two services. The pipeline silently skips the snapshot (prints "No existing image") rather than failing, masking the bug until a real rollback is needed.

**Required action — two options (choose one):**

Option A — Fix the deploy script to use compose service names for image naming:
```bash
# In ci-cd.yml snapshot loop (lines ~278–285):
CSVC=$(compose_name "$SVC")
IMAGE="dark-factory-${CSVC}:latest"
# Similarly for rollback_tag lookup: use "dark-factory-${CSVC}"
```

Option B — Add explicit `image:` fields to docker-compose.yml for the two mismatched services:
```yaml
user-input-manager:
  image: dark-factory-uim-backend:latest
  build: ...

ticket-manager:
  image: dark-factory-tm-backend:latest
  build: ...
```

Apply the same fix to `manual-rollback.yml` rollback_service() function.

**Evidence:** Docker Compose v2 image naming convention: image name = `{COMPOSE_PROJECT_NAME}-{service_name}:latest` when no explicit `image:` is set. The project name when running from `/app/dark-factory/` without a `name:` in compose file = `dark-factory`. Compose service names for both affected services differ from pipeline short-names.

---

### Blocker 2: Health check uses `curl` not present in `python:3.12-slim` images

**Location:** `.github/workflows/ci-cd.yml:335`

**Issue:** The health check loop runs `$COMPOSE exec -T "$CSVC" curl -sf "http://localhost:8000${HPATH}"`. This executes `curl` inside the running container. All Python backend service images are based on `python:3.12-slim`, which does not include `curl`. The `exec curl` call will fail with "executable not found" on every check.

**Impact:** Every deployment of a backend service will time out the 90-second health check window and trigger automatic rollback — even when the service is healthy. All backend deployments will roll back immediately, making the deploy stage non-functional.

**Required action:** Replace the `curl` exec with a `python3 urllib` call matching the pattern already used in `docker-compose.yml` healthchecks:
```bash
# Line 335 replacement:
if $COMPOSE exec -T "$CSVC" python3 -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:8000${HPATH}')" \
    >/dev/null 2>&1; then
```

Alternatively, poll Docker Compose's own healthcheck status:
```bash
if [ "$(docker inspect --format='{{.State.Health.Status}}' \
    "$(docker compose -f infra/docker-compose.yml ps -q "$CSVC")" 2>/dev/null)" = "healthy" ]; then
```

**Evidence:** `python:3.12-slim` Dockerfile installs only Python runtime, pip, and standard library. No `curl` package is installed. The `docker-compose.yml` healthchecks already correctly use `python3 -c "import urllib.request; ..."` (lines 160, 190, 228, 265, 331) for the same reason.

---

## Major Findings

### Major 1: `manual-rollback.yml` missing `set -e`

**Location:** `.github/workflows/manual-rollback.yml:55`

**Issue:** The rollback SSH script uses `set -uo pipefail` but omits `-e`. Without `-e`, a failed `docker tag` or `$COMPOSE up -d` in `rollback_service()` does not abort the function — the function calls after the failed command still run, and the function returns 0 despite partial failure.

**Impact:** A rollback may appear to succeed (exit 0) even when the `docker tag` step silently failed. The service would then restart with the wrong (or new, broken) image. Under an incident, this could extend downtime.

**Required action:** Add `-e` to the set line: `set -euo pipefail`.

**Evidence:** POSIX `set -e` exits a function on the first failing command. Without it, `docker tag "dark-factory-${SVC}:${ROLLBACK_TAG}" "dark-factory-${SVC}:latest" && $COMPOSE up -d "$CSVC"` is not affected (the `&&` handles sequential failure), but any standalone command before or after those in the function would silently fail through.

---

## Minor Findings

### Minor 1: `setup-vps.sh` has placeholder repo URL

**Location:** `infra/scripts/setup-vps.sh:7`

**Issue:** `REPO_URL="https://github.com/your-org/dark-factory.git"` is a hardcoded placeholder. Running the script on a fresh VPS would fail at the `git clone` step with "Repository not found."

**Impact:** Operator would discover this on first-time setup. Low risk since the script is run manually and the error is clear, but the placeholder creates unnecessary friction.

**Required action:** Either accept a `REPO_URL` argument (`REPO_URL="${1:?Usage: setup-vps.sh <repo-url>}"`), or document in DEPLOYMENT.md that the operator must edit this variable before running the script.

---

### Minor 2: detect-changes.sh initial-commit edge case

**Location:** `.github/scripts/detect-changes.sh:15`

**Issue:** On the very first push to main (where no parent commit exists), `git diff --name-only HEAD^ HEAD` fails. The `|| true` returns an empty string → `[]` → `has_changes=false` → pipeline does nothing. The initial deployment must be done manually.

**Impact:** Not a bug — it's a safe failure mode. However, it is undocumented, and an operator might be confused when the first push produces no pipeline activity.

**Required action:** Add a note to `infra/DEPLOYMENT.md` that the initial deployment must be performed manually via SSH before the pipeline handles subsequent pushes. Alternatively, handle the initial commit case by emitting all services when `HEAD^` is unavailable.

---

### Nit 1: `${{ inputs.reason }}` interpolated directly in audit log shell step

**Location:** `.github/workflows/manual-rollback.yml:39`

**Issue:** `echo " Reason: ${{ inputs.reason }}"` directly interpolates the user-provided input into a shell `run:` command. Shell metacharacters (quotes, backticks, `$()`) in the reason string could cause the step to fail. This is not a security risk (workflow_dispatch requires write access) but it could cause the audit log to be silently corrupted.

**Required action:** Pass `inputs.reason` via an env var instead:
```yaml
env:
  REASON: ${{ inputs.reason }}
run: echo "  Reason: $REASON"
```

---

## Tests and Evidence Reviewed

- All 5 Dockerfiles confirmed alembic-free (T001–T004 ✓; T005 CMD changed to `python -m src.server` ✓)
- `infra/docker-compose.yml` agent-tools healthcheck updated to process check (T005 ✓)
- `detect-changes.sh` handles infra/docker-compose.yml change → full rebuild (FR-003 ✓)
- `detect-changes.sh` handles doc-only changes → empty output (SC-002 ✓)
- `service-to-path.sh` returns correct compose/path pairs for all 9 services ✓
- All GitHub Actions pinned to full SHA hashes (security best practice ✓)
- Service name allowlist validation in validate and test steps ✓
- `envs:` used for passing shell values to SSH script (avoids direct interpolation of most variables ✓)
- `concurrency: group: production, cancel-in-progress: false` prevents concurrent deploys (FR-015 ✓)
- certbot service has `profiles: [certbot]` → not started by default (FR-019 ✓)
- `letsencrypt` and `certbot_www` volumes defined and mounted in nginx (T011 ✓)
- Exactly 3 secrets referenced: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` (FR-018 ✓)
- `manual-rollback.yml` has required `reason` input and audit record (FR-016, FR-017 ✓)
- DEPLOYMENT.md covers all 8 required sections including rollback retention policy ✓
- Migration-abort-on-failure path exits with code 1 and leaves old containers running (FR-012 ✓)

---

## Untested / Unverified Areas

- `docker compose exec -T` health check behavior when the container is still starting (race between restart and exec call) — the `sleep 5` poll interval mitigates this but the very first check may race against container init
- `xargs -I{} docker rmi "dark-factory-${SVC}:{}"` pruning syntax — the `{}` substitutes into the middle of the image name; verify this correctly handles the braces in the template string
- Whether `$COMPOSE run --rm "$CSVC" alembic upgrade head` correctly picks up the new image after `$COMPOSE build` vs. the old image — Docker Compose should use the freshly-built image; needs verification on first end-to-end test

---

## Required Follow-Up

| # | Severity | Owner | Action |
|---|---|---|---|
| 1 | Blocker | devops | Fix image name in snapshot/rollback to use compose service name (`dark-factory-$(compose_name "$SVC")`) in `ci-cd.yml` and `manual-rollback.yml` |
| 2 | Blocker | devops | Replace `curl` with `python3 urllib` in health check exec call |
| 3 | Major | devops | Add `-e` to `manual-rollback.yml` script set flags |
| 4 | Minor | devops | Document initial-commit bootstrap requirement in DEPLOYMENT.md or fix script |
| 5 | Minor | devops | Fix `setup-vps.sh` REPO_URL placeholder |
