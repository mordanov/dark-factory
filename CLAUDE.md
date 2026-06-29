# Dark Factory Monorepo

## Overview

Dark Factory is a distributed, service-oriented system deployed as a containerized monorepo. The architecture separates concerns across six autonomous HTTP services, each with independent data persistence and clear API boundaries. All services are coordinated through Docker Compose with centralized nginx routing and unified infrastructure provisioning.

## Service Map

| Service | Directory | Host Port (dev override) | Database | Internal URL |
|---------|-----------|--------------------------|----------|--------------|
| user-input-manager | `services/user-input-manager/backend` | 8001 | `df_user_input` (PostgreSQL) | `http://user-input-manager:8000` |
| ticket-manager | `services/ticket-manager/backend` | 8002 | `df_ticket_manager` (PostgreSQL) | `http://ticket-manager:8000` |
| orchestrator | `services/orchestrator` | 8003 | `df_orchestrator` (PostgreSQL + MongoDB `df_orchestrator_docs`) | `http://orchestrator:8000` |
| context-distiller | `services/context-distiller` | 8004 | `df_distiller` (PostgreSQL + MongoDB `df_distiller_docs`) | `http://context-distiller:8000` |
| agent-tools | `services/agent-tools` | 8005 | none | `http://agent-tools:8000` |
| agent-dispatcher | `services/agent-dispatcher` | 8006 | `df_dispatcher` (PostgreSQL) | `http://agent-dispatcher:8000` |

## Infrastructure

| Component | Location |
|-----------|----------|
| Unified compose | `infra/docker-compose.yml` |
| Dev port overrides | `infra/docker-compose.override.yml` |
| Environment example | `infra/.env.example` |
| Nginx template | `infra/nginx/nginx.conf.template` |
| PostgreSQL init | `infra/postgres/init/01_create_databases.sql` |
| Integration tests | `integration-tests/` |

## Deployment & Local Development

The complete system is provisioned through Docker Compose, which manages service lifecycle, networking, volume mounts, and health checks. All services discover each other through internal Docker DNS. Persistent state is managed through separate PostgreSQL and MongoDB instances with isolated databases per service. Local development includes nginx reverse proxy and optional authentication bypass for testing.

## Project Organization

| Directory | Purpose |
|-----------|---------|
| `services/` | Six autonomous HTTP services with independent codebases and deployments |
| `infra/` | Docker Compose orchestration, nginx routing, database initialization, and infrastructure configuration |
| `integration-tests/` | Cross-service contract and behavioral testing with isolated test environment |
| `development/` | Automation scripts and role definitions for agent-driven development workflows |
| `specs/` | Feature specifications, design artifacts, and architectural documentation |

## Canonical Versions

- Python: 3.12 (all services)
- FastAPI: 0.115.5, SQLAlchemy: 2.0.36, asyncpg: 0.30.0, pydantic: 2.10.3
- ruff: 0.8.3
- React: 18.3.1, Vite: 6.0.3, Vitest: 2.1.8, Zustand: 5.0.2
- PostgreSQL: 16, MongoDB: 7, Nginx: alpine

See `pyproject.toml [tool.versions]` and `package.json canonicalVersions` for pinned versions.

<!-- SPECKIT START -->
## Current Feature

**Branch**: `007-k3s-migration`
**Plan**: `specs/007-k3s-migration/plan.md`
**Spec**: `specs/007-k3s-migration/spec.md`
<!-- SPECKIT END -->
