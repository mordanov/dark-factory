# Feature Specification: Agent API SDLC Integration

**Feature Branch**: `003-agent-api-sdlc`
**Created**: 2026-05-24
**Status**: Draft

## Clarifications

### Session 2026-05-24

- Q: After an agent authenticates with username+password, how does it present its identity on subsequent API calls? → A: JWT Bearer token — login returns access+refresh tokens; agents pass `Authorization: Bearer <token>` on every call (consistent with existing platform auth).
- Q: What are the valid ticket statuses for the hard-coded initial set? → A: Open → In Progress → Review → Done (linear 4-stage SDLC flow).
- Q: How does an agent gain access to a project — automatically or by explicit grant? → A: All authenticated agents have read/write access to all projects automatically; no explicit per-project membership is required.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ticket Resource Tracking (Priority: P1)

Every ticket records the cumulative time spent and tokens consumed by agents working on it. Each increment is permanently logged in the ticket's event journal, giving project administrators a full audit trail of agent effort.

**Why this priority**: Without resource tracking, agents have no way to report their work cost back to the project administrator. All downstream accountability depends on this data being available and trustworthy.

**Independent Test**: Can be fully tested by creating a ticket, having an agent increment `time_spent` and `tokens_consumed` via the API, then reading the ticket and verifying both fields increased by the expected amounts and a corresponding journal entry was created.

**Acceptance Scenarios**:

1. **Given** a ticket with `time_spent = 0` and `tokens_consumed = 0`, **When** an agent submits an increment of 120 seconds and 500 tokens, **Then** the ticket shows `time_spent = 120`, `tokens_consumed = 500`, and one journal entry records the exact delta with timestamp and agent identity.
2. **Given** a ticket with existing non-zero resource values, **When** multiple agents submit increments independently, **Then** each increment is added to the running total and each produces a separate journal entry; no increment is lost or overwritten.
3. **Given** a request to decrement or set a negative increment, **When** the API processes the request, **Then** it is rejected with a validation error; the ticket values remain unchanged.
4. **Given** a project administrator account, **When** it submits a resource increment for any ticket, **Then** the increment is accepted regardless of whether the administrator is assigned to the ticket.

---

### User Story 2 - Agent User Bootstrapping (Priority: P2)

The project administrator skill automatically ensures all required agent accounts exist on the ticket platform before any SDLC workflow begins. It reads credential definitions from skill folders, creates missing users, and writes generated credentials back to each skill's credential file so subsequent agent skills can authenticate.

**Why this priority**: Agents cannot perform any ticket operations until their accounts exist. The project administrator is the entry point of every SDLC run and must guarantee the platform is ready before other skills start.

**Independent Test**: Can be fully tested by running the project administrator skill against a fresh environment where agent users do not yet exist, then verifying each expected user account was created on the platform and a credential file appeared in the corresponding skill folder.

**Acceptance Scenarios**:

1. **Given** an agent skill folder containing a credential definition file with a specified username and no existing platform account, **When** the project administrator runs the bootstrapping step, **Then** a user account is created on the ticket platform and the generated password is written to the skill's credential file.
2. **Given** an agent skill folder where a credential file already exists and the stored credentials are valid on the platform, **When** the project administrator checks the user, **Then** the account is left unchanged and no new credential file is written.
3. **Given** an agent skill folder where a credential file exists but the stored password is incorrect (rejected by the platform), **When** the project administrator checks the user, **Then** a new user account is created (or the password is reset) and the credential file is updated with the new password.
4. **Given** the project administrator's own credential file provided by a human operator, **When** the project administrator starts, **Then** it reads this file and authenticates with the platform using those credentials before performing any user management action.
5. **Given** credential files containing sensitive passwords, **When** the repository is committed, **Then** all credential files are excluded by `.gitignore` and do not appear in version control.

---

### User Story 3 - Agent Ticket Lifecycle via API (Priority: P3)

All SDLC agents (product manager, backend, frontend, etc.) perform the full ticket lifecycle — create, assign, transition status, attach updates — exclusively through the ticket platform API without any UI interaction.

**Why this priority**: This is the core SDLC automation scenario. Without API-only access, agents cannot operate autonomously.

