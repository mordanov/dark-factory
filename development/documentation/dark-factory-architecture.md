# Dark Factory Architecture

_Last updated: 2026-06-25_

## 1. Scope and source of truth

This document describes the **Dark Factory** platform as it exists in the monorepo: six backend subservices, two frontends, shared infrastructure, and the main runtime flows.

**Primary sources used for this document**:
- `README.md`
- `specs/004-keycloak-iam-migration/plan.md`
- `infra/docker-compose.yml`
- `infra/docker-compose.override.yml`
- Representative service entrypoints and module trees under `services/**/src`

> Note: some older per-service READMEs still describe legacy local-JWT flows. The architecture below follows the current runtime defined by compose + spec + current source: **Keycloak is the active identity provider in runtime**, while `AUTH_MODE=local` remains for automated tests.

---

## Original vision vs. implementation status

This section maps the original high-level architecture and workflow described in the early Dark Factory prompt to the current monorepo implementation.

### Status legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Implemented and operational |
| ⚠️ | Partially implemented — core present, gaps remain |
| ❌ | Not implemented |
| 🆕 | Implemented, but not part of the original vision |

### Workflow steps

| # | Step | Status | Current implementation |
|---|------|--------|------------------------|
| 1 | **Prompt Processing** — receive, analyze, clarify, and enhance a user prompt | ✅ | `user-input-manager` (Prompt Studio) performs iterative session-based refinement with LLM support before plan generation. |
| 2 | **Planning** — pass enhanced spec to Speckit; generate implementation plan with requirements, architecture, and milestones | ✅ | Planning is implemented in `user-input-manager` via `PlanningService`, which generates Epic → Stories → Tasks and stores agent configuration. |
| 3 | **Task Decomposition** — decompose plan into discrete tasks; register in Ticket Manager | ✅ | Confirmed plans are converted into `ticket-manager` entities over HTTP. |
| 4 | **Development Execution** — human operator initiates the cycle; Orchestrator monitors backlog | ✅ | Operators trigger orchestration jobs in `orchestrator`; `JobWorker` processes them asynchronously. |
| 5 | **Task Assignment** — Orchestrator analyzes scope, requirements, dependencies, and complexity, then assigns the most appropriate agent | ✅ | `OrchestratorService` uses FSM transitions, project memory, dependency state, and LLM-guided decisions to assign work back to Ticket Manager. |
| 6 | **Agent Collaboration** — agents collaborate through the Brainstorm MCP communication layer | ⚠️ | `agent-dispatcher` has `BrainstormCoordinator` for structured multi-round collaboration, but direct peer-to-peer messaging and shared working memory are not yet implemented. |
| 7 | **Iterative Development** — agents implement, test, validate, debug, document, and review | ✅ | `agent-dispatcher` launches agents in `claude_code` or `api` mode, parses results, and reports progress/outcomes. |
| 8 | **Completion Criteria** — the cycle continues until every ticket reaches Done | ✅ | `ticket-manager` FSM and event history track completion; `Done` is a terminal state. |

### Core components

| Original component | Status | Current implementation |
|-------------------|--------|------------------------|
| **Prompt Enhancement Layer** | ✅ | Delivered by `user-input-manager` as Prompt Studio with iterative prompt refinement. |
| **Speckit** | ✅ | Planning capabilities are embedded in `user-input-manager` instead of a standalone runtime service. |
| **Ticket Manager** | ✅ | `ticket-manager` is the system of record for projects, tickets, assignments, progress, and event history. |
| **Orchestrator** | ✅ | `orchestrator` coordinates workflow decisions, FSM transitions, audit trail, and distillation triggers. |
| **Specialized Agents** | ⚠️ | Agent execution is implemented, but agents are transient CLI/API-invoked processes rather than persistent deployable services. |
| **Brainstorm MCP** | ⚠️ | `agent-tools` provides MCP-style read tooling and `agent-dispatcher` coordinates brainstorm loops, but open inter-agent messaging is missing. |

### Components added during implementation

