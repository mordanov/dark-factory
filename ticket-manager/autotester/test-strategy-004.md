# Test Strategy: Frontend Design System — Feature 004

**Branch**: `004-ui-design-system` | **Date**: 2026-05-25
**Agent**: autotester
**Input**: spec.md, plan.md, data-model.md, contracts/, tasks.md

---

## Scope

This strategy covers verification of the 4 user stories and 8 success criteria for the
Frontend Design System refactor. The scope is **frontend-only** — no backend changes, no
API contracts, no schema migrations.

---

## Test Levels and Tools

| Level | Tool | Location |
|-------|------|----------|
| Frontend unit (hooks) | Vitest + renderHook | `frontend/tests/design-system/` |
| Frontend component | Vitest + React Testing Library | `frontend/tests/design-system/` |
| Frontend regression | Vitest + React Testing Library | `frontend/tests/components/`, `frontend/tests/pages/` |
| Style-prop audit | bash grep | CI gate (manual + automated) |
| Accessibility | axe-core/react (dev only) | Browser console / extension |
| Responsive layout | Chrome DevTools / manual | 375px, 768px, 1024px, 1440px |

---

## Baseline

Before any migration work, **46 tests** pass across 11 test files. This is the regression
baseline that must be maintained or updated with functional equivalence throughout the refactor.

```
Test Files  11 passed (11)
Tests  46 passed (46)
```

---

## Success Criteria Coverage Map

### SC-001: Zero mouse-only interactions — all workflows keyboard-navigable

| Test | File | Type |
|------|------|------|
| Dark mode toggle has aria-label | `Navbar.test.tsx` | Component |
| AppShell skip-to-content link focusable | `AppShell.test.tsx` | Component |
| All icon-only buttons have aria-label | `accessibility.test.tsx` | Component |
| TicketForm inputs paired with labels | `accessibility.test.tsx` | Component |
| AdminAssignModal focus trap (Radix Dialog) | `AdminAssignModal.test.tsx` | Component |
| StatusTransitionButton dialog closes on Escape | `StatusTransitionButton.test.tsx` | Component |

**Manual verification required**: Full tab-order traversal through ticket workflow (create → detail → transition → assign) without mouse.

---

### SC-002: Zero WCAG 2.1 AA violations on all pages

**Automated**: `@axe-core/react` in dev build — violations logged to console.

**Manual**: axe DevTools browser extension on each of the 5 pages:
- LoginPage
- ProjectListPage
- ProjectPage (Kanban)
- TicketDetailPage
- AdminUsersPage

**Automated test targets**:
- All `<Button size="icon">` have `aria-label` (grep check + component tests)
- All form controls have matching `<Label htmlFor>` + `id` (component tests)
- `aria-live` region present in AppShell for status announcements (component test)

---

### SC-003: Dark/light schemes applied to 100% of visible surfaces

| Test | File | Type |
|------|------|------|
| useTheme adds `.dark` class for dark/oceanic/high-contrast | `useTheme.dark-mode.test.ts` | Unit |
| useTheme removes `.dark` class for light/solarized/warm | `useTheme.dark-mode.test.ts` | Unit |
| `.dark` class applied on initial mount from localStorage | `useTheme.dark-mode.test.ts` | Unit |
| ThemeSwitcher still writes to localStorage + updates data-theme | `ThemeSwitcher.test.tsx` (existing) | Component |

**Manual verification**: Toggle dark in topbar → reload → dark persists, no flash. All overlays (Dialog, DropdownMenu, Popover) render dark.

---

### SC-004: All pages render at 375px/768px/1024px/1440px without horizontal scroll

**Manual verification required** at all 4 breakpoints for 5 pages.

**Automated tests**:
- AppShell container has responsive padding class (component test)
- Navbar hamburger button present for mobile (component test)

---

### SC-005: Zero inline `style` prop overrides

**CI gate command**:
```bash
grep -r "style=" frontend/src --include="*.tsx" | grep -v "swatch-color-required"
```
Must return zero results.

**Automated test**: `tests/design-system/no-style-props.test.ts` — runs grep via child_process
and asserts zero matches.

---

### SC-006: New features buildable from existing design system components only

**Verification**: Component library completeness check — verify all 17 shadcn components
exist in `frontend/src/components/ui/` after Phase 2.

---

### SC-007: All existing tests continue passing — zero functional regression

**Automated**: Run `npm run test` after each phase. All 46 baseline tests must pass (or be
updated with functional equivalence rationale when component APIs change — see risk table).

---

### SC-008: Initial load time ≤ 110% of pre-refactor baseline

**Manual / tooling**: Measure bundle size and LCP before and after. Acceptable if within 10%.
Not automated in Vitest — requires build + Lighthouse or `vite build --report`.

---

## Task-to-Test Mapping

### Phase 1 (Setup) — T001–T009

| Task | Test Coverage |
|------|---------------|
| T009: useTheme `.dark` class toggle | `tests/design-system/useTheme.dark-mode.test.ts` (new) |

Checkpoint: existing 46 tests pass + new T009 tests pass.

### Phase 2 (shadcn install) — T010–T013

No new functional tests. Checkpoint: `npm run typecheck` zero errors.

### Phase 3 (AppShell/Layout/Dialogs) — T014–T021

