# Feature Specification: Planning Agent for Prompt Studio

**Feature Branch**: `003-planning-agent`
**Created**: 2026-06-23
**Status**: Draft
**Input**: User description: "Extend user-input-manager (Prompt Studio) with a Planning Agent feature. After a prompt is approved, the Planning Agent decomposes it into an Epic → Stories → Tasks hierarchy, generates project-specific agent configuration, and creates all tickets in Ticket Manager."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Plan Generation (Priority: P1)

After a user has refined and approved their prompt in Prompt Studio, they click "Generate Plan."
The system decomposes the approved prompt into a structured work breakdown — one Epic, up to ten
Stories each containing up to ten Tasks — and presents the full plan tree on screen. The user's
plan is durably saved so they can close the browser and return to find it intact.

**Why this priority**: Without plan generation there is no planning feature. All downstream
capabilities (editing, confirmation, ticket creation) depend on this working first.

**Independent Test**: A session with `status = approved` exists. The user clicks "Generate Plan."
After 20–30 seconds the screen shows an Epic with at least one Story and at least one Task.
Closing and reopening the browser shows the same plan without regenerating.

**Acceptance Scenarios**:

1. **Given** a session with `status = approved`, **When** the user clicks "Generate Plan,"
   **Then** the UI shows a non-dismissable generating overlay and, within 60 seconds,
   replaces it with the full plan tree.
2. **Given** the plan has been generated, **When** the user closes the browser tab and
   returns to the session, **Then** the plan is shown in its last-saved state without
   a new generation being triggered.
3. **Given** the plan generation service is temporarily unavailable, **When** the user
   clicks "Generate Plan," **Then** an error banner is shown and a "Try again" option
   is offered; the session status remains `approved` so the user can retry.

---

### User Story 2 - Plan Review and Edit (Priority: P2)

After the plan is generated, the user reviews the work breakdown. They can expand and collapse
Stories, edit any node's title or description inline, and delete Stories or Tasks that are not
needed. When satisfied, they click "Confirm plan & create tickets." Until they confirm, nothing
is submitted to Ticket Manager.

**Why this priority**: The confirmation gate is a constitution requirement. Users must be able
to adjust an AI-generated plan before it triggers real work.

**Independent Test**: A plan is in `ready` state. The user edits a Story title inline and
deletes one Task. The edited plan is saved. The user then clicks "Confirm" — no tickets exist
in TM yet. After confirming, the plan enters the `confirmed` state.

**Acceptance Scenarios**:

1. **Given** a plan in `ready` state, **When** the user clicks a Story title and types a new
   value, **Then** the change is saved to the plan and visible after page reload.
2. **Given** a plan in `ready` state, **When** the user deletes a Task, **Then** it disappears
   from the tree and is not present after page reload.
3. **Given** a plan in `ready` state, **When** the user clicks "Confirm plan & create tickets,"
   **Then** no tickets are created until after the confirmation response; the plan transitions
   to `confirmed` state immediately.
4. **Given** a plan in `ready` state, **When** the user clicks "Cancel," **Then** the modal
   closes, the session remains in `plan_ready` status, and the plan is preserved for a future
   return.

---

### User Story 3 - Ticket Creation Progress and Recovery (Priority: P3)

After the user confirms the plan, the system creates all tickets in Ticket Manager
(Epic → Stories → Tasks, in dependency order) and shows live creation progress.
If creation partially fails, the user can retry and only uncreated tickets are attempted again.

**Why this priority**: Ticket creation is the final deliverable. Recovery from partial failures
prevents operators from manually reconciling partially-created ticket hierarchies.

**Independent Test**: A confirmed plan with 1 Epic, 2 Stories, 4 Tasks is submitted.
The progress bar advances as each ticket is created. On completion, the screen shows
"7 tickets created" and a link to the TM project. Simulating a TM failure after 3 tickets:
the screen shows "3 / 7 tickets created" with a "Retry" button. After retry, the remaining
4 tickets are created without duplicates.

**Acceptance Scenarios**:

