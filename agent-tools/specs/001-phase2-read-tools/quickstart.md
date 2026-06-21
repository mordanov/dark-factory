# Quickstart: Phase 2 Read Tools

**Date**: 2026-06-21

---

## Prerequisites

- Docker and Docker Compose installed
- A local clone of the target repository accessible on the host filesystem
- Context Distiller service running (or mocked for local dev)

---

## Environment variables

Create a `.env` file in the project root:

```env
# Required
GIT_REPO_PATH=/absolute/path/to/your/repo
JWT_SECRET_KEY=your-shared-secret-key-matching-other-df-services

# Optional overrides
DISTILLER_BASE_URL=http://context-distiller:8001
DISTILLER_TIMEOUT_SECONDS=10
GIT_READ_TIMEOUT_SECONDS=15
SEARCH_MAX_RESULTS=50
JWT_ALGORITHM=HS256
```

---

## Start the MCP server (Docker)

```bash
docker compose up agent-tools
```

The server communicates via stdio — it does not expose an HTTP port.

---

## Test the server interactively

```bash
mcp dev src/server.py
```

This opens the MCP Inspector UI where you can call individual tools manually.

Example — read a file:

```json
{
  "tool": "read_file",
  "arguments": {
    "path": "README.md",
    "ref": "main"
  }
}
```

Example — list Python files:

```json
{
  "tool": "list_files",
  "arguments": {
    "path": "src",
    "recursive": true,
    "pattern": "*.py"
  }
}
```

Example — search code:

```json
{
  "tool": "search_code",
  "arguments": {
    "query": "def authenticate",
    "path_filter": "src/**/*.py"
  }
}
```

---

## Run tests

```bash
pytest tests/ -v --cov=src --cov-report=term-missing
```

Coverage must be ≥ 80%. The test suite uses:
- A real temporary `git init` repo for git read tools
- `respx` mocking for Context Distiller HTTP calls

---

## Project layout

```
agent-tools/
├── src/
│   ├── server.py              # MCP server entrypoint; registers all tools
│   ├── schemas.py             # Pydantic models: ToolEnvelope, inputs, results
│   ├── config.py              # Pydantic Settings loaded from .env
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── git_read.py        # read_file, list_files, search_code, get_diff
│   │   └── document_store.py  # fetch_project_memory, fetch_adrs
│   └── utils/
│       ├── __init__.py
│       ├── envelope.py        # build_success / build_error helpers
│       ├── git_utils.py       # repo open/validate, path sanitisation
│       └── auth.py            # JWT generation for Distiller calls
├── tests/
│   ├── conftest.py            # shared fixtures: temp git repo, mock Distiller
│   ├── test_read_file.py
│   ├── test_list_files.py
│   ├── test_search_code.py
│   ├── test_get_diff.py
│   ├── test_fetch_project_memory.py
│   └── test_fetch_adrs.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```
