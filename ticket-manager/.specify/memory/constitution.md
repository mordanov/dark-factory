<!--
SYNC IMPACT REPORT
==================
Version change: none → 1.0.0 (initial ratification, 2026-05-23)

Modified principles: N/A — initial creation
Added sections:
  - Core Principles (I–X): 10 principles covering lifecycle, events, RBAC,
    collaboration, workflow evolution, API discipline, migrations, quality gates,
    observability, and security
  - Stack & Architecture Constraints
  - Quality Gates & Development Workflow
  - Governance (amendment process, versioning policy, PR compliance)

Removed sections: N/A — initial creation

Templates updated:
  ✅ .specify/memory/constitution.md — this file (initial ratification)
  ✅ .specify/templates/plan-template.md — Constitution Check gates enumerated
     with all 10 principle names and a re-check gate
  ✅ .specify/templates/tasks-template.md — Phase 2 Foundational examples updated
     to include event infrastructure, RBAC, and migration scaffolding
  ✅ .specify/templates/spec-template.md — no structural changes required;
     template is already implementation-agnostic

Deferred TODOs:
  - TODO(METRICS_PLATFORM): Observability platform (Prometheus, Datadog, etc.)
    not yet decided. Principle IX mandates structured logging as the minimum.
    Update Principle IX when the platform is chosen.
  - TODO(CI_PLATFORM): CI/CD pipeline and toolchain not yet defined. Quality
    Gates & Development Workflow section references this. Update when infrastructure
    decisions are finalized.
-->

# Ticket Management System Constitution

## Core Principles

### I. Lifecycle Traceability First

Every state-changing action on a ticket MUST produce a traceable record linking the
action type, actor identity, timestamp, and the resulting state transition. No ticket
lifecycle event may be processed without a corresponding audit trail entry. The system
MUST support querying the full chronological history of any ticket from creation to
current state. Traceability is non-negotiable and MUST NOT be bypassed for performance
or convenience reasons.

### II. Event Integrity and Auditability

Every domain action MUST emit an immutable, timestamped event containing: event type,
actor identity (user ID and role), target entity identifier (ticket or project ID),
previous state, new state, and a UTC ISO-8601 timestamp. Emitted events MUST NOT be
updated or deleted after creation. The event store is the authoritative system of
record for all state changes. Downstream projections (read models, API responses, UI
views) MUST be derived from events and MUST NOT be treated as the source of truth.
Event emission failures MUST be treated as errors, not warnings.

### III. Role-Based Access Control

The system defines exactly two roles: `administrator` and `user`. Permission checks
MUST be enforced at the API and backend service boundary; frontend enforcement is
supplemental only and MUST NOT be the sole enforcement layer. Administrators MAY
manage users, roles, and system configuration. Users MAY create follow-up tasks linked
to existing tasks and MAY submit progress records on their assigned tickets. No
privilege escalation is permitted client-side. All permission enforcement decisions
MUST be recorded as auditable events.

### IV. Collaborative Execution Model

A ticket MAY be assigned to one or more users. When multiple assignees exist, each
assigned user MUST independently provide a progress or update record. A ticket MUST
NOT be considered complete unless all assigned users have submitted their individual
progress records or assignments have been formally transferred. The system MUST
prevent implicit completion: progress state MUST be explicitly recorded and MUST NOT
be inferred from silence or inactivity.

### V. Controlled Workflow Evolution

During the discovery stage, ticket statuses are hard-coded as a named, versioned
enumeration. Status identifiers MUST NOT be embedded as raw strings in application
logic; they MUST reference the defined enumeration. Future workflow configurability
MUST be designed so that adding, deprecating, or renaming a status does NOT alter the
historical event record of prior transitions. Deprecated status identifiers MUST be
tombstoned (marked inactive) rather than deleted, so that historical events
referencing them remain interpretable indefinitely.

### VI. API and Contract Discipline

All backend APIs MUST be versioned using a URL path prefix (e.g., `/api/v1/...`).
API contracts (request and response schemas) MUST be documented in OpenAPI or an
equivalent machine-readable format. Breaking changes MUST increment the API major
version before deployment. The React.js frontend MUST consume only documented,
versioned API endpoints. Contract tests MUST exist for all API boundaries consumed
by the frontend. Undocumented or unversioned endpoints MUST NOT be introduced.

### VII. Data Integrity and Migration Safety

All PostgreSQL schema changes MUST be delivered as numbered, ordered migration files.
Every migration MUST include a rollback (down) path unless technically infeasible;
infeasibility MUST be documented inline in the migration file and noted in the PR
description. Migrations MUST be backward-compatible with the immediately preceding
deployed application version to support zero-downtime deployments. No migration may
drop a column or table without a documented deprecation period. Migrations MUST be
reviewed and approved before merge, independently of application code review.

### VIII. Quality Gates by Default

All code changes MUST include automated tests proportionate to risk: unit tests for
business logic; integration tests for persistence and API boundaries; contract tests
for all inter-layer boundaries (API ↔ frontend, service ↔ database). Every PR MUST
pass automated tests, linting, and code review by at least one engineer. PRs touching
authentication, authorization, event emission, or database migrations MUST also
receive an architecture or security review. Merging MUST be blocked until all required
gates pass.

