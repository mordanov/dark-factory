# /speckit.specify — Planning Agent

## Prompt (copy-paste into Claude Code)

```
/speckit.specify

Extend user-input-manager (Prompt Studio) with a Planning Agent feature.
This adds a new phase to the session lifecycle: after a prompt is approved,
the Planning Agent decomposes it into an Epic → Stories → Tasks hierarchy,
generates project-specific agent configuration, and creates all tickets
in Ticket Manager.

Read all context files before generating the spec. Do not deviate from
the constitution. Do not propose a separate service — this is an extension
to user-input-manager only.

## Context files (read in this order)

@.specify/memory/constitution.md
@.specify/memory/service-map.md
@.specify/memory/project-map.md
@../user-input-manager/README.md
@../user-input-manager/backend/src/models/models.py
@../user-input-manager/backend/src/schemas/schemas.py
@../user-input-manager/backend/src/services/session_service.py
@../user-input-manager/backend/src/api/v1/sessions.py
@../user-input-manager/frontend/src/components/sessions/ApproveModal.tsx
@../user-input-manager/frontend/src/api/client.ts
@../user-input-manager/frontend/src/store/
@../ticket-manager/README.md
@../context-distiller/README.md

Do not go above the ../ directory level.

## What to specify

### 1. Database migration (backend)

New Alembic migration chained to the current head of user-input-manager:

a) Extend `session_status` enum with four new values:
   planning | plan_ready | plan_confirmed | tickets_created

b) New table `prompt_plans`:
   - id: UUID PK
   - session_id: UUID FK → prompt_sessions(id) ON DELETE CASCADE
   - status: plan_status enum (draft | ready | confirmed | tickets_created | error)
   - plan_content: JSONB (the full plan tree — schema in constitution)
   - agent_config: JSONB nullable (project-specific agent overrides)
   - validation_errors: JSONB nullable
   - created_ticket_ids: TEXT[] nullable (TM IDs created so far)
   - ticket_id_map: JSONB nullable ({ "local-id": "tm-ticket-id" })
   - tm_epic_id: TEXT nullable
   - created_at: TIMESTAMPTZ
   - updated_at: TIMESTAMPTZ

c) New enum type `plan_status`.

### 2. Backend — new models and schemas

New ORM model `PromptPlan` mapped to `prompt_plans`.
Pydantic schemas:
- `PlanEpic`, `PlanStory`, `PlanTask` — mirrors the JSON schema in constitution
- `PlanContent` — top-level: { epic: PlanEpic, stories: list[PlanStory] }
- `AgentConfig` — { project_id, tech_stack, agent_overrides }
- `PlanResponse` — full plan DTO for API responses
- `PlanUpdateRequest` — user edits (plan_content only)
- `PlanStatusResponse` — { status, created_count, total, errors }

### 3. Backend — PlanRepository

`src/repositories/plan_repo.py`
Methods:
- `get_by_session_id(session_id) → PromptPlan | None`
- `create(session_id, plan_content, agent_config) → PromptPlan`
- `update_content(plan, plan_content) → PromptPlan`
- `update_status(plan, status, **kwargs) → PromptPlan`
- `append_created_ticket(plan, local_id, tm_id) → PromptPlan`

### 4. Backend — PlanningLLMService

`src/services/llm/planning_llm.py`
Two async functions:

a) `generate_plan(refined_prompt: str) → PlanContent`
   - Calls OpenAI with `response_format: json_object`
   - System prompt instructs Epic → Stories → Tasks decomposition
   - Validates output against PlanContent schema
   - Retries once on validation failure
   - Raises `UpstreamError` after two failures

b) `generate_agent_config(refined_prompt: str, plan: PlanContent, project_id: str) → AgentConfig | None`
   - Separate LLM call (may use cheaper model via PLANNING_MODEL env var)
   - Returns None on any failure (never raises — best-effort)
   - System prompt extracts tech stack from plan and generates per-agent overrides

### 5. Backend — PlanValidator

`src/services/planning/validator.py`
Pure function (no I/O):
`validate_plan(data: dict) → tuple[PlanContent | None, list[str]]`

Validates:
- Required keys at all levels
- ticket_type values in allowed set
- depends_on references exist within same story
- No circular depends_on
- Story count ≤ 10, task count per story ≤ 10
- String length limits (title ≤ 200, description ≤ 500)

Returns `(parsed_plan, [])` on success or `(None, [error_messages])` on failure.

### 6. Backend — TMPlanClient

`src/services/ticket_manager/plan_client.py`
Extends the existing TicketManagerClient pattern.
Methods:

a) `create_epic(project_id, epic: PlanEpic) → str`  (returns TM ticket ID)
b) `create_story(project_id, story: PlanStory, epic_tm_id: str) → str`
c) `create_task(project_id, task: PlanTask, story_tm_id: str, dep_tm_ids: list[str]) → str`

Each method maps local plan data to TM API payload:
- No `needs-estimation` tag (plan is already scoped)
- Stories tagged `story`, tasks tagged `complexity-{S|M|L|XL}`
- `depends_on` set using TM ticket IDs

### 7. Backend — PlanningService

`src/services/planning_service.py`
Orchestrates the full planning flow:

a) `generate(session_id, user_id) → PlanResponse`
   - Verifies session exists and status == "approved"
   - Sets session.status = "planning"
   - Calls PlanningLLMService.generate_plan()
   - Calls PlanningLLMService.generate_agent_config() (best-effort)
   - Validates output via PlanValidator
   - Creates PromptPlan row in DB
   - Sets session.status = "plan_ready"
   - Returns PlanResponse

b) `update(session_id, user_id, plan_content: dict) → PlanResponse`
   - Verifies plan.status == "ready"
   - Validates updated content via PlanValidator
   - Updates plan_content in DB
   - Returns updated PlanResponse

c) `confirm(session_id, user_id) → None`
   - Verifies plan.status == "ready"
   - Sets plan.status = "confirmed", session.status = "plan_confirmed"
   - Calls _create_tickets() in background (FastAPI BackgroundTasks)

d) `_create_tickets(session_id) → None`  (background task)
   - Creates epic → stories → tasks in TM (in order, tracking ids)
   - Updates plan.ticket_id_map incrementally
   - On partial failure: records error, retains created_ticket_ids for retry
   - On full success: sets plan.status = "tickets_created",
     session.status = "tickets_created"
   - Calls _store_agent_config() (best-effort, never blocks)

e) `_store_agent_config(project_id, agent_config) → None`
   - POST to ContextDistiller /memory/{project_id}/agent-config
   - Timeout 10s, no retry, failure only logged

f) `get_creation_status(session_id, user_id) → PlanStatusResponse`

### 8. Backend — API endpoints

`src/api/v1/planning.py` (new router, prefix `/sessions`)

```
POST   /sessions/{session_id}/plan           → trigger generation (202)
GET    /sessions/{session_id}/plan           → get plan (200 or 404)
PUT    /sessions/{session_id}/plan           → update plan content (200)
POST   /sessions/{session_id}/plan/confirm   → confirm and create tickets (202)
GET    /sessions/{session_id}/plan/status    → poll creation progress (200)
```

Register router in `src/main.py` alongside existing routers.

**Remove** the existing `POST /sessions/{id}/approve` endpoint and the
`approve_and_create_ticket` method from SessionService. Update any
references to it in tests and client code.

### 9. ContextDistiller extension

Add two endpoints to context-distiller service:
```
POST /memory/{project_id}/agent-config
  Body: AgentConfig JSON
  Response: 201 { "project_id": "...", "stored_at": "ISO8601" }

