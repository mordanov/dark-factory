# Feature Specification: Project Groups, Assignee-Only Transitions, and Tokens Spent

**Feature Branch**: `006-project-groups-transitions-tokens`
**Created**: 2026-06-23
**Status**: Draft
**Input**: User description: "Project groups, assignee-only transitions, and tokens spent field for tickets"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Project Groups (Priority: P1)

A user needs to organise projects into logical groups so that related projects can be
browsed and filtered together. Every project belongs to exactly one group. Groups have a
short, memorable identifier and a human-readable description. New installations start with
a built-in "Default" group so that existing projects are not orphaned.

**Why this priority**: Project organisation is foundational — it affects how all projects
are displayed, created, and navigated. Other features do not depend on it, but it has the
widest surface area (model, API, migration, UI).

**Independent Test**: Create a new group "TEAM-A" with description "Team Alpha projects".
Create a project assigned to that group. The project list shows a group filter; filtering
by "TEAM-A" shows only that project. Change the project's group to "Default"; it disappears
from the "TEAM-A" filter. Existing projects (before the feature) appear under "Default".

**Acceptance Scenarios**:

1. **Given** no groups exist yet, **When** the system is initialised (or migrated),
   **Then** a "Default" group exists with identifier `DEFAULT` and any pre-existing
   projects are linked to it.
2. **Given** a valid group identifier (4–8 alphanumeric characters), **When** a user creates
   a group, **Then** the group is saved and immediately available for project assignment.
3. **Given** an existing project, **When** a user changes its group, **Then** the project
   reflects the new group immediately and appears under the correct group filter.
4. **Given** the project list page, **When** a user selects a group filter, **Then** only
   projects belonging to that group are shown; selecting "All" removes the filter.
5. **Given** a user attempts to create a project without specifying a group, **Then** the
   project is automatically assigned to the "Default" group.
6. **Given** a user attempts to create a group with an identifier shorter than 4 or longer
   than 8 characters, or containing non-alphanumeric characters, **Then** the creation is
   rejected with a clear validation message.

---

### User Story 2 — Assignee-Only Transitions Without Mandatory Progress Update (Priority: P2)

A ticket assignee needs to move a ticket to the next status without being forced to submit
a progress update first. The rule that blocked transitions until all assignees had submitted
updates is removed. The rule that only assignees may trigger transitions is preserved and
strengthened.

**Why this priority**: This is a behaviour change that unblocks day-to-day ticket workflow
for the whole team. It does not depend on Project Groups.

**Independent Test**: Assign User A and User B to a ticket. Without either submitting a
progress update, User A transitions the ticket from `OPEN` to `IN_PROGRESS` — transition
succeeds. A non-assigned User C attempts the same transition on a different ticket — the
system rejects it with a "not an assignee" error. User A removes their assignment; they can
no longer transition that ticket.

**Acceptance Scenarios**:

1. **Given** a ticket with at least one assignee and no progress updates submitted,
   **When** one of the assignees transitions the ticket to the next allowed status,
   **Then** the transition succeeds immediately without requesting a progress update.
2. **Given** a ticket with two assignees, **When** either of them attempts a transition,
   **Then** both are individually authorised and the transition succeeds for whoever acts first.
3. **Given** a user who is not assigned to a ticket, **When** they attempt to transition
   that ticket, **Then** the system rejects the attempt with a clear "not an assignee" error.
4. **Given** a ticket with status `CLOSED`, **When** any user attempts a transition,
   **Then** the system rejects it (closed is a terminal state regardless of assignee status).

---

### User Story 3 — Tokens Spent Field with Increment-Only API (Priority: P3)

Any user working on a ticket can record how many tokens (e.g. AI tokens consumed during
work) were spent. The system only allows adding to the running total — it never allows
setting or reducing the value. Each addition is permanently logged as a timestamped
"update" event visible in the ticket's activity history.

**Why this priority**: This is an additive field with no dependency on the other two
features. It enhances auditability but does not block core workflows.

