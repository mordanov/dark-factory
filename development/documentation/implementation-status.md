# Dark Factory: Initial Vision vs. Implementation Status

_Last updated: 2026-06-24_

---

## Overview

This document compares the original high-level architecture vision for Dark Factory — an autonomous software development platform — against the current implementation in the monorepo. Each original component and workflow step is evaluated for its implementation status.

**Status legend**

| Symbol | Meaning |
|--------|---------|
| ✅ | Implemented and operational |
| ⚠️ | Partially implemented — core present, gaps noted |
| ❌ | Not implemented |
| 🆕 | Implemented but absent from original vision |

---

## Workflow Steps

The original vision described eight sequential workflow steps. The table below maps each step to its current implementation.

| # | Step | Status | Implementation |
|---|------|--------|----------------|
| 1 | **Prompt Processing** — receive, analyze, clarify, and enhance a user prompt | ✅ | `user-input-manager` (Prompt Studio): iterative session model, LLM-assisted prompt refinement, multi-round iteration before plan generation |
| 2 | **Planning** — pass enhanced spec to Speckit; generate implementation plan with requirements, architecture, and milestones | ✅ | `PlanningService` inside `user-input-manager` generates LLM-driven plans (Epic → Stories → Tasks). Speckit capabilities are embedded in this service rather than a separate component. |
| 3 | **Task Decomposition** — decompose plan into discrete tasks; register in Ticket Manager | ✅ | `PlanningService` confirms the plan into `ticket-manager` via HTTP, creating the full epic/story/task hierarchy as first-class tickets |
| 4 | **Development Execution** — human operator initiates the cycle; Orchestrator monitors backlog | ✅ | Operator triggers orchestration via `POST /api/v1/jobs/trigger`; `JobWorker` picks up work through PostgreSQL `LISTEN/NOTIFY` and periodic poll fallback |
| 5 | **Task Assignment** — Orchestrator analyzes each task and assigns to the most appropriate agent | ✅ | `OrchestratorService` applies FSM transitions, queries project memory, calls an LLM decision model, and writes assigned agent back to Ticket Manager |
| 6 | **Agent Collaboration** — agents collaborate through Brainstorm MCP | ⚠️ | `BrainstormCoordinator` in `agent-dispatcher` runs structured multi-round brainstorm loops (up to `BRAINSTORM_MAX_ROUNDS`) with consensus detection. Real-time free-form inter-agent messaging is not yet implemented — collaboration is round-based and coordinator-driven. |
| 7 | **Iterative Development** — agents implement, test, validate, debug, document, review; Orchestrator tracks progress | ✅ | `agent-dispatcher` executes agents in `claude_code` (subprocess) or `api` (OpenAI-direct) mode, parses `[RESULT]...[/RESULT]` blocks, reports outcomes to `ticket-manager` and triggers next orchestration step |
| 8 | **Completion Criteria** — cycle ends when all tickets reach Done | ✅ | `ticket-manager` FSM tracks every ticket through its lifecycle; `Done` is a terminal state. Orchestrator's audit log provides a full transition history. |

---

## Core Components

### Prompt Enhancement Layer

> _"Responsible for transforming user requests into high-quality specifications."_

**Status: ✅ Implemented**

Delivered as `user-input-manager` (`/services/user-input-manager`). Key capabilities:
- Session-based iterative refinement: users submit prompts; the LLM returns an improved version with each iteration.
- Multi-round session model before committing to a plan.
- Frontend UI (`uim-frontend`) provides an interactive Prompt Studio experience.

---

### Speckit

> _"Responsible for planning, requirements generation, and work breakdown."_

**Status: ✅ Implemented (integrated into `user-input-manager`)**

The planning capabilities originally associated with Speckit are fully implemented, but as an embedded subsystem of `user-input-manager` rather than a standalone service:
- `PlanningService` generates a structured plan (Epic → Stories → Tasks) using an LLM.
- Plan is editable by the user before confirmation.
- On confirmation, the plan is decomposed into Ticket Manager entities via `TMPlanClient`.
- Agent configuration is also generated and stored in `context-distiller` at this stage.

> Note: `Speckit` as a standalone CLI/tool also exists in the project's development workflow (`.claude/skills/`), covering specification authoring and task generation for development agents. These are separate from the runtime planning pipeline above.

---

### Ticket Manager

> _"Stores and tracks all tasks, statuses, dependencies, and execution history."_

**Status: ✅ Fully Implemented**

Delivered as `ticket-manager` (`/services/ticket-manager`). Full system of record:
- Projects, tickets, and epic/story/task hierarchies.
- FSM-based transitions with a dedicated `TransitionService` and `WorkflowService`.
- Assignment tracking (`AssignmentService`).
- Progress updates (`ProgressService`).
- Resource usage accounting (`ResourceService`).
- Immutable event log (`EventService`) providing complete execution history.
- Frontend UI (`tm-frontend`) for human operator visibility.

---

### Orchestrator

> _"Coordinates the overall workflow, assigns work, manages agent execution, and monitors progress."_

