# API Contract: ContextDistiller Service v1

**Base URL**: `http://context-distiller:8000` (Docker Compose network)
**Auth**: All endpoints except `/api/health` require `Authorization: Bearer <token>`
  (Prompt Studio JWT, HS256, validated against `JWT_SECRET_KEY`).

---

## POST /distill

Enqueue a distillation job. Returns immediately (202) — does not wait for the LLM.

**Request**
```json
{
  "ticket_id": "string",
  "project_id": "string"
}
```

**Response 202**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response 401** — missing or invalid JWT
**Response 422** — missing required fields

---

## GET /status/{job_id}

Poll job status. `error` is null unless status is `failed`.

**Response 200**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending | running | done | failed",
  "error": null
}
```

**Response 404** — job_id not found
**Response 401** — invalid JWT

---

## GET /memory/{project_id}

Retrieve the current project memory document.

**Response 200**
```json
{
  "project_id": "my-project",
  "content": "project_id: my-project\nlast_updated: ...\n...",
  "version": 12,
  "last_ticket_id": "TICKET-042",
  "updated_at": "2026-06-20T12:00:00Z"
}
```

**Response 404** — no memory exists for this project yet
**Response 401** — invalid JWT

---

## GET /memory/{project_id}/adrs

List ADRs for a project. Default filter is `accepted`.

**Query parameters**
- `status` (optional): `accepted` | `proposed` | `superseded` | `all` — default: `accepted`

**Response 200**
```json
{
  "adrs": [
    {
      "id": "ADR-001",
      "title": "Use PostgreSQL for async job queue",
      "status": "accepted",
      "summary": "PostgreSQL LISTEN/NOTIFY replaces Redis for job delivery.",
      "ticket_id": "TICKET-010",
      "created_at": "2026-05-01T09:00:00Z"
    }
  ]
}
```

**Response 401** — invalid JWT

---

## POST /memory/{project_id}/adrs

Create a new, immutable ADR. Content is write-once after creation.
Auto-generates the `ADR-NNN` identifier.

**Request**
```json
{
  "content": "# ADR-001: Use PostgreSQL for job queue\n\n## Status\nproposed\n\n## Decision\n...",
  "ticket_id": "TICKET-010",
  "title": "Use PostgreSQL for async job queue",
  "summary": "PostgreSQL LISTEN/NOTIFY replaces Redis for job delivery."
}
```

**Response 201**
```json
{
  "adr_id": "ADR-001"
}
```

**Response 401** — invalid JWT
**Response 422** — missing required fields

---

## PATCH /memory/{project_id}/adrs/{adr_id}/status

Transition an ADR's status. Only valid transitions are permitted.

**Request**
```json
{
  "status": "accepted"
}
```

**Valid transitions**:
- `proposed` → `accepted`
- `proposed` → `superseded`
- `accepted` → `superseded`

**Response 200**
```json
{
  "adr_id": "ADR-001",
  "status": "accepted"
}
```

**Response 404** — ADR not found
**Response 409** — invalid status transition
**Response 401** — invalid JWT

---

## GET /api/health

No authentication required.

**Response 200**
```json
{
  "status": "ok"
}
```
