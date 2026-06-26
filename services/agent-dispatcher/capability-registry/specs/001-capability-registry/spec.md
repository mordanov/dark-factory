# Feature Specification: Agent Capability Registry & Dynamic Selection

**Feature Branch**: `006-capability-registry`  
**Created**: 2026-06-26  
**Status**: Draft  
**Input**: User description: "Implement the Agent Capability Registry and dynamic LLM-assisted agent selection for Dark Factory."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Registry-Driven Agent Assignment (Priority: P1)

The workflow system assigns the best-fit agent to each ticket automatically, based on the ticket's content and the declared capabilities of available agents — not a hardcoded lookup table.

**Why this priority**: Eliminates the single hardcoded mapping that blocks multi-agent flexibility and prevents wrong-agent assignments (e.g., always picking `backend` even for UI-only tickets). All other stories depend on the registry existing.

**Independent Test**: A ticket describing a React UI change reaches the `implementation` state and is assigned to the `frontend` agent; a ticket describing a PostgreSQL migration is assigned to `backend`. Both paths can be verified end-to-end without the other being implemented.

**Acceptance Scenarios**:

1. **Given** a ticket titled "Add React component for user profile settings" in the `specification` state, **When** the workflow advances to `implementation`, **Then** the system assigns the `frontend` agent.
2. **Given** a ticket titled "Implement PostgreSQL migration for users table" in the `specification` state, **When** the workflow advances to `implementation`, **Then** the system assigns the `backend` agent.
3. **Given** a ticket of type `feature` advancing to `architecture_review`, **When** the system selects an agent, **Then** it picks from agents that own the `architecture_review` state, not from a hardcoded string.
4. **Given** an agent role name in the workflow decision that does not exist in the registry, **When** the system processes it, **Then** the ticket is blocked with a clear error message — not silently mis-assigned.

---

### User Story 2 — Brainstorm Participant Discovery (Priority: P2)

For states that involve collaborative review (e.g., architecture review), the system automatically identifies all agents that should participate in a brainstorm session — including agents that cross-cut into the state without owning it.

**Why this priority**: Architecture review sessions currently only include the architect. Security concerns must be reviewed in parallel, not as a separate later gate. This is a correctness gap, not just a convenience.

**Independent Test**: An architecture review brainstorm for a feature ticket includes both `software-architect` (state owner) and `security-architect` (declared cross-cutting participant), verified by inspecting participant list without running agent code.

**Acceptance Scenarios**:

1. **Given** a `feature` ticket advancing to `architecture_review`, **When** the system determines brainstorm participants, **Then** the list includes both `software-architect` and `security-architect`.
2. **Given** a state with a single owning agent and no cross-cutting participants declared, **When** the system determines brainstorm participants, **Then** the list contains exactly that one agent.

---

### User Story 3 — Registry Delivered to Orchestrator (Priority: P2)

The orchestrator's decision-making process is informed by the full capability registry so it can produce role assignments grounded in what agents actually exist and what they can do.

**Why this priority**: Without registry context in the prompt, the orchestrator LLM guesses role names from training data and may invent non-existent roles or use deprecated underscore-format names.

**Independent Test**: The orchestrator prompt for any ticket contains a structured `[AGENT REGISTRY]` section listing all role IDs and their capability summaries. Verifiable by inspecting the built prompt payload without executing an agent.

**Acceptance Scenarios**:

1. **Given** the agent-dispatcher has a loaded registry, **When** it reports a ticket result back to the orchestrator, **Then** the job trigger payload includes the full registry as a structured data section.
2. **Given** the orchestrator receives a job with a registry payload, **When** it builds the LLM prompt, **Then** the prompt includes an `[AGENT REGISTRY]` section summarising each agent's role, capabilities, and owned FSM states.
3. **Given** the orchestrator LLM returns an `assigned_agent` value not found in the registry, **When** the orchestrator validates the decision, **Then** a fallback selection mechanism is invoked and the invalid role is never passed to the dispatcher.

---

### User Story 4 — Credentials Written Before Agent Spawn (Priority: P3)

Every agent receives a fresh, valid ticket-manager credential file in its working directory immediately before it is launched.

**Why this priority**: Agents currently have no automated way to receive credentials; this is a security and reliability gap. It is lower priority only because agents can be piloted manually in the interim.

**Independent Test**: Before agent launch, a credentials file appears in `development/{role}/credentials.json` containing a valid host URL and token. The file is not committed to source control.

**Acceptance Scenarios**:

1. **Given** the dispatcher is about to spawn an agent with role `backend`, **When** the spawn is initiated, **Then** a `credentials.json` file exists in the agent's designated directory with a non-expired token.
2. **Given** the credentials file was written, **When** the git status is checked, **Then** `credentials.json` does not appear as a tracked or staged file (it is gitignored).

---

### Edge Cases

