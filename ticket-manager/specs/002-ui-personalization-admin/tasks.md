---
description: "Task list for UI Personalization & Admin Management — multi-agent execution via run-agents.sh"
---

# Tasks: UI Personalization & Admin Management

**Input**: Design documents from `/specs/002-ui-personalization-admin/`
**Prerequisites**: plan.md ✅ · spec.md ✅ · research.md ✅ · data-model.md ✅ · contracts/openapi-admin.yaml ✅ · quickstart.md ✅

---

## Brainstorm MCP Coordination

This task list is designed for multi-agent parallel execution. Before starting:

1. Run `bash run-agents.sh` from the project root — launches all nine agents in separate terminals, wired via Brainstorm MCP.
2. **product-manager** is coordinator and drives milestone order.
3. **Read first**: `specs/002-ui-personalization-admin/spec.md`, `plan.md`, `data-model.md`, `research.md`, and `contracts/openapi-admin.yaml`.
4. **Claim tasks**: broadcast via Brainstorm which task ID you are starting.
5. **Handoff**: when a task is done, post a summary and mark any tasks you unblock.
6. **[SECURITY-CRITICAL] gate** (T008): `security-architect` MUST review and post APPROVED before Phase 4 frontend US2 work may begin.
7. **[REVIEW] gate** (T030–T031): `code-reviewer` must post APPROVE or CHANGES REQUESTED before Phase 7 is considered done.

### Agent → Task Tag Mapping

| Agent | Claims tasks tagged |
|-------|-------------------|
| `product-manager` | `[PM]` — milestone tracking, coordinator |
| `software-architect` | `[ARCH]` |
| `security-architect` | `[SECURITY]`, reviews all `[SECURITY-CRITICAL]` |
| `backend` | `[BACKEND]`, `[DATA]` |
| `frontend` | `[FRONTEND]` |
| `devops` | `[PLATFORM]` |
| `code-reviewer` | `[REVIEW]` |
| `autotester` | `[TEST]` |
| `project-administrator` | records metrics after every task |

---

## Format: `[ID] [P?] [Story?] [ROLE] [SECURITY-CRITICAL?] Description — file path`

