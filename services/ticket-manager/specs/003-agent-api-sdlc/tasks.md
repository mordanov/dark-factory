# Tasks: Agent API SDLC Integration

**Input**: Design documents from `/specs/003-agent-api-sdlc/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Implementation**: Run `bash run-agents.sh [--project agent-api-sdlc]` to launch the full 9-agent team. The `product-manager` agent (coordinator) reads this file, creates a project on the ticket platform, and creates one ticket per task — tagged with `ticket_spec` matching the responsible agent. Agents claim and implement their tickets autonomously. Do NOT use `/speckit-implement`.

**Agents available**: project-administrator · product-manager · software-architect · security-architect · frontend · backend · devops · code-reviewer · autotester

---

## Phase 1: Setup

**Purpose**: Credential file security must be in place before any agent bootstrapping runs.

- [ ] T001 Update `.gitignore` at repo root to add `*/credentials.json` pattern, which excludes all per-role agent credential files from version control (see research.md Decision 6)

**Checkpoint**: `.gitignore` covers all `{role}/credentials.json` paths.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database migration and admin schema extension — must complete before any user story implementation begins.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T002 Create Alembic migration file `backend/alembic/versions/014_add_ticket_resource_fields.py` — up path: `ALTER TABLE tickets ADD COLUMN time_spent INTEGER NOT NULL DEFAULT 0; ALTER TABLE tickets ADD COLUMN tokens_consumed INTEGER NOT NULL DEFAULT 0;`; down path: `ALTER TABLE tickets DROP COLUMN time_spent; ALTER TABLE tickets DROP COLUMN tokens_consumed;`; revision must chain from `012_add_tags.py`
- [ ] T003 [P] Add `password: str | None = Field(None, min_length=8)` to the `AdminUserUpdate` class in `backend/src/schemas/admin.py` (enables password reset for agent credential recovery — see contracts/admin-password-reset.md)

**Checkpoint**: Foundation ready — run `cd backend && alembic upgrade head` to verify migration applies cleanly.

---

## Phase 3: User Story 1 — Ticket Resource Tracking (Priority: P1) 🎯 MVP

**Goal**: Any authenticated agent can atomically increment `time_spent` and `tokens_consumed` on any ticket. Each increment produces an immutable `ticket.resources_incremented` journal entry.

**Independent Test**: `POST /api/v1/tickets/{id}/resources {"time_spent_delta":120,"tokens_consumed_delta":500}` returns `time_spent=120, tokens_consumed=500, event_id=<uuid>`; `GET /api/v1/tickets/{id}/events` shows the new event; a negative delta returns HTTP 400.

- [ ] T004 [US1] Add `time_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")` and `tokens_consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")` to the `Ticket` class in `backend/src/models/ticket.py`; add `Integer` to SQLAlchemy imports
- [ ] T005 [P] [US1] Add `time_spent: int` and `tokens_consumed: int` as read-only fields to the `TicketResponse` Pydantic class in `backend/src/schemas/ticket.py` (model already uses `from_attributes=True`; no extra mapping needed)
- [ ] T006 [P] [US1] Create `backend/src/schemas/resource.py` with two Pydantic models: `TicketResourceIncrementRequest` (fields: `time_spent_delta: int = Field(0, ge=0)`, `tokens_consumed_delta: int = Field(0, ge=0)`; add a `model_validator` that raises `ValueError` if both are 0) and `TicketResourceIncrementResponse` (fields: `ticket_id: UUID`, `time_spent: int`, `tokens_consumed: int`, `event_id: UUID`)
- [ ] T007 [US1] Create `backend/src/services/resource_service.py` with async function `increment_resources(session: AsyncSession, ticket_id: UUID, actor: User, time_delta: int, token_delta: int) -> TicketResourceIncrementResponse`: (1) fetch ticket with `SELECT … FOR UPDATE`, raise 404 if missing; (2) record `prev_state = {"time_spent": ticket.time_spent, "tokens_consumed": ticket.tokens_consumed}`; (3) execute `await session.execute(update(Ticket).where(Ticket.id == ticket_id).values(time_spent=Ticket.time_spent + time_delta, tokens_consumed=Ticket.tokens_consumed + token_delta))`; (4) refresh ticket; (5) call `await emit_event(session, ticket_id, "ticket.resources_incremented", actor, prev_state=prev_state, new_state={"time_spent": ticket.time_spent, "tokens_consumed": ticket.tokens_consumed, "time_spent_delta": time_delta, "tokens_consumed_delta": token_delta})`; (6) commit; (7) return `TicketResourceIncrementResponse`
- [ ] T008 [US1] Create `backend/src/api/v1/resources.py` with a FastAPI `APIRouter(prefix="/tickets", tags=["Resources"])` and one endpoint: `POST /{ticket_id}/resources` — validates `TicketResourceIncrementRequest`, calls `resource_service.increment_resources`, returns `TicketResourceIncrementResponse`; requires `current_user = Depends(get_current_user)`
- [ ] T009 [US1] Register the resources router in `backend/src/api/v1/router.py` by importing `from src.api.v1 import resources` and calling `router.include_router(resources.router)`

**Checkpoint**: US1 independently testable — run quickstart.md Story 1 section against `uvicorn src.main:app --reload`.

---

## Phase 4: User Story 2 — Agent User Bootstrapping (Priority: P2)

**Goal**: project-administrator agent reads its own credential file, authenticates as platform admin, and ensures all 8 other agent accounts exist on the ticket platform with correct passwords — writing credentials to each agent's working directory.

**Independent Test**: Place `project-administrator/credentials.json` manually; run bootstrap simulation from quickstart.md Story 2; verify 8 `{role}/credentials.json` files exist and each agent can obtain a JWT via POST `/api/v1/auth/token`; verify all credential files absent from `git status`.

- [ ] T010 [US2] Update `admin_service.update_user` in `backend/src/services/admin_service.py`: inside the update block, add `if data.password is not None: user.hashed_password = hash_password(data.password)` and emit a structlog `admin_user_password_reset` info event with `actor_id`, `target_user_id`, and `target_email`
- [ ] T011 [US2] Add a **"Platform Bootstrap"** section to `agents/project-administrator.md` (insert before the existing "Workflow" section) describing the full bootstrap sequence: (1) read `project-administrator/credentials.json` — halt with error if missing; (2) `POST /api/v1/auth/token {"email": <username>, "password": <password>}` → store JWT; (3) `GET /api/v1/admin/users` → build email→id map; (4) for each role in `[product-manager, software-architect, security-architect, frontend, backend, devops, code-reviewer, autotester]`: (a) target email = `{role}@agents.local`; (b) if not in map: generate 24-char password with `secrets.token_urlsafe(18)`, `POST /api/v1/admin/users {email, password, role:"user"}`, write `{role}/credentials.json {"username": email, "password": password}`; (c) if in map but `{role}/credentials.json` exists: attempt login with stored creds, if 401 generate new password, `PATCH /api/v1/admin/users/{id} {"password": new_password}`, update credentials file
- [ ] T012 [P] [US2] Create `project-administrator/credentials.json.example` at the repo root level with content `{"username": "admin@example.com", "password": "replace-with-your-admin-password"}` as a format reference for human operators; this example file IS committed to git (the actual `credentials.json` is gitignored)

**Checkpoint**: US2 independently testable — follow quickstart.md Story 2 section.

---

## Phase 5: User Story 3 — Agent Ticket Lifecycle via API (Priority: P3)

**Goal**: Transition endpoint enforces assignee-only RBAC (HTTP 403 for non-assignees, including project-administrator unless assigned). All 9 agent skill files contain a "Platform Authentication" section so agents can authenticate and perform all ticket operations autonomously.

**Independent Test**: Attempt `POST /tickets/{id}/transitions` as non-assignee → HTTP 403; as assignee after progress update → HTTP 200 with new status; all agent skill files contain credentials-based auth instructions.

- [ ] T013 [US3] In `backend/src/services/transition_service.py` function `transition_ticket`, insert immediately after the `all_assignments` query (before `validate_transition`): `assignee_ids = {a.user_id for a in all_assignments}; if actor.id not in assignee_ids: raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only assignees may transition this ticket")` — applies to all roles including administrator (see contracts/transition-rbac.md)
- [ ] T014 [P] [US3] Add **"Platform Authentication"** section to `agents/product-manager.md` documenting: (1) read `product-manager/credentials.json`; (2) `POST /api/v1/auth/token` → store JWT; (3) use `Authorization: Bearer <token>` on all API calls; include curl examples for `POST /api/v1/projects`, `POST /api/v1/projects/{id}/tickets` (with `ticket_type`, `ticket_spec`, `tags` fields), and `POST /api/v1/tickets/{id}/assignments`
- [ ] T015 [P] [US3] Add **"Platform Authentication"** section to `agents/backend-developer-python.md` documenting: (1) read `backend/credentials.json`; (2) `POST /api/v1/auth/token` → store JWT; (3) use `Authorization: Bearer <token>`; include curl examples for `PUT /api/v1/tickets/{id}/progress {"content":"..."}`, `POST /api/v1/tickets/{id}/transitions {"to_status":"IN_PROGRESS"}`, and `POST /api/v1/tickets/{id}/resources {"time_spent_delta":N,"tokens_consumed_delta":M}`
- [ ] T016 [P] [US3] Add **"Platform Authentication"** section to `agents/frontend-developer-react.md` documenting: (1) read `frontend/credentials.json`; (2) `POST /api/v1/auth/token` → store JWT; (3) use `Authorization: Bearer <token>`; include curl examples for progress update, transition, and resource increment endpoints
- [ ] T017 [P] [US3] Add **"Platform Authentication"** section to `agents/software-architect.md` documenting: (1) read `software-architect/credentials.json`; (2) authenticate via `POST /api/v1/auth/token`; include examples for progress, transition, and resource increment
- [ ] T018 [P] [US3] Add **"Platform Authentication"** section to `agents/security-architect.md` documenting: (1) read `security-architect/credentials.json`; (2) authenticate via `POST /api/v1/auth/token`; include examples for progress, transition, and resource increment
- [ ] T019 [P] [US3] Add **"Platform Authentication"** section to `agents/devops.md` documenting: (1) read `devops/credentials.json`; (2) authenticate via `POST /api/v1/auth/token`; include examples for progress, transition, and resource increment
- [ ] T020 [P] [US3] Add **"Platform Authentication"** section to `agents/code-reviewer.md` documenting: (1) read `code-reviewer/credentials.json`; (2) authenticate via `POST /api/v1/auth/token`; include examples for progress, transition, and resource increment
- [ ] T021 [P] [US3] Add **"Platform Authentication"** section to `agents/autotester.md` documenting: (1) read `autotester/credentials.json`; (2) authenticate via `POST /api/v1/auth/token`; include examples for progress, transition, and resource increment

