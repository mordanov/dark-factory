from typing import Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------

class ToolError(BaseModel):
    code: str
    message: str
    retryable: bool


class ToolEnvelope(BaseModel):
    tool: str
    success: bool
    result: dict[str, Any] | None = None
    error: ToolError | None = None
    duration_ms: int
    timestamp: str


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------

class SearchMatch(BaseModel):
    file: str
    line: int
    content: str


class DiffStats(BaseModel):
    additions: int
    deletions: int
    files: int


class AdrSummary(BaseModel):
    id: str
    title: str
    status: str
    summary: str
    date: str


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class ReadFileInput(BaseModel):
    path: str
    ref: str = "main"


class ListFilesInput(BaseModel):
    path: str
    recursive: bool = False
    pattern: str = ""


class SearchCodeInput(BaseModel):
    query: str
    path_filter: str = ""
    case_sensitive: bool = False
    max_results: int = Field(default=50, ge=1, le=50)


class GetDiffInput(BaseModel):
    base_ref: str
    head_ref: str
    path_filter: str = ""


class FetchProjectMemoryInput(BaseModel):
    project_id: str
    ticket_id: str = ""
    max_tokens: int = 2000


class FetchAdrsInput(BaseModel):
    project_id: str
    status_filter: str = "accepted"
    domain_filter: str = ""


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

class ReadFileResult(BaseModel):
    content: str
    size_bytes: int
    language: str


class ListFilesResult(BaseModel):
    files: list[str]


class SearchCodeResult(BaseModel):
    matches: list[SearchMatch]
    truncated: bool


class GetDiffResult(BaseModel):
    diff: str
    files_changed: list[str]
    stats: DiffStats


class FetchProjectMemoryResult(BaseModel):
    memory: str
    source_ticket_ids: list[str]


class FetchAdrsResult(BaseModel):
    adrs: list[AdrSummary]
