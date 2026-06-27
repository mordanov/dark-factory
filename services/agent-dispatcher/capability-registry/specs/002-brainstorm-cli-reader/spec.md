# Feature Specification: Brainstorm CLI Reader

**Feature Branch**: `002-brainstorm-cli-reader`  
**Created**: 2026-06-27  
**Status**: Draft  
**Input**: Wire BrainstormCoordinator to brainstorm-mcp CLI for architecture_review transcript delivery

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Architecture Review Delivers Transcript to Orchestrator (Priority: P1)

When an architecture_review ticket completes its multi-agent brainstorm session, the system reads the transcript from the brainstorm session and delivers it to the Orchestrator so the gate evaluation can proceed with actual agent discussion content.

**Why this priority**: Without this, the Orchestrator cannot evaluate the `architecture_consistency` gate — it has no visibility into what agents discussed. This is the core value of the entire feature.

**Independent Test**: Trigger an architecture_review ticket with two agents, confirm the Orchestrator job payload contains a `brainstorm_transcript` field with messages from both agents.

**Acceptance Scenarios**:

1. **Given** an architecture_review ticket where agents `software-architect` and `security-architect` have posted messages in their brainstorm session, **When** all agents for the round complete their work, **Then** the Orchestrator job trigger payload includes `brainstorm_transcript` with all messages authored by each agent.
2. **Given** a brainstorm session with 3 agents all reporting consensus as "agreed", **When** the round concludes, **Then** the transcript carries `consensus: "agreed"` and the Orchestrator receives it.
3. **Given** a brainstorm session where one agent reports "disagreed", **When** the round concludes, **Then** the transcript carries `consensus: "disagreed"` regardless of how other agents voted.

---

### User Story 2 - Empty or Missing Session Does Not Block Processing (Priority: P2)

When agents have not yet posted any messages (e.g., session just started or project does not exist yet), the system treats this as a valid empty state and continues without failing or retrying indefinitely.

**Why this priority**: Resilience against timing races is essential for a polling-based workflow. An empty session must never be treated as a hard error.

**Independent Test**: Trigger a round-completion event when the brainstorm project has no messages; verify processing continues and the transcript has an empty messages list.

**Acceptance Scenarios**:

1. **Given** a brainstorm project that exists but has no messages, **When** the round-completion read is triggered, **Then** the transcript is produced with `messages: []` and no error is raised.
2. **Given** a brainstorm project that does not exist yet, **When** the read is triggered, **Then** the result is treated as empty (`messages: []`) and processing continues normally.
3. **Given** the CLI tool times out reading the session, **When** the timeout is reached, **Then** the system logs a warning, sets messages to empty, and continues — it does not abort the brainstorm round.

---

### User Story 3 - Single-Agent Tickets Skip Brainstorm Entirely (Priority: P3)

When a ticket requires only one agent (non-architecture_review), the brainstorm session reader is never invoked. The single agent completes its work and the Orchestrator receives the result without any brainstorm transcript.

**Why this priority**: Brainstorm is architecturally scoped to architecture_review only. Invoking it for single-agent tickets would be wasteful and incorrect.

**Independent Test**: Run an `implementation` ticket with one agent and confirm no brainstorm CLI call is made and no `brainstorm_transcript` key appears in the Orchestrator payload.

**Acceptance Scenarios**:

1. **Given** an `implementation` ticket assigned to a single agent, **When** the agent completes, **Then** no brainstorm session read is attempted and the Orchestrator payload has no `brainstorm_transcript` key.
2. **Given** any non-architecture_review ticket, **When** processing completes, **Then** the system behaves identically to how it did before this feature was introduced.

---

### User Story 4 - Orchestrator LLM Evaluates Gate Using Transcript (Priority: P4)

When the Orchestrator receives a job trigger payload containing a brainstorm transcript, its decision-making prompt includes the full transcript content so it can evaluate the `architecture_consistency` gate using what agents actually discussed.

**Why this priority**: Delivering the transcript is only valuable if the Orchestrator LLM actually uses it. Without this, the data is collected but ignored.

**Independent Test**: Call the Orchestrator's message-building function with a payload containing a transcript and verify the output prompt contains the agent messages and consensus value.

**Acceptance Scenarios**:

1. **Given** a job payload with a `brainstorm_transcript` containing two agent messages and `consensus: "inconclusive"`, **When** the Orchestrator builds its decision prompt, **Then** the prompt includes both agent messages, the consensus value, and round number.
2. **Given** an architecture_review job payload with no transcript (agents not yet done), **When** the Orchestrator builds its prompt, **Then** the prompt includes a hint that the system should wait rather than evaluate the gate prematurely.
3. **Given** a non-architecture_review job payload with no transcript, **When** the Orchestrator builds its prompt, **Then** no brainstorm section appears in the prompt at all.

---

### Edge Cases

- What happens when the brainstorm CLI tool returns malformed (non-JSON) output?
- What happens when the session has messages but all have null/missing consensus fields?
- How does the system handle a mix of agents: some reporting "agreed", some reporting null?
- What if the brainstorm session project name cannot be derived from the registry?
- What happens if the CLI tool is not installed (npx fails entirely)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST read brainstorm session messages after all agents for a round complete their work, for architecture_review tickets only.
- **FR-002**: The system MUST derive the brainstorm session project name from the capability registry, never from hardcoded values.
- **FR-003**: The system MUST treat an empty session (no messages) as a valid state and return an empty message list without raising an error.
- **FR-004**: The system MUST treat a non-existent brainstorm project as equivalent to an empty session (empty message list, no error).
- **FR-005**: The system MUST derive consensus from agent-reported values: "agreed" when all reporting agents agree, "disagreed" when any agent disagrees, "inconclusive" in all other cases (missing, mixed, or empty).
- **FR-006**: The system MUST include the brainstorm transcript in the Orchestrator job trigger payload under the key `brainstorm_transcript` when a transcript is available.
- **FR-007**: The system MUST NOT include `brainstorm_transcript` in the Orchestrator payload for non-architecture_review tickets.
- **FR-008**: The system MUST NOT write messages to the brainstorm session — it is read-only with respect to brainstorm.
- **FR-009**: The Orchestrator decision prompt MUST include the full transcript content (agent messages, consensus, round number) when a transcript is present.
- **FR-010**: The Orchestrator decision prompt MUST include a "wait" hint for architecture_review tickets where no transcript has been delivered yet.
- **FR-011**: The CLI tool path must be configurable via an environment variable; no path may be hardcoded.
- **FR-012**: The read operation MUST have a configurable timeout; on timeout, the system MUST log a warning, use an empty message list, and continue.
- **FR-013**: On CLI tool failure unrelated to "project not found", the system MUST log a warning and continue with an empty message list — it MUST NOT abort the brainstorm round.

### Key Entities

- **BrainstormMessage**: A single message posted by an agent in the brainstorm session. Has an author identity, content text, and timestamp.
- **BrainstormTranscript**: The full record of a completed brainstorm round. Contains all messages, a consensus verdict, round number, and max rounds. Delivered as part of the Orchestrator job payload.
- **Consensus**: A derived verdict from all agent reports. One of: `agreed`, `disagreed`, `inconclusive`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For any completed architecture_review brainstorm round, 100% of agent messages posted to the session appear in the transcript delivered to the Orchestrator.
- **SC-002**: An empty or missing brainstorm session results in zero processing failures — the system continues in 100% of such cases.
- **SC-003**: Single-agent (non-architecture_review) tickets complete without any brainstorm reads — verified by zero CLI invocations in those flows.
- **SC-004**: The Orchestrator correctly includes the brainstorm transcript section in 100% of architecture_review decision prompts where a transcript is available.
- **SC-005**: Brainstorm session read completes within the configured timeout in all non-failure cases; failures degrade gracefully with a log warning and empty transcript.
- **SC-006**: All unit tests for the brainstorm CLI reader pass with no real CLI invocations — 100% mocked.

## Assumptions

- The brainstorm-mcp CLI tool is pre-installed on the machine where the Dispatcher runs; this feature does not install it.
- The brainstorm session project name convention is `df-{ticket_id}` — this mapping is defined in the capability registry and this feature reads it from there.
- Agents write their messages to the brainstorm session independently using their own MCP tooling; the Dispatcher has no control over when or how agents post.
- The Orchestrator job trigger payload is a free-form dictionary that can accept new keys; no Orchestrator schema migration is needed beyond adding typed documentation.
- The capability registry already exposes a `brainstorm_project_name(ticket_id)` method; this feature calls it rather than computing the name itself.
- The `architecture_review` FSM state is the only state where multi-agent brainstorm sessions occur; all other states use single agents with no brainstorm session.
- Field names in the CLI output may vary between brainstorm-mcp versions; the reader must support aliases (`author`/`sender`, `content`/`message`, `timestamp`/`created_at`).