**Checkpoint**: All three user stories complete. Run full quickstart.md end-to-end flow.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T022 [P] Run `git status` and confirm no `*/credentials.json` file appears as tracked or untracked; if any does appear, update `.gitignore` accordingly
- [ ] T023 [P] Run `cd backend && python -m pytest tests/contract/ -q` and confirm all pre-existing contract tests still pass after the schema and service changes
- [ ] T024 [P] Inspect the `run-agents.sh` agent prompt factory for `project-administrator` role and confirm the bootstrap steps from `agents/project-administrator.md` are referenced or readable from the skill file path
- [ ] T025 Add brainstorm-mcp bootstrap synchronization — two coordinated changes (depends on T011 and T014 being complete): (1) update `agents/project-administrator.md` Platform Bootstrap section to broadcast `mcp__brainstorm__send_message` with `payload={"type":"bootstrap-complete","roles":[...list of roles bootstrapped...]}` and `reply_expected=false` after ALL credential files are written and before proceeding to metrics collection; (2) update `agents/product-manager.md` Platform Authentication section to call `mcp__brainstorm__receive_messages` with `wait=true, timeout_seconds=120` immediately after joining the brainstorm project, polling until a message arrives with `payload.type == "bootstrap-complete"` from `project-administrator`, before reading `product-manager/credentials.json` or making any ticket platform API call — if the 120s timeout expires without receiving the signal, halt with error `"Bootstrap signal not received from project-administrator within timeout"`

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1; blocks all user stories
- **US1 (Phase 3)**: Depends on T002 (migration creates columns); T005 and T006 parallel after T004
- **US2 (Phase 4)**: Depends on T003 (admin schema); T011 and T012 independent of T010
- **US3 (Phase 5)**: Depends on Foundational only; T014–T021 fully parallel with T013
- **Polish (Phase 6)**: After all user stories