**Independent Test**: Assign User A to a ticket (tokens spent = 0). User A increments by
500 — total becomes 500 and an activity entry appears. User A increments by 200 — total
becomes 700 and another activity entry appears. Non-assigned User B attempts to increment
— the system rejects it with a "not an assignee" error. Attempting to set the total
directly to 100 (not increment) is rejected by the API. The value can never decrease.

**Acceptance Scenarios**:

1. **Given** a ticket with at least one assignee, **When** an assignee increments tokens
   spent by a positive integer, **Then** the ticket's running total increases by exactly
   that amount.
2. **Given** a tokens-spent increment by an assignee, **When** the increment is applied,
   **Then** a new activity entry is created on the ticket recording the amount added,
   the user who added it, and the timestamp.
3. **Given** a user who is not assigned to the ticket, **When** they attempt to increment
   tokens spent, **Then** the system rejects the attempt with a "not an assignee" error.
4. **Given** an API request that attempts to set tokens spent to an absolute value
   (not increment), **Then** the request is rejected — no direct assignment is possible.
5. **Given** an increment of zero or a negative number, **When** submitted,
   **Then** the system rejects it with a clear validation error.
6. **Given** the ticket detail view, **When** a user views the ticket,
   **Then** the current tokens-spent total is visible alongside other ticket metadata.

---

### Edge Cases

- What happens when a group identifier is reused? Identifiers are unique; attempting to
  create a duplicate is rejected with a conflict error.
- What happens when the last project in a group is moved to another group? The now-empty
  group continues to exist; groups are not auto-deleted when empty.
- What happens when a group is referenced in a filter but has since been deleted? Deletion
  of a group that still has projects is rejected; the user must reassign all projects first.
- What happens when no assignees remain on a ticket? The ticket cannot be transitioned
  until at least one assignee is added (consistent with current RBAC: only assignees may
  transition).
- What happens if two users simultaneously increment tokens spent? Each increment is
  applied atomically; the final total reflects both increments without data loss.
- What happens when an admin attempts to transition a ticket they are not assigned to?
  Admins are subject to the same assignee-only rule for transitions; admin role does not
  bypass the check.

## Requirements *(mandatory)*

### Functional Requirements

**Project Groups**

- **FR-001**: The system MUST provide a group entity with a unique identifier of 4–8
  alphanumeric characters. Input is normalised to uppercase on write; the identifier
  is always stored and displayed in uppercase. The entity also has a human-readable
  name and an optional description.
- **FR-002**: A built-in group with identifier `DEFAULT` and name "Default" MUST exist
  at all times and MUST NOT be deletable.
- **FR-003**: Every project MUST belong to exactly one group. A project MUST NOT be
  created or left in a state without a group reference.
- **FR-004**: When a project is created without specifying a group, it MUST automatically
  be assigned to the "Default" group.
- **FR-005**: Existing projects MUST be migrated to the "Default" group with no data loss
  or downtime beyond normal migration time.
- **FR-006**: Any authenticated user MUST be able to change any project's group after creation.
- **FR-007**: The project list MUST support filtering by group; selecting a group shows
  only that group's projects; an "All" option removes the filter.
- **FR-008**: A group that still has projects linked to it MUST NOT be deletable; the user
  must reassign or delete all projects first.
- **FR-009**: All group management endpoints (create, list, delete, update) and the project
  group-assignment endpoints MUST be documented in `docs/api-updates.md`.

**Assignee-Only Transitions (No Mandatory Progress Update)**

- **FR-010**: The progress-update gate on ticket transitions MUST be removed; transitions
  MUST NOT be blocked because progress updates are absent.
- **FR-011**: Only a user who is currently assigned to the ticket MAY trigger a status
  transition. If there are multiple assignees, any one of them is sufficient.
- **FR-012**: A user who is not assigned to the ticket MUST be rejected when they attempt
  a transition, with an error message indicating they are not an assignee.
- **FR-013**: The transition endpoint change (removal of the progress gate, assignee-only
  check preserved) MUST be documented in `docs/api-updates.md`.

**Tokens Spent**

- **FR-014**: Every ticket MUST have a `tokens_spent` field initialised to `0`.
- **FR-015**: The system MUST expose an increment endpoint that adds a positive integer to
  `tokens_spent`. Only a user currently assigned to the ticket MAY call this endpoint;
  non-assignees MUST be rejected with a 403 error. Direct assignment (setting the field
  to an arbitrary value) MUST NOT be possible through any API endpoint.
