# Dark Factory Services: Initial Approach vs Implementation Status

_Last updated: 2026-06-28_
_Source baseline: `development/documentation/dark-factory-architecture.md`_

## Initial approach (from original prompt)

The original design describes a ticket-driven autonomous development loop:

1. Enhance user prompt into a clear specification.
2. Generate a plan (requirements, architecture, milestones).
3. Decompose plan into tickets.
4. Orchestrate assignment and execution.
5. Let specialized agents collaborate and iterate until all tickets are Done.

## Core components vs current modules

| Original core component | Current module(s) | Status | Notes |
|---|---|---|---|
| Prompt Enhancement Layer | `services/user-input-manager` (+ `uim-frontend`) | ✅ Completed | Prompt Studio implements iterative prompt refinement before planning. |
| Speckit (planning + breakdown) | `services/user-input-manager` (`PlanningService`) + `.claude/skills/speckit-*` | ✅ Completed | Runtime planning is integrated in User Input Manager; Spec Kit skills also exist for development workflows. |
| Ticket Manager | `services/ticket-manager` (+ `tm-frontend`) | ✅ Completed | System of record for projects, tickets, FSM status transitions, assignments, and event history. |
| Orchestrator | `services/orchestrator` | ✅ Completed | Coordinates FSM progression, assignment decisions, and workflow jobs. |
| Specialized Agents | `services/agent-dispatcher` + `development/agents/*` | ⚠️ Partial | Execution pipeline is implemented, but agents are mostly transient runner processes rather than persistent services. |
| Brainstorm MCP | `services/agent-tools` + brainstorm flow in `services/agent-dispatcher` | ⚠️ Partial | Coordinator-driven brainstorm exists; open peer-to-peer agent messaging is still limited. |

## Current services and what they do

| Service | Primary role |
|---|---|
| `user-input-manager` | Prompt refinement, plan generation, and ticket creation kickoff. |
| `ticket-manager` | Ticket/project lifecycle management, FSM transitions, assignment/progress/resource tracking, event log. |
| `orchestrator` | Workflow decision engine; advances tickets, assigns agents, coordinates next steps. |
| `context-distiller` | Distills project/ticket context into durable memory and ADR-like artifacts. |
| `agent-tools` | MCP-compatible helper tools (read-focused retrieval from repo/context sources). |
| `agent-dispatcher` | Runs agents, handles result collection/reporting, supports structured brainstorm rounds. |

## Missing or incomplete areas

- ⚠️ **Inter-agent communication depth**: collaboration is present, but still primarily dispatcher/coordinator mediated.
- ⚠️ **Persistent agent runtime model**: agents are not fully modeled as long-running deployable workers.
- ⚠️ **Capability discovery maturity**: assignment relies heavily on role definitions + orchestration logic; dynamic capability discovery remains limited.

## Overall status

- **Completed:** Prompt enhancement, planning, ticket decomposition, ticket lifecycle management, orchestration core, iterative execution loop, completion criteria.
- **Partially completed:** Specialized agent model and Brainstorm MCP collaboration model.
- **Net assessment:** The original architecture is largely implemented, with remaining gaps centered on advanced multi-agent collaboration and runtime agent lifecycle maturity.