1. **Given** a confirmed plan, **When** ticket creation begins, **Then** a non-dismissable
   progress indicator shows "Creating tickets: X / N" incrementing as each ticket is created.
2. **Given** all tickets are created successfully, **When** the last ticket is confirmed,
   **Then** the screen shows a success state with a count of created tickets and a link to
   the TM project.
3. **Given** ticket creation fails partway through, **When** the error is shown,
   **Then** a "Retry" button is available; clicking it creates only the tickets not yet
   created, without duplicates.
4. **Given** a session that has reached `tickets_created` status, **When** the user
   views the session detail, **Then** a permanent success banner shows the ticket count
   and TM project link.

---

### User Story 4 - Agent Configuration Preview (Priority: P4)

While reviewing the plan, the user can expand an "Agent configuration" section to see
the project-specific instructions that will guide each Dark Factory agent's behaviour.
This is an informational panel — the user cannot edit it in v1.

**Why this priority**: The agent config is best-effort and purely informational for the user.
All core user journeys are complete with US1–US3; this story only adds transparency.

**Independent Test**: A generated plan includes non-null `agent_config`. The "Agent configuration
for this project" panel is visible (collapsed by default) and expands to show a table of agent
names and their overrides.

**Acceptance Scenarios**:

1. **Given** agent configuration was generated successfully, **When** the plan is shown,
   **Then** a collapsible "Agent configuration" panel exists below the plan tree.
2. **Given** agent configuration generation failed, **When** the plan is shown,
   **Then** the agent configuration panel is hidden entirely; the plan and confirm button
   are unaffected.

---

### Edge Cases

- What happens if plan generation succeeds but the database write fails? The plan is NOT
  shown to the user; an error banner is shown. The session remains `approved` for retry.
- What happens if the user edits a plan that is already in `confirmed` or later state?
  Edit endpoints return 409 Conflict; the plan tree is shown as read-only.
- What happens if ticket creation is already in progress when the user hits the retry button?
  The retry endpoint is idempotent — if creation is still running the response returns the
  current progress without starting a second job.
- What happens if the Ticket Manager project does not exist yet?
  For `new_project` sessions, the TM project is created during the approval flow before
  plan generation is triggered. If project creation previously failed, the user must retry
  from the approve step.
- What happens when the plan has 10 stories × 10 tasks plus the epic (101 nodes)?
  The validator enforces the 10/10 limit; any plan exceeding this is rejected with a
  validation error before being shown to the user.
- What happens if the user clicks "Regenerate" while a plan already exists?
  A new LLM call is made, the existing plan is replaced, and plan status resets to `draft`
  then `ready`. Already-created tickets (if any) are NOT deleted.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: After a prompt session reaches `approved` status, the user MUST be able to
  trigger plan generation from the session detail view.
- **FR-002**: A generated plan MUST be persisted in the database before it is displayed
  to the user. The session retains `approved` status and an error is shown if DB persistence
  fails.
- **FR-003**: The system MUST NOT create any ticket in Ticket Manager until the user
  explicitly confirms the plan via the confirm action.
- **FR-004**: The system MUST allow the user to edit any plan node's title and description,
  and to delete any Story or Task, while the plan is in `ready` state.
- **FR-005**: Adding new nodes (Stories or Tasks) to a plan is out of scope for v1.
- **FR-006**: The system MUST create all tickets in Ticket Manager as an atomic operation
  at the plan level: either all tickets are eventually created, or the partial state is
  retryable. Retry MUST NOT create duplicate tickets.
- **FR-007**: The plan MUST model an Epic → Stories → Tasks hierarchy. The Epic represents
  the approved prompt as a whole; Stories represent major deliverable slices; Tasks represent
  individual implementation units within a Story.
- **FR-008**: Tasks MUST support `depends_on` relationships to other Tasks within the same
  Story. Cross-story dependencies are out of scope for v1.
- **FR-009**: The system MUST validate a plan before storing it: required fields present,
  `ticket_type` values from allowed set, `depends_on` references exist within the same story,
  no circular dependencies, Story count ≤ 10, Task count per Story ≤ 10, title ≤ 200 chars,
  description ≤ 500 chars.