### US1 internal dependency graph

```
T002 (migration) → T004 (model)
                       ├── T005 [P] (TicketResponse)
                       └── T006 [P] (resource schema) → T007 (service) → T008 (router) → T009 (register)
T003 [P] (AdminUserUpdate) — parallel with T002/T004
```

### Parallel opportunities

| Phase | Parallel set |
|---|---|
| Foundational | T002 ‖ T003 |
| US1 | T005 ‖ T006 (after T004) |
| US2 | T011 ‖ T012 (independent of T010) |
| US3 | T013 ‖ T014 ‖ T015 ‖ T016 ‖ T017 ‖ T018 ‖ T019 ‖ T020 ‖ T021 |
| Polish | T022 ‖ T023 ‖ T024; T025 depends on T011+T014 |

---

## Parallel Example: User Story 3 (9 simultaneous tasks)

```bash
# These 8 agent skill updates run simultaneously (different files):
Task T014: agents/product-manager.md
Task T015: agents/backend-developer-python.md
Task T016: agents/frontend-developer-react.md
Task T017: agents/software-architect.md
Task T018: agents/security-architect.md
Task T019: agents/devops.md
Task T020: agents/code-reviewer.md
Task T021: agents/autotester.md

# Runs concurrently — different file, no dependency on T014-T021:
Task T013: backend/src/services/transition_service.py
```

