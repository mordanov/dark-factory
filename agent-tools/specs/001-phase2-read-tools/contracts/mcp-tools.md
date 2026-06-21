# MCP Tool Contracts — Phase 2 Read Tools

**Date**: 2026-06-21

These contracts define the exact input/output schemas for each MCP tool as
registered with `@mcp.tool()`. They are the source of truth for agent callers.

---

## Tool: read_file

**Description**: Read the content of a file from the repository at a given git ref.

**Input schema**:

| Parameter | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `path` | string | yes | — | Relative to repo root; no `..` after normalisation |
| `ref` | string | no | `"main"` | Branch name, tag, or commit SHA |

**Output result** (on success):

| Field | Type | Description |
|---|---|---|
| `content` | string | UTF-8 decoded file content |
| `size_bytes` | integer | Raw byte size of the blob |
| `language` | string | Inferred from extension; `"unknown"` if unrecognised |

**Error codes**: `FILE_NOT_FOUND`, `REF_NOT_FOUND`, `REPO_NOT_CONFIGURED`, `INVALID_INPUT`, `TIMEOUT`

---

## Tool: list_files

**Description**: List files in a repository directory, optionally filtered by glob pattern.

**Input schema**:

| Parameter | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `path` | string | yes | — | Directory path relative to repo root; no `..` |
| `recursive` | boolean | no | `false` | |
| `pattern` | string | no | `""` | Glob pattern, e.g. `"*.py"`; empty means all |

**Output result** (on success):

| Field | Type | Description |
|---|---|---|
| `files` | list[string] | Paths relative to repo root, sorted |

**Error codes**: `FILE_NOT_FOUND`, `REF_NOT_FOUND`, `REPO_NOT_CONFIGURED`, `INVALID_INPUT`, `TIMEOUT`

---

## Tool: search_code

**Description**: Search repository content for a string or pattern (grep-like).

**Input schema**:

| Parameter | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `query` | string | yes | — | Must be non-empty |
| `path_filter` | string | no | `""` | Glob to restrict search scope |
| `case_sensitive` | boolean | no | `false` | |
| `max_results` | integer | no | `50` | Range: [1, 50]; hard cap |

**Output result** (on success):

| Field | Type | Description |
|---|---|---|
| `matches` | list[Match] | Each match: `{ file: str, line: int, content: str }` |
| `truncated` | boolean | `true` if results were capped at `max_results` |

**Error codes**: `REPO_NOT_CONFIGURED`, `INVALID_INPUT`, `SEARCH_TIMEOUT`, `TIMEOUT`

---

## Tool: get_diff

**Description**: Retrieve the unified diff between two git refs.

**Input schema**:

| Parameter | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `base_ref` | string | yes | — | Branch, tag, or commit SHA |
| `head_ref` | string | yes | — | Branch, tag, or commit SHA |
| `path_filter` | string | no | `""` | Optional glob to restrict diff scope |

**Output result** (on success):

| Field | Type | Description |
|---|---|---|
| `diff` | string | Unified diff format |
| `files_changed` | list[string] | Relative paths of modified files |
| `stats` | object | `{ additions: int, deletions: int, files: int }` |

**Error codes**: `REF_NOT_FOUND`, `REPO_NOT_CONFIGURED`, `INVALID_INPUT`, `TIMEOUT`

---

## Tool: fetch_project_memory

**Description**: Retrieve compressed project memory from the Context Distiller service.

**Input schema**:

| Parameter | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `project_id` | string | yes | — | |
| `ticket_id` | string | no | `""` | Used for relevance context in JWT payload |
| `max_tokens` | integer | no | `2000` | Character budget = `max_tokens × 4` |

**Output result** (on success):

| Field | Type | Description |
|---|---|---|
| `memory` | string | YAML-formatted memory string (may end with `# [TRUNCATED]`) |
| `source_ticket_ids` | list[string] | Contributing ticket IDs |

**Upstream call**: `GET {DISTILLER_BASE_URL}/api/v1/memory/{project_id}`

**Error codes**: `MEMORY_NOT_FOUND`, `DISTILLER_UNAVAILABLE`, `AUTH_FAILED`, `TIMEOUT`

---

## Tool: fetch_adrs

**Description**: Retrieve architectural decision records from the Context Distiller service.

**Input schema**:

| Parameter | Type | Required | Default | Constraints |
|---|---|---|---|---|
| `project_id` | string | yes | — | |
| `status_filter` | string | no | `"accepted"` | `"accepted"` \| `"proposed"` \| `"all"` |
| `domain_filter` | string | no | `""` | Substring matched against title + summary |

**Output result** (on success):

| Field | Type | Description |
|---|---|---|
| `adrs` | list[AdrSummary] | Each summary: `{ id, title, status, summary, date }` |

**Upstream call**: `GET {DISTILLER_BASE_URL}/api/v1/memory/{project_id}/adrs?status={status}`
`domain_filter` applied client-side after fetch.

**Error codes**: `DISTILLER_UNAVAILABLE`, `AUTH_FAILED`, `TIMEOUT`

---

## Envelope Contract (all tools)

```json
{
  "tool": "<tool_name>",
  "success": true,
  "result": { },
  "error": null,
  "duration_ms": 42,
  "timestamp": "2026-06-21T10:00:00Z"
}
```

On failure:

```json
{
  "tool": "<tool_name>",
  "success": false,
  "result": null,
  "error": {
    "code": "FILE_NOT_FOUND",
    "message": "Path 'src/missing.py' not found at ref 'main'",
    "retryable": false
  },
  "duration_ms": 5,
  "timestamp": "2026-06-21T10:00:00Z"
}
```