| Component | Status | Role |
|-----------|--------|------|
| 🆕 **Context Distiller** | Implemented | Compresses project history and ADRs into durable memory used by orchestration and agent runs. |
| 🆕 **Identity & Access Management** | Implemented | Keycloak + `oauth2-proxy` provide centralized runtime authentication and authorization. |
| 🆕 **Frontend applications** | Implemented | `uim-frontend` and `tm-frontend` provide browser UIs for prompt refinement and ticket management. |
| 🆕 **Edge proxy & routing** | Implemented | `nginx` handles browser ingress and routes traffic through the auth layer. |
| 🆕 **Agent Tools** | Implemented | MCP-compatible helper service for read-only git and memory access. |

### Remaining gaps from the original vision

- **Brainstorm MCP**: collaboration is still coordinator-driven; agents do not yet exchange messages peer-to-peer or share a live working memory.
- **Specialized Agents**: agents are not yet long-running services with a registry and capability discovery API.
- **Dynamic specialization**: agent selection is still mostly driven by static role definitions and LLM reasoning rather than a formal capability index.

---

## 2. Executive summary

Dark Factory is an **AI-assisted software delivery platform** built as a Docker Compose monorepo. Users refine work items in **Prompt Studio** (`user-input-manager`), persist and manage tickets in **Ticket Manager** (`ticket-manager`), advance work through a workflow engine in **Orchestrator** (`orchestrator`), compress project context in **Context Distiller** (`context-distiller`), expose agent-side retrieval tools via **Agent Tools** (`agent-tools`), and execute specialist coding/review agents via **Agent Dispatcher** (`agent-dispatcher`).

### Service catalog

| Service | Internal URL | Primary responsibility | Storage |
|---|---|---|---|
| `user-input-manager` | `http://user-input-manager:8000` | Prompt refinement, planning, ticket creation kickoff | PostgreSQL |
| `ticket-manager` | `http://ticket-manager:8000` | Projects, tickets, assignments, events, progress, resource accounting | PostgreSQL |
| `orchestrator` | `http://orchestrator:8000` | FSM-based ticket orchestration and audit trail | PostgreSQL + MongoDB |
| `context-distiller` | `http://context-distiller:8000` | Project memory, ADRs, agent config, distillation jobs | PostgreSQL + MongoDB |
| `agent-tools` | `http://agent-tools:8000` | MCP tools for code and memory access | none |
| `agent-dispatcher` | `http://agent-dispatcher:8000` | Agent execution, brainstorm coordination, result reporting | PostgreSQL |

### Shared infrastructure

| Component | Role |
|---|---|
| `nginx` | Browser entrypoint and reverse proxy |
| `oauth2-proxy` | Bearer-token validation at the edge |
| `keycloak` | Identity provider for runtime users and service accounts |
| `postgres` | Per-service relational databases |
| `mongo` | Document storage for Orchestrator and Context Distiller |
| OpenAI-compatible LLM | Prompt refinement, planning, orchestration, distillation, agent API mode |

---

## 3. System context diagrams

### 3.1 C4 Level 1 — system context

```mermaid
flowchart LR
    User[Product user / engineer]
    Admin[Platform admin]
    Agents[AI specialist agents]
    LLM[OpenAI-compatible LLM]
    KC[Keycloak]

    subgraph DF[Dark Factory Platform]
        UIM[Prompt Studio\nuser-input-manager]
        TM[Ticket Manager\nticket-manager]
        ORCH[Orchestrator\norchestrator]
        DIST[Context Distiller\ncontext-distiller]
        AT[Agent Tools\nagent-tools]
        DISP[Agent Dispatcher\nagent-dispatcher]
    end

    User --> UIM
    User --> TM
    Admin --> KC
    UIM --> KC
    TM --> KC
    ORCH --> KC
    DIST --> KC
    AT --> KC
    DISP --> KC

    UIM --> LLM
    ORCH --> LLM
    DIST --> LLM
    DISP --> LLM

    Agents --> DISP
    Agents --> AT

    UIM --> TM
    UIM --> DIST
    ORCH --> TM
    ORCH --> DIST
    DISP --> ORCH
    DISP --> TM
    DISP --> DIST
    AT --> DIST
```

