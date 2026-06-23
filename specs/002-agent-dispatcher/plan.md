# Implementation Plan: Agent Dispatcher Service

**Branch**: `002-agent-dispatcher` | **Date**: 2026-06-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/002-agent-dispatcher/spec.md`

## Summary

Build `services/agent-dispatcher/` — a new standalone FastAPI microservice that polls the
Orchestrator for tickets with `assigned_agent` set, executes the assigned agent (via Claude
Code subprocess or OpenAI API), coordinates multi-round brainstorm sessions for
architecture-review tickets, and reports results back to Ticket Manager and Orchestrator.
No FSM state is modified directly; the service is self-driving via a polling loop with an
async semaphore for concurrency control.

Agents that implement tasks (run via `development/run-agents.sh`) MUST report their task
completion using `development/scripts/report-task-metrics.sh` as the final step of every
task handshake.

## Technical Context

**Language/Version**: Python 3.12 (monorepo canonical)
**Primary Dependencies**: FastAPI 0.115.5, SQLAlchemy 2.0.36 async + asyncpg 0.30.0,
  Pydantic 2.10.3, Pydantic-Settings 2.6.1, httpx 0.28.0, openai 1.57.0, ruff 0.8.3,
  python-jose 3.3.0, alembic 1.14.0
**Storage**: PostgreSQL 16 (`df_dispatcher` database — two tables: `agent_runs`,
  `brainstorm_sessions`)
**Testing**: pytest 8.3.4, pytest-asyncio 0.24.0, pytest-cov 6.0.0; ≥ 80% coverage;
  no real Claude Code or API calls in tests (AsyncMock for subprocess and httpx)
**Target Platform**: Linux server (Docker container, `python:3.12-slim` base image)
**Project Type**: web-service (FastAPI, no frontend)
**Performance Goals**: Detect and start an agent run within `POLL_INTERVAL_SECONDS + 5s`;
  sustain `WORKER_MAX_CONCURRENT_RUNS` (default 3) simultaneous runs without polling stall
**Constraints**: Never block polling loop on slow agent; never run two agents per ticket
  simultaneously; never crash on missing `[RESULT]`; never cache prompt files; never
  expose `SERVICE_JWT` or TM credentials in logs or API responses
**Scale/Scope**: Single-service addition to the monorepo; no frontend; no changes to
  existing services

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|-----------|-------|--------|
| I. Independently deployable | Service has its own `docker-compose.yml`; communicates with other services via HTTP only | ✅ PASS |
| II. Auth adapter pattern | `src/core/auth_adapter.py` with `AUTH_MODE=local\|keycloak`; JWT validation for incoming requests; service JWT for outbound calls | ✅ PASS |
| III. Python 3.12 everywhere | `python:3.12-slim` Dockerfile; all deps compatible with 3.12 | ✅ PASS |
| IV. Python versions pinned | `requirements.txt` uses exact versions from root `pyproject.toml` canonical table | ✅ PASS |
| V. Frontend versions N/A | No frontend in this service | ✅ N/A |
| VI. Zustand N/A | No frontend | ✅ N/A |
| VII. Vitest N/A | No frontend | ✅ N/A |
| VIII. ruff for linting | `.pre-commit-config.yaml` at service root using `ruff==0.8.3` for lint+format | ✅ PASS |
| IX. Nginx N/A | No frontend DNS entry needed | ✅ N/A |
| X. No cross-service DB access | Dispatcher owns `df_dispatcher` exclusively; all cross-service data via HTTP API | ✅ PASS |
| XI. FSM sovereignty | Dispatcher never calls Orchestrator FSM endpoints; only reads assigned tickets and triggers job re-evaluation | ✅ PASS |
| XII. Operational safety | Graceful `[RESULT]` degradation; no prompt caching; no secret exposure in logs/API | ✅ PASS |

**All gates pass. Proceed to Phase 0.**

## Project Structure

### Documentation (this feature)

```text
specs/002-agent-dispatcher/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/           ← Phase 1 output
└── tasks.md             ← Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
services/agent-dispatcher/
├── src/
│   ├── core/
│   │   ├── config.py              # Settings + env vars + agent_timeout_for() + brainstorm_agents_list
│   │   ├── exceptions.py          # AppError hierarchy
│   │   ├── security.py            # create_service_token(), verify_access_token()
│   │   └── auth_adapter.py        # JWT validation (local | keycloak stub)
│   ├── db/
│   │   └── session.py             # async engine + get_db dependency
│   ├── models/
│   │   └── models.py              # AgentRun, BrainstormSession ORM + agent_run_status enum
│   ├── schemas/
│   │   └── schemas.py             # AgentRunResponse, AgentRunListResponse,
│   │                              # BrainstormSessionResponse, AgentResult, AgentContext
│   ├── repositories/
│   │   ├── run_repo.py            # AgentRunRepository
│   │   └── brainstorm_repo.py     # BrainstormSessionRepository
│   ├── services/
│   │   ├── poller.py              # Polls Orchestrator for assigned tickets
│   │   ├── context_builder.py     # Assembles full agent context string
│   │   ├── result_parser.py       # Extracts [RESULT] block — pure, no I/O
│   │   ├── brainstorm_coordinator.py  # Multi-round sequential session management
│   │   ├── reporter.py            # POSTs to TM + triggers Orchestrator job
│   │   ├── dispatcher_service.py  # Top-level ticket lifecycle coordinator
│   │   └── runner/
│   │       ├── base.py            # AgentRunner ABC
│   │       ├── claude_code.py     # asyncio subprocess runner
│   │       └── api_runner.py      # OpenAI API runner
│   ├── workers/
│   │   └── dispatch_worker.py     # Async polling loop + semaphore
│   ├── api/
│   │   └── v1/
│   │       └── runs.py            # GET /api/v1/runs, GET /api/v1/runs/{id}
│   └── main.py                    # FastAPI app + lifespan + health endpoint
├── prompts/
│   ├── backend.md                 # Agent system prompts (read-only at runtime)
│   ├── software_architect.md
│   ├── security_architect.md
│   ├── project_manager.md
│   ├── frontend.md
│   ├── designer.md
│   ├── code_reviewer.md
│   ├── autotester.md
│   ├── devops.md
│   └── project_administrator.md
├── tests/
│   ├── unit/
│   │   ├── test_result_parser.py
│   │   ├── test_context_builder.py
│   │   └── test_brainstorm_coordinator.py
│   ├── integration/
│   │   ├── test_run_repo.py
│   │   ├── test_brainstorm_repo.py
│   │   ├── test_dispatcher_service.py
│   │   └── test_poller.py
│   └── conftest.py
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 0001_create_agent_dispatcher_tables.py
├── alembic.ini
├── Dockerfile
├── docker-compose.yml             # standalone dev compose
├── requirements.txt
├── pytest.ini
├── .coveragerc
└── .pre-commit-config.yaml
```

**Structure Decision**: Single Python service (no frontend). Mirrors the structure of
`services/orchestrator/` exactly — same layer split (core/db/models/schemas/repositories/
services/workers/api). This minimises onboarding friction for agents familiar with the
existing codebase.

---

## Phase 0: Research

### R-001 — Agent runner subprocess pattern

**Decision**: Use `asyncio.create_subprocess_exec` with `stdout=PIPE`, `stderr=PIPE`.
Capture via `asyncio.wait_for(proc.communicate(), timeout_seconds)`. Kill subprocess on
timeout with `proc.kill()` then `await proc.communicate()` to drain pipes.

**Rationale**: `communicate()` is the correct asyncio pattern for capturing both streams
and avoiding deadlock. `create_subprocess_exec` avoids shell injection risks (no shell=True).

**Alternatives considered**: `asyncio.create_subprocess_shell` — rejected (injection risk);
`subprocess.run` in an executor — rejected (blocks event loop thread pool under load).

### R-002 — JWT generation for service-to-service calls

**Decision**: Generate short-lived JWTs using `python-jose` with the shared
`JWT_SECRET_KEY`. Token includes `sub=service:agent-dispatcher`, `exp=now+SERVICE_JWT_EXPIRE_HOURS`.
Reuse the same pattern as `services/orchestrator/src/core/security.py`.

**Rationale**: All services share the same JWT secret; generating a compatible token is
the lightest-weight path. No new auth infrastructure needed.

**Alternatives considered**: Static API key header — rejected (not consistent with
monorepo auth pattern); OAuth2 client credentials — rejected (Keycloak not yet active).

### R-003 — OpenAI API runner for `api` mode

**Decision**: Use the `openai` Python SDK (async client, `AsyncOpenAI`). Send
`messages=[{"role": "system", content: system_prompt}, {"role": "user", content: context}]`.
Model from `OPENAI_MODEL` (default `gpt-4o`). Wrap in try/except for `openai.APIError`.

**Rationale**: Identical to how `services/orchestrator/` and `services/context-distiller/`
call the OpenAI API.

**Alternatives considered**: Anthropic SDK — valid alternative but `OPENAI_API_KEY` is
already the configured env var in the monorepo; the spec explicitly names OpenAI.

### R-004 — Context token truncation strategy

**Decision**: Count tokens using `len(text.split()) * 1.3` as a cheap approximation
(no tiktoken dependency). Truncate `project_memory.content` at the end of the last
complete sentence before the `CONTEXT_MAX_TOKENS` word boundary. Log a warning when
truncation occurs.

**Rationale**: tiktoken adds a dependency and startup cost. The approximation is
sufficient for a safety truncation on context injection; agents can handle slightly
over/under the limit.

**Alternatives considered**: tiktoken — accurate but adds dep and latency; hard character
limit — simpler but mid-word truncation degrades context quality.

### R-005 — Brainstorm coordination in `claude_code` mode

**Decision**: In `claude_code` mode, agents use the brainstorm-mcp MCP server natively
(already in their `~/.claude/mcp_config.json`). The Dispatcher only tracks round numbers
and session state in the DB. In `api` mode, the Dispatcher injects previous agents'
`tm_comment` values as a "Previous agent responses:" prefix in the next agent's context.

**Rationale**: This keeps `claude_code` mode maximally autonomous (agents self-coordinate
via MCP) while making `api` mode work without MCP support.

### R-006 — Task metrics reporting contract (run-agents.sh integration)

**Decision**: Agents launched via `development/run-agents.sh` receive a mandatory
completion handshake instruction as part of their startup prompt. After every completed
task, each agent MUST:
1. Run `bash development/scripts/report-task-metrics.sh` with feature name, task ID,
   description, time spent, tokens spent, and model used.
2. Send a brainstorm message to `project-administrator` with `payload.type = "task-metrics"`
   and the same fields.
3. Only then announce task completion or hand off work.

The Agent Dispatcher's `context_builder.py` injects this reporting contract into every
agent context document under a "## Completion and Metrics Reporting" section, alongside
the `[RESULT]` block instructions. This ensures agents spawned by the Dispatcher (not just
by `run-agents.sh`) also follow the metrics contract.

**Rationale**: `run-agents.sh` already encodes this handshake in every agent's startup
prompt (STEP 5 in both coordinator and contributor templates). The Dispatcher must mirror
this contract so that agents are consistent regardless of how they are launched. The
`project-administrator` agent collects all metrics into a SQLite DB via `agent_metrics.py`.

**Alternatives considered**: Omitting metrics from Dispatcher-launched agents — rejected
(inconsistency would produce gaps in the project-administrator's reconciliation report);
injecting only the bash script call without the brainstorm message — rejected (PA agent
won't detect completion without the message).

---

## Phase 1: Design & Contracts

### Data Model (`data-model.md`)

See [data-model.md](data-model.md) — generated below.

### API Contracts (`contracts/`)

See [contracts/api.md](contracts/api.md) — generated below.

### Quickstart (`quickstart.md`)

See [quickstart.md](quickstart.md) — generated below.

### Agent Context CLAUDE.md update

Updated `CLAUDE.md` to reference this plan (see step at end of phase).

---

## Complexity Tracking

No constitution violations. No complexity justification required.
