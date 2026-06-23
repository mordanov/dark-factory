# Data Model: Project Groups, Assignee-Only Transitions, and Tokens Spent

**Feature**: `006-project-groups-transitions-tokens` | **Date**: 2026-06-23

## New Table: `project_groups`

### Schema

```sql
CREATE TABLE project_groups (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    identifier  VARCHAR(8)  NOT NULL UNIQUE,     -- 4–8 uppercase alphanumeric (e.g. DEFAULT, TEAM1)
    name        VARCHAR(255) NOT NULL,            -- human-readable display name
    description TEXT,                             -- optional description
    is_system   BOOLEAN     NOT NULL DEFAULT FALSE, -- TRUE for DEFAULT group (undeletable)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### ORM Model (`src/models/project_group.py`)

```python
class ProjectGroup(Base):
    __tablename__ = "project_groups"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    identifier: Mapped[str] = mapped_column(String(8), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # back-reference
    projects: Mapped[list["Project"]] = relationship("Project", back_populates="group")
```

### Validation Rules

- `identifier`: strip whitespace, `.upper()`, then validate `^[A-Z0-9]{4,8}$`
- Identifier uniqueness: enforced by UNIQUE constraint + service-layer 409 on IntegrityError
- `is_system = TRUE` → deletion blocked with 409 ("Default group cannot be deleted")
- Non-empty `projects` → deletion blocked with 409 ("Group still has projects; reassign them first")

### Seeded Rows (migration 017)

| identifier | name      | description                        | is_system |
|------------|-----------|------------------------------------|-----------|
| `DEFAULT`  | `Default` | Default group for ungrouped projects | TRUE      |

---

## Modified Table: `projects`

### New Column

```sql
ALTER TABLE projects
    ADD COLUMN group_id UUID REFERENCES project_groups(id) ON DELETE RESTRICT;
-- Then backfill: UPDATE projects SET group_id = <DEFAULT_group_id>
-- Then: ALTER TABLE projects ALTER COLUMN group_id SET NOT NULL;
```

### ORM Change (`src/models/project.py`)

```python
# New column
group_id: Mapped[UUID] = mapped_column(ForeignKey("project_groups.id"), nullable=False)

# New relationship
group: Mapped["ProjectGroup"] = relationship("ProjectGroup", back_populates="projects", lazy="joined")
```

### Behaviour

- `group_id` is `NOT NULL` after migration (all existing rows backfilled to DEFAULT).
- On `POST /api/v1/projects`: if `group_id` omitted → assign DEFAULT group id automatically.
- `ON DELETE RESTRICT` prevents group deletion when projects reference it.

---

## Modified Table: `tickets`

### New Column

```sql
ALTER TABLE tickets
    ADD COLUMN tokens_spent INTEGER NOT NULL DEFAULT 0 CHECK (tokens_spent >= 0);
```

### ORM Change (`src/models/ticket.py`)

```python
tokens_spent: Mapped[int] = mapped_column(
    Integer,
    nullable=False,
    default=0,
    server_default="0",
)
```

### Behaviour

- Initialised to `0` for all existing and new tickets (no backfill needed — DEFAULT 0).
- Only incrementable via `POST /api/v1/tickets/{id}/tokens-spent`.
- Direct assignment of `tokens_spent` via `PATCH /api/v1/tickets/{id}` MUST NOT be possible;
  `TicketUpdate` schema does not include this field.
- CHECK constraint ensures DB-level non-negativity.

---

## New Schemas

### `project_group.py`

```python
class ProjectGroupCreate(BaseModel):
    identifier: str            # 4–8 chars, normalized to uppercase in service
    name: str
    description: str | None = None

class ProjectGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    # identifier is immutable after creation

class ProjectGroupResponse(BaseModel):
    id: UUID
    identifier: str
    name: str
    description: str | None
    is_system: bool
    created_at: datetime
    project_count: int         # computed: how many projects in this group

    model_config = ConfigDict(from_attributes=True)

class ProjectGroupListResponse(BaseModel):
    items: list[ProjectGroupResponse]
    total: int
```

### Modified `project.py`

```python
class ProjectCreate(BaseModel):
    name: str
    code: str | None = None    # existing, regex: ^[A-Z]{4}-\d{3}$
    group_id: UUID | None = None  # NEW: auto-defaults to DEFAULT group if omitted

class ProjectResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    code: str | None
    group_id: UUID             # NEW
    group: ProjectGroupResponse  # NEW — nested, always populated (lazy="joined")
    created_at: datetime
    ticket_counts: ProjectTicketCounts
```

### Modified `ticket.py`

```python
class TicketResponse(BaseModel):
    # ... existing fields ...
    tokens_consumed: int       # existing (system-driven)
    tokens_spent: int          # NEW (user-driven)

class TokensSpentIncrementRequest(BaseModel):
    amount: int                # MUST be > 0; validated in schema + service

class TokensSpentIncrementResponse(BaseModel):
    ticket_id: UUID
    tokens_spent: int          # new total after increment
    amount_added: int
    event_id: UUID             # id of the TicketEvent emitted
```

---

## New TicketEvent Type

### `ticket.tokens_spent_incremented`

Emitted by `tokens_spent_service.increment_tokens_spent()`.

```json
{
  "event_type": "ticket.tokens_spent_incremented",
  "actor_id": "<user_id>",
  "actor_role": "user | administrator",
  "ticket_id": "<ticket_id>",
  "prev_state": { "tokens_spent": 500 },
  "new_state":  { "tokens_spent": 700 },
  "metadata":   { "amount": 200 }
}
```

---

## Transition Service: Removed Lines

**File**: `src/services/transition_service.py`

Lines **53–86** (progress gate + TransitionBlockedError raise) are removed.
The function signature, row locking, assignee check (lines 41–46), status update, and
`ticket.status_changed` event emission remain unchanged.

Before (removed block):
```python
progress_result = await session.execute(
    select(ProgressUpdate).where(ProgressUpdate.ticket_id == ticket_id)
)
progress_user_ids = {pu.user_id for pu in progress_result.scalars().all()}
missing: list[MissingUpdate] = []
for assignment in all_assignments:
    if assignment.user_id not in progress_user_ids:
        user = await session.get(User, assignment.user_id)
        if user:
            missing.append(MissingUpdate(user_id=assignment.user_id, email=user.email))
if missing:
    async with session.begin_nested():
        event = TicketEvent(
            ticket_id=ticket_id,
            event_type="ticket.transition_blocked",
            actor_id=actor.id,
            actor_role=actor.role,
            metadata_={"missing_updates": [m.model_dump() for m in missing]},
        )
        session.add(event)
    await session.commit()
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=TransitionBlockedError(missing_updates=missing).model_dump(),
    )