### 3.2 C4 Level 2 — container/runtime view

```mermaid
flowchart TB
    Browser[Browser]
    ClaudeCLI[Claude CLI / agent runtime]
    OpenAI[OpenAI-compatible API]

    subgraph Edge[Edge / ingress]
        NGINX[nginx]
        OAUTH[oauth2-proxy]
        KC[Keycloak]
    end

    subgraph Apps[Application containers]
        UIMF[uim-frontend]
        TMF[tm-frontend]
        UIM[user-input-manager]
        TM[ticket-manager]
        ORCH[orchestrator]
        DIST[context-distiller]
        AT[agent-tools]
        DISP[agent-dispatcher]
    end

    subgraph Data[Stateful services]
        PG[(PostgreSQL 16)]
        MG[(MongoDB 7)]
    end

    Browser --> NGINX
    NGINX --> UIMF
    NGINX --> TMF
    NGINX --> OAUTH
    OAUTH --> KC
    NGINX --> UIM
    NGINX --> TM

    UIM --> PG
    TM --> PG
    ORCH --> PG
    DIST --> PG
    DISP --> PG

    ORCH --> MG
    DIST --> MG

    UIM --> KC
    TM --> KC
    ORCH --> KC
    DIST --> KC
    AT --> KC
    DISP --> KC

    UIM --> OpenAI
    ORCH --> OpenAI
    DIST --> OpenAI
    DISP --> OpenAI

    ClaudeCLI --> DISP
    ClaudeCLI --> AT
```

### 3.3 Internal service relationship map

```mermaid
flowchart LR
    UIM[user-input-manager]
    TM[ticket-manager]
    ORCH[orchestrator]
    DIST[context-distiller]
    AT[agent-tools]
    DISP[agent-dispatcher]

    UIM -- create plan / confirm plan --> TM
    UIM -- store agent config --> DIST
    ORCH -- read ticket / patch FSM --> TM
    ORCH -- read memory / save ADR / distill --> DIST
    DISP -- poll work / report lifecycle --> ORCH
    DISP -- post run results / comments --> TM
    DISP -- fetch memory / ADRs / agent config --> DIST
    AT -- fetch memory / ADRs --> DIST
```

---

## 4. Data stores and ownership

### 4.1 Persistence ownership

```mermaid
flowchart LR
    subgraph PostgreSQL
        UIMDB[(df_user_input)]
        TMDB[(df_ticket_manager)]
        ORCHDB[(df_orchestrator)]
        DISTDB[(df_distiller)]
        DISPDB[(df_dispatcher)]
    end

    subgraph MongoDB
        ORCHDOCS[(df_orchestrator_docs)]
        DISTDOCS[(df_distiller_docs)]
    end

    UIM[user-input-manager] --> UIMDB
    TM[ticket-manager] --> TMDB
    ORCH[orchestrator] --> ORCHDB
    ORCH --> ORCHDOCS
    DIST[context-distiller] --> DISTDB
    DIST --> DISTDOCS
    DISP[agent-dispatcher] --> DISPDB
```

### 4.2 High-level domain data map

```mermaid
flowchart TD
    Prompt[Prompt session + iterations] --> Plan[Plan content + ticket map]
    Plan --> Tickets[Projects / tickets / assignments / progress / events]
    Tickets --> Jobs[Orchestration jobs + agent runs]
    Jobs --> Memory[Project memory + ADRs + agent config]
    Memory --> Agents[Agent execution context]
    Agents --> Tickets

    Prompt:::uim
    Plan:::uim
    Tickets:::tm
    Jobs:::orch
    Memory:::dist
    Agents:::disp

    classDef uim fill:#d9ecff,stroke:#1f78b4;
    classDef tm fill:#ffe4d6,stroke:#d95f02;
    classDef orch fill:#e6f5d0,stroke:#66a61e;
    classDef dist fill:#f1e2ff,stroke:#7570b3;
    classDef disp fill:#fff7c2,stroke:#e6ab02;
```

---

## 5. Core runtime flows

## 5.1 Prompt refinement and planning flow