- **[P]**: safe to run in parallel with other [P] tasks in the same phase
- **[US#]**: user story from spec.md (US1 = i18n, US2 = admin users, US3 = URL nav, US4 = themes)
- **[ROLE]**: agent responsible (see table above)
- **[SECURITY-CRITICAL]**: must be reviewed by security-architect before downstream work starts

---

## Phase 1: Setup

**Purpose**: Backend model change + migration + frontend i18n dependency — foundational for all stories.

- [ ] T001 [BACKEND] Add `blocked_at: Mapped[datetime | None]` field and `is_blocked` property to `User` model — `backend/src/models/user.py`
- [ ] T002 [DATA] Create Alembic migration adding `blocked_at TIMESTAMPTZ NULL` column to `users` table with `downgrade()` path — `backend/alembic/versions/XXXX_add_users_blocked_at.py`
- [ ] T003 [P] [FRONTEND] Install `i18next` and `react-i18next` in `frontend/package.json`; create `frontend/src/i18n.ts` initialising i18next with `localStorage` key `lang`, default `en`, fallback `en`, and JSON file backend

**Checkpoint**: User model updated, migration ready, i18next installed. All agents can proceed.

---

## Phase 2: Foundational — Admin Backend (Blocking for US2)

**Purpose**: Backend admin API must be complete and security-approved before US2 frontend work starts.

> **⚠ CRITICAL**: Phase 4 (US2 frontend) MUST NOT start until T008 security-architect review is APPROVED.

- [ ] T004 [BACKEND] Create `AdminUserResponse`, `AdminUserCreate`, `AdminUserUpdate` Pydantic schemas — `backend/src/schemas/admin.py`
- [ ] T005 [BACKEND] Create `AdminService` with `create_user`, `update_user`, `block_user`, `unblock_user` methods and `structlog` audit events (event_type, actor_id, target_user_id, action) — `backend/src/services/admin_service.py`
- [ ] T006 [BACKEND] Create admin API router with five endpoints per contract: `GET /admin/users`, `POST /admin/users`, `PATCH /admin/users/{id}`, `POST /admin/users/{id}/block`, `POST /admin/users/{id}/unblock` — `backend/src/api/v1/admin.py`
- [ ] T007 [BACKEND] Register admin router in `backend/src/api/v1/router.py`; add blocked-user check to login path in `backend/src/api/v1/auth.py` — returns HTTP 403 `"Your account has been blocked. Contact an administrator."` if `user.blocked_at is not None`
- [ ] T008 [SECURITY] [SECURITY-CRITICAL] Review admin endpoints for: role enforcement at service boundary (not just frontend), self-block/self-edit prevention, bcrypt password hashing for created users, structlog audit completeness, and login block enforcement — `backend/src/api/v1/admin.py`, `admin_service.py`, `auth.py`

**Checkpoint**: Admin backend live, security-approved. US2 frontend and story phases can now proceed in parallel.

---

## Phase 3: US1 — Multi-Language Interface (Priority: P1) 🎯 MVP

**Goal**: Every visible text string is translatable; users can switch language from any page; preference persists across sessions.

**Independent Test**: Switch to Russian, refresh — all text is in Russian. Switch to Spanish, close browser, reopen — Spanish is still active. `localStorage.getItem("lang")` returns `"es"`.

- [ ] T009 [FRONTEND] [US1] Create English translation source file with all visible text keys for components and pages — `frontend/src/locales/en/common.json`
- [ ] T010 [P] [FRONTEND] [US1] Create Russian translation file matching all keys from T009 — `frontend/src/locales/ru/common.json`
- [ ] T011 [P] [FRONTEND] [US1] Create Spanish translation file matching all keys from T009 — `frontend/src/locales/es/common.json`
- [ ] T012 [FRONTEND] [US1] Replace hardcoded text with `t()` calls in all ticket components: `FilterBar.tsx`, `KanbanBoard.tsx`, `KanbanCard.tsx`, `KanbanColumn.tsx`, `StatusTransitionButton.tsx`, `TagInput.tsx`, `TicketCard.tsx`, `TicketEventHistory.tsx`, `TicketForm.tsx`, `AssigneeProgressList.tsx` — `frontend/src/components/`
- [ ] T013 [FRONTEND] [US1] Replace hardcoded text with `t()` calls in all pages: `LoginPage.tsx`, `ProjectListPage.tsx`, `ProjectPage.tsx`, `TicketDetailPage.tsx` — `frontend/src/pages/`
- [ ] T014 [FRONTEND] [US1] Replace `TICKET_STATUS_LABELS`, `TICKET_TYPE_LABELS`, `TICKET_SPEC_LABELS` static maps with `t()` lookups at usage sites (these maps cannot be translated as static objects) — `frontend/src/types.ts` and component usages
- [ ] T015 [FRONTEND] [US1] Create `LanguageSwitcher` component showing EN/RU/ES options; on select writes `localStorage` and calls `i18n.changeLanguage()`; add to app header — `frontend/src/components/common/LanguageSwitcher.tsx`
- [ ] T016 [FRONTEND] [US1] Wrap `<App />` with `<I18nextProvider i18n={i18n}>` and initialise theme on mount — `frontend/src/main.tsx`

**Checkpoint**: Full language switching works. Refresh persists language. All three locales complete and consistent.

---

## Phase 4: US2 — Admin User Management (Priority: P2)

**Goal**: Admin-only page to create users, edit email/role, block and unblock users. Self-actions disabled.

**Independent Test**: Admin creates user → user can log in. Admin blocks user → user login rejected with 403. Admin unblocks → login works. Non-admin direct URL access → redirected.

> Requires Phase 2 complete (T001–T008 APPROVED) before starting.

- [ ] T017 [FRONTEND] [US2] Add `AdminUserResponse`, `AdminUserCreate`, `AdminUserUpdate` TypeScript interfaces to `frontend/src/types.ts`
- [ ] T018 [FRONTEND] [US2] Create admin API client with `listAdminUsers`, `createAdminUser`, `updateAdminUser`, `blockAdminUser`, `unblockAdminUser` functions using the existing Axios client — `frontend/src/api/admin.ts`
- [ ] T019 [P] [FRONTEND] [US2] Create `UserTable` component displaying email, role, blocked status; block/unblock and edit action buttons; own-account actions disabled — `frontend/src/components/admin/UserTable.tsx`
- [ ] T020 [P] [FRONTEND] [US2] Create `UserForm` modal component for create and edit; fields: email (required), password (create only, min 8), role select — `frontend/src/components/admin/UserForm.tsx`
- [ ] T021 [FRONTEND] [US2] Create `AdminUsersPage` using React Query (`["admin","users"]` query key) to fetch and mutate user list via T018 client; integrates `UserTable` and `UserForm`; shows loading/error/empty states — `frontend/src/pages/AdminUsersPage.tsx`
- [ ] T022 [FRONTEND] [US2] Add `/admin/users` route to router wrapped in a role guard (`currentUser.role === "administrator"`); non-admin redirect to `/projects` — `frontend/src/router.tsx`
- [ ] T023 [P] [TEST] [US2] Write contract tests for all five admin endpoints (list, create, patch, block, unblock) including 403 for non-admin and 403 for self-block — `backend/tests/contract/test_admin.py`
- [ ] T024 [P] [TEST] [US2] Write integration test: create user → block → attempt login → expect 403 → unblock → login succeeds — `backend/tests/integration/test_auth_blocked.py`

**Checkpoint**: Admin page fully functional. Backend contract tests and integration tests pass.

---

## Phase 5: US3 — Persistent URL Navigation (Priority: P2)

**Goal**: Board/list view state encoded in URL; refresh restores the same view; URLs are shareable.

**Independent Test**: Navigate to board, copy URL, open in new tab → board shown. Refresh list view → list shown. Browser back/forward syncs URL and view.

- [ ] T025 [FRONTEND] [US3] Replace `const [view, setView] = useState<View>("list")` with `useSearchParams` — read `searchParams.get("view") ?? "list"`, write via `setSearchParams({ view }, { replace: true })` — `frontend/src/pages/ProjectPage.tsx`

**Checkpoint**: Board/list toggle persists on refresh and in shared URLs. Zero regressions in ticket list or board rendering.

---

## Phase 6: US4 — Color Scheme Selection (Priority: P3)

**Goal**: Six WCAG 2.1 AA-compliant themes; user preference persists in browser; theme applies immediately across all pages.

**Independent Test**: Select Dark theme, refresh — Dark is applied. Open DevTools → `document.documentElement.dataset.theme === "dark"`. `localStorage.getItem("theme") === "dark"`. Cycle all six schemes — each applies within 300ms.

- [ ] T026 [FRONTEND] [US4] Create CSS custom properties for all six themes (`light`, `dark`, `solarized`, `oceanic`, `high-contrast`, `warm`) using `[data-theme="X"]` selectors; variables: `--color-bg`, `--color-surface`, `--color-border`, `--color-text-primary`, `--color-text-secondary`, `--color-text-inverse`, `--color-accent`, `--color-accent-hover`, `--color-danger`, `--color-success`, `--color-warning`; all contrast ratios ≥ 4.5:1 (WCAG AA) — `frontend/src/styles/themes.css`
- [ ] T027 [FRONTEND] [US4] Create `useTheme` hook: reads `localStorage.getItem("theme") ?? "light"` on mount, sets `document.documentElement.dataset.theme`, exposes `theme` and `setTheme(key)` — `frontend/src/hooks/useTheme.ts`
- [ ] T028 [FRONTEND] [US4] Create `ThemeSwitcher` component rendering six labelled colour swatches; calls `setTheme(key)` from `useTheme` on click; highlights active scheme — `frontend/src/components/common/ThemeSwitcher.tsx`
- [ ] T029 [FRONTEND] [US4] Import `themes.css` in `frontend/src/main.tsx`; call `useTheme()` at app root to apply stored theme on load; add `ThemeSwitcher` to app header layout

**Checkpoint**: All six themes apply and persist. WCAG AA verified visually and through colour-contrast tooling.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Review gates, full test run, CI verification.

- [ ] T030 [P] [REVIEW] Review all backend changes: `user.py` (blocked_at field), migration file, `schemas/admin.py`, `services/admin_service.py`, `api/v1/admin.py`, `api/v1/auth.py` login block — verify correctness, error handling, audit logging, no secrets in responses
- [ ] T031 [P] [REVIEW] Review all frontend changes: `i18n.ts` + locale files (key completeness), admin components (UserTable, UserForm, AdminUsersPage), `ProjectPage.tsx` URL fix, `themes.css` + `useTheme`, `ThemeSwitcher`, router admin guard — verify accessibility, security (role guard not bypassable), UX correctness
- [ ] T032 [P] [TEST] Run full backend test suite and confirm zero failures — `cd backend && pytest tests/integration/ tests/contract/ -v --tb=short`
- [ ] T033 [P] [TEST] Run frontend test suite and confirm zero failures — `cd frontend && npm run test:run`
- [ ] T034 [PLATFORM] Verify CI pipeline (`pre-commit` + `backend` + `frontend` jobs) passes with updated `package.json` (i18next deps), new backend tests, and new locale JSON files

**Final Checkpoint**: All review gates APPROVED, all tests pass, CI green. Feature ready to merge.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Admin Backend)**: Requires Phase 1 complete (T001 blocks T002; T003 independent)
- **Phase 3 (US1 i18n)**: Requires T003 complete (i18n.ts installed)
- **Phase 4 (US2 Admin Frontend)**: Requires Phase 2 complete AND T008 APPROVED
- **Phase 5 (US3 URL Nav)**: Requires T003 complete (no other dependencies)
- **Phase 6 (US4 Themes)**: Requires T003 complete; independent of other stories
- **Phase 7 (Polish)**: All story phases complete