```

The `TransitionBlockedError` schema and `MissingUpdate` schema are no longer used by transitions;
they can be retained for backward compatibility or removed in a follow-up cleanup.

---

## Migration Files

### 017_add_project_groups.py (summary)

```python
# upgrade():
# 1. Create project_groups table
op.create_table("project_groups", ...)
# 2. Seed DEFAULT group — capture its generated UUID
conn = op.get_bind()
default_id = conn.execute(
    sa.text("INSERT INTO project_groups (identifier, name, is_system) "
            "VALUES ('DEFAULT', 'Default', TRUE) RETURNING id")
).scalar()
# 3. Add group_id as nullable
op.add_column("projects", sa.Column("group_id", PGUUID, nullable=True))
# 4. Backfill
op.execute(sa.text(f"UPDATE projects SET group_id = '{default_id}'"))
# 5. Set NOT NULL
op.alter_column("projects", "group_id", nullable=False)
# 6. Add FK
op.create_foreign_key("fk_projects_group_id", "projects", "project_groups", ["group_id"], ["id"])

# downgrade():
op.drop_constraint("fk_projects_group_id", "projects", type_="foreignkey")
op.drop_column("projects", "group_id")
op.drop_table("project_groups")
```

### 018_add_tokens_spent.py (summary)

```python
# upgrade():
op.add_column("tickets", sa.Column("tokens_spent", sa.Integer, nullable=False,
              server_default="0"))
op.create_check_constraint("ck_tickets_tokens_spent_non_negative",
                           "tickets", "tokens_spent >= 0")

# downgrade():
op.drop_constraint("ck_tickets_tokens_spent_non_negative", "tickets", type_="check")
op.drop_column("tickets", "tokens_spent")
```
