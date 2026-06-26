# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]
**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]
**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]
**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]
**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]
**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]
**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]
**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]
**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]
**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Verify compliance with each principle from `.specify/memory/constitution.md` (v2.1.0):

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | Services Remain Independently Deployable — no code-level coupling, HTTP-only inter-service | ☐ Pass / ☐ N/A | |
| II | Keycloak IAM Migration — Keycloak is IdP; no local password storage or user token issuance | ☐ Pass / ☐ N/A | |
| III | Python 3.12 Everywhere — all backends on python:3.12-slim | ☐ Pass / ☐ N/A | |
| IV | Shared Python Library Versions — canonical versions from root pyproject.toml | ☐ Pass / ☐ N/A | |
| V | Shared Frontend Library Versions — canonical versions from root package.json | ☐ Pass / ☐ N/A | |
| VI | Zustand for All Frontend State — tokens in-memory only, no localStorage | ☐ Pass / ☐ N/A | |
| VII | Vitest for All Frontend Tests — coverage ≥ 80% enforced in vite.config.ts | ☐ Pass / ☐ N/A | |
| VIII | ruff for All Python Linting — pre-commit hooks with ruff lint + ruff-format | ☐ Pass / ☐ N/A | |
| IX | Nginx DNS-Name Aware — envsubst, auth_request on /api/*, no hardcoded DNS | ☐ Pass / ☐ N/A | |
| X | No Cross-Service Database Access — HTTP API only, no shared DB or collections | ☐ Pass / ☐ N/A | |
| XI | Agent Dispatcher — FSM Sovereignty and Run Isolation | ☐ Pass / ☐ N/A | |
| XII | Agent Dispatcher — Operational Safety Contracts (graceful degradation, no prompt cache, secret hygiene) | ☐ Pass / ☐ N/A | |
| XIII | Planning Agent — Plan Persistence Before User Exposure | ☐ Pass / ☐ N/A | |
| XIV | Planning Agent — User Confirmation Gate for LLM Output | ☐ Pass / ☐ N/A | |
| XV | Planning Agent — Ticket Creation Is All-or-None with Retry | ☐ Pass / ☐ N/A | |
| XVI | Planning Agent — Agent Config Is Best-Effort, Never Blocking | ☐ Pass / ☐ N/A | |
| XVII | Keycloak is the Single Source of Truth for Identity — realm fixed, startup order enforced | ☐ Pass / ☐ N/A | |
| XVIII | JWKS Validation MUST Be Cached — min 300s TTL, never per-request, RS256 only in production | ☐ Pass / ☐ N/A | |
| XIX | Service-to-Service Authentication via Client Credentials — KeycloakServiceClient, 1h token TTL | ☐ Pass / ☐ N/A | |
| XX | Frontend Auth via keycloak-js — tokens in-memory only, no login route, PKCE S256 | ☐ Pass / ☐ N/A | |
| XXI | Users Table Permanently Removed — user_id is Keycloak sub; destructive migrations non-reversible | ☐ Pass / ☐ N/A | |
| XXII | Build on VPS, Not in CI — no container registry; CI validates only, VPS builds and deploys | ☐ Pass / ☐ N/A | |
| XXIII | Path-Based Change Detection — only changed services are rebuilt; full rebuild on docker-compose.yml change | ☐ Pass / ☐ N/A | |
| XXIV | Migrations Before Container Restart — alembic upgrade head runs as docker compose run before docker compose up | ☐ Pass / ☐ N/A | |
| XXV | Automatic Rollback on Healthcheck Failure — pipeline snapshots images and restores on failure; no manual step | ☐ Pass / ☐ N/A | |
| XXVI | VPS-Only Secrets — only VPS_HOST, VPS_USER, VPS_SSH_KEY in GitHub Actions; .env lives on VPS only | ☐ Pass / ☐ N/A | |
| XXVII | Validation Gates — ruff + docker build --no-cache run in CI before any VPS SSH connection | ☐ Pass / ☐ N/A | |
| XXVIII | CI Tests Use SQLite + mongomock + AUTH_MODE=local — no real PG/Mongo/Keycloak in CI | ☐ Pass / ☐ N/A | |

> Any row marked as a violation MUST be documented in the Complexity Tracking table below
> with justification, or resolved before merge.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