### User Story Dependencies

- **US1 (P1)**: Depends on Phase 1 only — can start after T003
- **US2 (P2)**: Backend (Phase 2) must complete first; frontend after Phase 2 security approval
- **US3 (P2)**: Fully independent of US1, US2, US4 — single file change after Phase 1
- **US4 (P3)**: Independent of all other stories — frontend-only, start any time after Phase 1

### Within Each Story

- T009 (English locale) → T010/T011 [P] (RU/ES locales) → T012/T013/T014 (component wrapping) → T015 (LanguageSwitcher) → T016 (Provider)
- T017 (types) → T018 (API client) + T019/T020 [P] (components) → T021 (page) → T022 (route); T023/T024 [P] (tests)
- T025 is a single atomic change with no sub-dependencies
- T026 (CSS) → T027 (hook) → T028 (switcher) → T029 (main.tsx wiring)

### Parallel Opportunities

| Parallel group | Tasks |
|---|---|
| Phase 1 model + frontend setup | T001 + T003 (different repos) |
| Locale files (after T009) | T010 + T011 |
| Admin components | T019 + T020 |
| Admin contract + integration tests | T023 + T024 |
| Stories US3 + US4 (any time after Phase 1) | T025 runs alongside T026–T029 |
| Final review + test runs | T030 + T031 + T032 + T033 |