**Status: ✅ Fully Implemented**

Delivered as `orchestrator` (`/services/orchestrator`). Key capabilities:
- FSM engine (`fsm.engine`) drives ticket state transitions.
- LLM-assisted decision-making: given ticket context, project memory, and dependency states, the LLM determines the next action and agent assignment.
- Jobs are triggered via HTTP and processed asynchronously by `JobWorker` (PostgreSQL LISTEN/NOTIFY + poll fallback).
- Architecture Decision Records (ADRs) generated during orchestration are persisted to MongoDB.
- Immutable audit trail for every orchestration decision.
- Triggers `context-distiller` distillation jobs on ticket completion.

---

### Specialized Agents

> _"Autonomous workers responsible for implementation, testing, research, review, documentation, and other development activities."_

**Status: ⚠️ Partially Implemented**

The execution infrastructure is complete; the agents themselves are externally invoked processes:

**Implemented:**
- `agent-dispatcher` manages the full execution lifecycle: polling, context assembly, launch, result parsing, reporting, and orphan-run recovery.
- Agents run in two modes: `claude_code` (Claude CLI subprocess, full tool access) or `api` (direct OpenAI calls for lighter tasks).
- Agent role definitions exist in `development/agents/` for: backend developer, frontend developer, autotester, designer, devops, product manager, project administrator, code reviewer, security architect, and software architect.
- `BrainstormCoordinator` allows multiple agents to be invoked collaboratively on architecture-review class tickets.

**Not yet implemented / gaps:**
- Agents are not containerized or deployed as persistent services — they are spawned as transient CLI subprocesses.
- No dedicated agent registry or capability discovery API; agent selection is LLM-driven at orchestration time using static role definitions.
- Dynamic agent specialization (e.g., selecting the optimal agent variant per technology stack) is not yet automated.

---

### Brainstorm MCP

> _"A communication and collaboration layer that enables agents to coordinate, exchange knowledge, and solve problems collectively."_

**Status: ⚠️ Partially Implemented**

Two complementary pieces exist, but the vision of a fully open inter-agent communication protocol is not yet realized:

**Implemented:**
- `agent-tools` (`/services/agent-tools`) is an MCP-compatible service (FastMCP) providing agents with structured tool access: memory retrieval from `context-distiller`, and read-only git repository introspection.
- `BrainstormCoordinator` in `agent-dispatcher` orchestrates multi-round brainstorming sessions: multiple agents receive the same ticket context each round, produce independent results, and the coordinator aggregates findings with configurable consensus exit criteria.

**Not yet implemented / gaps:**
- No real-time or asynchronous message-passing between agents — collaboration is mediated entirely by the coordinator, not directly between agents.
- Agents cannot independently initiate peer consultation; brainstorm sessions are always dispatcher-driven.
- No shared "working memory" workspace where agents leave intermediate artifacts visible to peers mid-round.
- MCP tool surface is read-focused; no write tools (e.g., posting agent-to-agent messages, creating shared scratch space) are exposed.

---

## Components Present in Implementation but Absent from Original Vision

The following components were introduced during implementation and add significant capability beyond the original blueprint:

| Component | Service | Role |
|-----------|---------|------|
| 🆕 **Context Distiller** | `context-distiller` | Compresses ticket history and project facts into compact YAML memory using an LLM. Serves as the authoritative source of project memory, ADRs, and per-project agent configuration for all consuming services. |
| 🆕 **Identity & Access Management** | Keycloak + oauth2-proxy | Centralized IAM for user authentication and service-to-service authorization. All runtime tokens are Keycloak-issued (RS256); services validate against JWKS endpoints. |
| 🆕 **Frontend Applications** | `uim-frontend`, `tm-frontend` | React/Vite UIs providing human-operator access to Prompt Studio and Ticket Manager. State managed through Zustand; authentication via keycloak-js (in-memory, no token persistence). |
| 🆕 **Edge Proxy & Routing** | nginx + oauth2-proxy | Unified ingress: all browser traffic enters through nginx, with oauth2-proxy enforcing authentication at the edge before forwarding to backend services. |

---

## Summary

```
Workflow steps:    8 / 8 defined  →  7 ✅ fully implemented, 1 ⚠️ partial
Core components:   6 / 6 defined  →  4 ✅ fully implemented, 2 ⚠️ partial
New components:    4 🆕 added beyond original vision
```

### Critical gaps to close

1. **Brainstorm MCP — direct inter-agent communication**: Agents currently cannot communicate peer-to-peer. The coordinator-mediated round model covers architectural review use cases but not emergent collaboration (e.g., a backend agent requesting a review mid-task from a code reviewer agent without a full brainstorm session).

2. **Agent deployment model**: Agents are transient CLI subprocesses rather than persistent deployable workers. This limits horizontal scaling, observability, and lifecycle management of long-running agent tasks.

3. **Agent registry / capability discovery**: Agent selection is currently driven by LLM inference over static role files. A structured agent registry with declared capabilities, technology affinities, and availability would make assignment more deterministic and auditable.