- **FR-016**: Every increment MUST be recorded as an immutable activity entry on the
  ticket, capturing: the amount added, the user who added it, and the timestamp.
- **FR-017**: An increment of zero or a negative number MUST be rejected with a validation
  error.
- **FR-018**: The current `tokens_spent` total MUST be visible in the ticket detail view
  and included in ticket API responses.
- **FR-019**: The tokens-spent increment endpoint MUST be documented in `docs/api-updates.md`.

### Key Entities

- **ProjectGroup**: Represents a logical grouping of projects. Has a unique alphanumeric
  identifier (4–8 chars), a display name, and a description. The "Default" group is
  system-managed and cannot be deleted.
- **Project** (modified): Gains a mandatory foreign-key reference to a ProjectGroup.
  Existing and future projects must have exactly one group.
- **Ticket** (modified): The `tokens_spent` field is added (non-negative integer, default 0).
  Status-transition logic changes: progress gate removed, assignee-only check retained.
- **TokensSpentEvent**: An immutable activity record capturing each increment to a ticket's
  tokens-spent total (amount, actor, timestamp). Stored as a specialised ticket event.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of projects (existing and new) are linked to a group at all times —
  zero orphaned projects exist after migration.
- **SC-002**: The project list group filter shows correct results in 100% of cases —
  no projects appear under the wrong group filter.
- **SC-003**: Ticket transitions by valid assignees succeed without requiring a progress
  update in 100% of attempted transitions.
- **SC-004**: Ticket transition attempts by non-assignees are rejected in 100% of cases.
- **SC-005**: 100% of tokens-spent increments are reflected in the running total and
  produce a corresponding activity log entry; no increments are lost or duplicated under
  concurrent conditions.
- **SC-006**: Attempted direct assignment of `tokens_spent` (bypassing the increment API)
  is rejected in 100% of cases.
- **SC-007**: All three features are covered by the `docs/api-updates.md` document before
  any new endpoint is deployed.

## Clarifications

### Session 2026-06-24

- Q: Which roles may create, update, and delete project groups? → A: Any authenticated user (all roles) may create, update, and delete groups. The only restrictions are the business rules already in the spec: DEFAULT group is undeletable; a group with projects linked to it is undeletable.
- Q: Who may reassign a project to a different group? → A: Any authenticated user may change any project's group assignment.
- Q: Which users may call the tokens-spent increment endpoint? → A: Only current assignees of the ticket may increment its tokens_spent. Non-assignees receive 403 Forbidden.
- Q: After normalisation to uppercase on write, how is the group identifier displayed? → A: Always displayed as uppercase (as stored). Input is normalised to uppercase before persistence; no original casing is preserved.

## Assumptions

- Group management (create, list, update, and delete) is available to **all authenticated users** regardless of role. The `administrator` role confers no extra permissions for group operations beyond the standard business-rule guards (DEFAULT undeletable; non-empty group undeletable).
- The "Default" group identifier is the string `DEFAULT` (all caps); display name is
  "Default"; it is seeded during migration and cannot be removed.
- The existing `tokens_consumed` field on the ticket (used elsewhere in the system) is
  separate from the new `tokens_spent` field. `tokens_spent` is user-driven; `tokens_consumed`
  is system-driven. They coexist without conflict.
- Admins are subject to the same assignee-only rule for transitions; admin role does not
  grant the ability to transition tickets they are not assigned to.
- Group identifiers are normalised to uppercase on write (e.g., input `team1` is stored and displayed as `TEAM1`). No original casing is preserved. A UNIQUE constraint on the stored uppercase value enforces uniqueness without a case-insensitive extension.
- The "All API changes documented in `docs/api-updates.md`" requirement means the file
  must exist and be updated as part of this feature's implementation — it is a required
  deliverable, not a post-implementation note.
- Progress updates (ProgressUpdate records) continue to exist as a feature; users can still
  submit them voluntarily. Only the gate that blocked transitions is removed.
