# Dark Factory — Planning Agent Constitution

## Identity

Planning Agent is an extension to **user-input-manager** (Prompt Studio).
It is not a separate service. It adds a new phase to the existing session
lifecycle: after a user approves a refined prompt, the Planning Agent
decomposes it into a structured plan (Epic → Stories → Tasks) and creates
the corresponding tickets in Ticket Manager.

Planning Agent also generates **project-specific agent configuration** —
overrides that tune each Dark Factory agent's behaviour for the concrete
project described in the prompt. These overrides are stored in the
ContextDistiller Document Store and consumed by the Orchestrator when
building `agent_briefing` for each ticket assignment.

Planning Agent does not execute tasks. It does not assign agents.
It only produces the work breakdown structure and project context
that the Orchestrator and agents will use.

---

## Session Lifecycle Extension

The existing `session_status` enum must be extended with three new values:

```
in_progress        (existing — prompt refinement loop)
approved           (existing — prompt approved, plan not yet generated)
  ↓
planning           (new — LLM is generating the decomposition)
plan_ready         (new — plan generated, shown to user for review/edit)
plan_confirmed     (new — user confirmed the plan)
tickets_created    (new — N tickets created in TM, session complete)
cancelled          (existing)
```

The transition `approved → planning` is triggered by the user clicking
"Generate Plan" (replaces the current "Create Ticket" flow in `ApproveModal`).

**The existing `approve_and_create_ticket` endpoint must be replaced.**
It currently transitions directly `in_progress → approved` and creates
one ticket. The new flow:
1. User approves prompt → session status: `approved`
2. User clicks "Generate Plan" → `POST /sessions/{id}/plan`
   → status: `planning` → LLM call → status: `plan_ready`
3. User reviews/edits plan → `PUT /sessions/{id}/plan`
4. User confirms → `POST /sessions/{id}/plan/confirm`
   → creates N tickets in TM → status: `tickets_created`

The old single-ticket creation path is removed entirely.
Do not keep it as a fallback or legacy endpoint.

---

## Core Principles

### 1. Plan is stored, not ephemeral

The generated plan must be persisted in a new `prompt_plans` PostgreSQL table
before being shown to the user. A plan that exists only in memory or the LLM
response is not acceptable — the user must be able to close the browser and
return to a plan in progress.

### 2. User has full editorial control before confirmation

Between `plan_ready` and `plan_confirmed`, the user may:
- Edit the title and description of any node (Epic, Story, Task)
- Delete any Story or Task
- Change the `ticket_type` of any node
- Reorder Stories (Tasks within a Story maintain their relative order)

The user may NOT add new nodes in v1 (adding is a future enhancement).
The UI must make this limitation clear.

### 3. LLM output is validated before storage

The planning LLM must return JSON. Before saving to `prompt_plans.plan_content`,
the service validates:
- Required top-level keys: `epic`, `stories`
- Each story has `id`, `title`, `ticket_type`, `tasks`
- Each task has `id`, `title`, `ticket_type`, `depends_on`
- No circular dependencies in `depends_on` references
- All `depends_on` values reference valid task `id` values within the plan

Validation failure → retry once → if second attempt also fails →
status: `plan_ready` with `validation_errors` populated → user sees error banner,
can trigger re-generation.

### 4. Agent config is best-effort

Agent configuration generation (project-specific overrides) must NOT block
ticket creation. If the LLM call for agent config fails or times out:
- Log the error
- Store `agent_config: null` in `prompt_plans`
- Continue to ticket creation
- The Orchestrator will use base agent prompts without project overrides

### 5. Ticket creation is transactional at the plan level

Either all tickets in the plan are created in TM, or none are (rollback).
If TM returns an error mid-creation, the service must:
- Record which tickets were created (`prompt_plans.created_ticket_ids`)
- Set status: `plan_confirmed` (not `tickets_created`)
- Surface the error to the user with a "Retry ticket creation" option
- On retry, skip already-created tickets (idempotent by checking
  `created_ticket_ids`)

### 6. Local IDs in the plan, TM IDs after creation

Plan nodes use local IDs (`story-1`, `task-1-2`) for dependency references
before tickets exist in TM. After creation, the mapping
`local_id → tm_ticket_id` is stored in `prompt_plans.ticket_id_map` (JSONB).
Dependencies are set in TM using TM ticket IDs, not local IDs.

---

## Data Model

### New table: `prompt_plans`

```sql
CREATE TABLE prompt_plans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES prompt_sessions(id) ON DELETE CASCADE,
    status          plan_status NOT NULL DEFAULT 'draft',
    plan_content    JSONB NOT NULL,          -- full plan tree
    agent_config    JSONB,                   -- project-specific agent overrides, nullable
    validation_errors JSONB,                 -- populated on LLM validation failure
    created_ticket_ids TEXT[],               -- TM ticket IDs created so far
    ticket_id_map   JSONB,                   -- { "local-id": "tm-ticket-id" }
    tm_epic_id      TEXT,                    -- TM ID of the epic ticket
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TYPE plan_status AS ENUM ('draft', 'ready', 'confirmed', 'tickets_created', 'error');
```