- What happens when two agents equally match a ticket and the selection mechanism produces a tie? The system must define a deterministic fallback order.
- What happens when the registry file is missing or malformed at service startup? The service must fail fast with a clear error rather than starting in a broken state.
- What happens when a ticket's FSM state has no owning agent in the registry? The system must return a safe default and log a warning, not throw an unhandled exception.
- What happens if the agent selection call times out? The system must fall back to the first candidate in deterministic order without surfacing the timeout to the ticket as an error.
- What happens when the registry is updated on disk? Changes take effect only after a service restart — no hot-reload is supported.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST load agent capability definitions from a single structured configuration file at startup, and use that as the sole source of truth for all agent role information.
- **FR-002**: The configuration file MUST define, for each agent: a unique role identifier, a human-readable display name, the FSM states the agent owns, domain capability tags, and brainstorm participation rules.
- **FR-003**: All role identifiers MUST use hyphenated format and MUST match the identifiers used by the agent launch scripts exactly.
- **FR-004**: The system MUST allow multiple agents to own the same FSM state (e.g., both `backend` and `frontend` own `implementation`).
- **FR-005**: The system MUST support agents declaring cross-cutting brainstorm participation for states they do not own (e.g., `security-architect` participating in `architecture_review` brainstorm without owning it).
- **FR-006**: The FSM engine MUST NOT contain hardcoded agent role assignments. It MUST return a list of candidate role IDs for each state transition, not a single assigned agent.
- **FR-007**: When multiple candidate agents exist for a state, the system MUST invoke an intelligent selection process using the ticket's title, type, description, and the capability registry to choose the best-fit agent.
- **FR-008**: The intelligent selection process MUST always return a valid role ID — never raise an exception or leave the assignment empty. If the process fails, it MUST fall back to the first candidate in list order.
- **FR-009**: The agent selection process MUST complete within 10 seconds; exceeding this limit MUST trigger the fallback without propagating the timeout as a ticket error.
- **FR-010**: The capability registry MUST be delivered to the orchestrator's decision-making context on every job trigger, so the orchestrator can use it when producing agent assignments.
- **FR-011**: The orchestrator MUST validate every agent role assignment it produces against the registry. Any role not found in the registry MUST trigger the fallback selection process rather than being passed downstream.
- **FR-012**: The agent-dispatcher MUST write a credentials file to the agent's designated working directory immediately before spawning each agent.
- **FR-013**: Credential files MUST be excluded from source control via the repository's ignore configuration.
- **FR-014**: The capability registry MUST be loaded exactly once at service startup. Subsequent requests MUST not trigger file reads.
- **FR-015**: If the registry file is absent or unparseable at startup, the service MUST refuse to start and emit a descriptive error.

### Key Entities

- **Agent Capability Entry**: Represents one agent role. Key attributes: role identifier, display name, skill file name, coordinator flag, capability tag list, list of owned FSM states, keyword hints for selection, list of states where the agent cross-participates in brainstorm, brainstorm role (coordinator or contributor).
- **Capability Registry**: The in-memory index of all agent capability entries, queryable by role ID, by FSM state ownership, and by brainstorm participation. Also holds the raw configuration text for injection into LLM contexts.
- **FSM Evaluation Result**: The output of the FSM logic for one ticket. Changes from holding a single assigned agent string to holding a list of candidate role IDs for the target state.
- **Orchestrator Job Payload**: The data package sent from agent-dispatcher to orchestrator when triggering a new evaluation cycle. Now includes the serialised capability registry.
- **Agent Credentials File**: A per-agent file written at spawn time, containing the ticket-manager host URL and a valid access token. Not persisted to source control.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For any ticket advancing to the `implementation` state, the correct specialist agent (frontend vs. backend) is selected in over 95% of cases based on ticket content alone, as measured against a labelled test set of 20 representative tickets.
- **SC-002**: Agent selection adds no more than 10 seconds of latency to the ticket processing pipeline in the worst case, and under 2 seconds in the median case.
- **SC-003**: Zero tickets are blocked due to "unknown agent role" errors after the registry is in place, compared to the current state where role name format mismatches (underscore vs. hyphen) are a recurring source of failures.
- **SC-004**: The service startup time increases by no more than 500 milliseconds due to registry loading, ensuring no operational regression.
- **SC-005**: All new modules achieve at least 80% unit test coverage, verifiable by the project's coverage reporting tool.
- **SC-006**: Architecture review brainstorm sessions include the security architect in 100% of `feature` and `improvement` ticket reviews, eliminating the current gap where security is only reviewed in a dedicated later state.

## Assumptions

- The 10 agent roles currently present in the `development/agents/` directory are the complete set for the initial registry. New roles require a registry update and service restart.
- The agent selection intelligence is called only when two or more candidates own the same target FSM state; single-owner states bypass the selection call entirely.
- The orchestrator's existing job trigger endpoint already accepts an open-ended payload dictionary; no endpoint schema changes are needed to carry the registry.
- The ticket-manager client within the agent-dispatcher already has access to a valid service account token that can be forwarded to agent credential files.
- Changes to the registry file require a service restart; no live reload mechanism is in scope.
- Per-project capability overrides (e.g., disabling a specific agent for one project) are out of scope; that is handled by existing project-memory mechanisms.
- A GUI for browsing or editing the registry is out of scope for this feature.
- Agent load balancing across multiple instances of the same role is out of scope.