This flow starts in Prompt Studio and ends with a plan persisted locally, then confirmed into Ticket Manager and mirrored into Context Distiller as agent configuration.

```mermaid
sequenceDiagram
    actor User
    participant UIMF as UIM Frontend
    participant UIM as user-input-manager
    participant LLM as Planning / refinement LLM
    participant TM as ticket-manager
    participant DIST as context-distiller

    User->>UIMF: Submit prompt / feedback
    UIMF->>UIM: POST /api/v1/sessions
    UIM->>LLM: Refine prompt
    LLM-->>UIM: Improved prompt text
    UIM-->>UIMF: Session + iterations

    User->>UIMF: Approve session and generate plan
    UIMF->>UIM: POST /api/v1/sessions/{id}/plan
    UIM->>LLM: generate_plan(refined prompt)
    LLM-->>UIM: Epic + Stories + Tasks
    UIM->>LLM: generate_agent_config(plan)
    LLM-->>UIM: Agent config
    UIM-->>UIMF: Plan status=ready

    User->>UIMF: Confirm plan
    UIMF->>UIM: POST /api/v1/sessions/{id}/plan/confirm
    UIM->>TM: create epic/story/task hierarchy
    TM-->>UIM: Created TM IDs
    UIM->>DIST: POST /api/v1/memory/{project_id}/agent-config
    DIST-->>UIM: Stored
    UIM-->>UIMF: status=tickets_created
```

## 5.2 Orchestration / FSM flow

This is the orchestration cycle for advancing a ticket based on current state, dependencies, project memory, and LLM guidance.

```mermaid
sequenceDiagram
    actor User
    participant ORCH as orchestrator API
    participant WORKER as JobWorker
    participant TM as ticket-manager
    participant MONGO as DocumentStore / MongoDB
    participant LLM as Orchestrator LLM
    participant AUDIT as AuditRepository

    User->>ORCH: POST /api/v1/jobs/trigger
    ORCH->>ORCH: Persist job in PostgreSQL
    ORCH->>WORKER: PG NOTIFY df_new_job
    WORKER->>TM: GET fresh ticket + dependency statuses
    TM-->>WORKER: Ticket graph + FSM state
    WORKER->>MONGO: Read project memory + accepted ADRs
    MONGO-->>WORKER: Context bundle
    WORKER->>LLM: call_orchestrator_llm(ticket, gates, memory)
    LLM-->>WORKER: Decision(action, to_state, assigned_agent, adr?)
    WORKER->>TM: PATCH ticket FSM / assigned_agent / blocked_reason
    opt decision generates ADR
        WORKER->>MONGO: Save ADR
    end
    WORKER->>AUDIT: Append immutable audit entry
    opt ticket completion triggers distillation
        WORKER->>ORCH: Enqueue distill job
    end
```

## 5.3 Memory distillation flow

```mermaid
sequenceDiagram
    participant ORCH as orchestrator
    participant DISTW as context-distiller JobWorker
    participant TM as ticket-manager
    participant LLM as Distillation LLM
    participant MONGO as MemoryRepository / MongoDB

    ORCH->>DISTW: Enqueue distill job for project/ticket
    DISTW->>TM: Collect ticket details / history context
    TM-->>DISTW: Ticket snapshots and event-related data
    DISTW->>LLM: Distill context into compact YAML memory
    LLM-->>DISTW: Distilled project memory
    DISTW->>MONGO: Archive previous memory, write new version
```

## 5.4 Agent execution flow

This is the primary execution loop for non-brainstorm tickets.

```mermaid
sequenceDiagram
    participant DISP as agent-dispatcher
    participant ORCH as orchestrator
    participant DIST as context-distiller
    participant RUN as Agent Runner
    participant TM as ticket-manager

    DISP->>ORCH: Poll pending tickets / assignments
    ORCH-->>DISP: Ticket assigned to agent
    DISP->>DIST: GET memory / ADRs / agent-config
    DIST-->>DISP: Context documents
    DISP->>RUN: Execute agent in claude_code or api mode
    RUN-->>DISP: stdout / result block
    DISP->>DISP: parse_result([RESULT]...[/RESULT])
    alt result completed
        DISP->>TM: Post comment / resource usage / progress outcome
        DISP->>ORCH: Report completion for next FSM step
    else result malformed or failed
        DISP->>TM: needs_review comment with safe stdout excerpt
        DISP->>ORCH: Report needs_review
    end
```

