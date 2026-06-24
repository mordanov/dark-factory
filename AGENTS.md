# Dark Factory Architecture Overview

## System Architecture

**Dark Factory** is a distributed, service-oriented system designed as a six-service monorepo orchestrated through containerized deployment. The architecture emphasizes clear runtime boundaries, independent data persistence, and stateless service coordination via HTTP APIs.

### Core Design Principles

**Service Isolation & Clear Boundaries**
- Runtime communication occurs over HTTP within containerized environments, not through shared Python packages or in-memory coupling
- Each service maintains independent data persistence, supporting both PostgreSQL (relational state) and MongoDB (document-oriented state) where domain requirements justify multi-model storage
- This approach trades some coupling overhead for architectural clarity, operational observability, and independent scaling/deployment

**Authentication & Security**
- Identity and access control are centralized through a dedicated IAM provider (Keycloak)
- All services perform runtime validation against centralized identity pools, not local token management
- Frontend applications use stateless, in-memory authentication flows; token persistence to browser storage is explicitly avoided to reduce attack surface
- Test environments support seeded identity fixtures separate from production auth flows

**Configuration & Environment Management**
- Runtime configuration is externalized through environment variables aggregated at service startup
- No ad-hoc reads of environmental state within service logic; configuration is instantiated once and injected throughout application lifecycle
- This centralizes configuration decisions and enables safe environment-specific overrides

### Service Ecosystem

The system coordinates six primary services, each addressing a distinct domain:

1. **User Input Manager** — Ingestion and validation of user-submitted problems and context
2. **Ticket Manager** — Stateful lifecycle management of tickets through FSM-driven state transitions
3. **Orchestrator** — Central coordination hub for multi-stage ticket processing and decision workflows
4. **Context Distiller** — Synthesis and retrieval of contextual information supporting agent decision-making
5. **Agent Tools** — Utility endpoints and helper services
6. **Agent Dispatcher** — Autonomous agent invocation, result collection, and asynchronous task orchestration

### Data Persistence Strategy

- **Primary Relational Store (PostgreSQL)**: All services maintain transactional state except `orchestrator` and `context-distiller`
- **Hybrid Approach**: `Orchestrator` and `context-distiller` maintain both PostgreSQL (transactional records) and MongoDB (larger, unstructured documents)
- This hybrid model supports both ACID guarantees for critical state and flexible document storage for evolving agent outputs and context

### Development Consistency

All Python services follow unified patterns for reliability and maintainability:
- FastAPI-based HTTP service architecture with async request handling
- Structured application initialization and graceful shutdown lifecycle management
- Shared error handling conventions and middleware configuration
- SQLAlchemy for ORM and async database access
- Syntax and style enforcement through `ruff` linter with consistent line-length conventions

Frontend applications use React with Vite for development and build optimization, coordinated state management through Zustand, and component testing through Vitest.

### Cross-Service Dependencies

Many features require coordination across multiple services. Key interaction patterns:

- **User Input → Ticket Coordination**: User submissions flow through validation, storage, and scheduling
- **Orchestration → Ticket Lifecycle**: Ticket state machine transitions are driven by orchestrator decisions, with state changes persisted to Ticket Manager
- **Agent Dispatch Cycle**: Dispatcher polls orchestrator for pending work, invokes agents, aggregates results, and triggers downstream updates through multiple services

When modifying cross-service behavior, complementary API and schema changes must be coordinated across service boundaries to maintain contract consistency.


