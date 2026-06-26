# Feature Specification: GitHub Actions CI/CD Pipeline

**Feature Branch**: `005-github-actions-cicd`
**Created**: 2026-06-25
**Status**: Draft

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Automated Validation on Every Push (Priority: P1)

Every time code is pushed to the `main` branch, the system automatically checks that all
changed services are syntactically correct and pass code quality standards — before any
deployment attempt is made. No human review is needed to catch obvious breakage.

**Why this priority**: Fast feedback on broken code is the foundation of all other
pipeline benefits. Without it, bad code reaches production or the team must rely entirely
on developer discipline. This story delivers value immediately, even without deploy or
test automation.

**Independent Test**: Push a commit with a Python syntax error to `main`. The pipeline
fails within 5 minutes, the pull request is marked red, and no deployment occurs. Push
a clean commit — the pipeline passes validation and proceeds.

**Acceptance Scenarios**:

1. **Given** a developer pushes to `main` with a ruff linting violation in a Python service,
   **When** the pipeline runs, **Then** the validate stage fails within 5 minutes and no
   deployment is triggered.
2. **Given** a developer pushes a Dockerfile with a syntax error, **When** the pipeline
   runs, **Then** the validate stage catches the error without connecting to the VPS.
3. **Given** only documentation files changed, **When** the pipeline runs, **Then** no
   validate, test, or deploy jobs run (nothing to rebuild).
4. **Given** only `infra/docker-compose.yml` changed, **When** the pipeline runs,
   **Then** all services are included in validation scope.
5. **Given** only `services/ticket-manager/backend/**` changed, **When** the pipeline
   runs, **Then** only the `tm-backend` service is validated (not all services).

---

### User Story 2 — Automated Tests Before Deployment (Priority: P2)

All automated tests for changed services run automatically after validation passes.
A deployment is blocked if any test fails or coverage drops below the threshold.
No real external infrastructure (database, identity provider) is required to run tests.

**Why this priority**: Tests prevent regressions. Without automated test gating,
deployments carry unknown risk. This story ensures every deployment has a verified
green test suite.

**Independent Test**: Push a commit that breaks a unit test. The test stage fails and
the deploy stage does not run. Fix the test, push again — tests pass and deployment
proceeds. Check that coverage failure also blocks deployment.

**Acceptance Scenarios**:

1. **Given** a Python backend test fails, **When** the pipeline reaches the test stage,
   **Then** the deploy stage does not run and the pipeline is marked failed.
2. **Given** code coverage for a changed service drops below 80%, **When** the test
   stage runs, **Then** the stage fails and deployment is blocked.
3. **Given** a frontend test fails, **When** the pipeline runs, **Then** deploy is
   blocked and the failing test is identified in the pipeline output.
4. **Given** both backend and frontend services changed, **When** the test stage runs,
   **Then** backend and frontend tests run in parallel to reduce total pipeline duration.
5. **Given** a service has no tests (infrastructure-only, e.g., nginx), **When** the
   pipeline runs for that service, **Then** the test stage is skipped for it without
   failing the pipeline.

---

### User Story 3 — Automated Deployment to VPS with Safe Rollback (Priority: P3)

After validation and tests pass, changed services are automatically built on the VPS
and deployed. If any service fails its health check after deployment, the system
automatically restores the previous version without human intervention.

**Why this priority**: Automated deployment removes the error-prone manual SSH workflow.
Automatic rollback makes the pipeline safe to use — a broken deployment is self-healing
rather than an incident requiring urgent manual action.

**Independent Test**: Push a commit that introduces a runtime startup error (e.g., a
bad environment variable reference). After deployment, the service health check fails,
and the pipeline automatically restores the previous running version. The pipeline exits
as failed. The service continues to serve the previous version.

**Acceptance Scenarios**:

1. **Given** validation and tests pass, **When** the deploy stage runs, **Then** only
   changed services are rebuilt and restarted on the VPS (not all services).
2. **Given** a database migration runs and succeeds, **When** the deploy stage proceeds,
   **Then** containers restart with the new image only after migration success.