## 5.5 Architecture-review brainstorm flow

```mermaid
sequenceDiagram
    participant DISP as agent-dispatcher
    participant BC as BrainstormCoordinator
    participant A1 as software-architect
    participant A2 as security-architect
    participant TM as ticket-manager

    DISP->>BC: run_brainstorm(ticket)
    loop up to BRAINSTORM_MAX_ROUNDS
        BC->>A1: Run round N context
        BC->>A2: Run round N context
        A1-->>BC: AgentResult
        A2-->>BC: AgentResult
        BC->>BC: detect consensus / aggregate findings
    end
    BC-->>DISP: consensus + per-agent results
    DISP->>TM: Post aggregated architecture review result
```

---

## 6. C4 Level 3 / service component architecture

## 6.1 `user-input-manager` components

**Purpose**: Prompt Studio for iterative prompt refinement, plan generation, and plan confirmation.

**Primary internal components**:
- API routers: `sessions.py`, `planning.py`, `ticket_manager.py`, `orchestrator.py`
- Services: `SessionService`, `PlanningService`
- LLM adapters: `services/llm/*`
- Ticket Manager clients: `services/ticket_manager/*`
- Persistence: `SessionRepository`, `PlanRepository`, `IterationRepository`

```mermaid
classDiagram
    class SessionsRouter
    class PlanningRouter
    class SessionService
    class PlanningService
    class PlanningLLM
    class TMPlanClient
    class SessionRepository
    class PlanRepository
    class IterationRepository
    class KeycloakValidator
    class PromptSession
    class PromptIteration
    class Plan

    SessionsRouter --> SessionService
    PlanningRouter --> PlanningService
    SessionsRouter --> KeycloakValidator
    PlanningRouter --> KeycloakValidator

    SessionService --> SessionRepository
    SessionService --> IterationRepository

    PlanningService --> PlanRepository
    PlanningService --> SessionRepository
    PlanningService --> IterationRepository
    PlanningService --> PlanningLLM
    PlanningService --> TMPlanClient

    SessionRepository --> PromptSession
    IterationRepository --> PromptIteration
    PlanRepository --> Plan
```

## 6.2 `ticket-manager` components

**Purpose**: System of record for projects, tickets, assignments, transitions, progress, audit-style events, and resource usage.

**Primary internal components**:
- API routers under `backend/src/api/v1/`
- Services: `TicketService`, `AssignmentService`, `WorkflowService`, `TransitionService`, `ProgressService`, `ResourceService`, `AdminService`, `EventService`
- Models under `backend/src/models/`

```mermaid
classDiagram
    class ApiRouter
    class ProjectsRouter
    class TicketsRouter
    class AssignmentsRouter
    class ProgressRouter
    class ResourcesRouter
    class TransitionsRouter
    class AdminRouter
    class TicketService
    class AssignmentService
    class WorkflowService
    class TransitionService
    class ProgressService
    class ResourceService
    class EventService
    class AdminService
    class Project
    class Ticket
    class TicketAssignment
    class ProgressUpdate
    class TicketEvent

    ApiRouter --> ProjectsRouter
    ApiRouter --> TicketsRouter
    ApiRouter --> AssignmentsRouter
    ApiRouter --> ProgressRouter
    ApiRouter --> ResourcesRouter
    ApiRouter --> TransitionsRouter
    ApiRouter --> AdminRouter

    ProjectsRouter --> TicketService
    TicketsRouter --> TicketService
    AssignmentsRouter --> AssignmentService
    ProgressRouter --> ProgressService
    ResourcesRouter --> ResourceService
    TransitionsRouter --> TransitionService
    AdminRouter --> AdminService

    TransitionService --> WorkflowService
    TransitionService --> EventService
    ProgressService --> EventService
    ResourceService --> EventService
    AssignmentService --> EventService
    TicketService --> EventService

    TicketService --> Project
    TicketService --> Ticket
    AssignmentService --> TicketAssignment
    ProgressService --> ProgressUpdate
    EventService --> TicketEvent
```