One `prompt_plan` per session. A new LLM call replaces the existing plan
(status resets to `draft`). History of previous plan versions is not required in v1.

### `prompt_sessions` status enum extension

```sql
ALTER TYPE session_status ADD VALUE 'planning';
ALTER TYPE session_status ADD VALUE 'plan_ready';
ALTER TYPE session_status ADD VALUE 'plan_confirmed';
ALTER TYPE session_status ADD VALUE 'tickets_created';
```

---

## Plan JSON Schema (fixed — LLM must conform to this exactly)

```json
{
  "epic": {
    "title": "string (max 200 chars)",
    "description": "string (max 1000 chars)",
    "acceptance_criteria": ["string"]
  },
  "stories": [
    {
      "id": "story-N",
      "title": "string (max 200 chars)",
      "description": "string (max 500 chars)",
      "ticket_type": "feature | bugfix | improvement",
      "tasks": [
        {
          "id": "task-N-M",
          "title": "string (max 200 chars)",
          "description": "string (max 500 chars)",
          "ticket_type": "feature | bugfix | improvement",
          "depends_on": ["task-N-K"],
          "estimated_complexity": "S | M | L | XL"
        }
      ]
    }
  ]
}
```

Constraints enforced by the service (not delegated to the LLM):
- Maximum 10 stories per plan
- Maximum 10 tasks per story (100 tasks total)
- `depends_on` references must be within the same story only (v1 limitation)
- `ticket_type` must be one of the three values; default to `feature` if missing

### Agent Config JSON Schema

```json
{
  "project_id": "string",
  "tech_stack": {
    "backend": "string",
    "frontend": "string",
    "database": "string",
    "infra": "string"
  },
  "agent_overrides": {
    "software_architect": "string | null",
    "backend": "string | null",
    "frontend": "string | null",
    "designer": "string | null",
    "code_reviewer": "string | null",
    "security_architect": "string | null",
    "autotester": "string | null",
    "devops": "string | null",
    "project_manager": "string | null",
    "project_administrator": "string | null"
  }
}
```

Each `agent_overrides` value is a short paragraph (max 300 chars) with
project-specific instructions that the Orchestrator prepends to the agent's
base system prompt in `agent_briefing.constraints`.

---

## TM Ticket Creation Strategy

### Epic ticket
- Type: `feature`
- Tag: `epic`
- Title: from `plan.epic.title`
- Description: `plan.epic.description` + formatted acceptance criteria
- No `needs-estimation` tag (plan is already estimated by definition)

### Story tickets
- Type: from `story.ticket_type`
- Title: from `story.title`
- Description: from `story.description`
- Tag: `story`
- `depends_on`: `[epic_tm_id]`

### Task tickets
- Type: from `task.ticket_type`
- Title: from `task.title`
- Description: from `task.description`
- `depends_on`: `[story_tm_id] + task.depends_on mapped to TM IDs`
- Tag: `complexity-{S|M|L|XL}`

### Creation order
1. Epic first
2. Stories in plan order (parallel creation is acceptable if TM API supports it)
3. Tasks in story order after their parent story is created

---

## Agent Config Storage

After ticket creation succeeds, the agent config is written to the
ContextDistiller Document Store via:

```
POST http://context-distiller:8004/memory/{project_id}/agent-config
Body: { agent_config object }
```

If ContextDistiller is unavailable, log and continue.
The Orchestrator reads agent config via:
```
GET http://context-distiller:8004/memory/{project_id}/agent-config
```
Returns 404 if not set → Orchestrator uses base prompts without overrides.

ContextDistiller must implement these two endpoints as part of this feature
(added to the existing `/memory/*` route group).

---

## New API Endpoints (user-input-manager backend)

```
POST /api/v1/sessions/{session_id}/plan
  Auth: Bearer (current user must own session)
  Body: {} (empty — triggers plan generation from session's approved prompt)
  Response: 202 { "plan_id": "uuid", "status": "planning" }
  Side effect: session.status → "planning"

GET /api/v1/sessions/{session_id}/plan
  Auth: Bearer
  Response: full PlanResponse (see schemas)
  404 if no plan exists

PUT /api/v1/sessions/{session_id}/plan
  Auth: Bearer
  Body: { "plan_content": { ...edited plan tree... } }
  Response: updated PlanResponse
  Validates edited content against schema before saving
  Only allowed when plan.status == "ready"

POST /api/v1/sessions/{session_id}/plan/confirm
  Auth: Bearer
  Body: {} (empty)
  Response: 202 { "status": "confirmed" }
  Triggers async ticket creation job
  Only allowed when plan.status == "ready"

GET /api/v1/sessions/{session_id}/plan/status
  Auth: Bearer
  Response: { "status": "...", "created_count": N, "total": M, "errors": [] }
  Used by frontend to poll ticket creation progress
```