| Task | Test Coverage |
|------|---------------|
| T014: Navbar | `tests/design-system/Navbar.test.tsx` (new) |
| T015: AppShell | `tests/design-system/AppShell.test.tsx` (new) |
| T016: ProtectedRoute wraps AppShell | `tests/design-system/AppShell.test.tsx` (new) |
| T017: PageTransition | `tests/design-system/PageTransition.test.tsx` (new) |
| T018: AdminAssignModal extraction | `tests/design-system/AdminAssignModal.test.tsx` (new) |
| T019: StatusTransitionButton Dialog | `tests/components/StatusTransitionButton.test.tsx` (existing — verify no regression) |
| T020: ARIA labels on form buttons | `tests/design-system/accessibility.test.tsx` (new) |
| T021: aria-live region | `tests/design-system/AppShell.test.tsx` (new) |

### Phase 4 (Dark mode) — T022–T024

| Task | Test Coverage |
|------|---------------|
| T022: Anti-FOSC inline script | Manual: open page in browser → no flash; cannot test in jsdom |
| T023: ThemeSwitcher Tailwind migration | `tests/components/ThemeSwitcher.test.tsx` (existing — must still pass) |
| T024: Dark overlay completeness | Manual: open Dialog in dark mode |

### Phase 5 (Visual migration) — T025–T039

All phase 5 tasks are pure style migrations. The existing component tests cover functional
behavior. Key risk: **FilterBar migration to shadcn `<Select>` may break existing tests**
(see Risk Table).

| Existing test | Risk after migration | Action |
|---------------|---------------------|--------|
| `FilterBar.test.tsx` | HIGH — uses native `<select>` queries (`getByLabelText`, `selectOptions`) | Update to use `combobox` role queries after T028 |
| `ThemeSwitcher.test.tsx` | LOW — tests swatch button clicks, not style | Should pass unchanged |
| `TicketCard.test.tsx` | LOW — tests content rendering | Should pass unchanged |
| `TicketForm.test.tsx` | MEDIUM — `TicketForm` uses custom `<select>` (ticket_type, priority) → migrated to shadcn `<Select>` in T026 | Update to use `combobox` role |
| `StatusTransitionButton.test.tsx` | LOW — tests modal behavior | Verify dialog behavior preserved |
| `LoginPage.test.tsx` | LOW — tests form submission | Should pass; inputs become shadcn `<Input>` |

### Phase 6 (Responsive) — T040–T044

Manual verification at 375px/768px/1440px. No Vitest automation possible.

### Phase 7 (Polish) — T045–T047

| Task | Test Coverage |
|------|---------------|
| T045: Final style-prop audit | `tests/design-system/no-style-props.test.ts` |
| T046: Run all tests | `npm run test` — all pass |
| T047: 8 quickstart scenarios | Manual walkthrough per `quickstart.md` |

---

## Risk Table

| Risk | Severity | Mitigation |
|------|----------|------------|
| FilterBar tests break after shadcn Select migration | HIGH | Update tests with combobox/listbox queries; document rationale |
| TicketForm tests break after shadcn Select migration | MEDIUM | Update field queries; keep functional assertions unchanged |
| Anti-FOSC script not verifiable in jsdom | LOW | Manual browser check + document as untestable in report |
| axe-core not integrated in CI | MEDIUM | Add `@axe-core/react` to dev, verify in browser; note as gap if not in CI |
| Framer Motion animations break in test environment | LOW | Mock framer-motion in jsdom setup if needed |
| Radix Dialog focus trap not tested in jsdom | MEDIUM | Radix unit tests cover this; add smoke test for open/close behavior |

---

## CI Integration Recommendations

| Suite | Trigger | Max duration |
|-------|---------|--------------|
| All Vitest tests | Every commit / PR | < 3 min |
| Style-prop grep audit | Pre-merge CI gate | < 5 sec |
| TypeScript check | Every commit / PR | < 1 min |
| Manual a11y scan (axe DevTools) | Before merge to main | Developer |
| Responsive layout check (DevTools) | Before merge to main | Developer |

---

## Quality Gates

**Block merge when**:
- Any Vitest test fails
- `grep style=` returns non-exempt results
- `npm run typecheck` has errors
- Dark mode flash reproduced manually

**Track but do not block**:
- Framer Motion animations in edge browsers
- Performance baseline (SC-008) unless 10% threshold exceeded
- Cosmetic alignment issues not covered by acceptance criteria

---

## Definition of Done

- [ ] All Vitest tests pass (46 baseline + new design system tests)
- [ ] `grep -r "style=" frontend/src --include="*.tsx" | grep -v "swatch-color-required"` — zero results
- [ ] useTheme `.dark` class toggle verified by unit test
- [ ] Navbar dark mode toggle has `aria-label`
- [ ] AppShell skip-to-content link present and focusable
- [ ] AdminAssignModal is a Dialog; closes on Escape
- [ ] FilterBar and TicketForm tests updated for shadcn Select (with functional equivalence rationale)
- [ ] Manual: dark mode toggle works, persists on reload, no flash
- [ ] Manual: Tab navigation reaches all interactive elements on all 5 pages
- [ ] Manual: 375px viewport — no horizontal scroll on all 5 pages
- [ ] axe DevTools — zero violations on all 5 pages
