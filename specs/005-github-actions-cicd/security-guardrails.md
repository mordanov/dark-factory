# Security Guardrails: GitHub Actions CI/CD Pipeline
# Feature: 005-github-actions-cicd

**Author**: Security Architect Agent
**Date**: 2026-06-25
**Status**: APPROVED WITH CONDITIONS (conditions listed in Required Mitigations)

---

## Security Review Result

### Scope Reviewed

- GitHub Actions workflow design: `ci-cd.yml`, `manual-rollback.yml`
- Change detection scripts: `detect-changes.sh`, `service-to-path.sh`
- Secret management model (FR-018, SC-006)
- VPS access and SSH key security
- Supply-chain: third-party Actions usage
- Rollback audit trail integrity
- CI test isolation (AUTH_MODE, in-memory DB, no real LLM)
- Dockerfile CMD changes (T001–T005)
- Certbot/nginx configuration (T011)

### Decision

**APPROVED WITH CONDITIONS**

The design is sound. No application secrets enter GitHub Actions. The conditions below
are implementation-level requirements that DevOps and Backend must enforce — none of them
require design changes. All Blocker items must be verified before the first live deployment.

---

## Threat Model: GitHub Actions CI/CD Pipeline

### Assets

| Asset | Sensitivity | Why Critical |
|-------|-------------|-------------|
| VPS SSH private key (`VPS_SSH_KEY`) | Critical | Full VPS shell access if leaked |
| Production `.env` on VPS (`/app/dark-factory/infra/.env`) | Critical | Contains all DB passwords, API keys |
| Docker images on VPS | High | Running code; tampered image = RCE |
| GitHub Actions job logs | Medium | May expose partial env var values if mis-logged |
| Rollback snapshots (image tags) | Medium | Restoring wrong snapshot = service disruption |
| `github.actor` in audit trail | Low | Identity assertion only; no auth secret |

### Actors

| Actor | Trust Level | Access Path |
|-------|-------------|-------------|
| Authorised developer (push to main) | Trusted | GitHub repo write access → triggers pipeline |
| GitHub Actions runner (ubuntu-latest) | Semi-trusted | Hosted runner; ephemeral; no secrets beyond job scope |
| VPS deployment shell | Trusted within VPS | Only reached after SSH auth with `VPS_SSH_KEY` |
| GitHub Actions operator (manual rollback) | Trusted | Must have Actions:write permission on repo |
| Compromised dependency / action | Hostile | Supply-chain vector; pins mitigate |
| Insider with repo write | Hostile (contingency) | Can edit workflow YAML to exfiltrate secrets |

### Trust Boundaries

```
[GitHub repo] → [GitHub Actions runner] --SSH--> [VPS /app/dark-factory/]
      ↑                    ↑
  Secrets store        Ephemeral; isolated per job
  (VPS_HOST,           No app secrets; only infra creds
   VPS_USER,
   VPS_SSH_KEY)
```

Key boundary: **No application secret ever crosses from VPS → GitHub Actions runner**.
All build and migration steps happen ON the VPS; the runner is a remote executor only.

### Entry Points

1. `push` to `main` branch → triggers `ci-cd.yml`
2. `workflow_dispatch` → triggers `manual-rollback.yml` (requires Actions:write)
3. SSH from runner to VPS (authenticated via `VPS_SSH_KEY`)
4. `git pull` on VPS pulls from GitHub (authenticated via deploy key or HTTPS token already on VPS)
5. Third-party Actions: `actions/checkout@v4`, `appleboy/ssh-action@v1`

### Threats and Abuse Cases

