# Resource Consumption Tracker — Project Constitution

**Constitution Version:** 1.0.0
**Ratification Date:** 2026-06-05
**Last Amended:** 2026-06-05
**Status:** Active

> This constitution establishes the non-negotiable principles, architectural constraints, and governance rules for the Resource Consumption Tracker project. Every specification, implementation plan, and generated artifact MUST comply with these articles. AI agents MUST read this document before producing any output for this project.

---

## Table of Contents

1. [Project Identity](#article-i-project-identity)
2. [Technology Stack](#article-ii-technology-stack)
3. [Architectural Principles](#article-iii-architectural-principles)
4. [Code Quality Standards](#article-iv-code-quality-standards)
5. [Security Mandate](#article-v-security-mandate)
6. [Data Model Conventions](#article-vi-data-model-conventions)
7. [API Design Rules](#article-vii-api-design-rules)
8. [Testing Philosophy](#article-viii-testing-philosophy)
9. [Frontend Principles](#article-ix-frontend-principles)
10. [Documentation Standards](#article-x-documentation-standards)
11. [Governance](#article-xi-governance)
12. [Compliance Checklist](#compliance-checklist)

---

## Article I — Project Identity

### 1.1 Purpose

The Resource Consumption Tracker is a **single-user, self-hosted web application** that helps a household monitor, understand, and forecast electricity, water, and gas consumption by ingesting utility bills, extracting structured data via LLM, and producing ML-driven predictions.

### 1.2 Scope Boundaries

The following are **IN SCOPE** for this constitution:

- Bill ingestion and LLM-based parsing (electricity, gas, water)
- Consumption and cost storage in PostgreSQL
- ML prediction service (1-, 2-, 3-month horizons)
- User authentication (username/password only)
- Analysis charts and dashboards
- PDF export of consumption reports

The following are **OUT OF SCOPE** and MUST NOT be introduced without a formal constitution amendment:

- SSO, OAuth 2.0, or any social login provider
- Multi-tenancy or shared accounts
- Real-time WebSocket updates
- CSV export
- Mobile-native applications
- Admin panel or user management UI

### 1.3 User Model

The application serves a **single registered household user** per deployment instance. There is no concept of an organisation, team, or public user base. All data is private and user-scoped by `user_id` at the repository layer.

---

## Article II — Technology Stack

The following stack is **locked**. No alternative library or runtime may be introduced for a locked concern without a Major amendment (see Article XI).

### 2.1 Backend

| Concern | Technology | Version |
|---|---|---|
| Language | Python | 3.12 |
| Web framework | FastAPI | latest stable |
| ORM | SQLAlchemy (async) | 2.x |
| Migrations | Alembic | latest stable |
| Validation | Pydantic | v2 |
| Password hashing | bcrypt (via passlib) | latest stable |
| JWT | python-jose | latest stable |
| PDF text extraction | PyMuPDF (`fitz`) | latest stable |
| Image OCR | pytesseract | latest stable |
| LLM client | openai (official SDK) | latest stable |
| ML | scikit-learn | latest stable |
| Chart rendering (server) | Matplotlib (Agg backend) | latest stable |
| PDF generation | WeasyPrint | latest stable |
| Template engine | Jinja2 | latest stable |
| Logging | structlog | latest stable |
| Settings | pydantic-settings | latest stable |

### 2.2 Frontend

| Concern | Technology |
|---|---|
| Language | TypeScript (strict mode) |
| Framework | React 18 |
| Component library | HeroUI |
| State management | Zustand (auth state only) |
| Server state / caching | React Query (TanStack Query v5) |
| HTTP client | Axios |
| Charts | Recharts |
| Routing | React Router v6 |
| Build tool | Vite |

### 2.3 Infrastructure

| Concern | Technology |
|---|---|
| Database | PostgreSQL 16 |
| Reverse proxy | Nginx (latest stable) |
| Containerisation | Docker + Docker Compose v2 |

### 2.4 Stack Discipline

- **No new runtime languages.** The backend is Python 3.12. The frontend is TypeScript. No Go, Rust, or Node.js services.
- **No ORMs other than SQLAlchemy.** Raw SQL queries via `text()` are permitted for analytics aggregations only; all other queries MUST use SQLAlchemy constructs.
- **No additional databases.** PostgreSQL is the single data store. No Redis, Elasticsearch, or SQLite.
- **No headless browsers.** PDF generation uses WeasyPrint only — no Playwright, Puppeteer, or Chrome.

---

## Article III — Architectural Principles

### 3.1 SOLID

Every class and module MUST conform to all five SOLID principles:

- **Single Responsibility**: Each class has exactly one reason to change. `AuthService` handles authentication only. `BillService` orchestrates bill ingestion only. `ExportService` renders PDFs only. `AnalyticsService` aggregates data only. Mixing concerns is a violation.
- **Open / Closed**: Behaviour is extended via inheritance or composition, never by modifying existing stable code. `BaseParser`, `BasePredictor` are abstract bases — new resource types or model algorithms extend them without touching callers.
- **Liskov Substitution**: Any concrete `BasePredictor` or `BaseParser` subclass MUST be substitutable for its parent without altering any caller. Subtypes may not narrow contracts or raise exception types not declared by the base.
- **Interface Segregation**: Injected dependencies expose only the methods a caller needs. A service that only reads bills receives a `ReadableBillRepository`, not the full mutable repository.
- **Dependency Inversion**: All services depend on abstractions injected via FastAPI `Depends()`. No service instantiates its own dependencies. No circular imports between service modules.

### 3.2 DRY

- The `get_current_user` dependency MUST be defined exactly once in `app/api/deps.py` and reused across all protected routers.
- Pydantic schemas use inheritance (`BillBase → BillCreate → BillRead`) to avoid field duplication.
- No business logic is duplicated between the HTTP layer and the service layer. Routers delegate immediately to services.
- Database session management is defined once in `app/core/database.py`.

### 3.3 KISS

- Start with the simplest solution that satisfies the requirement. `LinearRegression` before `GradientBoostingRegressor`. One Alembic migration per feature branch. One Jinja2 template for PDF export, not a template hierarchy.
- Premature abstraction is a violation. Do not create a `ModelRegistry`, `ParserPipeline`, or `ServiceLocator` before there is a concrete need for three or more implementations.
- No wrapper classes around framework primitives unless they provide measurable simplification.

### 3.4 Layered Architecture

The backend MUST follow a strict four-layer architecture. Calls flow downward only — no layer may call a layer above it:

```
HTTP Layer    (app/api/v1/)        — routing, request parsing, response serialisation
Service Layer (app/services/)      — business logic, orchestration
Repository    (app/repositories/)  — data access, query construction
Domain        (app/domain/)        — models, schemas, enums (no logic)
```

The `core/` package provides cross-cutting infrastructure (config, database, security) and may be imported by any layer.

### 3.5 Data Isolation

Every repository query that touches `Bill` or `Prediction` MUST accept and filter by `user_id`. There is no global bill query. Violating data isolation is a critical security defect.

---

## Article IV — Code Quality Standards

### 4.1 Python

- All public functions, methods, and class attributes MUST have type annotations. `mypy --strict` MUST pass with zero errors.
- No function body may exceed **30 lines**. Extract helpers; name them for what they do.
- No bare `except:` or `except Exception:` clauses. All exception handlers MUST catch a specific typed exception.
- `ruff` linter and formatter MUST pass with zero warnings using the project's `pyproject.toml` configuration.
- All modules MUST have a module-level docstring summarising their responsibility.
- No `print()` statements in production code. Use `structlog` for all logging.

### 4.2 TypeScript / React

- `strict: true` in `tsconfig.json`. No `any` types.
- No inline styles in JSX except for dynamic values that cannot be expressed in Tailwind/HeroUI classes.
- Components MUST be functional with hooks. No class components.
- All React Query keys MUST be defined as constants in a `queryKeys.ts` file to avoid key collisions.
- No direct `fetch()` calls — all HTTP calls go through the configured Axios instance with the token-refresh interceptor.

### 4.3 Naming Conventions

| Artefact | Convention | Example |
|---|---|---|
| Python class | `PascalCase` | `BillRepository` |
| Python function / variable | `snake_case` | `get_current_user` |
| Python constant | `SCREAMING_SNAKE_CASE` | `ACCESS_TOKEN_EXPIRE_MINUTES` |
| Python file | `snake_case.py` | `bill_service.py` |
| React component | `PascalCase.tsx` | `UploadModal.tsx` |
| React hook | `camelCase`, `use` prefix | `useBillHistory` |
| TypeScript type / interface | `PascalCase` | `BillRead` |
| CSS class (Tailwind) | utility classes only | — |
| DB table | `snake_case`, plural | `bills`, `refresh_tokens` |
| DB column | `snake_case` | `amount_consumed` |
| Alembic revision | `<date>_<description>` | `20260605_add_refresh_token` |

---

## Article V — Security Mandate

### 5.1 Authentication

- Passwords MUST be hashed with **bcrypt** at cost factor ≥ 12. Plaintext passwords MUST never be logged, stored, or returned in any response.
- The `hashed_password` field MUST NOT appear in any Pydantic response schema. Violating this is a critical security defect that blocks the quality gate.
- Access tokens are JWTs (HS256), valid for **15 minutes**, containing only `{ "sub": "<user_id>", "exp": ... }`.
- Refresh tokens are 64-byte cryptographically random strings, stored as SHA-256 hashes in the `refresh_tokens` table with an expiry timestamp and a revocation flag.
- Refresh tokens MUST be rotated on every use. The old token is atomically revoked before the new pair is issued.
- The refresh token is delivered as an `HttpOnly; Secure; SameSite=Strict` cookie. It MUST NOT be accessible to JavaScript.

### 5.2 Input Validation

- All request bodies are validated by Pydantic before reaching the service layer. No service method accepts raw `dict` from an HTTP handler.
- File uploads MUST be validated for MIME type (allowed: `application/pdf`, `image/jpeg`, `image/png`) and size (max: `MAX_UPLOAD_SIZE_MB` from env).
- All SQL queries MUST use SQLAlchemy parameterised statements. String interpolation into SQL is prohibited.

### 5.3 Secrets Management

- Secrets (`JWT_SECRET_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`) MUST come from environment variables via `pydantic-settings`.
- No secret, credential, or API key may appear in source code, Git history, or log output.
- `JWT_SECRET_KEY` MUST be at least 256 bits (32 bytes) of entropy.

### 5.4 CORS

- CORS origins are configured via the `CORS_ORIGINS` env var. The wildcard `*` is prohibited in production configuration.

---

## Article VI — Data Model Conventions

### 6.1 Primary Keys

All tables use `UUID` primary keys generated server-side (`uuid4`). Auto-increment integers are prohibited.

### 6.2 Timestamps

All tables include `created_at` and `updated_at` columns of type `TIMESTAMPTZ` (timezone-aware). `updated_at` MUST be updated automatically via a SQLAlchemy `onupdate` trigger.

### 6.3 Soft Deletes

The `bills` table uses soft deletion via a nullable `deleted_at: TIMESTAMPTZ` column. All repository queries MUST filter `WHERE deleted_at IS NULL` by default. Hard deletes are prohibited.

### 6.4 Enumerations

Domain enumerations (`ResourceType`, `Unit`, `Currency`) are defined in `app/domain/enums.py` as Python `enum.Enum` subclasses and stored as `VARCHAR` in PostgreSQL (not native `ENUM` types, to simplify migrations).

### 6.5 Decimals

Monetary and consumption values MUST be stored as `NUMERIC(12, 4)` — never `FLOAT` or `DOUBLE PRECISION`. Python-side, use `decimal.Decimal`.

### 6.6 Migrations

- Every schema change MUST be captured in an Alembic migration. Modifying `models.py` without a corresponding migration is a violation.
- Migration scripts MUST be reviewed for `downgrade()` correctness.
- `alembic upgrade head` MUST succeed against a fresh database with no manual intervention.

---

## Article VII — API Design Rules

### 7.1 URL Structure

All API endpoints live under `/api/v1/`. The version prefix is mandatory.

| Resource | Base path |
|---|---|
| Authentication | `/api/v1/auth/` |
| Bills | `/api/v1/bills/` |
| Predictions | `/api/v1/predictions/` |
| Analytics | `/api/v1/analytics/` |
| Exports | `/api/v1/exports/` |

### 7.2 HTTP Methods

| Operation | Method | Notes |
|---|---|---|
| Create | `POST` | Returns `201 Created` |
| Read list | `GET` | Supports pagination via `page` + `size` |
| Read single | `GET /{id}` | Returns `404` if not found |
| Replace | `PUT /{id}` | Full replacement |
| Partial update | `PATCH /{id}` | Partial update |
| Soft delete | `DELETE /{id}` | Sets `deleted_at`; returns `204 No Content` |

### 7.3 Error Responses

All error responses MUST follow **RFC 7807 Problem Details** (`application/problem+json`):

```json
{
  "type": "https://resource-tracker/errors/not-found",
  "title": "Resource not found",
  "status": 404,
  "detail": "Bill with id 'abc-123' does not exist.",
  "instance": "/api/v1/bills/abc-123"
}
```

### 7.4 Pagination

List endpoints MUST support `page` (1-based) and `size` (default 20, max 100) query parameters. Responses MUST include:

```json
{
  "items": [...],
  "total": 42,
  "page": 1,
  "size": 20,
  "pages": 3
}
```

### 7.5 OpenAPI Documentation

Every endpoint MUST include a `summary`, `description`, and at least one `response` example in its FastAPI decorator or docstring. The OpenAPI schema MUST be valid and accessible at `/api/v1/openapi.json`.

### 7.6 Streaming Responses

The PDF export endpoint (`GET /api/v1/exports/report.pdf`) MUST use `StreamingResponse` with `Content-Type: application/pdf` and `Content-Disposition: attachment; filename="report.pdf"`.

---

## Article VIII — Testing Philosophy

### 8.1 Test-First Requirement

For every service method and repository method, tests MUST be written **before or alongside** the implementation. No service method is considered complete without passing tests.

### 8.2 Coverage Thresholds

| Scope | Minimum Coverage |
|---|---|
| Overall project | 85% |
| `app/services/` | 90% |
| `app/repositories/` | 85% |
| `app/api/` | 80% |

These thresholds are enforced by the rigour-labs/mcp quality gate.

### 8.3 Test Categories

**Unit tests** (`tests/unit/`)
- Isolate a single class or function.
- External dependencies (OpenAI, DB) are mocked.
- Must be fast (< 50ms each).

**Integration tests** (`tests/integration/`)
- Test a full request–response cycle against a real (in-memory or Docker) PostgreSQL instance.
- No mocking of the database layer.
- OpenAI calls MUST be mocked via `pytest-mock` to prevent live API usage in CI.

**Quality-gate tests** (`tests/quality/`)
- Performance benchmarks (`pytest-benchmark`): analytics endpoint < 200ms for ≤ 100 bills.
- Security checks: brute-force 10 wrong-password attempts returns only `401`s.
- PDF validation: export response starts with `%PDF` magic bytes.

### 8.4 Test Tooling

- Test runner: `pytest`
- Mocking: `pytest-mock`
- Async support: `anyio` (via `pytest-anyio`)
- Fixtures: shared fixtures in `tests/conftest.py`
- Test database: spun up via Docker Compose `test` profile; isolated per test session with Alembic migrations applied fresh.

### 8.5 LLM Call Prohibition in Tests

No test may make a live call to the OpenAI API. All `LLMParserService` calls MUST be mocked. Leaving an un-mocked OpenAI call in the test suite is a blocking quality-gate failure.

---

## Article IX — Frontend Principles

### 9.1 Route Protection

All routes except `/login` and `/register` MUST be wrapped in a `<ProtectedRoute>` component that redirects unauthenticated users to `/login`.

### 9.2 Token Storage

- The JWT access token MUST be stored in Zustand in-memory state only. It MUST NOT be written to `localStorage`, `sessionStorage`, or any cookie accessible to JavaScript.
- The refresh token is managed exclusively via the `HttpOnly` cookie set by the backend. Frontend code MUST NOT read, write, or reference the refresh token value directly.

### 9.3 Token Refresh Interceptor

A single Axios response interceptor MUST be configured on the shared Axios instance. On receiving a `401` response, it MUST:

1. Call `POST /api/v1/auth/refresh` (the browser sends the `HttpOnly` cookie automatically).
2. Update the Zustand store with the new access token.
3. Retry the original request with the new token.
4. If the refresh call also returns `401`, clear auth state and redirect to `/login`.

This interceptor is defined exactly once. No other code may handle token refresh.

### 9.4 Server State

All server data (bills, predictions, analytics) MUST be managed by React Query. No manual `useEffect` + `useState` combinations for data fetching. Query keys MUST be centralised in `src/lib/queryKeys.ts`.

### 9.5 Error Handling

Every React Query mutation MUST have an `onError` handler that displays a HeroUI toast notification with the RFC 7807 `detail` message from the server response. Silent failures are prohibited.

### 9.6 Empty States

Every data-displaying component MUST render a meaningful empty state when there are zero records, rather than rendering nothing or showing a spinner indefinitely.

### 9.7 Loading States

File upload and LLM parsing operations MUST show a progress indicator for the duration of the request. The upload button MUST be disabled during processing to prevent duplicate submissions.

---

## Article X — Documentation Standards

### 10.1 Separation of Concerns

Documentation strictly follows the SDD separation model:

- **`spec.md`** — WHAT the feature does and WHY. Technology-agnostic. Audience: product / domain experts.
- **`plan.md`** — HOW the feature is implemented. Contains all technical decisions, library choices, architecture. Audience: engineers.
- **`constitution.md`** (this file) — Non-negotiable principles. Constrains both spec and plan.

No implementation detail (framework name, library, database schema) may appear in `spec.md`. No user story or business rationale needs to be repeated in `plan.md`.

### 10.2 README

The project `README.md` MUST include:

- Prerequisites (Docker, Docker Compose version)
- One-command local startup: `docker compose up`
- Required environment variables (with safe placeholder values)
- Link to the OpenAPI docs URL

### 10.3 ADR Log

Significant architectural decisions (library selection, schema design choices, ML algorithm selection) MUST be recorded as Architecture Decision Records in `docs/adr/`. Each ADR follows the Nygard format: Context, Decision, Consequences.

---

## Article XI — Governance

### 11.1 Amendment Process

This constitution is a living document versioned with semantic rules:

| Change type | Version bump | Examples |
|---|---|---|
| Remove or redefine a principle | **MAJOR** (breaking) | Changing auth scheme, switching ORM |
| Add a new principle or section | **MINOR** | New logging rule, new naming convention |
| Clarify wording without changing intent | **PATCH** | Fixing a typo, adding an example |

All amendments MUST:

1. Increment `Constitution Version` and update `Last Amended` date.
2. Document the rationale in `docs/adr/` as a new ADR.
3. Verify that all existing `spec.md` and `plan.md` files remain compliant or are updated in the same PR.
4. Be merged via a pull request — no direct commits to `main`.

### 11.2 Compliance Review

The `/speckit.analyze` command MUST run constitutional compliance checks before any `plan.md` is merged. A spec or plan that violates any article in this constitution MUST NOT be merged until the violation is resolved or a formal amendment is ratified.

### 11.3 Quality Gate Integration

| Gate tool | Enforcement scope |
|---|---|
| **Selena MCP** | Type annotations, function length (≤ 30 lines), OpenAPI docs completeness, no hardcoded secrets, no `hashed_password` in responses, `AuthService` coupling check |
| **rigour-labs/mcp** | Test coverage thresholds, parameterised queries, `ruff` lint, Docker build, Alembic migration health, integration suite, PDF magic bytes, brute-force auth test |

Both gates MUST pass before any PR may be merged.

---

## Compliance Checklist

Use this checklist when reviewing any AI-generated artifact (spec, plan, task list, or code) for constitutional compliance.

### Architecture
- [ ] Four-layer architecture respected — no layer calls upward
- [ ] All services depend on injected abstractions, not concrete implementations
- [ ] `user_id` scoping present in every bill/prediction repository query
- [ ] No new runtime language, database, or PDF library introduced

### Code Quality
- [ ] All Python public functions have type annotations
- [ ] No function exceeds 30 lines
- [ ] No bare `except` clauses
- [ ] `ruff` passes with zero warnings
- [ ] TypeScript `strict` mode — no `any`

### Security
- [ ] `hashed_password` absent from all response schemas
- [ ] Passwords never logged
- [ ] All SQL uses parameterised statements
- [ ] Refresh token stored as `HttpOnly` cookie only
- [ ] `JWT_SECRET_KEY` loaded from environment, never hardcoded

### Data Model
- [ ] UUIDs for all PKs
- [ ] `created_at` / `updated_at` on all tables
- [ ] Monetary values use `NUMERIC(12,4)`, not `FLOAT`
- [ ] Alembic migration present for every schema change

### API
- [ ] All endpoints under `/api/v1/`
- [ ] Errors follow RFC 7807 Problem Details
- [ ] Paginated list endpoints include `total`, `page`, `size`, `pages`
- [ ] Every endpoint documented in OpenAPI with summary + example

### Testing
- [ ] Service and repository methods have tests
- [ ] No live OpenAI calls in test suite
- [ ] Coverage ≥ 85% overall, ≥ 90% for `services/`

### Frontend
- [ ] All routes except `/login` and `/register` are protected
- [ ] Access token in Zustand memory only — not in storage or cookies
- [ ] Single Axios interceptor handles token refresh
- [ ] All mutations have `onError` toast handlers
- [ ] Empty states rendered for zero-data views

### Documentation
- [ ] `spec.md` is technology-agnostic
- [ ] `plan.md` contains all technical decisions
- [ ] `README.md` includes startup instructions and env var reference