---

## Implementation Strategy

### run-agents.sh execution model

1. Human runs `bash run-agents.sh --project agent-api-sdlc`
2. `project-administrator` starts first (5-second head start per script), initialises SQLite metrics DB
3. `product-manager` (coordinator) starts, creates the brainstorm project, reads this `tasks.md`, creates one ticket per task on the ticket platform with `ticket_spec` and tags matching the responsible agent
4. Specialist agents receive task assignments via brainstorm-mcp messages, claim tickets, implement, submit progress updates, transition to DONE, and report time/tokens to project-administrator
5. `project-administrator` reconciles metrics and generates the final HTML report

### Agent → task mapping

| Task IDs | Responsible agent | ticket_spec |
|---|---|---|
| T001, T022, T023, T024 | devops | `other` |
| T025 | project-administrator + product-manager | `other` |
| T002, T003, T004, T005, T006, T007, T008, T009, T010, T013 | backend | `backend` |
| T011, T012 | project-administrator | `other` |
| T014 | product-manager | `product_management` |
| T015 | backend | `backend` |
| T016 | frontend | `frontend` |
| T017 | software-architect | `architecture` |
| T018 | security-architect | `architecture` |
| T019 | devops | `other` |
| T020 | code-reviewer | `other` |
| T021 | autotester | `testing` |

### MVP Scope (US1 only — 9 tasks)

T001 → T002 ‖ T003 → T004 → T005 ‖ T006 → T007 → T008 → T009

Result: any authenticated agent can increment resource counters; journal events created; TicketResponse exposes totals.

### Full delivery order

1. Phase 1+2 (Setup + Foundation) — prerequisite gates cleared
2. Phase 3 (US1) — resource tracking live, independently testable
3. Phase 4 (US2) — agent bootstrapping live, independently testable
4. Phase 5 (US3) — RBAC enforced, all agent skills updated, full SDLC flow operational
5. Phase 6 (Polish) — validation, no regressions

---

## Notes

- `[P]` = task operates on a different file from its phase peers; no blocking dependency
- `[USn]` maps to User Story n in spec.md
- The existing `ProgressUpdate` gate in `transition_service.py` already satisfies the "mandatory update text before transition" requirement (FR-011) — T013 ADDS assignee RBAC; it does NOT replace the progress gate
- `TicketStatus` enum already has OPEN/IN_PROGRESS/IN_REVIEW/DONE/CLOSED — no enum changes needed
- `parent_ticket_id` already exists on `Ticket` — follow-up ticket creation requires no new code
- `AdminUserUpdate.password` is `None` by default — existing PATCH behavior is unchanged when omitted
- Credential files (`*/credentials.json`) must never be committed — T001 ensures this before any agent run
