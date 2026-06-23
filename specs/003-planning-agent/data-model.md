# Data Model: Planning Agent for Prompt Studio

**Feature**: `003-planning-agent`
**Date**: 2026-06-23

## Enum Changes

### `session_status` (existing PostgreSQL enum — extend via ALTER TYPE)

**Existing values**: `in_progress`, `approved`, `cancelled`

**New values added by migration `0002`**:
| Value | Meaning |
|-------|---------|
| `planning` | Plan generation LLM call is in progress |
| `plan_ready` | Plan generated and persisted; awaiting user review/edit |
| `plan_confirmed` | User confirmed; ticket creation started or pending |
| `tickets_created` | All tickets created successfully in Ticket Manager |

**Full lifecycle**: `in_progress` → `approved` → `planning` → `plan_ready` → `plan_confirmed` → `tickets_created`

The `cancelled` value is unchanged. Error states are tracked on `prompt_plans.status`; the
session status does not have a dedicated error value — on plan generation failure the session
stays at `approved` to allow retry.

### `plan_status` (new PostgreSQL enum — created by migration `0002`)

| Value | Meaning |
|-------|---------|
| `draft` | Plan is being generated (transient) |
| `ready` | Generation complete and validated; user can edit |
| `confirmed` | User confirmed; creation started |
| `tickets_created` | All TM tickets created |
| `error` | Generation or validation failed |

---

## New Table: `prompt_plans`

One row per `prompt_session`. A session has at most one plan at a time (UNIQUE on `session_id`).

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | UUID PK | NO | `gen_random_uuid()` | |
| `session_id` | UUID FK → `prompt_sessions(id)` ON DELETE CASCADE | NO | | UNIQUE |
| `status` | `plan_status` enum | NO | `'draft'` | |
| `plan_content` | JSONB | YES | NULL | Full plan tree; null while draft |
| `agent_config` | JSONB | YES | NULL | Per-agent overrides; null if generation failed |
| `validation_errors` | JSONB | YES | NULL | Array of error strings from last failed validation |
| `created_ticket_ids` | TEXT[] | YES | NULL | TM ticket IDs created so far (for retry) |
| `ticket_id_map` | JSONB | YES | NULL | `{ "local_id": "tm_ticket_id" }` mapping |
| `tm_epic_id` | TEXT | YES | NULL | TM ID of the created Epic |
| `created_at` | TIMESTAMPTZ | NO | `now()` | |
| `updated_at` | TIMESTAMPTZ | NO | `now()` | Auto-updated on every write |

**Indexes**:
- `UNIQUE (session_id)` — enforces one plan per session
- `INDEX (status)` — for status polling queries

---

## ORM Model: `PromptPlan`

Location: `backend/src/models/models.py` (add to existing file)

```python
PLAN_STATUS_ENUM = Enum(
    "draft", "ready", "confirmed", "tickets_created", "error",
    name="plan_status", create_type=False,
)

class PromptPlan(Base):
    __tablename__ = "prompt_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_sessions.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    status: Mapped[str] = mapped_column(PLAN_STATUS_ENUM, nullable=False, default="draft")
    plan_content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    agent_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validation_errors: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_ticket_ids: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    ticket_id_map: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tm_epic_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    session: Mapped[PromptSession] = relationship(back_populates="plan")
```

**`PromptSession` additions** (in existing model):
- Add `plan: Mapped[PromptPlan | None] = relationship(back_populates="session", uselist=False, cascade="all, delete-orphan")`
- Extend `SessionStatus` constants and the `SESSION_STATUS_ENUM` Enum with the four new values

---

## Pydantic Schemas

Location: `backend/src/schemas/schemas.py` (additions)

### Plan Tree Nodes

```python
class PlanTask(BaseModel):
    local_id: str = Field(pattern=r'^task-\d+-\d+$')
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=500)
    ticket_type: Literal["task", "implementation", "investigation"] = "task"
    complexity: Literal["S", "M", "L", "XL"] = "M"
    depends_on: list[str] = Field(default_factory=list)

class PlanStory(BaseModel):
    local_id: str = Field(pattern=r'^story-\d+$')
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=500)
    ticket_type: Literal["story"] = "story"
    tasks: list[PlanTask] = Field(min_length=0, max_length=10)

class PlanEpic(BaseModel):
    local_id: Literal["epic-1"] = "epic-1"
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(max_length=500)
    ticket_type: Literal["epic"] = "epic"

class PlanContent(BaseModel):
    epic: PlanEpic
    stories: list[PlanStory] = Field(min_length=1, max_length=10)
```

### Agent Config

```python
class AgentOverride(BaseModel):
    agent_id: str
    override_text: str

class AgentConfig(BaseModel):
    project_id: str
    tech_stack: list[str] = Field(default_factory=list)
    agent_overrides: list[AgentOverride] = Field(default_factory=list)
```

### API DTOs

```python
class PlanResponse(OrmModel):
    id: uuid.UUID
    session_id: uuid.UUID
    status: str
    plan_content: dict | None
    agent_config: dict | None
    validation_errors: list[str] | None
    created_ticket_ids: list[str] | None
    ticket_id_map: dict | None
    tm_epic_id: str | None
    created_at: datetime
    updated_at: datetime

class PlanUpdateRequest(BaseModel):
    plan_content: dict  # validated by PlanValidator before storage

class PlanStatusResponse(BaseModel):
    status: str
    created_count: int
    total: int
    errors: list[str]
```

---

## State Transition Diagram

```
Session:   in_progress → approved → planning → plan_ready → plan_confirmed → tickets_created

Plan:                              draft ----→ ready ------→ confirmed ----→ tickets_created
                                    ↓ (fail)    ↓ (regenerate)
                                   error      draft (reset)
```

- Session transitions to `planning` when generation starts; back to `approved` on generation failure (plan deleted or set to `error`).
- Plan `error` is a terminal state until the user regenerates; regeneration creates a new plan row (old `error` row replaced via upsert on `session_id`).