### IX. Operability and Observability

The Python backend MUST emit structured logs (JSON format) for all request/response
cycles, domain events, and error conditions. Log entries MUST include sufficient
context (request ID, actor ID, event type, error class) to diagnose an incident
without accessing production data. The system MUST expose `/health` and `/ready`
endpoints. Sensitive data (passwords, tokens, PII) MUST NOT appear in logs.
TODO(METRICS_PLATFORM): define specific metrics infrastructure (e.g., Prometheus,
Datadog) when platform decision is finalized — structured logging is the minimum
required observability mechanism until then.

### X. Security and Privacy Baseline

All user credentials MUST be hashed with a strong adaptive algorithm (bcrypt or
Argon2). Authentication tokens MUST be short-lived, signed, and individually
revocable. API endpoints MUST enforce least-privilege access by role (see Principle
III). All administrator actions (user creation, role assignment, deletion) MUST emit
auditable events (see Principle II). Sensitive data MUST NOT appear in logs or error
responses visible to clients. Application dependencies MUST be scanned for known
vulnerabilities as part of the CI/CD pipeline. Secure defaults MUST be applied; any
reduction in security posture MUST require explicit, documented justification.

## Stack & Architecture Constraints

These constraints are non-negotiable and apply to all features and services unless an
amendment to this constitution explicitly overrides them.

- **Frontend**: React.js. No alternative frontend framework may be introduced without
  a MAJOR constitution amendment.
- **Backend**: Python. All server-side business logic, API handling, and event
  emission MUST be implemented in Python.
- **Database**: PostgreSQL. No alternative relational or document store may be
  introduced for primary data persistence without a MAJOR constitution amendment.
- **Architecture**: Event-driven. Every state-changing domain action MUST emit a
  timestamped event (Principle II). Read models may be built from event projections
  but MUST NOT replace the event store as the source of truth.
- **Organizational model**: Tasks belong to projects (project as namespace boundary
  only). Product owners define and create core tasks. Any user may create follow-up
  tasks linked to an existing task. Tasks may be assigned to one or many users.
  Each assigned user MUST provide an individual progress record (Principle IV).

## Quality Gates & Development Workflow

This section defines minimum process requirements for all contributors.

- All feature work MUST originate from a specification (`spec.md`) and implementation
  plan (`plan.md`) before coding begins.
- The Constitution Check in `plan.md` MUST be completed and pass before Phase 0
  research proceeds, and MUST be re-verified after Phase 1 design.
- PRs MUST reference the user story or task they implement.
- Test failures, linting errors, or missing migration files MUST block merge.
- Reviewers MUST explicitly verify compliance with the principles listed in the
  Constitution Check section of the relevant `plan.md`.
- Security-sensitive PRs (authentication, RBAC, event store, migrations) require a
  designated security or architecture reviewer in addition to a standard code reviewer.
- TODO(CI_PLATFORM): CI/CD platform and pipeline configuration to be defined when
  infrastructure decisions are finalized. Until then, all gates MUST be run locally
  and documented in the PR description.

## Governance

### Amendment Process

1. Any contributor may propose a constitution amendment by opening a PR that modifies
   `.specify/memory/constitution.md` with a written rationale.
2. Amendments require approval from at least two engineers with merge access, or the
   designated technical lead if the active team has fewer than three engineers.
3. MAJOR amendments (removal or redefinition of existing principles, breaking
   governance changes, or stack constraint changes) additionally require a synchronous
   recorded design session before the PR is opened.
4. All amendments MUST update `Last Amended` and increment `Version` according to
   the versioning policy below.
5. A sync impact report (as an HTML comment at the top of this file) documenting
   affected templates and follow-up items MUST accompany every amendment PR.

### Versioning Policy

Constitution versions follow semantic versioning (`MAJOR.MINOR.PATCH`):

- **MAJOR**: Backward-incompatible governance changes — removal or redefinition of
  existing principles, removal of governance requirements, or stack constraint changes.
- **MINOR**: Additive changes — new principle, new section, materially expanded
  guidance that does not conflict with existing principles.
- **PATCH**: Non-semantic refinements — clarifications, wording improvements, typo
  fixes, formatting changes with no semantic impact.

### PR Compliance Expectations

Every PR merged to this repository MUST:

1. Pass the Constitution Check documented in the corresponding `plan.md`.
2. Include automated tests per Principle VIII (Quality Gates by Default).
3. Emit the required domain events per Principle II (Event Integrity and Auditability).
4. Enforce role-based permissions per Principle III (Role-Based Access Control).
5. Include numbered migration files for any schema change per Principle VII.
6. Not introduce unversioned or undocumented API endpoints per Principle VI.

Reviewers MUST reject PRs that violate non-negotiable principles without documented
justification. If a principle must be relaxed, the correct path is an amendment to
this constitution — not a silent bypass in code.

**Version**: 1.0.0 | **Ratified**: 2026-05-23 | **Last Amended**: 2026-05-23