| ID | Threat | STRIDE | Impact | Likelihood | Controls |
|----|--------|--------|--------|------------|----------|
| T1 | Application secret (DB password, API key) committed to workflow YAML or passed to runner | Info Disclosure | Critical | Medium | FR-018 enforcement; SC-006 test; pre-commit secret scan |
| T2 | Supply-chain compromise via un-pinned third-party Action | Tampering / Escalation | Critical | Low-Medium | Pin actions to commit SHA; review SHA on update |
| T3 | VPS SSH key leaked via job log (`echo $VPS_SSH_KEY`) | Info Disclosure | Critical | Low | Never log secrets; GH masks them; verify no `echo`/`set -x` around secret use |
| T4 | Compromised runner reads `VPS_SSH_KEY` via env dump | Info Disclosure | High | Low | Limit `VPS_SSH_KEY` exposure to deploy job only; restrict to protected branch |
| T5 | Malicious `detect-changes.sh` output injects shell into matrix service name | Code Injection | High | Low | Validate JSON array; matrix values must match service allowlist before use |
| T6 | Migration step corrupts DB; rollback restores container but not schema | Data Integrity | High | Low-Medium | Document no schema rollback (already in spec edge-case); operators must be aware |
| T7 | Concurrent deployments race, leaving services in mixed-version state | Availability | High | Low | `concurrency: group: production, cancel-in-progress: false` — correctly specified |
| T8 | Manual rollback triggered by unauthorised user | Repudiation/Unauth | High | Low | `workflow_dispatch` requires repo Actions:write; restrict to protected environments |
| T9 | Rollback snapshot garbage-collected before rollback needed | Availability | Medium | Medium | Retain 3 most recent; document in DEPLOYMENT.md (T014) |
| T10 | `git pull` on VPS pulls attacker-controlled commit (if branch protections bypass) | Tampering | High | Low | Enforce branch protection on `main`; require PR + review |
| T11 | CI test secret `TEST_JWT_SECRET=ci-test-secret` used in production | Auth Bypass | High | Low | `AUTH_MODE=local` only in CI; production uses Keycloak; verify env segregation |
| T12 | `OPENAI_BASE_URL` override not applied; CI makes real LLM calls leaking data | Info Disclosure | Medium | Low | `OPENAI_BASE_URL=http://localhost:9999` set in test job; must be verified |
| T13 | Certbot container starts unexpectedly; exposes ACME challenge endpoint prematurely | Availability | Low | Low | `profiles: [certbot]` ensures no auto-start; checkpoint in T011 |

---

## Required Mitigations

### BLOCKER — Must enforce before first live deployment

**B1 — Zero application secrets in GitHub Actions (FR-018 / SC-006)**