**Independent Test**: Can be fully tested end-to-end by running the product manager skill to create a project and tickets via API, then running a downstream agent skill to transition a ticket status via API (with a required update text), and verifying the final ticket state, assignees, and journal are correct.

**Acceptance Scenarios**:

1. **Given** an authenticated product manager agent, **When** it calls the API to create a project and then creates a ticket with a specified type, tags, and assignee, **Then** the ticket appears in the project with all specified attributes set correctly.
2. **Given** a ticket assigned to an agent, **When** that agent calls the API to transition the ticket to a new status, **Then** the transition is accepted, the status changes, and a journal entry records the transition along with the mandatory update text provided by the agent.
3. **Given** a ticket transition request that includes no update text, **When** the API processes it, **Then** the request is rejected with a validation error requiring an update message.
4. **Given** a project administrator account, **When** it calls the ticket status transition endpoint for a ticket it is NOT assigned to, **Then** the request is rejected with a permission error.
5. **Given** a project administrator account, **When** it calls the ticket status transition endpoint for a ticket it IS assigned to, **Then** the transition proceeds normally.
6. **Given** any agent (including product manager), **When** it calls the API to add another agent as an assignee to a ticket, **Then** the assignee is added and a journal entry records the change with the acting agent's identity.
7. **Given** an agent wishing to create a follow-up ticket linked to an existing ticket, **When** it calls the API to create the follow-up, **Then** the new ticket is created in the same project and is linked to the parent ticket.

---

### Edge Cases

- What happens when the project administrator credential file does not exist at startup? The skill must halt with a clear error — it cannot proceed without authentication credentials.
- What happens when a credential file exists but is malformed (invalid JSON)? The bootstrapping step must reject it with a descriptive error identifying which file is invalid.
- What happens if an agent tries to transition a ticket it is not assigned to? The API must return a permission error; the ticket status must remain unchanged.
- What happens when two agents simultaneously increment resource counters on the same ticket? Each increment must be applied atomically so no data is lost.
- What happens when a skill folder for a specified agent does not exist when the project administrator tries to write credentials? The write must fail with an error identifying the missing path; the human must create the folder before the credential can be stored.
- What happens when an agent requests a status transition that skips a step (e.g., `Open` directly to `Done`) or moves backwards (e.g., `In Progress` to `Open`)? The API must reject it with a validation error; the ticket status must remain unchanged.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every ticket MUST have two additional numeric fields: `time_spent` (integer seconds, default 0) and `tokens_consumed` (integer units, default 0).
- **FR-002**: Both `time_spent` and `tokens_consumed` MUST only be modified by increment operations; arbitrary set operations are not permitted through the agent API.
- **FR-003**: Every increment to `time_spent` or `tokens_consumed` MUST produce an immutable journal entry recording the delta amount, the resulting total, the acting agent's identity, and a UTC timestamp.
- **FR-004**: The project administrator MUST be permitted to submit resource increments for any ticket, regardless of assignment.
- **FR-005**: The system MUST provide an API endpoint for agents to increment `time_spent` and `tokens_consumed` on a ticket by specifying a non-negative integer delta.
- **FR-006**: The project administrator skill MUST read its own authentication credentials from a JSON credential file located in its skill folder, provided initially by a human operator.
- **FR-007**: The project administrator MUST check each defined agent account on the ticket platform at startup: if the account does not exist, it MUST be created; if the stored password is invalid, a new account MUST be created (or the password reset) and the credential file updated.
- **FR-008**: When the project administrator creates an agent user account, it MUST write the account credentials (username and generated password) to a JSON credential file in the corresponding agent's skill folder.
- **FR-009**: All credential JSON files in skill folders MUST be listed in `.gitignore` so they are never committed to version control.
- **FR-010**: The ticket platform API MUST expose a login endpoint that accepts username and password and returns a JWT access token and refresh token. All subsequent API endpoints MUST require a valid JWT passed as an `Authorization: Bearer <token>` header. Authenticated agents MUST be able to: create a project, create a ticket (with type, tags, description, and optional assignee), list tickets, read a ticket, add or remove an assignee, transition ticket status, and submit a progress update.
- **FR-011**: A status transition request submitted by an agent MUST include a non-empty text update; the API MUST reject transitions without an update.
- **FR-012**: Only agents currently listed as assignees on a ticket (or the project administrator for resource-only updates) MUST be permitted to transition that ticket's status; the API MUST reject unauthorized transition attempts.
- **FR-013**: The project manager agent MUST be able to create tickets with explicit type and tag values that route the ticket to the correct specialist agent.
- **FR-014**: Any authenticated agent MUST be able to read tickets and add or remove assignees on any ticket in any project. No per-project membership grant is required.
- **FR-015**: Any agent MUST be able to create a follow-up ticket linked to an existing ticket within the same project.
- **FR-016**: The valid ticket statuses MUST be `Open`, `In Progress`, `Review`, and `Done`, in that progression order. The API MUST reject any transition that skips a step or moves backwards (e.g., `Open` → `Done` is not permitted; `In Progress` → `Open` is not permitted).

