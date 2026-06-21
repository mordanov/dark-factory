# Feature Specification: Workflow Orchestrator Integration Extensions

**Feature Branch**: `005-orchestrator-extensions`
**Created**: 2026-06-21
**Status**: Draft
**Input**: User description: "Add FSM fields, polling endpoints, audit log, override, tag management, and batch status lookup for Workflow Orchestrator integration"

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Orchestrator Polls for Pending Tickets (Priority: P1)

The Workflow Orchestrator service periodically polls the Ticket Manager to discover tickets that need processing. It retrieves only tickets that have changed since the last run, minimizing redundant work.

**Why this priority**: This is the core integration loop. Without it, the orchestrator cannot function at all. All other features depend on the orchestrator being able to discover work.

**Independent Test**: Can be tested by calling the pending-tickets endpoint and verifying it returns only tickets not yet processed or updated since last processing.

**Acceptance Scenarios**:

1. **Given** tickets exist with various states, **When** the orchestrator calls the pending endpoint, **Then** only tickets where `fsm_status ≠ done` AND (`last_orchestrator_run` is null OR `updated_at > last_orchestrator_run`) are returned.
2. **Given** 150 pending tickets exist, **When** the orchestrator calls with `limit=20`, **Then** 20 tickets are returned along with a pagination cursor to retrieve the next page.
3. **Given** multiple projects exist, **When** the orchestrator calls with `project_id` filter, **Then** only tickets from that project are returned.
4. **Given** no pending tickets exist, **When** the orchestrator polls, **Then** an empty list is returned with `total_pending: 0`.

---

### User Story 2 — Orchestrator Updates FSM State on a Ticket (Priority: P1)

After processing a ticket, the orchestrator updates the ticket's FSM state (e.g., advancing it from `triage` to `specification`, or marking it `BLOCKED` with a reason) without touching human-managed fields like title or description.

**Why this priority**: The FSM state update is the primary write operation of the orchestrator. Without it, the orchestrator cannot record its decisions.

**Independent Test**: Call the FSM update endpoint and verify the FSM fields change while native TM fields remain unchanged.

**Acceptance Scenarios**:

1. **Given** a ticket in `triage` state, **When** the orchestrator patches FSM fields with `fsm_status: "specification"` and `assigned_agent: "agent-42"`, **Then** the ticket reflects the new FSM values and `title`/`description` are unchanged.
2. **Given** a ticket being blocked, **When** the orchestrator patches with `fsm_status: "BLOCKED"` and `blocked_reason: "Missing acceptance criteria"`, **Then** the ticket shows `BLOCKED` status with the reason stored.
3. **Given** a non-existent ticket ID, **When** the orchestrator attempts a FSM patch, **Then** a 404 error is returned.
4. **Given** a request from a non-service account, **When** attempting the FSM patch endpoint, **Then** a 403 error is returned.

---

### User Story 3 — Orchestrator Writes and Reads Audit Log Events (Priority: P1)

Every decision the orchestrator makes (advance, block, assign, wait) is recorded as an immutable audit event linked to the ticket. Humans can inspect this log to understand why a ticket is in its current state.

**Why this priority**: Audit trail is critical for debugging orchestrator behavior and maintaining accountability for automated decisions. Required by the Dark Factory compliance model.

**Independent Test**: Post an audit event and then retrieve the audit log to verify the event was recorded with correct fields.

**Acceptance Scenarios**:

1. **Given** a ticket, **When** the orchestrator posts an `ADVANCE` event with `from_state`, `to_state`, and `details`, **Then** a 201 response is returned with the new audit entry ID.
2. **Given** multiple audit events exist for a ticket, **When** the audit log is requested, **Then** all events are returned in chronological order with all fields intact.
3. **Given** an audit log request for a ticket with no events, **When** the endpoint is called, **Then** an empty entries array is returned.

---

### User Story 4 — Human Admin Overrides a Failed Gate (Priority: P2)

A project admin manually marks a ticket so the orchestrator will skip a failed quality gate on the next polling cycle. This is used for urgent hotfixes or when a gate failure is known to be acceptable.

**Why this priority**: Necessary for operational flexibility, but not blocking for initial orchestrator function. The orchestrator can operate without this; humans would be stuck without a workaround for gate failures.

**Independent Test**: Set override on a ticket, then verify the orchestrator's next poll cycle processes the ticket despite the failed gate; confirm override resets after processing.

**Acceptance Scenarios**:

