# Research: Frontend Design System

## Decision 1: Tailwind CSS version

**Decision**: Tailwind CSS v3 (latest v3.x)

**Rationale**: shadcn/ui's stable component registry targets Tailwind v3. Tailwind v4 changes the
config format significantly (`@theme` CSS directives replace `tailwind.config.js`) and shadcn/ui's
v4 support is still maturing. Tailwind v3 + `tailwind.config.ts` is the production-proven choice
for this stack.

**Alternatives considered**: Tailwind v4 — rejected because shadcn/ui CLI tooling and component
templates still assume v3 config shape; introducing v4 mid-project would require manual adaptation
of every installed component.

---

## Decision 2: CSS variable naming — bridge strategy

**Decision**: Keep existing `--color-*` variables in `themes.css` unchanged (backwards-compatible
with feature 002's admin color customization). Add a second set of shadcn/ui-expected variables
(`--background`, `--foreground`, `--primary`, etc.) that reference the existing vars by value, in
HSL format. Both naming conventions coexist in the same CSS block.

**Rationale**: Feature 002 sets `data-theme` on `<html>` and the admin color customization UI
writes `--color-*` overrides. Renaming these would silently break feature 002. The bridge approach
lets Tailwind `dark:` utilities work via shadcn/ui vars while feature 002 continues setting the
underlying `--color-*` values.

**Implementation**: Convert existing hex values to HSL in `themes.css`. Add aliases:
```css
[data-theme="light"] {
  --color-bg: #f5f5f5;          /* existing — feature 002 writes this */
  --background: 0 0% 96%;       /* shadcn alias (HSL, no hsl() wrapper) */
  --primary: 211 100% 40%;      /* = #0066cc */
  /* etc. */
}
```

**Alternatives considered**: Full rename to shadcn/ui vars only — rejected because it breaks
feature 002's admin color customization without a coordinated migration of that feature.

---

## Decision 3: Tailwind dark mode strategy — `class` + `data-theme` dual approach

**Decision**: Configure Tailwind `darkMode: ["class", '[data-theme="dark"]']` (Tailwind v3 selector
strategy). Update `useTheme` to apply both `document.documentElement.classList.toggle("dark", ...)`
AND `document.documentElement.dataset.theme = key` when switching themes.

**Rationale**: Tailwind `dark:` utilities require `.dark` class on `<html>`. Feature 002's
`[data-theme="dark"]` CSS rules require `data-theme`. The dual application is a one-line change to
`applyTheme()` in `useTheme.ts` and makes both systems work simultaneously.

**Alternatives considered**: Tailwind `darkMode: "media"` — rejected because spec requires
user-controlled in-app toggle that overrides OS preference. `darkMode: "class"` only — rejected
because it would break feature 002's CSS selectors without additional changes.

---

## Decision 4: shadcn/ui component list (minimal viable set)

**Decision**: Install these shadcn/ui components in priority order:

| Component | Replaces |
|-----------|----------|
| `button` | All inline-styled `<button>` elements |
| `input`, `textarea`, `label` | All inline-styled form controls |
| `select` | Custom select in TicketForm, UserForm |
| `dialog` | Inline modal in TicketDetailPage (AdminAssignModal, progress modal, StatusTransitionButton modal) |
| `badge` | Ticket status/type/tag display chips |
| `card` | TicketCard, KanbanCard |
| `table` | UserTable, ProjectTicketList |
| `dropdown-menu` | User context menus |
| `popover` | TagInput |
| `toast` | Notification feedback |
| `sheet` | Mobile sidebar navigation |
| `skeleton` | Loading states |
| `separator` | Section dividers |
| `avatar` | User initials display |
| `alert` | Error/blocked messages (replaces inline alert boxes) |

**Alternatives considered**: Building custom components from Radix primitives directly — rejected
because shadcn/ui already does this and provides tested, accessible implementations ready to copy.

---

## Decision 5: Framer Motion animation patterns

**Decision** (confirmed in clarification — Option C):

| Interaction | Pattern |
|-------------|---------|
| Page transitions | `AnimatePresence` wrapping route outlet; each page has `motion.div` with `initial/animate/exit` opacity+y variants |
| Modal/Dialog enter+exit | Wrap `DialogContent` children in `motion.div`; Radix Dialog handles `data-[state]`, Framer handles entrance animation |
| Card hover lift | `<motion.div whileHover={{ y: -2 }} transition={{ duration: 0.15 }}>` wrapping card content |
| Button press feedback | `<motion.button whileTap={{ scale: 0.97 }}>` on primary action buttons |

**Rationale**: These four patterns cover all high-value animation touchpoints from the clarification
answer without overwhelming the UI. Animations use `duration: 0.15–0.2s` to feel snappy, not
sluggish.

**Alternatives considered**: CSS transitions only — rejected per clarification answer C. Full
micro-animation system (D) — rejected as over-engineered for a ticket tool.

---

## Decision 6: Layout / AppShell architecture

**Decision**: Extract a new `AppShell` layout component (`src/components/layout/AppShell.tsx`)
containing the top navigation bar with: app name/logo, navigation links, dark mode toggle, language
switcher, and user menu. All authenticated routes render inside `AppShell`.

**Rationale**: Currently there is no layout component — every page reimplements its own header/nav
(or doesn't have one). Centralizing this in `AppShell` enables the topbar dark mode toggle (FR-006,
clarification Q1 answer) and eliminates per-page navigation duplication.

**Current router pattern**: `ProtectedRoute` is a simple auth guard component. It wraps children
but provides no layout. Update it to render `<AppShell><Outlet /></AppShell>`.

**Alternatives considered**: Per-page layout — rejected because it duplicates the dark mode toggle
and navigation across every page, creating divergence risk.

---

## Decision 7: Component folder structure

**Decision**: Add `src/components/ui/` for all shadcn/ui primitives (generated by shadcn CLI),
`src/components/layout/` for structural components (AppShell, Navbar, Sidebar), and `src/lib/`
for utilities (cn helper = clsx + tailwind-merge). Keep existing domain folders:
`components/tickets/`, `components/admin/`, `components/common/`, `components/projects/`.

```text
frontend/src/
├── components/
│   ├── ui/          ← shadcn/ui generated components (Button, Dialog, etc.)
│   ├── layout/      ← AppShell, Navbar, Sidebar (new)
│   ├── common/      ← existing: ThemeSwitcher, LanguageSwitcher, FilterBar, ProtectedRoute
│   ├── tickets/     ← existing: TicketCard, TicketForm, etc.
│   ├── admin/       ← existing: UserForm, UserTable
│   └── projects/    ← existing: KanbanBoard, ProjectTicketList
├── lib/
│   └── utils.ts     ← cn() helper: clsx + tailwind-merge
├── hooks/           ← useTheme (updated), any new hooks
├── pages/           ← existing page components (refactored)
└── styles/
    └── themes.css   ← updated with HSL values + shadcn/ui aliases
```

**Alternatives considered**: Flat `components/` — rejected because shadcn/ui generates many files
and mixing primitives with domain components creates navigation confusion.

---

## Decision 8: TicketDetailPage decomposition

**Decision**: Extract embedded inline components from `TicketDetailPage.tsx` (528 lines) into
dedicated files: `AdminAssignModal` → `components/tickets/AdminAssignModal.tsx`, progress update
modal → already extracted as part of StatusTransitionButton work, tag editor → reuse existing
`TagInput.tsx`. Page becomes a coordinator (~150 lines) delegating to extracted components.

**Rationale**: 528-line page components violate the spec's "no deeply nested JSX" and
"composable reusable UI pieces" requirements. Extraction also makes each component independently
testable.

**Alternatives considered**: Keep monolithic page — rejected because SC-006 requires new features
to be buildable from existing components; monolithic pages prevent reuse.

---

## Decision 9: CSS reset and base styles

**Decision**: Replace `index.css` custom reset with Tailwind's `@tailwind base` (Preflight).
Add `@tailwind components` and `@tailwind utilities` layers. Keep `themes.css` separate and
import it before Tailwind base to ensure CSS vars are defined before Preflight runs.

**Rationale**: Tailwind Preflight provides a consistent cross-browser reset. The existing `index.css`
is minimal (7 rules) and can be replaced. Preflight sets `font-family: inherit` on inputs/buttons
which matches the existing intent.

**Alternatives considered**: Keep custom reset alongside Tailwind — rejected because Preflight
conflicts with the existing `box-sizing`, `margin`, and font-inheritance rules, causing duplication.