### Key Entities

- **Ticket**: The core work item. Gains `time_spent` (integer seconds) and `tokens_consumed` (integer units) fields alongside existing attributes. Both fields accumulate monotonically. Valid statuses (hard-coded): `Open` → `In Progress` → `Review` → `Done`.
- **TicketResourceIncrement**: A journal event sub-type recording one agent's increment of `time_spent` or `tokens_consumed`. Attributes: ticket reference, field name, delta value, resulting total, agent identity, UTC timestamp.
- **AgentCredential**: A JSON file stored in a skill folder. Contains at minimum: `username` (string), `password` (string). Used by the project administrator to authenticate and by agent skills to authenticate to the API.
- **AgentUser**: A ticket platform user account created and managed by the project administrator. Corresponds one-to-one with a skill's credential file.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After any agent increments `time_spent` or `tokens_consumed`, a corresponding journal entry is visible on the ticket within one API round-trip.
- **SC-002**: The project administrator skill completes full user bootstrapping (checking all defined agents, creating missing accounts, updating invalid credentials) in a single unattended run with zero manual steps beyond providing the initial admin credential file.
- **SC-003**: An agent that authenticates using credentials written by the project administrator can successfully perform all permitted ticket operations (create, transition with update, add assignee, increment resources) without any UI interaction.
- **SC-004**: Any attempt to perform a non-permitted operation (decrement resources, transition a ticket without being assigned, transition without an update text) results in a clear API error response; the ticket state is not modified.
- **SC-005**: All credential files generated during a run are absent from `git status` output and from any commit made during or after the run.
- **SC-006**: The complete SDLC flow — project administrator bootstraps users, product manager creates project and tickets, specialist agent transitions a ticket with an update and increments resources — can be executed from start to finish using only API calls with no UI steps.

## Assumptions

- The ticket platform is already deployed and reachable by all agent skills at a known base URL.
- Skill folder paths are known to the project administrator at runtime (either hard-coded in its configuration or discoverable by convention).
- The initial project administrator credential file is created and placed in the correct skill folder by a human operator before the first SDLC run.
- The credential file format is a flat JSON object with at minimum `username` and `password` keys; additional fields are permitted and ignored.
- Agent usernames are determined by the skill's credential definition or by a naming convention the project administrator applies consistently.
- The ticket platform supports creating users programmatically via an admin-authenticated API endpoint.
- The existing role model (administrator, user) is sufficient; no new role is needed — the project administrator skill authenticates as a platform `administrator` account.
- Agents authenticate by calling the login endpoint with `username` and `password` from their credential file; the response includes a JWT access token and refresh token. The access token is used as `Authorization: Bearer <token>` on all subsequent API calls. This is consistent with the existing platform authentication pattern.
- Password validation (checking stored credentials) is performed by attempting a login API call; a 401 response means the password is wrong.
- "Follow-up ticket" linking is represented by a parent-ticket reference field on the new ticket; the platform already supports or will support this field.
- All authenticated platform users (agent accounts) have implicit read/write access to all projects. No per-project membership management is required.
- Mobile or browser-based access by agents is out of scope; the API surface is the only integration point for agent skills.