## 6.3 `orchestrator` components

**Purpose**: Ticket FSM engine and orchestration job runner.

**Primary internal components**:
- API routers: `jobs.py`, `audit.py`, `memory.py`
- Worker: `JobWorker`
- Services: `OrchestratorService`, `DistillerService`, `DocumentStore`, `TicketManagerClient`, `call_orchestrator_llm`, `fsm.engine`
- Repositories: `JobRepository`, `AuditRepository`

```mermaid
classDiagram
    class JobsRouter
    class AuditRouter
    class MemoryRouter
    class JobWorker
    class OrchestratorService
    class DistillerService
    class FSMEngine
    class OrchestratorLLM
    class TicketManagerClient
    class DocumentStore
    class JobRepository
    class AuditRepository
    class Job
    class AuditLog

    JobsRouter --> JobRepository
    JobsRouter --> JobWorker
    AuditRouter --> AuditRepository
    MemoryRouter --> DocumentStore

    JobWorker --> JobRepository
    JobWorker --> OrchestratorService
    JobWorker --> DistillerService

    OrchestratorService --> TicketManagerClient
    OrchestratorService --> DocumentStore
    OrchestratorService --> FSMEngine
    OrchestratorService --> OrchestratorLLM
    OrchestratorService --> AuditRepository
    OrchestratorService --> JobRepository

    DistillerService --> DocumentStore
    DistillerService --> JobRepository
    DistillerService --> AuditRepository

    JobRepository --> Job
    AuditRepository --> AuditLog
```

## 6.4 `context-distiller` components

**Purpose**: Project memory compression and retrieval service.

**Primary internal components**:
- API routers: `distill.py`, `memory.py`
- Worker: `JobWorker`
- Services: `DataCollector`, `distill`, `TMClient`
- Repositories: `JobRepository`, `MemoryRepository`

```mermaid
classDiagram
    class DistillRouter
    class MemoryRouter
    class JobWorker
    class DataCollector
    class DistillService
    class TMClient
    class JobRepository
    class MemoryRepository
    class DistillJob
    class MemoryDoc
    class AdrDoc
    class AgentConfigDoc

    DistillRouter --> JobRepository
    MemoryRouter --> MemoryRepository
    JobWorker --> JobRepository
    JobWorker --> DataCollector
    JobWorker --> DistillService
    JobWorker --> TMClient
    JobWorker --> MemoryRepository

    JobRepository --> DistillJob
    MemoryRepository --> MemoryDoc
    MemoryRepository --> AdrDoc
    MemoryRepository --> AgentConfigDoc
```

## 6.5 `agent-tools` components

**Purpose**: MCP-accessible helper tools for agents.

**Primary internal components**:
- Entry point: `server.py` with `FastMCP`
- Tool groups: `tools/document_store.py`, `tools/git_read.py`
- Utilities: `utils/envelope.py`, `utils/git_utils.py`
- Auth/service client: `core/auth_adapter.py`, `core/keycloak_client.py`

```mermaid
classDiagram
    class FastMCP
    class DocumentStoreTools
    class GitReadTools
    class KeycloakServiceClient
    class EnvelopeBuilder
    class GitUtils
    class ContextDistillerAPI
    class GitRepository

    FastMCP --> DocumentStoreTools
    FastMCP --> GitReadTools

    DocumentStoreTools --> KeycloakServiceClient
    DocumentStoreTools --> ContextDistillerAPI
    DocumentStoreTools --> EnvelopeBuilder

    GitReadTools --> GitUtils
    GitReadTools --> GitRepository
    GitReadTools --> EnvelopeBuilder
```

## 6.6 `agent-dispatcher` components

**Purpose**: Poll Orchestrator, execute agents, parse results, and report outcomes.