3. **Given** a database migration fails, **When** the deploy stage encounters the failure,
   **Then** no containers are restarted and the old containers continue running.
4. **Given** a newly deployed service fails its health check within 90 seconds, **When**
   the pipeline detects the failure, **Then** the previous image is automatically restored
   and the pipeline exits as failed.
5. **Given** an in-flight deployment is running, **When** another push to main triggers a
   new pipeline run, **Then** the new deployment waits for the current one to finish rather
   than running concurrently.
6. **Given** all deployed services pass health checks, **When** the deploy stage completes,
   **Then** the pipeline exits successfully and the VPS runs the new version.

---

### User Story 4 — Emergency Manual Rollback (Priority: P4)

An operator can trigger a rollback for any service at any time via the GitHub Actions UI,
providing an audit trail that records who triggered the rollback and why.

**Why this priority**: Automated rollback covers the common case, but does not cover
scenarios where a defect is discovered after the health check window (e.g., a subtle
data-layer bug). A manual override gives operators a safe escape hatch.

**Independent Test**: Via GitHub Actions UI, trigger a manual rollback for `tm-backend`
with reason "regression in ticket search". Verify the previous image is restored on VPS
and the audit trail shows the triggering actor and reason.

**Acceptance Scenarios**:

1. **Given** an operator notices a production issue, **When** they trigger the manual
   rollback workflow for the affected service from the GitHub Actions UI, **Then** the
   previous image is restored on VPS within 2 minutes.
2. **Given** a rollback is triggered, **When** it completes, **Then** an audit entry is
   recorded capturing the service name, triggering actor, timestamp, and stated reason.
3. **Given** rollback is triggered for "all" services, **When** it runs, **Then** all
   services revert to their most recent pre-deployment snapshots.

---

### Edge Cases

- What happens if the VPS is unreachable during deployment? The deploy stage fails with
  an SSH connection error; validation and test results are preserved; no partial deployment
  occurs.
- What happens if the rollback snapshot has been garbage-collected? The rollback step logs
  a warning for the affected service and skips it; other services in the rollback batch
  still proceed.
- What happens if a migration succeeds but the new container immediately crashes? The
  migration is already applied; the rollback restores the container image only (not the
  schema); operators must handle schema state manually via `manual-rollback.yml`.
- What happens if two developers push to `main` at the same time? The second pipeline
  queues behind the first (concurrency lock on the deploy job); both pipelines complete
  in order.
- What happens if health checks have no health endpoint defined? Services without explicit
  health checks are treated as passed after container start (no wait); infrastructure-only
  services (nginx) fall into this category.
- What happens if a changed service has 0% test coverage because no tests exist? The test
  stage fails on the coverage threshold; developers must add tests or explicitly exclude
  the service from coverage enforcement.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST run automatically on every push to the `main` branch.
- **FR-002**: The pipeline MUST detect which services changed and operate only on those;
  unchanged services MUST NOT be rebuilt, retested, or redeployed.
- **FR-003**: A change to the central infrastructure configuration file MUST trigger
  full rebuilds of all services.
- **FR-004**: The validate stage MUST run `ruff check` and `ruff format --check` for
  every changed Python service.
- **FR-005**: The validate stage MUST attempt a Docker image build for every changed
  service to catch Dockerfile and dependency errors before any VPS connection is made.
- **FR-006**: The test stage MUST run unit and integration tests for every changed Python
  backend service using an in-memory database and local auth mode (no real database or
  identity provider in CI).
- **FR-007**: The test stage MUST run frontend tests (Vitest) for every changed frontend
  service.
- **FR-008**: The test stage MUST fail and block deployment if test coverage for any
  changed service drops below 80%.
- **FR-009**: The deploy stage MUST NOT run if either validate or test stages fail.
- **FR-010**: The deploy stage MUST build Docker images on the VPS; no container registry
  or image push from CI is permitted.
- **FR-011**: Database migrations MUST run as a separate step after image build but before
  containers are restarted.