1. **Given** a ticket blocked by a failed gate, **When** an admin posts an override with reason text, **Then** the ticket's `override` flag is set to `true` and `override_reason` is stored.
2. **Given** a non-admin user, **When** attempting to set an override, **Then** a 403 error is returned.
3. **Given** a ticket with `override: true`, **When** the orchestrator processes it and clears the flag, **Then** `override` returns to `false`.

---

### User Story 5 — Orchestrator Checks Dependency Statuses in Bulk (Priority: P2)

Before advancing a ticket, the orchestrator checks whether all its dependency tickets are in `done` state. It fetches statuses for multiple ticket IDs in one request rather than making N individual calls.

**Why this priority**: Dependency checking is a common orchestrator operation. The batch endpoint prevents request fan-out that would degrade performance at scale.

**Independent Test**: Post a batch request with 3 ticket IDs and verify each ticket's `fsm_status` and title are returned in a single response.

**Acceptance Scenarios**:

1. **Given** three tickets with different FSM states, **When** the orchestrator posts a batch status request with their IDs, **Then** a map of `ticket_id → { fsm_status, title }` (plus `blocked_reason` for BLOCKED tickets) is returned.
2. **Given** a batch request containing an ID that does not exist, **When** the endpoint is called, **Then** the missing ID is absent from the response map (no error).
3. **Given** an empty `ticket_ids` array, **When** the endpoint is called, **Then** an empty statuses map is returned.

---

### User Story 6 — Orchestrator Manages Tags Without Overwriting Ticket (Priority: P2)

The orchestrator needs to add or remove specific tags (e.g., `needs-estimation`) from a ticket without sending the full ticket payload, avoiding race conditions with other concurrent writers.

**Why this priority**: Tag-only updates are needed for workflow signaling. The targeted endpoint prevents accidental overwrites of other fields.

**Independent Test**: Add a tag via the endpoint and verify only that tag is added; remove a tag and verify only that tag is removed, with other tags unchanged.

**Acceptance Scenarios**:

1. **Given** a ticket with tags `["bug", "urgent"]`, **When** the tag endpoint is called with `add: ["needs-estimation"]`, **Then** the ticket now has tags `["bug", "urgent", "needs-estimation"]`.
2. **Given** a ticket with tags `["needs-estimation", "urgent"]`, **When** the tag endpoint is called with `remove: ["needs-estimation"]`, **Then** the ticket now has tags `["urgent"]`.
3. **Given** adding a tag that already exists, **When** the endpoint is called, **Then** the tag is not duplicated and a 200 is returned.
4. **Given** removing a tag that does not exist, **When** the endpoint is called, **Then** no error is raised and the existing tags are unchanged.

---

### User Story 7 — Retrieve Full Ticket with FSM Fields (Priority: P3)

The orchestrator (or a debugging human) retrieves a single ticket's complete data including all FSM fields in one call.

**Why this priority**: Useful for detailed inspection but the orchestrator can construct the full picture from other endpoints in a pinch.

**Independent Test**: Request a ticket via the `/full` endpoint and verify all FSM fields are present alongside native ticket fields.

**Acceptance Scenarios**:

1. **Given** a ticket with FSM fields set, **When** the full endpoint is called, **Then** all FSM fields (`fsm_status`, `blocked_reason`, `brainstorm_round`, `assigned_agent`, `override_reason`, `last_orchestrator_run`, `orchestrator_errors`) are included in the response.
2. **Given** a ticket with no FSM fields set, **When** the full endpoint is called, **Then** FSM fields are present with their null/zero defaults.

---

### User Story 8 — List Tickets with FSM Status (Priority: P3)

The existing ticket-list endpoint can optionally include FSM fields when requested via a query parameter, giving dashboards and admin tools a unified view.

**Why this priority**: Convenience enhancement; existing list endpoint remains fully functional without it.

**Independent Test**: Call the list endpoint with `include_fsm=true` and verify FSM fields appear on each ticket object.

**Acceptance Scenarios**:

1. **Given** a project with tickets, **When** the list endpoint is called with `include_fsm=true`, **Then** each ticket in the response includes all FSM fields.
2. **Given** the same list endpoint, **When** called without `include_fsm`, **Then** the response is identical to the current behavior (no FSM fields, no regressions).

---

### Edge Cases

- What happens when the orchestrator sends a `brainstorm_round` increment concurrently with a human edit? (Last-write-wins on FSM fields is acceptable; FSM patch only touches FSM fields.)
- How does the pending endpoint behave when `updated_at` and `last_orchestrator_run` are identical to the millisecond? (Ticket is not considered pending — strict `>` comparison.)
- What if `orchestrator_errors` grows unbounded? (Assume the orchestrator is responsible for trimming; TM stores whatever is sent.)
- What if a batch status request contains duplicate IDs? (Deduplicated in the response map.)
- What if the override endpoint is called on a ticket already processing? (Override flag is set; orchestrator reads it on next cycle.)