The pipeline MUST contain exactly 3 GitHub secrets: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`.

- No `POSTGRES_PASSWORD`, `OPENAI_API_KEY`, `*_SECRET_KEY`, or any other application secret may be added to GitHub Secrets.
- All application secrets reside exclusively in `/app/dark-factory/infra/.env` on the VPS — they never leave the VPS.
- Build and migration steps run on the VPS via SSH; the runner receives no application secret values.
- **Verification**: After implementing T008–T013, run: `grep -r 'secret\.' .github/workflows/ | grep -v 'VPS_HOST\|VPS_USER\|VPS_SSH_KEY'` — must return zero matches.
- **Verification**: `grep -rE 'PASSWORD|API_KEY|SECRET_KEY|TOKEN' .github/workflows/` — must return zero matches (except `TEST_JWT_SECRET=ci-test-secret` in test job, which is acceptable as a non-secret test constant).

**B2 — Pin third-party Actions to commit SHA (supply chain)**

Both Actions used in the pipeline must be pinned to immutable commit SHAs, not version tags:

```yaml
# REQUIRED (not version tags like @v4):
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
- uses: appleboy/ssh-action@7eaf76671a0d7eec5d98ee897acda4f968735a17  # v1.2.0
```

Rationale: A tag like `@v4` can be force-pushed to point at a malicious commit. A SHA cannot be moved.

- **Verification**: `grep -r 'uses:' .github/workflows/ | grep -v '@[a-f0-9]\{40\}'` — must return zero matches.

**B3 — `VPS_SSH_KEY` scope limited to deploy job and protected branch**

- Configure `VPS_SSH_KEY` as an environment-level secret on a `production` environment in GitHub, not a repository-level secret.
- The `deploy` job and `manual-rollback.yml` must specify `environment: production` to access it.
- The `production` environment must have branch protection restricting deployments to `main`.
- This prevents `validate` and `test` jobs (which run on any PR) from having access to the SSH key.

**B4 — No `alembic upgrade head` in container CMD (T001–T005)**

All five Dockerfile/entrypoint.sh changes must be applied and verified before the deploy pipeline runs.
If any service still runs migrations at startup, a failed migration will crash the container silently
rather than aborting the pipeline, corrupting the rollback sequence.

- **Verification**: `grep -r 'alembic upgrade' services/ infra/` — must return zero matches in CMD/entrypoint contexts.

---

### HIGH — Fix before release or formally accept risk

**H1 — `detect-changes.sh` output validation before matrix use**

The `services` output from the `detect` job is a JSON array written by a shell script and consumed
by `fromJSON()`. If an attacker can influence file paths in the repo to contain shell metacharacters,
and those paths are not sanitised before inclusion in the JSON, a crafted service name could inject
into downstream `docker compose build {service}` invocations on the VPS.

Mitigation:
```yaml
# In validate/test/deploy jobs, add a check step:
- name: Validate service matrix entry
  run: |
    SERVICE="${{ matrix.service }}"
    ALLOWED="uim-backend tm-backend orchestrator context-distiller agent-dispatcher agent-tools uim-frontend tm-frontend nginx"
    if ! echo "$ALLOWED" | grep -qw "$SERVICE"; then
      echo "ERROR: Unknown service '$SERVICE' — aborting"
      exit 1
    fi
```

**H2 — Branch protection on `main`**

The pipeline deploys on every push to `main`. Without branch protection:
- Anyone with repo write can push directly to main, triggering a deployment
- PRs can be merged without review

Require: 1 approving review, status checks must pass (the pipeline itself), no force-push.
This is a repository settings change — DevOps/product manager to configure in GitHub.

**H3 — `TEST_JWT_SECRET` must not match any production secret**

`TEST_JWT_SECRET=ci-test-secret` is a hardcoded test constant in ci-cd.yml. This is acceptable
because it is not a secret — it is a meaningless CI-only value. However:
- It MUST NOT match `ORCHESTRATOR_SECRET_KEY`, `TM_SECRET_KEY`, or any service secret in `.env`
- **Verification**: Compare `ci-test-secret` against all `*_SECRET_KEY` values in `.env.example` and production `.env`

---

### MEDIUM — Track and fix in planned timeframe

**M1 — Rollback snapshot retention and cleanup**

The deploy job must retain exactly the 3 most recent rollback tags per service and delete older ones.
If retention is not enforced, disk pressure accumulates on the VPS.

```bash
# After tagging: prune old rollback tags (retain 3 newest)
docker images --format '{{.Tag}}' dark-factory-${SERVICE} \
  | grep '^rollback-' | sort -r | tail -n +4 \
  | xargs -I{} docker rmi dark-factory-${SERVICE}:{} || true
```

**M2 — No `set -x` or verbose logging around SSH commands that receive env vars**

The `appleboy/ssh-action` passes env vars to the remote shell. Ensure no `set -x` or debug trace
is enabled in the remote commands, as this would print env var values to the job log.
GitHub Actions masks known secrets (`VPS_SSH_KEY`) but does not mask values that only exist on VPS.

**M3 — Audit trail permanence for manual rollback**

The GitHub Actions job log provides a permanent audit URL. However, GitHub retains logs for 90 days
by default (or less on free plans). For compliance, consider:
- Logging rollback events to a persistent location (e.g., append to a file on VPS at `/app/dark-factory/rollback-audit.log`)
- Format: `ISO8601 | actor | service | reason`

---

### LOW — Hardening

**L1 — `setup-vps.sh` must not store secrets or accept them as arguments**

`infra/scripts/setup-vps.sh` is committed to the repo. It must never accept a password as a
positional argument or environment variable. The `.env` placement reminder is the correct pattern.

**L2 — Certbot renewal cron must not run as root**

When SSL is enabled (post-scope), certbot renewal cron should run as the deployment user, not root.
Document this in `DEPLOYMENT.md` (T014).

**L3 — `OPENAI_BASE_URL=http://localhost:9999` in CI test job**

