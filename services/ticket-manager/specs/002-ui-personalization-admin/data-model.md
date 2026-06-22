# Data Model: UI Personalization & Admin Management

**Branch**: `002-ui-personalization-admin` | **Date**: 2026-05-24

---

## Backend Schema Changes

### Modified: `users` table

One new column added via Alembic migration:

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `blocked_at` | `TIMESTAMP WITH TIME ZONE` | YES | `NULL` | Set on block, cleared on unblock. NULL = active user. |

**Full updated schema** (additions in bold):

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| `id` | `UUID` | NO | PK, default uuid4 |
| `email` | `VARCHAR(255)` | NO | UNIQUE, indexed |
| `hashed_password` | `VARCHAR(255)` | NO | bcrypt |
| `role` | `user_role` enum | NO | `administrator` \| `user` |
| `created_at` | `TIMESTAMPTZ` | NO | server default now() |
| `updated_at` | `TIMESTAMPTZ` | NO | server default now(), onupdate |
| **`blocked_at`** | **`TIMESTAMPTZ`** | **YES** | **NULL = active, non-null = blocked since** |

**Migration**: `backend/alembic/versions/XXXX_add_users_blocked_at.py`
- Up: `ALTER TABLE users ADD COLUMN blocked_at TIMESTAMP WITH TIME ZONE NULL;`
- Down: `ALTER TABLE users DROP COLUMN blocked_at;`

---

## Backend: New/Modified Python Models

### `src/models/user.py` — Updated `User` model

New field:
```python
blocked_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)
```

Helper property:
```python
@property
def is_blocked(self) -> bool:
    return self.blocked_at is not None
```

---

## Backend: New Pydantic Schemas

### `src/schemas/admin.py` (new file)

```
AdminUserResponse
  id: UUID
  email: str
  role: UserRole
  created_at: datetime
  blocked_at: datetime | None    # None = active

AdminUserCreate
  email: str                     # validated email format
  password: str                  # min 8 chars, set by admin
  role: UserRole                 # default "user"

AdminUserUpdate
  email: str | None
  role: UserRole | None

AdminUserListResponse
  items: list[AdminUserResponse]
  total: int
```

---

## Frontend: New/Modified Types

### `src/types.ts` additions

```typescript
// Extended user type for admin view
export interface AdminUserResponse {
  id: string;
  email: string;
  role: UserRole;
  created_at: string;
  blocked_at: string | null;     // null = active
}

export interface AdminUserCreate {
  email: string;
  password: string;
  role: UserRole;
}

export interface AdminUserUpdate {
  email?: string;
  role?: UserRole;
}
```

---

## Frontend: Browser-Persisted State

These are not database entities — they live in `localStorage` only.

### Language Preference

| Key | `lang` |
|-----|--------|
| Type | `string` |
| Allowed values | `"en"` \| `"ru"` \| `"es"` |
| Default | `"en"` |
| Written by | `LanguageSwitcher` component |
| Read by | `i18next` initialisation in `src/i18n.ts` |

### Color Scheme

| Key | `theme` |
|-----|---------|
| Type | `string` |
| Allowed values | `"light"` \| `"dark"` \| `"solarized"` \| `"oceanic"` \| `"high-contrast"` \| `"warm"` |
| Default | `"light"` |
| Written by | `ThemeSwitcher` component via `useTheme` hook |
| Read by | `useTheme` hook on app mount; applied as `document.documentElement.dataset.theme` |

---

## Frontend: CSS Theme Variables

Each theme defines the following CSS custom properties in `src/styles/themes.css`:

| Variable | Usage |
|----------|-------|
| `--color-bg` | Page background |
| `--color-surface` | Card / panel background |
| `--color-border` | Borders and dividers |
| `--color-text-primary` | Primary text |
| `--color-text-secondary` | Muted / secondary text |
| `--color-text-inverse` | Text on coloured backgrounds |
| `--color-accent` | Buttons, links, active states |
| `--color-accent-hover` | Button hover state |
| `--color-danger` | Destructive action indicators |
| `--color-success` | Positive status indicators |
| `--color-warning` | Warning status indicators |

All contrast ratios are verified ≥ 4.5:1 (WCAG 2.1 AA) for `--color-text-primary` on `--color-bg` and on `--color-surface`.

---

## State Transitions: User `blocked_at`

```
         block(admin)
active ─────────────────► blocked
(blocked_at = NULL)        (blocked_at = now())

         unblock(admin)
blocked ────────────────► active
(blocked_at = non-null)    (blocked_at = NULL)
```

**Invariant**: An admin cannot transition their own account to `blocked`.

---

## Entities Not Changed by This Feature

- `tickets`, `ticket_assignments`, `progress_updates`, `ticket_events`, `projects`, `refresh_tokens` — no schema changes required.
- `tags` — no changes.