**Primary internal components**:
- API router: `runs.py`
- Worker: `DispatchWorker`
- Services: `poller.py`, `dispatcher_service.py`, `context_builder.py`, `result_parser.py`, `reporter.py`, `brainstorm_coordinator.py`, `services/runner/*`
- Repository: `AgentRunRepository`

```mermaid
classDiagram
    class RunsRouter
    class DispatchWorker
    class Poller
    class DispatcherService
    class BrainstormCoordinator
    class ContextBuilder
    class ResultParser
    class Reporter
    class AgentRunner
    class AgentRunRepository
    class AgentRun
    class AgentResult

    RunsRouter --> AgentRunRepository
    DispatchWorker --> Poller
    DispatchWorker --> DispatcherService

    DispatcherService --> AgentRunRepository
    DispatcherService --> ContextBuilder
    DispatcherService --> ResultParser
    DispatcherService --> Reporter
    DispatcherService --> AgentRunner
    DispatcherService --> BrainstormCoordinator

    AgentRunRepository --> AgentRun
    ResultParser --> AgentResult
    Reporter --> AgentResult
```

---

## 7. Programming module segregation

This section summarizes the top-level source segregation pattern repeated across most services.

### 7.1 Common backend package pattern

```mermaid
flowchart LR
    MAIN[main.py]
    API["api/"]
    CORE["core/"]
    DB["db/"]
    MODELS["models/"]
    SCHEMAS["schemas/"]
    REPOS["repositories/"]
    SERVICES["services/"]
    WORKERS["workers/"]

    MAIN --> API
    MAIN --> CORE
    API --> SERVICES
    API --> SCHEMAS
    SERVICES --> REPOS
    SERVICES --> DB
    SERVICES --> MODELS
    WORKERS --> SERVICES
    WORKERS --> REPOS
    CORE --> API
    CORE --> SERVICES
```

### 7.2 Frontend segregation pattern

Only `user-input-manager` and `ticket-manager` have frontends.

```mermaid
flowchart LR
    APP[App / router entry]
    PAGES["pages/"]
    COMPONENTS["components/"]
    STORE["store/"]
    API["api/"]
    KC[keycloak.ts]
    I18N[i18n / locales]
    STYLES[styles / css]

    APP --> PAGES
    PAGES --> COMPONENTS
    PAGES --> STORE
    COMPONENTS --> STORE
    STORE --> API
    STORE --> KC
    APP --> I18N
    APP --> STYLES
```

### 7.3 Runtime cross-cutting concerns

```mermaid
flowchart TD
    Auth[KeycloakValidator / service tokens]
    Config[pydantic-settings config]
    Errors[AppError / HTTP exception mapping]
    Logging[structlog / request logging]
    Startup[Lifespan startup hooks]

    Auth --> APIHandlers[API handlers]
    Config --> Services[Service layer]
    Errors --> APIHandlers
    Logging --> Services
    Startup --> Workers
    Startup --> Auth
```

---

## 8. Deployment architecture

## 8.1 Docker Compose deployment diagram

```mermaid
flowchart TB
    subgraph Host[Developer workstation / server host]
        Browser[Browser]
        Claude[Claude CLI / agent process]
        Port80[:80]
        Port8080[:8080]
        Port8001[:8001]
        Port8002[:8002]
        Port8003[:8003]
        Port8004[:8004]
        Port8005[:8005]
        Port8006[:8006]
        Port5432[:5432]
        Port27017[:27017]
    end

    subgraph Compose[Docker Compose stack]
        subgraph ExternalNet[external network]
            NGINX[nginx]
        end

        subgraph InternalNet[internal network]
            KC[keycloak]
            OAUTH[oauth2-proxy]
            UIM[user-input-manager]
            TM[ticket-manager]
            ORCH[orchestrator]
            DIST[context-distiller]
            AT[agent-tools]
            DISP[agent-dispatcher]
            UIMF[uim-frontend]
            TMF[tm-frontend]
            PG[(postgres)]
            MG[(mongo)]
        end
    end

    Browser --> Port80 --> NGINX
    Browser --> Port8080 --> KC
    Browser -. optional dev direct .-> Port8001 --> UIM
    Browser -. optional dev direct .-> Port8002 --> TM
    Browser -. optional dev direct .-> Port8003 --> ORCH
    Browser -. optional dev direct .-> Port8004 --> DIST
    Browser -. optional dev direct .-> Port8005 --> AT
    Browser -. optional dev direct .-> Port8006 --> DISP
    Browser -. optional dev DB access .-> Port5432 --> PG
    Browser -. optional dev DB access .-> Port27017 --> MG

    NGINX --> UIMF
    NGINX --> TMF
    NGINX --> OAUTH
    OAUTH --> KC
    NGINX --> UIM
    NGINX --> TM

    UIM --> PG
    TM --> PG
    ORCH --> PG
    DIST --> PG
    DISP --> PG

    ORCH --> MG
    DIST --> MG

    UIM --> KC
    TM --> KC
    ORCH --> KC
    DIST --> KC
    AT --> KC
    DISP --> KC

    Claude --> DISP
    Claude --> AT
```