This correctly prevents real LLM calls. The port 9999 is not bound; the connection will be refused,
which is the desired behaviour (tests should not depend on LLM responses). Document why this is
intentional for future maintainers.

---

## Security Acceptance Criteria

These are required tests / verifications before SC-006 can be claimed:

| ID | Criterion | How to Verify |
|----|-----------|---------------|
| SAC-001 | Zero application secrets in workflow YAML | `grep -rE 'PASSWORD\|API_KEY\|SECRET_KEY' .github/workflows/` returns 0 matches (except `TEST_JWT_SECRET`) |
| SAC-002 | Exactly 3 GitHub Secrets configured | GitHub repo → Settings → Secrets and Variables → Actions: only `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` |
| SAC-003 | All Actions pinned to commit SHA | `grep -r 'uses:' .github/workflows/ \| grep -v '@[a-f0-9]\{40\}'` returns 0 matches |
| SAC-004 | Service name validated against allowlist before shell use | Validation step present in validate/test/deploy jobs (see H1) |
| SAC-005 | `alembic upgrade head` absent from all container CMDs | `grep -r 'alembic upgrade' services/ infra/` returns 0 in CMD/entrypoint contexts |
| SAC-006 | `VPS_SSH_KEY` bound to `production` environment only | Deploy job has `environment: production`; validate/test do not |
| SAC-007 | Rollback snapshot retention enforced (3 max per service) | Deploy job includes prune step after tag creation |
| SAC-008 | `manual-rollback.yml` logs actor, timestamp, service, reason | Job log contains all 4 fields for every run |
| SAC-009 | Certbot does not start with `docker compose up` (no profile flag) | `docker compose -f infra/docker-compose.yml up` starts without certbot container |
| SAC-010 | `TEST_JWT_SECRET` value differs from all production `*_SECRET_KEY` values | Compare manually before first live run |

---

## Security Test Cases for Autotester

| Test | Description | Expected Result |
|------|-------------|-----------------|
| SEC-T001 | Run `grep -rE 'PASSWORD\|API_KEY\|SECRET_KEY' .github/workflows/` | 0 matches (except `TEST_JWT_SECRET`) |
| SEC-T002 | Verify GitHub Secrets count | Exactly VPS_HOST, VPS_USER, VPS_SSH_KEY — no others |
| SEC-T003 | Run `grep 'uses:' .github/workflows/*.yml` and check for non-SHA pins | All `uses:` must include 40-char hex SHA |
| SEC-T004 | Push commit with Python syntax error to main | Pipeline fails at validate; no deploy occurs |
| SEC-T005 | Push commit with failing test to main | Pipeline fails at test; no deploy occurs |
| SEC-T006 | Run `docker compose -f infra/docker-compose.yml up` locally | certbot container NOT started |
| SEC-T007 | Run `docker compose -f infra/docker-compose.yml --profile certbot up` | certbot container IS started |
| SEC-T008 | Trigger manual-rollback.yml from Actions UI | Job log contains actor, timestamp, service, reason |
| SEC-T009 | Push commit changing only README.md | `detect` outputs `[]`; validate/test/deploy all skip |
| SEC-T010 | Verify no `alembic upgrade` in Dockerfiles after T001–T005 | `grep -r 'alembic upgrade' services/` returns 0 in CMD contexts |