---

## New Frontend Components

### `PlanningModal.tsx`
Replaces the existing `ApproveModal.tsx` flow. Shown after prompt approval.

States:
- `generating` — spinner, "Generating plan…" message, non-dismissable
- `ready` — plan tree visible, editable, confirm button enabled
- `confirming` — ticket creation in progress, progress bar
  (`X of N tickets created`)
- `done` — success state with link to TM project
- `error` — error banner with retry button

Plan tree renders:
- Epic node (title + description, editable inline)
- Story nodes (collapsible, title + type badge, editable)
- Task nodes (title + type badge + complexity badge + depends_on chip, editable)

### `AgentConfigPanel.tsx`
Collapsible panel inside `PlanningModal`, shown below the plan tree.
Displays agent config overrides in read-only mode (editing is a future feature).
Hidden if `agent_config` is null.

### State management (Zustand)
New store slice: `usePlanStore`
```typescript
interface PlanState {
  plan: Plan | null
  status: PlanStatus
  agentConfig: AgentConfig | null
  creationProgress: { created: number; total: number; errors: string[] }
  fetchPlan: (sessionId: string) => Promise<void>
  triggerGeneration: (sessionId: string) => Promise<void>
  updatePlan: (sessionId: string, content: PlanContent) => Promise<void>
  confirmPlan: (sessionId: string) => Promise<void>
  pollCreationStatus: (sessionId: string) => Promise<void>
}
```

---

## LLM Prompt Requirements

The planning LLM call uses a dedicated system prompt (separate from the
refinement loop prompt). The system prompt must instruct the model to:

1. Read the refined prompt as a software specification
2. Identify the epic (top-level goal)
3. Break it into 3–8 stories (user-facing features or domains)
4. Break each story into 2–8 tasks (implementable units)
5. Assign `ticket_type` based on nature of work
6. Assign `depends_on` only for true sequential dependencies
7. Return ONLY valid JSON conforming to the plan schema — no prose
8. Respond in the same language as the prompt

A separate LLM call (smaller context, cheaper model acceptable) generates
the agent config. It receives: refined prompt + tech stack extracted from
the plan. It returns ONLY the agent_config JSON object.

Both calls use `response_format: { "type": "json_object" }`.

---

## Technology Constraints

- Backend: Python 3.12, same FastAPI/SQLAlchemy/Alembic versions as the
  rest of user-input-manager (from monorepo `pyproject.toml`)
- New DB table via Alembic migration (new revision chained to existing head)
- Frontend: React 18, Zustand, Vitest — no new frontend dependencies
- No new Docker container, no new nginx route, no new database
- Agent config storage: ContextDistiller HTTP API (no direct MongoDB access
  from user-input-manager)

---

## Testing Requirements

### Backend (pytest, ≥ 80% coverage on new code)

Unit tests:
- Plan JSON schema validation (valid, invalid types, circular deps, too many nodes)
- Local ID → TM ID mapping
- Ticket creation order (epic → stories → tasks)
- Partial creation retry (skip already-created tickets)
- Agent config generation (success, LLM timeout → null config)

Integration tests (existing `tests/integration/` in user-input-manager):
- Full flow: POST plan → GET plan → PUT plan (edit) → POST confirm
- TM ticket creation: mocked TM client, verify call sequence and payloads
- Session status transitions at each step
- Concurrent confirm requests (second request should 409)

### Frontend (Vitest, ≥ 80% coverage on new components)

- `PlanningModal` renders all three states (generating, ready, done)
- Task editing updates Zustand store
- Confirm button disabled while creating
- Progress bar reflects `creationProgress`
- `AgentConfigPanel` hidden when `agentConfig` is null

---

## Definition of Done

1. Session status flow works end-to-end (approved → planning → plan_ready
   → plan_confirmed → tickets_created)
2. Plan is persisted in DB; user can close browser and return to plan
3. Plan tree is editable (title, description, ticket_type per node)
4. Tickets created in TM with correct hierarchy:
   Epic ticket → Story tickets (depends_on epic) → Task tickets
   (depends_on story + task dependencies)
5. Agent config written to ContextDistiller Document Store on success
6. Partial creation is retryable without duplicates
7. Old `approve_and_create_ticket` endpoint removed; no single-ticket path remains
8. All backend tests pass; ≥ 80% coverage on new modules
9. All frontend tests pass; ≥ 80% coverage on new components
10. Alembic migration runs cleanly on existing DB (`alembic upgrade head`)

---

## Principles That Must Never Be Violated

- **Plan must be persisted before shown to user.** No ephemeral plans.
- **Ticket creation is all-or-none with retry.** Never leave orphaned tickets.
- **Agent config failure never blocks ticket creation.**
- **User confirms before any ticket is created.** LLM output is never
  automatically sent to TM without user review.
- **Local IDs in plan, TM IDs after creation.** Never mix the two namespaces.
- **No direct MongoDB access from user-input-manager.** Agent config
  goes through ContextDistiller API only.