---

## Requirements *(mandatory)*

### Functional Requirements

**FSM Model**

- **FR-001**: The ticket data model MUST be extended with the following FSM fields: `fsm_status` (enum), `blocked_reason` (string or null), `brainstorm_round` (integer, default 0), `assigned_agent` (string or null), `override_reason` (string or null), `last_orchestrator_run` (datetime or null), `orchestrator_errors` (string array or null).
- **FR-002**: The `fsm_status` field MUST accept only these values: `backlog`, `triage`, `specification`, `architecture_review`, `implementation`, `code_review`, `security_review`, `testing`, `release`, `done`, `BLOCKED`.
- **FR-003**: Existing tickets MUST default to `fsm_status: null` (or `backlog`) and `brainstorm_round: 0` on migration; all other new FSM fields default to null.

**FSM Update Endpoint**

- **FR-004**: The system MUST provide a `PATCH /api/projects/{project_id}/tickets/{ticket_id}/fsm` endpoint that updates only FSM fields without touching native ticket fields (title, description, native status, etc.).
- **FR-005**: The FSM patch endpoint MUST accept partial updates (only the fields provided in the body are changed).
- **FR-006**: The FSM patch endpoint MUST return the full updated ticket object on success (200).
- **FR-007**: The FSM patch endpoint MUST be restricted to the Dark Factory service account.

**Polling Endpoint**

- **FR-008**: The system MUST provide a `GET /api/orchestrator/pending` endpoint returning tickets where `fsm_status ≠ done` AND (`last_orchestrator_run` is null OR `updated_at > last_orchestrator_run`).
- **FR-009**: The pending endpoint MUST support optional `project_id` query filter, `limit` (default 20, max 100), and `after_cursor` pagination parameter.
- **FR-010**: The pending endpoint response MUST include `tickets`, `next_cursor`, and `total_pending` fields.
- **FR-011**: Each ticket in the pending response MUST include native fields (id, project_id, title, description, ticket_type, tags, status, created_at, updated_at), all FSM fields, and dependency/subtask IDs.

**Full Ticket Endpoint**

- **FR-012**: The system MUST provide a `GET /api/projects/{project_id}/tickets/{ticket_id}/full` endpoint that returns the complete ticket including all FSM fields.

**Audit Log**

- **FR-013**: The system MUST provide a `POST /api/tickets/{ticket_id}/audit` endpoint that creates an immutable audit event with fields: `event`, `actor`, `from_state`, `to_state`, `details`, `timestamp`.
- **FR-014**: The system MUST provide a `GET /api/tickets/{ticket_id}/audit` endpoint returning all audit events for a ticket in chronological order.
- **FR-015**: Audit events MUST be stored in a separate data store (not as ticket comments).

**Override Endpoint**

- **FR-016**: The system MUST provide a `POST /api/projects/{project_id}/tickets/{ticket_id}/override` endpoint accepting `override: true` and `override_reason` string.
- **FR-017**: The override endpoint MUST be restricted to users with the `admin` role in the Ticket Manager.
- **FR-018**: The `override` field MUST be reset to `false` after the orchestrator acknowledges it (via FSM patch clearing the field).

**Tag Management Endpoint**

- **FR-019**: The system MUST provide a `POST /api/projects/{project_id}/tickets/{ticket_id}/tags` endpoint accepting `add` (string array) and `remove` (string array) and applying the delta atomically.
- **FR-020**: Adding a tag that already exists MUST be idempotent (no duplicate, no error).
- **FR-021**: Removing a tag that does not exist MUST be idempotent (no error).

**Batch FSM Status Endpoint**

- **FR-022**: The system MUST provide a `POST /api/v1/tickets/batch-fsm-status` endpoint accepting a `ticket_ids` array and returning a map of `ticket_id → { fsm_status, title, blocked_reason? }`.
- **FR-023**: Unknown ticket IDs in the batch request MUST be silently omitted from the response.

**List Extension**

- **FR-024**: The existing `GET /api/projects/{project_id}/tickets` endpoint MUST support an `include_fsm=true` query parameter that appends all FSM fields to each ticket in the response without changing default behavior.

**Authorization**