- **FR-010**: Agent configuration generation MUST NOT block or delay ticket creation.
  If it fails for any reason, ticket creation proceeds without it.
- **FR-011**: After successful ticket creation, the generated agent configuration MUST be
  stored in the ContextDistiller service for the project. `user-input-manager` MUST NOT
  write to any database other than its own; all agent config storage goes via the
  ContextDistiller HTTP API.
- **FR-012**: The system MUST expose a creation-status polling endpoint so the frontend
  can display live progress without requiring websockets.
- **FR-013**: The `POST /sessions/{id}/approve` endpoint and the single-ticket creation
  flow MUST be removed and replaced entirely by this new planning flow. The approval action
  now transitions the session to `approved` and no longer creates a ticket directly.
- **FR-014**: The session lifecycle MUST extend with four new status values:
  `planning` (generation in progress), `plan_ready` (plan generated, awaiting user review),
  `plan_confirmed` (user confirmed, ticket creation started or pending),
  `tickets_created` (all tickets created successfully).
- **FR-015**: The system MUST allow the user to regenerate the plan (new LLM call replacing
  the existing plan) at any point before confirmation. Regeneration resets plan status to
  `draft` → `ready`.

### Key Entities

- **PromptPlan**: Represents the generated work breakdown for one session. Tracks the full
  plan tree (Epic + Stories + Tasks as structured data), plan lifecycle status, agent
  configuration, ticket ID mapping, and partial-creation state for retry.
- **PlanEpic**: The top-level deliverable node. Has title, description, and ticket type.
- **PlanStory**: A major deliverable slice within the Epic. Contains one or more Tasks.
  Tagged as a story in Ticket Manager.
- **PlanTask**: An individual implementation unit within a Story. Has complexity (S/M/L/XL),
  ticket type, and optional `depends_on` list referencing sibling Tasks by local ID.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After clicking "Generate Plan," a valid plan tree is displayed within 60 seconds
  in 95% of cases (p95 of plan generation calls).
- **SC-002**: A user who closes the browser mid-session and returns finds their plan unchanged
  in 100% of cases — no data loss, no re-generation triggered.
- **SC-003**: Zero tickets are created in Ticket Manager before the user explicitly confirms
  the plan in 100% of cases — the confirmation gate is never bypassed.
- **SC-004**: After the user confirms the plan, the first ticket appears in Ticket Manager
  within 15 seconds.
- **SC-005**: A partial-failure retry creates only the missing tickets — zero duplicates
  in 100% of cases.
- **SC-006**: Agent configuration failure does not affect ticket creation success rate —
  all plans confirm and create tickets regardless of whether agent config generation succeeds.
- **SC-007**: The session detail view correctly reflects the current plan status
  (`approved`, `planning`, `plan_ready`, `plan_confirmed`, `tickets_created`) without
  a page refresh, using status polling.

## Assumptions

- `user-input-manager` is the Prompt Studio service. This feature is an extension to that
  service — no new service is introduced.
- Approved sessions always have a `tm_project_id` by the time plan generation is triggered.
  For `new_project` sessions this is set during the approval step.
- The Ticket Manager API supports creating Epic, Story, and Task ticket types with a
  `depends_on` field referencing other TM ticket IDs.
- The ContextDistiller service exposes HTTP endpoints for storing and retrieving per-project
  agent configuration. `user-input-manager` calls those endpoints; it does not write to any
  shared database directly.
- A single user owns each session; multi-user collaborative editing of a plan is out of scope.
- Keycloak integration is out of scope; the local JWT auth mode is used throughout.
- Any changes to Orchestrator, agent-tools, or agent-tools-catalog are out of scope.
- Re-planning after tickets are already created (status = `tickets_created`) is out of scope for v1.
- The plan generation LLM call may take up to 60 seconds; the frontend must handle this with
  a non-dismissable overlay rather than a short timeout.
- The existing `ApproveModal.tsx` component and its backend `approve_and_create_ticket` endpoint
  are removed as part of this feature; the new planning flow replaces them entirely.
