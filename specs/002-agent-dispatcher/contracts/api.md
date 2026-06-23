# API Contracts: Agent Dispatcher Service

**Feature**: `002-agent-dispatcher`
**Base URL (internal)**: `http://agent-dispatcher:8000`
**Base URL (dev override)**: `http://localhost:8006`
**Auth**: Bearer JWT (same `JWT_SECRET_KEY` as all other services)

---

## GET /api/health

Returns service health and runner mode. No authentication required.

**Response 200**:
```json
{
  "status": "ok",
  "runner_mode": "claude_code"
}
```

---

## GET /api/v1/runs

Returns paginated list of agent runs. Auth required.

**Query parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ticket_id` | string | — | Filter by ticket ID |
| `status` | string | — | Filter by run status |
| `offset` | integer | 0 | Pagination offset |
| `limit` | integer | 50 | Page size (max 200) |

**Response 200**:
```json
{
  "items": [
    {
      "id": "uuid",
      "ticket_id": "TKT-001",
      "project_id": "proj-123",
      "agent_id": "backend",
      "runner_mode": "claude_code",
      "status": "completed",
      "round_number": 1,
      "brainstorm_session_id": null,
      "raw_output": null,
      "result": {
        "status": "completed",
        "summary": "Implemented login endpoint",
        "artifacts": ["services/agent-dispatcher/src/api/v1/runs.py"],
        "tm_comment": "Done. Added GET /api/v1/runs endpoint.",
        "brainstorm_consensus": null,
        "errors": []
      },
      "error_message": null,
      "started_at": "2026-06-22T10:00:00Z",
      "finished_at": "2026-06-22T10:05:30Z",
      "created_at": "2026-06-22T10:00:00Z"
    }
  ],
  "total": 1
}
```

Note: `raw_output` is omitted from list responses for size reasons.

---

## GET /api/v1/runs/{run_id}

Returns a single run including `raw_output`. Auth required.

**Path parameter**: `run_id` — UUID of the run

**Response 200**: Same schema as list item but with `raw_output` populated.

**Response 404**:
```json
{
  "detail": "Run not found"
}
```

---

## Outbound Calls (made by this service)

### Orchestrator — poll for assigned tickets

```
GET {ORCHESTRATOR_BASE_URL}/api/v1/jobs/pending-tickets
Authorization: Bearer {SERVICE_JWT}
```

**Expected response**:
```json
{
  "tickets": [
    {
      "id": "TKT-001",
      "project_id": "proj-123",
      "assigned_agent": "backend",
      "fsm_status": "implementation",
      "ticket_type": "feature",
      ...
    }
  ]
}
```

Tickets without `assigned_agent` are filtered client-side.

### Orchestrator — trigger evaluation

```
POST {ORCHESTRATOR_BASE_URL}/api/v1/jobs/trigger
Authorization: Bearer {SERVICE_JWT}
Content-Type: application/json

{
  "ticket_id": "TKT-001",
  "project_id": "proj-123"
}
```

Retried once on failure. Raises on second failure.

### Ticket Manager — post comment

```
POST {TICKET_MANAGER_BASE_URL}/api/projects/{project_id}/tickets/{ticket_id}/comments
Authorization: Bearer {SERVICE_JWT}
Content-Type: application/json

{
  "content": "Agent backend completed implementation. See summary below..."
}
```

Failure is logged and not re-raised (graceful degradation). The Orchestrator trigger
still proceeds even if TM comment fails.

### Context Distiller — project memory

```
GET {CONTEXT_DISTILLER_BASE_URL}/memory/{project_id}
Authorization: Bearer {SERVICE_JWT}
```

404 and network errors treated as "empty section". Timeout: 5 seconds.

### Context Distiller — ADRs

```
GET {CONTEXT_DISTILLER_BASE_URL}/memory/{project_id}/adrs
Authorization: Bearer {SERVICE_JWT}
```

Failure treated as empty section. Timeout: 5 seconds.

### Context Distiller — agent config

```
GET {CONTEXT_DISTILLER_BASE_URL}/memory/{project_id}/agent-config
Authorization: Bearer {SERVICE_JWT}
```

Failure treated as no overrides. Timeout: 5 seconds.

---

## Agent Context Document Contract

The context string passed to every agent (as positional argument to `claude --print` or
as the `user` message in API mode) is a UTF-8 Markdown document with the following
mandatory sections, in this order:

```markdown
# Agent Task

## Your Role
{contents of prompts/{agent_id}.md}

## Ticket
- **ID**: {ticket_id}
- **Title**: {ticket.title}
- **Type**: {ticket.ticket_type}
- **Project**: {ticket.project_id}

## Description
{ticket.description}

## Your Constraints
{agent_briefing.constraints}
{project_agent_config_overrides}

## Relevant Files
{agent_briefing.relevant_files}

## Project Context
{project_memory — truncated to CONTEXT_MAX_TOKENS words}

## Active ADRs
{adr summaries — omitted if none}

## Brainstorm Project
(Only for architecture_review tickets)
Project name: df-{ticket_id}
Round: {round_number} of {max_rounds}
Previous agent messages are available in the brainstorm project.

## Task Manager Access
TM API: {TM_BASE_URL}
Your service token: {SERVICE_JWT}
Ticket: {ticket_id} in project {project_id}

## Completion and Metrics Reporting
After completing your task:

1. Run the metrics script:
   bash development/scripts/report-task-metrics.sh \
     --feature-name "{project_id}" \
     --task-id "{ticket_id}" \
     --task-description "<brief summary>" \
     --time-spent-seconds <seconds> \
     --tokens-spent <tokens> \
     --model-used "<model-id>" \
     --token-source "estimated"

2. Send a brainstorm message to project-administrator:
   payload: { "type": "task-metrics", "feature_name": "...", "task_id": "...",
              "task_description": "...", "time_spent_seconds": 0,
              "tokens_spent": 0, "model_used": "...", "token_source": "estimated" }

3. End your response with a result block:

[RESULT]
{
  "status": "completed | needs_review | blocked",
  "summary": "What was accomplished (max 500 chars)",
  "artifacts": ["relative/path/to/file.py"],
  "tm_comment": "Comment to post on the TM ticket",
  "brainstorm_consensus": null,
  "errors": []
}
[/RESULT]
```

The `SERVICE_JWT` injected into the context under "Task Manager Access" MUST NOT be
persisted in `agent_runs.context_snapshot` or `agent_runs.raw_output`. The Dispatcher
strips it before storage.

---

## `[RESULT]` Block Parse Contract

The result parser (`src/services/result_parser.py`) extracts the last occurrence of
`[RESULT]...[/RESULT]` from agent stdout. Valid JSON within the block is parsed into
`AgentResult`. On any failure:

| Failure | Behavior |
|---------|---------|
| No `[RESULT]` block found | `status=needs_review`, `tm_comment=stdout[:2000]` |
| Invalid JSON in block | `status=needs_review`, `tm_comment=stdout[:2000]` |
| `status` field missing | Default to `needs_review` |
| `status` value unrecognised | Default to `needs_review` |
| `brainstorm_consensus: "agreed"` | Session concludes early |

Parser never raises. All errors are logged at WARNING level.