---

## Residual Risks

| Risk | Severity | Owner | Due Date | Notes |
|------|----------|-------|----------|-------|
| No staging environment — deploys go directly to production | High | Product Manager | Out of scope for this feature | Accepted per spec Assumptions; mitigated by green test gate and auto-rollback |
| GitHub Actions log retention (90 days default) may lose rollback audit | Medium | DevOps | Phase 7 (T014) | Mitigate with VPS-side audit log (M3) |
| `main` branch protection not enforced yet | High | DevOps | Before first live deployment | GitHub repo settings change; not a code change |
| Schema rollback not automated — migration-then-crash leaves forward-migrated schema | High | Product Manager / Backend | Accepted | Documented in spec edge-cases; operators must handle manually |

---

## Implementation Guidance for DevOps

### ci-cd.yml: Secrets and Environment Scoping

```yaml
jobs:
  deploy:
    needs: test
    environment: production           # <-- REQUIRED: limits VPS_SSH_KEY access
    if: needs.detect.outputs.has_changes == 'true'
    concurrency:
      group: production
      cancel-in-progress: false
    steps:
      - name: Validate service name
        run: |
          SERVICE="${{ matrix.service }}"
          ALLOWED="uim-backend tm-backend orchestrator context-distiller agent-dispatcher agent-tools uim-frontend tm-frontend nginx"
          echo "$ALLOWED" | grep -qw "$SERVICE" || { echo "Unknown service: $SERVICE"; exit 1; }
      - uses: appleboy/ssh-action@<FULL_SHA_HERE>    # pin to SHA
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          # ... script runs entirely on VPS; no app secrets pass through runner
```

### ci-cd.yml: Test Job Environment Variables

The following are safe to include in test job YAML — they are test constants, not secrets:

```yaml
env:
  AUTH_MODE: local
  TEST_JWT_SECRET: ci-test-secret      # Non-secret CI constant; must differ from prod secrets
  DATABASE_URL: sqlite+aiosqlite:///:memory:
  MONGO_URL: mongomock://localhost      # orchestrator, context-distiller only
  OPENAI_API_KEY: test-key             # Refused by localhost:9999; no real calls
  OPENAI_BASE_URL: http://localhost:9999
```

### manual-rollback.yml: Audit Logging (mandatory)

```yaml
- name: Audit log
  run: |
    echo "=== ROLLBACK AUDIT ==="
    echo "Actor:     ${{ github.actor }}"
    echo "Timestamp: ${{ github.run_started_at }}"
    echo "Service:   ${{ inputs.service }}"
    echo "Reason:    ${{ inputs.reason }}"
    echo "Run URL:   ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
    echo "======================"
```

### Action SHA Pins (current as of 2026-06-25)

Verify these SHAs before use — confirm against the Actions' release pages:

- `actions/checkout@v4` — check https://github.com/actions/checkout/releases for latest v4 SHA
- `appleboy/ssh-action@v1` — check https://github.com/appleboy/ssh-action/releases for latest v1 SHA
- `actions/setup-python@v5` — if used, pin similarly
- `actions/setup-node@v4` — if used, pin similarly

Use `gh release view` or the GitHub UI to retrieve the tag-to-SHA mapping.

---

## Open Questions

1. **Environment secrets vs repo secrets**: Has the `production` environment been created in GitHub repo settings? DevOps to confirm before T010 is merged.
2. **Branch protection**: Is `main` currently protected (require PR + passing checks)? DevOps to confirm.
3. **VPS deploy user**: The spec assumes the deployment user is already in the `docker` group. If `setup-vps.sh` adds the user, a logout/login cycle is needed before docker commands work — document in DEPLOYMENT.md (T014).
4. **Rollback audit log on VPS**: Is a persistent `/app/dark-factory/rollback-audit.log` acceptable, or is there a preferred logging mechanism? Product Manager to clarify.