- **FR-012**: If a migration step fails, the deploy stage MUST abort; previously running
  containers MUST remain running.
- **FR-013**: After restarting containers, the pipeline MUST wait up to 90 seconds for all
  deployed services to pass health checks before marking the deployment successful.
- **FR-014**: If any service fails its health check within the 90-second window, the
  pipeline MUST automatically restore the previously running images and restart those
  services with the old version.
- **FR-015**: The pipeline MUST prevent concurrent deployments to production; a second
  deployment MUST queue and wait for the first to finish.
- **FR-016**: A `manual-rollback` workflow MUST exist, triggerable via the GitHub Actions
  UI, that restores the most recent snapshot for one or all services.
- **FR-017**: The manual rollback MUST record the triggering actor, timestamp, service
  name, and operator-provided reason in the pipeline log.
- **FR-018**: The pipeline MUST contain only three GitHub credentials: VPS host, VPS
  username, and VPS SSH key. No application secrets, passwords, or API keys may be stored
  in GitHub.
- **FR-019**: A certbot container MUST be present in the Docker Compose configuration
  but MUST NOT start automatically with the standard `docker compose up` command.
- **FR-020**: All backend service container startup commands MUST NOT run database
  migrations; migrations are exclusively a pipeline responsibility.

### Key Entities

- **Pipeline Run**: A triggered execution of the full `validate → test → deploy` sequence
  for a given git commit. Has a status (pass/fail) and a set of changed services in scope.
- **Changed Service Set**: The subset of services determined to be affected by a commit,
  derived by matching changed file paths against a fixed service mapping.
- **Rollback Snapshot**: A point-in-time record of the running image for each service,
  taken immediately before a deployment attempt. Retained for at least the most recent
  3 deployments.
- **Deployment**: A single execution of the build → migrate → restart → healthcheck
  sequence for a set of changed services on the VPS.
- **Manual Rollback Record**: An audit entry capturing actor, timestamp, target service(s),
  and stated reason for a manually triggered rollback.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A pipeline run completes (validate + test + deploy) for a single changed
  service within 10 minutes of a push to `main`.
- **SC-002**: A push that changes only documentation triggers zero rebuild, test, or
  deploy activity.
- **SC-003**: 100% of pushes to `main` with a failing test result in no deployment to
  the VPS.
- **SC-004**: A failed deployment due to health check timeout is automatically remediated
  (old version restored) within 2 minutes of the health check deadline passing, without
  any human action.
- **SC-005**: An operator can complete a manual rollback for any single service within
  2 minutes of triggering the workflow.
- **SC-006**: The pipeline contains zero application secrets — no database passwords,
  API keys, or service credentials appear in any GitHub Actions workflow file or secret.
- **SC-007**: After pipeline setup, a developer can go from `git push` to running new
  code on the VPS without any manual SSH or Docker commands.

## Assumptions

- A Hetzner VPS running Ubuntu 24.04 LTS is already provisioned and accessible via SSH
  from a deployment key.
- Docker is already installed on the VPS; the deployment user is already in the `docker`
  group. No `sudo` is required for Docker commands.
- The production `.env` file is already in place at `/app/dark-factory/infra/.env` on
  the VPS before the first deployment runs.
- The monorepo is already cloned at `/app/dark-factory/` on the VPS.
- GitHub Actions' hosted runners (ubuntu-24.04) are used; self-hosted runners are out
  of scope.
- There is no staging environment; the pipeline deploys directly to production.
- HTTPS/SSL certificate setup is out of scope — the pipeline supports HTTP only; SSL is
  a manual post-deployment step using certbot.
- Hetzner firewall rule configuration (ports 80, 443, 22) is out of scope; assumed
  already configured.
- Monitoring, alerting, and log aggregation are out of scope for this feature.
- Docker Swarm and Kubernetes are out of scope; single-VPS Docker Compose deployment only.
- The `agent-tools` service has no HTTP server and therefore has no health check endpoint;
  its container is not monitored for health after deployment.