---

## Parallel Example: Phase 3 (US1)

```bash
# After T009 (English keys defined):
# T010 and T011 can launch simultaneously:
Task(frontend): "Create Russian translations in frontend/src/locales/ru/common.json"
Task(frontend): "Create Spanish translations in frontend/src/locales/es/common.json"

# After T009–T011 complete, T012–T014 can all start in parallel:
Task(frontend): "Wrap ticket components with t() in frontend/src/components/"
Task(frontend): "Wrap pages with t() in frontend/src/pages/"
Task(frontend): "Replace static label maps with t() lookups in frontend/src/types.ts"
```

## Parallel Example: Phase 4 (US2)

```bash
# After T017 (types added):
# T019 and T020 can launch simultaneously:
Task(frontend): "Create UserTable component in frontend/src/components/admin/UserTable.tsx"
Task(frontend): "Create UserForm component in frontend/src/components/admin/UserForm.tsx"

# T023 and T024 can launch as soon as T007 (admin backend) is complete:
Task(autotester): "Contract tests for admin endpoints in backend/tests/contract/test_admin.py"
Task(autotester): "Integration test for blocked-user login in backend/tests/integration/test_auth_blocked.py"
```

---

## Implementation Strategy

### MVP First (US1 — i18n Only)

1. Complete Phase 1 (T001–T003)
2. Complete Phase 3 (T009–T016) — US1 i18n
3. **STOP and VALIDATE**: Language switching works end-to-end per `quickstart.md` Scenario 1
4. Demo: App fully translated in three languages

### Incremental Delivery

1. Phase 1 → Phase 3 (US1 i18n) → Deploy/Demo (MVP)
2. Phase 2 + Phase 4 (US2 admin) → Test Scenarios 4+5 → Deploy/Demo
3. Phase 5 (US3 URL routing) → Test Scenario 3 → Deploy/Demo
4. Phase 6 (US4 themes) → Test Scenario 2 → Deploy/Demo
5. Phase 7 (Polish) → CI green → Merge

### Parallel Agent Strategy (with run-agents.sh)

Once Phase 1 is complete:
- `backend` agent: executes Phase 2 (T004–T008) sequentially
- `frontend` agent: executes Phase 3 (T009–T016) in parallel with Phase 2
- `security-architect` agent: stands by for T008 review gate
- `autotester` agent: begins T023/T024 as soon as Phase 2 complete
- `frontend` agent: executes Phase 4 frontend (T017–T022) after T008 APPROVED
- `frontend` agent: executes Phase 5 (T025) and Phase 6 (T026–T029) independently

---

## Notes

- `[P]` tasks operate on different files and have no cross-task output dependencies
- `[SECURITY-CRITICAL]` tasks gate downstream work — do not skip the review
- Each user story can be independently demoed using the relevant `quickstart.md` scenario
- Locale JSON completeness (T009–T011): all three files must have identical key sets; missing keys fall back to English silently
- Admin self-protection (T006/T007): enforced in service layer, not just router — frontend guard is supplemental only
- `blocked_at` migration (T002): nullable column, zero-downtime safe
- URL state (T025): `replace: true` prevents duplicate history entries on every view toggle
