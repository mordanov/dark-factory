# Research: UI Personalization & Admin Management

**Branch**: `002-ui-personalization-admin` | **Date**: 2026-05-24

---

## Decision 1: i18n Library

**Decision**: `i18next` v24 + `react-i18next` v15

**Rationale**: De-facto standard for React/TypeScript i18n. Supports lazy-loaded namespaces, pluralization, interpolation, and TypeScript key inference. Integrates cleanly with Vite without ejecting configuration. Alternatives (Lingui, FormatJS) offer similar features but have smaller ecosystems and require more setup for this scale.

**Alternatives considered**:
- `@lingui/react` — excellent for extraction workflow, but heavier toolchain (babel macro or vite plugin required)
- `react-intl` (FormatJS) — ICU message format is powerful but verbose for simple label translations
- Custom JSON + Context — too much boilerplate for three languages across dozens of components

**Storage**: `localStorage` key `lang` (values: `en`, `ru`, `es`). Default: `en`. Fallback language: `en`.

**Translation file structure**:
```
frontend/src/locales/
├── en/common.json
├── ru/common.json
└── es/common.json
```

**Key discovery**: All existing user-visible text is hardcoded as JSX strings. Every component needs `t()` call wrapping. Labels defined in `types.ts` (`TICKET_STATUS_LABELS`, `TICKET_TYPE_LABELS`, `TICKET_SPEC_LABELS`) must be replaced with `t()` equivalents — they cannot be translated as static objects.

---

## Decision 2: Color Theme System

**Decision**: CSS custom properties (CSS variables) with a `data-theme` attribute on `<html>`

**Rationale**: Allows pure-CSS theming without JS re-renders. Every component automatically picks up theme changes when the attribute changes on the root element. Compatible with Vite/React without additional libraries. Supports WCAG 2.1 AA contrast validation at design time via color palette selection.

**6 named schemes**:
| Key | Name | Character |
|-----|------|-----------|
| `light` | Light | Default white/grey, blue accents |
| `dark` | Dark | Dark grey backgrounds, light text |
| `solarized` | Solarized | Warm beige/teal palette |
| `oceanic` | Oceanic | Deep blue backgrounds, cyan accents |
| `high-contrast` | High Contrast | Pure black/white, no colours |
| `warm` | Warm | Cream/amber backgrounds, brown text |

All six schemes use palette colors verified against WCAG 2.1 AA (minimum 4.5:1 contrast ratio for normal text, 3:1 for large text and UI components).

**Storage**: `localStorage` key `theme` (value: one of the six keys above). Default: `light`.

**Implementation pattern**:
```
frontend/src/
├── styles/
│   ├── themes.css        # :root[data-theme="X"] { --color-bg: ...; ... }
│   └── variables.css     # consumed by components
└── hooks/useTheme.ts     # reads/writes localStorage + document.documentElement.dataset.theme
```

**Alternatives considered**:
- CSS-in-JS (styled-components, Emotion) — heavier bundle, not needed given existing plain-CSS approach in the codebase
- Tailwind dark mode — project does not use Tailwind; introducing it solely for themes is out of scope
- CSS modules per theme — too much duplication; variables are cleaner

---

## Decision 3: URL View State (Board/List)

**Decision**: URL query parameter `?view=list` / `?view=board` in `/projects/:projectId`

**Rationale**: React Router v6 (already used) provides `useSearchParams` hook that reads and writes query params cleanly. This approach keeps the route stable (`/projects/abc123`) while making the view bookmarkable and refresh-safe. No routing schema changes, no new routes.

**Before (broken)**:
```tsx
const [view, setView] = useState<View>("list");  // lost on refresh
```

**After (correct)**:
```tsx
const [searchParams, setSearchParams] = useSearchParams();
const view = (searchParams.get("view") as View) ?? "list";
```

Default fallback: `list` when no `?view` param present.

**Alternatives considered**:
- Sub-routes (`/projects/:id/board`, `/projects/:id/list`) — more verbose, breaks existing ticket deep-link pattern
- Hash routing (`#board`) — not supported by `createBrowserRouter`; search params are cleaner
- localStorage per-project view memory — does not satisfy "URL is shareable" requirement

---

## Decision 4: Admin User Management API Design

**Decision**: New router at `/api/v1/admin/users` with admin-role-gated endpoints, separate from the existing `/api/v1/users` (which lists users for ticket assignment)

**Rationale**: Separation of concerns — the existing `GET /api/v1/users` is used by all authenticated users to populate assignee dropdowns. Admin CRUD operations need different payloads, responses, and access control. Keeping them in a separate namespace (`/admin/`) makes the RBAC boundary explicit and auditable.

**New endpoints**:
| Method | Path | Action |
|--------|------|--------|
| `POST` | `/api/v1/admin/users` | Create user (admin sets initial password) |
| `GET` | `/api/v1/admin/users` | List all users with `blocked_at` |
| `PATCH` | `/api/v1/admin/users/{id}` | Edit email, role |
| `POST` | `/api/v1/admin/users/{id}/block` | Block user |
| `POST` | `/api/v1/admin/users/{id}/unblock` | Unblock user |

**Alternatives considered**:
- Extending `/api/v1/users` with admin-only fields — mixes access levels, harder to test and audit
- Using `PUT` for full user replacement — `PATCH` is more appropriate for partial updates

---

## Decision 5: Blocked User Representation in Database

**Decision**: Add `blocked_at: datetime | None` column to the `users` table (nullable timestamp)

**Rationale**: Timestamp-based representation is richer than a boolean — it records *when* the user was blocked, which satisfies the audit trail requirement (Principle II). A `NULL` value means active; a non-null datetime means blocked. Reversible: unblocking sets `blocked_at = NULL`.

**Login enforcement**: `get_current_user` in `backend/src/core/security.py` is extended to check `user.blocked_at is not None` after loading the user record, raising HTTP 403. This enforces the block on the next login attempt (session tokens remain valid but login is blocked).

**Alembic migration**: A single nullable `ALTER TABLE users ADD COLUMN blocked_at TIMESTAMP NULL` migration. No down-migration risk — column is nullable and has no FK dependencies.

**Alternatives considered**:
- `is_blocked: bool` — simpler but loses the timestamp; harder to audit when blocking happened
- Separate `blocked_users` table — over-engineered for a simple flag; adds join overhead

---

## Decision 6: Admin Event Emissions (Constitution Principle II compliance)

All admin actions (create user, block, unblock, edit) MUST emit a `TicketEvent`-style audit record. Since these are not ticket events, they are recorded in a separate log using the existing `TicketEvent` model pattern: a new `admin_event` table (or reuse `ticket_event` with `ticket_id = NULL` for system events).

**Decision**: Reuse the structured logging infrastructure (Principle IX) for admin action logging, emitting `structlog` events with `event_type`, `actor_id`, `target_user_id`, and `action`. A formal database `admin_event` table is deferred to a future feature; structured logs satisfy the audit trail requirement for this iteration.

**Rationale**: Adding a new DB table for admin events is out of scope for this feature. Structured JSON logs are searchable, immutable (append-only log files), and sufficient for operational audit in this stage.