GET /memory/{project_id}/agent-config
  Response: AgentConfig JSON or 404
```

Stored in MongoDB collection `agent_configs`, document `_id = project_id`.
These endpoints follow the same auth pattern as existing `/memory/*` routes.

### 10. Frontend — Zustand store

`src/store/planStore.ts`

```typescript
interface PlanState {
  plan: Plan | null
  planStatus: PlanStatus | null
  agentConfig: AgentConfig | null
  creationProgress: { created: number; total: number; errors: string[] }
  isGenerating: boolean
  isConfirming: boolean
  error: string | null

  triggerGeneration: (sessionId: string) => Promise<void>
  fetchPlan: (sessionId: string) => Promise<void>
  updateNode: (sessionId: string, nodeId: string, updates: Partial<PlanNode>) => Promise<void>
  confirmPlan: (sessionId: string) => Promise<void>
  pollCreationStatus: (sessionId: string) => void  // starts polling, auto-stops on done/error
  reset: () => void
}
```

### 11. Frontend — API client extension

Add to `src/api/client.ts`:

```typescript
export const planningApi = {
  trigger:       (sessionId: string) => api.post(`/sessions/${sessionId}/plan`),
  get:           (sessionId: string) => api.get<PlanResponse>(`/sessions/${sessionId}/plan`),
  update:        (sessionId: string, content: PlanContent) =>
                   api.put<PlanResponse>(`/sessions/${sessionId}/plan`, { plan_content: content }),
  confirm:       (sessionId: string) => api.post(`/sessions/${sessionId}/plan/confirm`),
  getStatus:     (sessionId: string) => api.get<PlanStatusResponse>(`/sessions/${sessionId}/plan/status`),
}
```

### 12. Frontend — PlanningModal component

`src/components/sessions/PlanningModal.tsx`

Four visual states driven by Zustand store:

**generating state:**
- Full-screen overlay (non-dismissable)
- Spinner + "Generating plan…" message
- Estimated time note ("This may take 20–30 seconds")

**ready state:**
- Plan tree: Epic at top, Stories collapsible, Tasks nested
- Each node: inline-editable title (click to edit), type badge, complexity badge
- Story: collapse/expand toggle, task count
- Task: depends_on shown as chips (read-only in v1)
- "Regenerate" button (top right, triggers new LLM call, replaces current plan)
- AgentConfigPanel (collapsible, below tree)
- "Confirm plan & create tickets" primary button (bottom)
- "Cancel" ghost button (returns to session detail, session stays "plan_ready")

**confirming state:**
- Plan tree visible but non-editable (greyed out)
- Progress bar: "Creating tickets: X / N"
- List of created tickets appearing as they complete
- Non-dismissable

**done state:**
- Success icon
- "N tickets created in [Project Name]"
- Link to TM project (opens in new tab)
- "Back to sessions" button

**error state:**
- Error banner with specific message
- "Retry" button (retries only uncreated tickets)
- Already-created tickets listed as succeeded

### 13. Frontend — AgentConfigPanel component

`src/components/sessions/AgentConfigPanel.tsx`

Collapsible panel, collapsed by default.
Title: "Agent configuration for this project"
Content: table of agent name + override text (or "—" if null).
Note: "These instructions will guide each agent's behaviour for this project."
Hidden entirely if agentConfig is null.

### 14. Frontend — Session flow update

In `SessionDetailPage.tsx`:
- Remove the "Approve & create ticket" button and ApproveModal import
- When `session.status === "approved"`: show "Generate Plan" primary button
- Clicking opens PlanningModal (which auto-triggers generation on mount)
- When `session.status === "tickets_created"`: show success banner
  "Plan executed — N tickets created" with TM link

Remove `ApproveModal.tsx` entirely.

### 15. i18n additions

Add to `en.json` and `ru.json`:

```json
"planning": {
  "generate_plan": "Generate plan",
  "generating": "Generating plan…",
  "generating_hint": "This may take 20–30 seconds",
  "plan_title": "Work breakdown",
  "epic_label": "Epic",
  "story_label": "Story",
  "task_label": "Task",
  "complexity": "Complexity",
  "depends_on": "Depends on",
  "confirm_plan": "Confirm plan & create tickets",
  "regenerate": "Regenerate",
  "creating_tickets": "Creating tickets",
  "tickets_created": "tickets created",
  "view_in_tm": "View in Ticket Manager",
  "agent_config_title": "Agent configuration for this project",
  "agent_config_hint": "These instructions guide each agent's behaviour",
  "retry_creation": "Retry ticket creation",
  "cancel": "Cancel",
  "error_generation": "Failed to generate plan. Please try again.",
  "error_validation": "Plan structure is invalid",
  "error_creation": "Some tickets could not be created"
}
```

Russian translations follow the same keys.

## Constraints from constitution (enforce all)

- Plan persisted in DB before shown to user — no ephemeral plans
- User must confirm before any ticket is created
- Ticket creation is all-or-none with idempotent retry
- Agent config failure never blocks ticket creation
- depends_on references scoped to same story only (v1)
- Maximum 10 stories, 10 tasks per story
- No direct MongoDB access from user-input-manager — agent config via
  ContextDistiller API only
- `POST /sessions/{id}/approve` endpoint removed entirely
- No new Docker container, no new nginx route

## New environment variables

Add to user-input-manager backend settings:
```
PLANNING_MODEL=gpt-4o-mini     # model for agent config generation (cheaper)
CONTEXT_DISTILLER_BASE_URL=http://context-distiller:8004
CONTEXT_DISTILLER_TIMEOUT_SECONDS=10
```

## Out of scope for this spec

- Adding new nodes to the plan (user can only edit/delete)
- Cross-story task dependencies
- Re-planning after tickets are created
- Keycloak auth changes
- Any changes to orchestrator, agent-tools, or agent-tools-catalog
- Ticket Manager internal changes beyond what TMPlanClient calls
```

---

## Setup

```bash
cd services/user-input-manager

# Place constitution
cp /path/to/planning-agent-constitution.md .specify/memory/constitution.md

# Create service-map for this repo
cat > .specify/memory/service-map.md << 'EOF'
# user-input-manager — Current State

## Backend
- FastAPI, Python 3.12, PostgreSQL
- Sessions table: prompt_sessions (in_progress → approved)
- Iterations table: prompt_iterations
- Single ticket created on approve: POST /sessions/{id}/approve
- TM client: src/services/ticket_manager/client.py
- LLM service: src/services/llm/openai_service.py (refinement)
- Auth: JWT, local mode

## Frontend
- React 18, Zustand, TypeScript, Vite
- Auth store: src/store/auth.ts (Zustand, tokens in memory)
- Routing: /sessions, /sessions/:id, /queue, /admin
- ApproveModal.tsx: current single-ticket creation UI (to be replaced)
- Components: SessionListPage, SessionDetailPage, NewSessionModal, ApproveModal

## Sibling services
- ticket-manager: at ../ticket-manager/ — receives ticket creation calls
- context-distiller: at ../context-distiller/ — receives agent-config storage calls
- orchestrator: at ../orchestrator/ — reads agent-config from context-distiller
EOF

# Create project-map
cat > .specify/memory/project-map.md << 'EOF'
# Sibling projects (read these, do not go above ../)

- ../ticket-manager/     — TM API contract (POST /projects/{id}/tickets etc.)
- ../orchestrator/       — reads agent_briefing.constraints (agent overrides)
- ../context-distiller/  — stores agent-config at /memory/{project_id}/agent-config
EOF

# Run specify
# Then paste the prompt above
/speckit.specify
```
