# Data Model: Phase 2 Read Tools

**Date**: 2026-06-21

This document describes the input/output schemas and key internal types.
There is no persistent storage in Phase 2; all entities are in-memory request/response structures.

---

## 1. Universal Tool Envelope

Every tool returns this structure. Defined in `src/schemas.py`.

```
ToolEnvelope
├── tool: str                  # tool name, e.g. "read_file"
├── success: bool
├── result: dict | None        # None on failure
├── error: ToolError | None    # None on success
├── duration_ms: int           # wall-clock time of the tool call
└── timestamp: str             # ISO 8601 UTC, e.g. "2026-06-21T10:00:00Z"

ToolError
├── code: str                  # one of the defined error codes
├── message: str               # human-readable description
└── retryable: bool
```

**Error codes (Phase 2 exhaustive list)**:

| Code | Retryable |
|---|---|
| `FILE_NOT_FOUND` | false |
| `REF_NOT_FOUND` | false |
| `REPO_NOT_CONFIGURED` | false |
| `SEARCH_TIMEOUT` | true |
| `MEMORY_NOT_FOUND` | false |
| `DISTILLER_UNAVAILABLE` | true |
| `TIMEOUT` | true |
| `AUTH_FAILED` | false |
| `INVALID_INPUT` | false |

---

## 2. Git Read Tool Schemas

### read_file

```
ReadFileInput
├── path: str                  # relative to repo root; must not traverse above root
└── ref: str = "main"          # git branch, tag, or commit SHA

ReadFileResult
├── content: str               # decoded file content (UTF-8)
├── size_bytes: int            # raw byte size of the blob
└── language: str              # inferred from extension; "unknown" if not recognised
```

**Language inference table (representative)**:

| Extension | language |
|---|---|
| `.py` | `python` |
| `.ts`, `.tsx` | `typescript` |
| `.js`, `.jsx` | `javascript` |
| `.md` | `markdown` |
| `.yml`, `.yaml` | `yaml` |
| `.json` | `json` |
| `.sh` | `shell` |
| `.dockerfile`, `Dockerfile` | `dockerfile` |
| (binary detected) | `binary` |
| (unknown) | `unknown` |

---

### list_files

```
ListFilesInput
├── path: str                  # directory path relative to repo root
├── recursive: bool = False
└── pattern: str = ""          # glob pattern; "" means all files

ListFilesResult
└── files: list[str]           # paths relative to repo root, sorted
```

---

### search_code

```
SearchCodeInput
├── query: str                 # search string; must be non-empty
├── path_filter: str = ""      # glob to restrict scope, e.g. "src/**/*.py"
├── case_sensitive: bool = False
└── max_results: int = 50      # hard cap [1, 50]

SearchCodeResult
├── matches: list[SearchMatch]
└── truncated: bool            # true if results were capped

SearchMatch
├── file: str                  # path relative to repo root
├── line: int                  # 1-indexed line number
└── content: str               # the matching line (stripped)
```

---

### get_diff

```
GetDiffInput
├── base_ref: str              # e.g. "main"
├── head_ref: str              # e.g. "feature/my-branch"
└── path_filter: str = ""      # optional glob

GetDiffResult
├── diff: str                  # unified diff format
├── files_changed: list[str]   # relative paths of modified files
└── stats: DiffStats

DiffStats
├── additions: int
├── deletions: int
└── files: int
```

---

## 3. Document Store Tool Schemas

### fetch_project_memory

```
FetchProjectMemoryInput
├── project_id: str            # identifier matching Context Distiller's project_id
├── ticket_id: str = ""        # optional; included in JWT context if provided
└── max_tokens: int = 2000     # character budget = max_tokens * 4

FetchProjectMemoryResult
├── memory: str                # YAML-formatted memory string (may be truncated)
└── source_ticket_ids: list[str]  # [last_ticket_id] or [] if empty
```

---

### fetch_adrs

```
FetchAdrsInput
├── project_id: str
├── status_filter: str = "accepted"   # "accepted" | "proposed" | "all"
└── domain_filter: str = ""           # substring matched against title + summary

FetchAdrsResult
└── adrs: list[AdrSummary]

AdrSummary
├── id: str
├── title: str
├── status: str                # "accepted" | "proposed" | "superseded"
├── summary: str
└── date: str                  # ISO 8601 date string from created_at
```

---

## 4. Internal Configuration Model

Loaded once at server startup via Pydantic Settings from environment.

```
Settings
├── git_repo_path: str          # required; absolute path to local repo clone
├── git_read_timeout_seconds: int = 15
├── search_max_results: int = 50
├── distiller_base_url: str = "http://context-distiller:8001"
├── distiller_timeout_seconds: int = 10
├── jwt_secret_key: str         # required
└── jwt_algorithm: str = "HS256"
```