## 8.2 Service startup dependency view

```mermaid
flowchart LR
    PG[(postgres)] --> KC[keycloak]
    KC --> OAUTH[oauth2-proxy]
    PG --> UIM[user-input-manager]
    PG --> TM[ticket-manager]
    PG --> ORCH[orchestrator]
    PG --> DIST[context-distiller]
    PG --> DISP[agent-dispatcher]
    MG[(mongo)] --> ORCH
    MG --> DIST
    KC --> UIM
    KC --> TM
    KC --> ORCH
    KC --> DIST
    KC --> AT[agent-tools]
    KC --> DISP
    UIM --> NGINX[nginx]
    TM --> NGINX
    OAUTH --> NGINX
    UIMF[uim-frontend] --> NGINX
    TMF[tm-frontend] --> NGINX
```

---

## 9. Cross-service design decisions

1. **HTTP boundaries over shared libraries**  
   Cross-service reuse is done by repeating patterns per service, not by importing a shared backend package.

2. **Keycloak as runtime source of truth**  
   All backend services validate Keycloak-issued tokens in runtime; service-to-service auth also flows through Keycloak client credentials.

3. **Per-service state ownership**  
   Each service owns its relational schema; only Orchestrator and Context Distiller additionally own MongoDB documents.

4. **Ticket Manager as system of record for delivery work**  
   Ticket data, assignments, transitions, progress, and events live in `ticket-manager`, even when initiated from other services.

5. **Orchestrator owns workflow logic, not ticket persistence**  
   It decides transitions and assignments, but applies them back through Ticket Manager APIs.

6. **Agent Dispatcher owns execution semantics**  
   Result parsing, brainstorm rounds, orphan-run recovery, and reporting are product behavior, not incidental infrastructure.

7. **Context Distiller owns compressed memory**  
   It is the main source for project memory, ADR retrieval, and project-level agent configuration.

---

## 10. Risks / architectural watchpoints

- **Documentation drift**: some service READMEs still describe legacy local auth and older stacks; prefer compose + current source for runtime truth.
- **Cross-service contract fragility**: because patterns are copy-consistent instead of shared-library based, interface changes must be mirrored carefully across services.
- **Auth split between runtime and tests**: runtime uses Keycloak, while integration tests intentionally use local seeded auth.
- **Dual async patterns**: Orchestrator and Context Distiller use `LISTEN/NOTIFY` plus poll fallback; Agent Dispatcher uses periodic HTTP polling.
- **Two stores for workflow context**: ticket facts live in Ticket Manager, while distilled memory/ADRs/agent config live in MongoDB-backed Context Distiller.

---

## 11. Suggested reading order for implementers

1. `README.md`
2. `specs/004-keycloak-iam-migration/plan.md`
3. `infra/docker-compose.yml`
4. `services/user-input-manager/backend/src/main.py`
5. `services/ticket-manager/backend/src/main.py`
6. `services/orchestrator/src/main.py`
7. `services/context-distiller/src/main.py`
8. `services/agent-tools/src/server.py`
9. `services/agent-dispatcher/src/main.py`
10. `development/run-agents.sh`