- **FR-025**: All new endpoints MUST accept the same Bearer token mechanism used by the existing Ticket Manager API.
- **FR-026**: The Dark Factory service account (`TICKET_MANAGER_SERVICE_EMAIL`) MUST have permission to call all new endpoints.
- **FR-027**: The `/override` endpoint MUST additionally require the `admin` role.
- **FR-028**: If `TICKET_MANAGER_SERVICE_EMAIL` is not set in the environment, the service account check MUST fail closed: only users with the `admin` role are granted access to service-account-protected endpoints. The system MUST NOT reject all requests or raise a 500 error due to a missing env var.

---

### Key Entities

- **Ticket (extended)**: Existing ticket entity augmented with FSM fields. FSM fields are managed exclusively by the orchestrator service; native fields remain human-managed.
- **FSM Status**: An enumerated state machine value representing where a ticket sits in the Dark Factory development pipeline.
- **Audit Event**: An immutable record of a single orchestrator action on a ticket. Attributes: id, ticket_id, event type, actor, from_state, to_state, details, timestamp. Stored separately from ticket comments.
- **Override Flag**: A transient boolean on the ticket (plus reason string) that signals the orchestrator to bypass a failed gate. Resets after use.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The orchestrator can complete a full polling cycle (discover pending → update FSM → write audit → check dependencies) for 50 tickets in under 10 seconds under normal load.
- **SC-002**: The pending endpoint returns accurate results — zero false negatives (no pending ticket is missed) and zero false positives (no already-processed, unchanged ticket appears) across all test scenarios.
- **SC-003**: All FSM patch operations are atomic: concurrent FSM updates and human edits never corrupt native ticket fields.
- **SC-004**: The audit log preserves 100% of orchestrator events with no data loss, and the full log for any ticket is retrievable within 2 seconds.
- **SC-005**: Tag add/remove operations are idempotent: calling the endpoint twice with the same payload produces the same result with no errors.
- **SC-006**: All new endpoints return appropriate 4xx errors (400, 403, 404) for invalid inputs, unauthorized access, or missing resources, with descriptive error messages.
- **SC-007**: The existing ticket-list endpoint behaves identically with and without `include_fsm=true` — no regressions in response shape, pagination, or performance for requests without the parameter.

---

## Clarifications

### Session 2026-06-21

- Q: If `TICKET_MANAGER_SERVICE_EMAIL` is missing from the environment, should the endpoint fail closed or raise a server configuration error? → A: Fail closed — treat as "no service account configured"; only admin role passes the check.
- Q: Which agent owns implementation vs. test vs. review tasks in the multi-agent run? → A: Role-aligned: backend agent implements (T001–T036), autotester writes integration tests (T037–T038), code-reviewer runs final validation (T039–T041).
- Q: Should the multi-agent run target MVP only or implement all 41 tasks? → A: All 41 tasks — full scope including P2 and P3 stories.
- Q: What Brainstorm project ID should agents use for this feature run? → A: ticket-manager-extensions-1
- Q: Which path should the batch FSM status endpoint use — versioned `/api/v1/` or unversioned per original spec doc? → A: `/api/v1/tickets/batch-fsm-status` (versioned, consistent with all existing endpoints).

---

## Assumptions

- The Ticket Manager uses a persistent relational or document database that supports schema migration to add new fields to existing ticket records.
- Existing tickets that predate this feature will receive null/default FSM field values without data loss.
- The Dark Factory service account is already provisioned in the Ticket Manager's user system and can be identified by the `TICKET_MANAGER_SERVICE_EMAIL` environment variable.
- The `admin` role already exists in the Ticket Manager's authorization system; no new role needs to be created.
- The orchestrator clears the `override` flag itself via the FSM patch endpoint after processing; TM does not auto-clear it.
- Audit events are append-only; there is no delete or update operation on audit records.
- Pagination for the pending endpoint uses an opaque cursor (not offset-based) to avoid missed or duplicate tickets across pages during concurrent writes.
- The `ticket_type` field in the pending response uses the values already present in the TM: `feature`, `bugfix`, `improvement`, `other`.
- Performance requirements (SC-001) are based on the orchestrator's expected polling interval; the system is not expected to handle real-time event streaming.
- The `include_fsm` list extension is a read-only addition and does not affect write behavior.
- When implemented via `run-agents.sh`, task ownership follows role alignment: the `backend` agent owns all implementation tasks (T001–T036); the `autotester` agent owns integration tests (T037–T038); the `code-reviewer` agent owns final validation (T039–T041). The `software-architect` and `security-architect` agents review design and security aspects without implementing.
- The multi-agent run targets full scope: all 41 tasks (T001–T041), covering all P1, P2, and P3 stories.
- The Brainstorm project ID for the `run-agents.sh` execution of this feature is `ticket-manager-extensions-1`. Pass it as: `bash run-agents.sh --project ticket-manager-extensions-1`.
