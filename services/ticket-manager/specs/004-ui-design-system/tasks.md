# Tasks: Frontend Design System

**Input**: Design documents from `specs/004-ui-design-system/`
**Branch**: `004-ui-design-system`
**Implementation**: Agents via `run-agents.sh` — frontend agent executes tasks sequentially; [P] tasks may run in parallel when agent spawns sub-agents or when multiple agents collaborate.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other [P] tasks in the same phase (different files, no shared dependencies)
- **[Story]**: User story this task belongs to (US1–US4)
- All paths are relative to repo root

---

## Phase 1: Setup (Toolchain Installation)

**Purpose**: Install and configure Tailwind CSS, shadcn/ui, Framer Motion, and supporting utilities. Nothing else can proceed until this phase is complete and `npm run dev` starts without errors.

- [ ] T001 Install Tailwind CSS v3 + PostCSS + Autoprefixer as dev dependencies: run `npm install -D tailwindcss@3 postcss autoprefixer` from `frontend/`
- [ ] T002 [P] Create `frontend/tailwind.config.ts` — set `darkMode: ["class", '[data-theme="dark"]']`, `content: ["./src/**/*.{ts,tsx}"]`, and extend colors/borderRadius per the full token table in `specs/004-ui-design-system/data-model.md` (background, foreground, card, popover, primary, secondary, destructive, muted, accent, border, input, ring, success, warning) all mapped to `hsl(var(--TOKEN))`
- [ ] T003 [P] Create `frontend/postcss.config.js` with `plugins: { tailwindcss: {}, autoprefixer: {} }`
- [ ] T004 [P] Update `frontend/src/styles/themes.css` — convert all hex values to `hsl(H S% L%)` format for the existing `--color-*` vars; add the complete set of shadcn/ui CSS variable aliases (background, foreground, card, card-foreground, popover, popover-foreground, primary, primary-foreground, secondary, secondary-foreground, muted, muted-foreground, accent, accent-foreground, destructive, destructive-foreground, border, input, ring) as HSL channel strings (no `hsl()` wrapper) to ALL 6 theme blocks (`light`, `dark`, `solarized`, `oceanic`, `high-contrast`, `warm`) per `specs/004-ui-design-system/contracts/theming-integration.md`; also add `--radius: 0.375rem` to each block
- [ ] T005 Replace `frontend/src/index.css` contents with `@tailwind base;\n@tailwind components;\n@tailwind utilities;`; update `frontend/src/main.tsx` import order so `themes.css` is imported before `index.css`
- [ ] T006 [P] Initialize shadcn/ui from `frontend/` directory: run `npx shadcn@latest init --defaults` (use style: default, base color: neutral, CSS variables: yes); this creates `frontend/components.json`; then add `"@/*": ["./src/*"]` path alias to both `frontend/tsconfig.json` (compilerOptions.paths) and `frontend/vite.config.ts` (resolve.alias mapping `@/` to `path.resolve(__dirname, "src")`)
- [ ] T007 [P] Install clsx and tailwind-merge as production dependencies (`npm install clsx tailwind-merge` from `frontend/`); create `frontend/src/lib/utils.ts` exporting `cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }`
- [ ] T008 [P] Install Framer Motion 11 and Lucide React as production dependencies (`npm install framer-motion lucide-react` from `frontend/`); create `frontend/src/lib/motion.ts` exporting `pageVariants`, `dialogVariants`, and `cardHover` per `specs/004-ui-design-system/contracts/component-api.md` Animation Variants section
- [ ] T009 Update `frontend/src/hooks/useTheme.ts` — add `const DARK_THEMES: ThemeKey[] = ["dark", "oceanic", "high-contrast"]`; update `applyTheme()` to also run `document.documentElement.classList.toggle("dark", DARK_THEMES.includes(theme))` after setting `dataset.theme`, per `specs/004-ui-design-system/contracts/theming-integration.md`

**Checkpoint**: Run `npm run dev` from `frontend/` — no errors, page renders, `<html>` has `data-theme="light"`, `npm run typecheck` passes.

---

## Phase 2: Foundational (shadcn/ui Component Installation)

**Purpose**: Install all required shadcn/ui primitive components into `frontend/src/components/ui/`. All user story phases depend on these components existing. Install from the `frontend/` directory.

**⚠️ CRITICAL**: Depends on Phase 1 complete (especially T006 shadcn init). All T010–T013 can run in parallel.

- [ ] T010 [P] Install shadcn/ui layout/action primitives from `frontend/`: run `npx shadcn@latest add button badge avatar separator`
- [ ] T011 [P] Install shadcn/ui form primitives from `frontend/`: run `npx shadcn@latest add input textarea label select`
- [ ] T012 [P] Install shadcn/ui overlay primitives from `frontend/`: run `npx shadcn@latest add dialog dropdown-menu popover sheet toast`
- [ ] T013 [P] Install shadcn/ui data-display primitives from `frontend/`: run `npx shadcn@latest add card table alert skeleton`

**Checkpoint**: `frontend/src/components/ui/` contains all installed component files; `npm run typecheck` passes.

---

## Phase 3: User Story 1 — Accessible & Keyboard-Navigable Interface (Priority: P1) 🎯 MVP

**Goal**: Every feature is reachable and operable via keyboard alone; screen reader announcements are correct; focus is trapped in modals and restored on close; the AppShell layout wrapper is in place for all authenticated routes.

**Independent Test**: Tab through the full ticket workflow (list → detail → transition → assign) without touching the mouse; verify focus ring is visible at each step; open a modal with Enter, close with Escape, confirm focus returns to trigger.

- [ ] T014 Create `frontend/src/components/layout/Navbar.tsx` — top navigation bar rendering: brand text left-aligned (`text-xl font-semibold`); nav links to `/projects` and `/admin/users` (admin link hidden for `role !== "administrator"`) using React Router `<Link>` styled as `<Button variant="ghost">`; dark mode toggle `<Button variant="ghost" size="icon">` with `<Sun className="h-4 w-4" />` or `<Moon className="h-4 w-4" />` (imports from lucide-react) toggling only between `light` / `dark` themes using `useTheme`; `aria-label="Toggle dark mode"` on the toggle; `<LanguageSwitcher />` component; user email + logout in a `<DropdownMenu>` (DropdownMenuTrigger/Content/Item from `ui/dropdown-menu`); reads `useAuthStore` for `currentUser` and `logout`; all styling via Tailwind, zero style props; export `Navbar`
- [ ] T015 Create `frontend/src/components/layout/AppShell.tsx` — accepts `children: React.ReactNode`; renders `<div className="min-h-screen bg-background">` containing `<Navbar />` and `<main id="main-content" className="container mx-auto max-w-7xl px-4 py-6">{children}</main>`; also add a skip-to-content link `<a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-background focus:text-foreground focus:rounded focus:shadow">Skip to content</a>` as the first child; export `AppShell`
- [ ] T016 Update `frontend/src/components/common/ProtectedRoute.tsx` — import `AppShell`; wrap the authenticated content render (the `<Outlet />` or children) with `<AppShell>…</AppShell>`; the login redirect path is unchanged
- [ ] T017 Create `frontend/src/components/layout/PageTransition.tsx` — a `motion.div` component that wraps page content with `pageVariants` (initial/animate/exit) from `frontend/src/lib/motion.ts`; accepts `children: React.ReactNode` and optional `className?: string`; uses `<motion.div variants={pageVariants} initial="initial" animate="animate" exit="exit" className={cn("w-full", className)}>`; then wrap each of the 5 page root elements (`LoginPage`, `ProjectListPage`, `ProjectPage`, `TicketDetailPage`, `AdminUsersPage`) with `<PageTransition>` and add `<AnimatePresence mode="wait">` in `frontend/src/router.tsx` around the router outlet (import AnimatePresence from framer-motion; wrap `<RouterProvider>` children or use location key)
- [ ] T018 [US1] Extract `AdminAssignModal` out of `frontend/src/pages/TicketDetailPage.tsx` into new file `frontend/src/components/tickets/AdminAssignModal.tsx` — use shadcn `<Dialog>` with `<DialogContent>`, `<DialogHeader>`, `<DialogTitle>`, `<DialogDescription>`, `<DialogFooter>`; keep identical props interface (`open`, `onClose`, `ticketId`, `currentUserId`, `onAssigned`) per `specs/004-ui-design-system/contracts/component-api.md`; dialog close on Escape and overlay click handled by Radix automatically; use `<Button>` for confirm/cancel; zero style props; update `TicketDetailPage.tsx` to import from the new file
- [ ] T019 [US1] Migrate the progress-update modal in `frontend/src/components/tickets/StatusTransitionButton.tsx` — replace the custom `modalOverlay`/`modalBox` style constants and their `<div>` usage with shadcn `<Dialog open={!!pendingToStatus} onOpenChange={(open) => !open && handleCancelUpdate()}>` containing `<DialogContent>`, `<DialogHeader>`, `<DialogTitle>` (using `t("tickets.progress.submitUpdate")`), `<DialogDescription>` (using `t("tickets.detail.updateRequiredForTransition")`), `<Textarea>` (from `ui/textarea`), and `<DialogFooter>` with `<Button variant="outline">` cancel and `<Button>` submit; remove all `const modalOverlay`, `const modalBox`, `const textareaStyle`, `const cancelBtn` style objects; zero style props remaining
- [ ] T020 [P] [US1] Add ARIA labels and focus ring styles across all interactive elements in `frontend/src/components/tickets/TicketForm.tsx`, `frontend/src/components/admin/UserForm.tsx`, `frontend/src/components/common/FilterBar.tsx` — every `<Button size="icon">` or icon-only button must have `aria-label`; all form inputs paired with `<Label htmlFor>` using matching `id` attrs; verify shadcn `<Button>` already includes `focus-visible:ring-2 focus-visible:ring-ring` (check `ui/button.tsx`), add if missing; no new style props
- [ ] T021 [P] [US1] Add `aria-live="polite"` announcement regions for async state changes — add a `<div aria-live="polite" className="sr-only" id="status-announcer">` to `AppShell.tsx`; update `frontend/src/components/tickets/StatusTransitionButton.tsx` to update the announcer text when transition succeeds or fails (via `document.getElementById("status-announcer")!.textContent = message`)

**Checkpoint**: Tab through the full ticket workflow without mouse — every element focusable, modals trap focus, Escape closes modals, focus returns to trigger. `npm run typecheck` passes.

---

## Phase 4: User Story 2 — Dark Mode Support (Priority: P2)

**Goal**: Dark mode toggle in topbar switches theme instantly; preference persists on reload with no flash; all surfaces (including shadcn overlays) render in dark palette.

**Independent Test**: Toggle dark mode → reload → confirm dark mode active with no flash; open Dialog, DropdownMenu, Popover in dark mode → all render dark.

- [ ] T022 [US2] Add anti-FOSC inline script to `frontend/index.html` — insert before `</head>`: `<script>try{var t=localStorage.getItem("theme")||"light";document.documentElement.dataset.theme=t;if(["dark","oceanic","high-contrast"].includes(t))document.documentElement.classList.add("dark")}catch(e){}</script>` — this prevents flash of wrong theme before React hydrates
- [ ] T023 [US2] Update `frontend/src/components/common/ThemeSwitcher.tsx` — replace `const container: React.CSSProperties` and `const swatchBtn: React.CSSProperties` style constants with Tailwind; each swatch button becomes `<button className="h-5 w-5 rounded-full border border-border cursor-pointer p-0 focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 flex-shrink-0" style={{ background: swatch }} ...>` — `style={{ background: swatch }}` is the ONLY permitted style prop here (data-driven color swatch, document with `{/* swatch-color-required */}` comment); remove `const container` style object; use `<div className="flex gap-1 items-center">` for container
- [ ] T024 [P] [US2] Verify dark mode completeness — open `frontend/src/styles/themes.css` and confirm the `[data-theme="dark"]` and other dark theme blocks (`oceanic`, `high-contrast`) each have all required shadcn vars; if any are missing add them (cross-reference against `[data-theme="light"]` block as the authoritative list); run `npm run dev`, switch to dark mode, and open Dialog/DropdownMenu/Popover — all must render with dark background (if using CSS vars correctly they will automatically)

**Checkpoint**: Toggle dark in topbar → reload → dark persists, no flash. All overlays dark. `npm run typecheck` passes.

---

## Phase 5: User Story 3 — Consistent Visual Design System (Priority: P3)

**Goal**: All inline `style` props and `React.CSSProperties` constant objects are replaced with Tailwind utility classes. All interactive components use shadcn/ui primitives. Zero `style` prop usage (except documented `swatch-color-required` exception).

**Independent Test**: Run `grep -r "style=" frontend/src --include="*.tsx" | grep -v "swatch-color-required"` — must return zero results. Visual comparison: buttons, inputs, cards identical appearance across all pages.

- [ ] T025 [P] [US3] Migrate `frontend/src/pages/LoginPage.tsx` — replace all style constants and inline style props with Tailwind; center layout `<div className="min-h-screen flex items-center justify-center bg-background px-4">`; login form in `<Card className="w-full max-w-sm"><CardHeader>…</CardHeader><CardContent>…</CardContent></Card>`; use `<Input>`, `<Label>`, `<Button>` from `ui/`; error message as `<p className="text-sm text-destructive">`; zero style props
- [ ] T026 [P] [US3] Migrate `frontend/src/components/tickets/TicketForm.tsx` — replace all `React.CSSProperties` style constants (find with grep) with Tailwind; title/description/type/priority fields wrapped in `<div className="space-y-2"><Label>…</Label><Input>…</Input></div>`; use `<Select>` from `ui/select` for type/status/priority dropdowns; submit/cancel using `<Button>` and `<Button variant="outline">`; form layout `<div className="space-y-4">`; zero style props
- [ ] T027 [P] [US3] Migrate `frontend/src/components/admin/UserForm.tsx` — same pattern as T026; email/password/role fields using `<Input>`, `<Label>`, `<Select>` from `ui/`; form in `<div className="space-y-4">`; zero style props
- [ ] T028 [P] [US3] Migrate `frontend/src/components/common/FilterBar.tsx` — search input → `<Input className="max-w-xs" placeholder="…">`; filter chips → `<Badge variant="secondary" className="cursor-pointer">` + remove `×` as `<Button variant="ghost" size="icon" className="h-4 w-4">`; container `<div className="flex flex-wrap gap-2 items-center">`; zero style props
- [ ] T029 [US3] Migrate `frontend/src/components/tickets/TicketCard.tsx` — wrap content in shadcn `<Card className="cursor-pointer hover:shadow-md transition-shadow">`; wrap `<Card>` in `<motion.div>` with `cardHover` from `src/lib/motion.ts`; ticket status → `<Badge variant="outline">`; ticket type → `<Badge variant="secondary">`; title `<CardTitle className="text-sm font-medium line-clamp-2">`; remove all style constants; zero style props
- [ ] T030 [US3] Migrate `frontend/src/components/tickets/KanbanCard.tsx` — same pattern as T029; use `<Card>`, `<Badge>`, `<motion.div>` with `cardHover`; assignee avatars using `<Avatar><AvatarFallback>` with initials; zero style props
- [ ] T031 [P] [US3] Migrate `frontend/src/components/tickets/KanbanColumn.tsx` — column container `<div className="flex flex-col gap-2 min-w-[280px] w-72">`; header `<div className="flex items-center justify-between px-1 mb-2"><h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{title}</h3><Badge variant="secondary">{count}</Badge></div>`; tickets area `<div className="flex flex-col gap-2">`; zero style props
- [ ] T032 [P] [US3] Migrate `frontend/src/components/projects/KanbanBoard.tsx` — board container `<div className="flex gap-4 overflow-x-auto pb-4">`; no style props
- [ ] T033 [P] [US3] Migrate `frontend/src/components/projects/ProjectTicketList.tsx` — replace custom table markup with shadcn `<Table><TableHeader><TableRow><TableHead>…</TableHead></TableRow></TableHeader><TableBody>…</TableBody></Table>`; status column uses `<Badge variant="outline">`; ticket title is a `<Link>` styled as `className="text-sm font-medium hover:underline"`; zero style props
- [ ] T034 [US3] Migrate `frontend/src/components/admin/UserTable.tsx` — same pattern as T033; use shadcn `<Table>`; role column `<Badge variant={role === "administrator" ? "default" : "secondary"}`; blocked status `<Badge variant="destructive">` / `<Badge variant="outline">`; action buttons `<Button variant="ghost" size="sm">`; zero style props
- [ ] T035 [P] [US3] Migrate `frontend/src/components/tickets/AssigneeProgressList.tsx` — each assignee row as `<div className="flex items-center gap-3 py-2">`; user avatar `<Avatar className="h-8 w-8"><AvatarFallback className="text-xs">{initials}</AvatarFallback></Avatar>`; update status `<Badge variant="secondary">` or `<Badge variant="outline">`; progress text `<p className="text-sm text-muted-foreground">`; zero style props
- [ ] T036 [P] [US3] Migrate `frontend/src/components/tickets/TicketEventHistory.tsx` — event list `<div className="space-y-3">`; each event `<div className="flex items-start gap-3 text-sm">`; timestamp `<span className="text-xs text-muted-foreground whitespace-nowrap">`; event type `<Badge variant="secondary" className="shrink-0">`; event description `<span className="text-foreground">`; separator line `<Separator className="my-1">`; zero style props
- [ ] T037 [P] [US3] Migrate `frontend/src/components/tickets/TagInput.tsx` — replace custom popover with shadcn `<Popover><PopoverTrigger asChild><Button variant="outline" size="sm">Add tag</Button></PopoverTrigger><PopoverContent><Input placeholder="Tag name…" /></PopoverContent></Popover>`; existing tags displayed as `<Badge variant="secondary" className="gap-1">{tag}<button onClick={remove} className="ml-1 rounded-full hover:bg-muted"><X className="h-3 w-3" /></button></Badge>`; zero style props
- [ ] T038 [US3] Migrate `frontend/src/pages/TicketDetailPage.tsx` — remove all inline style constants (there are many: container, section headers, modals etc.); use Tailwind two-column layout `<div className="grid grid-cols-1 lg:grid-cols-3 gap-6">`; ticket main content (title, description, progress, transitions) in `<div className="lg:col-span-2 space-y-6">`; sidebar (assignees, metadata, tags) in `<div className="space-y-4">`; each section in `<Card><CardHeader><CardTitle>…</CardTitle></CardHeader><CardContent>…</CardContent></Card>`; import `AdminAssignModal` from `../components/tickets/AdminAssignModal`; zero style props; target: coordinator component under 200 lines
- [ ] T039 [US3] Migrate `frontend/src/pages/ProjectListPage.tsx`, `frontend/src/pages/ProjectPage.tsx`, and `frontend/src/pages/AdminUsersPage.tsx` — for each: replace all style constants with Tailwind; ProjectListPage: project cards in `<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">`; ProjectPage: Kanban board with `<div className="flex gap-4 overflow-x-auto pb-4">`; AdminUsersPage: `<div className="space-y-4">` with table + add-user button; zero style props in all three files

**Checkpoint**: `grep -r "style=" frontend/src --include="*.tsx" | grep -v "swatch-color-required"` returns zero results. `npm run typecheck` passes. Visual inspection shows consistent buttons/inputs/cards across pages.

---

## Phase 6: User Story 4 — Responsive Layout (Priority: P4)

**Goal**: All pages usable at 375px mobile width without horizontal scroll; navigation collapses on mobile; touch targets ≥ 44px.

**Independent Test**: Chrome DevTools at 375px — navigate all 5 pages, no horizontal scrollbar, all tap targets reachable.

- [ ] T040 [US4] Add mobile navigation Sheet to `frontend/src/components/layout/Navbar.tsx` — add a hamburger `<Button variant="ghost" size="icon" className="md:hidden">` with `<Menu className="h-5 w-5" />` (Lucide); clicking opens a `<Sheet>` (`<SheetContent side="left">`) containing all nav links and language switcher; hide desktop nav links `<div className="hidden md:flex">` and show hamburger only on mobile `<div className="md:hidden">`; dark mode toggle remains visible on all screen sizes
- [ ] T041 [P] [US4] Audit and fix touch targets in `frontend/src/components/tickets/StatusTransitionButton.tsx` and `frontend/src/components/common/FilterBar.tsx` — all `<Button>` elements must have `size="default"` (h-10 = 40px, acceptable) or `size="lg"` for primary actions; icon buttons must be `size="icon"` (h-10 w-10); add `className="w-full sm:w-auto"` to transition buttons so they stack full-width on mobile
- [ ] T042 [P] [US4] Verify responsive layouts in `frontend/src/pages/ProjectListPage.tsx` — project card grid already set to `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3` (from T039); verify page header and filter bar don't overflow at 375px; add `flex-wrap` to any horizontal flex containers
- [ ] T043 [P] [US4] Verify `frontend/src/pages/TicketDetailPage.tsx` responsive — single column on mobile (already `grid-cols-1 lg:grid-cols-3` from T038); ensure `<Card>` sections have `overflow-hidden` to prevent content overflow; dialog modals must use `<DialogContent className="w-full max-w-[95vw] sm:max-w-lg">` to stay within mobile viewport
- [ ] T044 [US4] Verify all 5 pages at 375px — open each page in browser at 375px viewport width and confirm: (1) no horizontal scrollbar, (2) all content readable, (3) all buttons tappable; fix any remaining overflow issues with `overflow-x-hidden` on containers or `max-w-full` on wide elements; update `frontend/src/components/layout/AppShell.tsx` container to `px-4 sm:px-6` for comfortable mobile padding

**Checkpoint**: All 5 pages at 375px — no horizontal scroll, all content visible. `npm run typecheck` passes.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final audit, cleanup, and verification that all 8 success criteria are met.

- [ ] T045 [P] Final style-prop audit and main.tsx cleanup — run `grep -rn "style=" frontend/src --include="*.tsx"` and fix any remaining usages not already marked `swatch-color-required`; migrate `frontend/src/main.tsx` `SessionRestorer` loading div from `style={{ minHeight: "100vh", display: "flex", ... }}` to `className="min-h-screen flex items-center justify-center bg-background text-muted-foreground"`; run `npm run typecheck` — zero errors
- [ ] T046 [P] Run `npm run test` from `frontend/` — all existing Vitest tests must pass (SC-007: zero functional regression); if any test fails due to changed class names or missing style attributes, update test assertions to match new rendered output while verifying the functionality is identical
- [ ] T047 Run all 8 quickstart.md verification scenarios — verify SC-001 through SC-008 per `specs/004-ui-design-system/spec.md`; confirm: (1) keyboard-only navigation works end-to-end, (2) dark mode toggle present in topbar and persists, (3) zero axe violations on all pages (install `@axe-core/react` as dev dep if needed), (4) all pages at 375px/768px/1440px — no horizontal scroll, (5) `grep style=` returns only `swatch-color-required` exceptions, (6) new component buildable from existing primitives only, (7) all tests pass, (8) bundle size baseline acceptable

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately; T002–T009 can run in parallel after T001 completes
- **Phase 2 (Foundational)**: Requires Phase 1 complete (especially T006 shadcn init); T010–T013 run in parallel
- **Phase 3 (US1)**: Requires Phase 2 complete; T014 → T015 → T016 sequential; T017–T021 after T016
- **Phase 4 (US2)**: Requires Phase 3 complete (Navbar already has toggle from T014); T022–T024 relatively independent
- **Phase 5 (US3)**: Requires Phase 2 complete (shadcn components needed); T025–T037 all [P] within story; T038–T039 depend on T018 (AdminAssignModal extraction)
- **Phase 6 (US4)**: Requires Phase 5 complete (Tailwind responsive classes added to already-migrated files)
- **Phase 7 (Polish)**: Requires all prior phases complete

### User Story Dependencies

- **US1 (P1)**: Depends on Phase 2 (shadcn Dialog/DropdownMenu needed for modals and Navbar)
- **US2 (P2)**: Depends on US1 (Navbar with toggle built in T014)
- **US3 (P3)**: Depends on Phase 2 (all shadcn primitives); independent of US1/US2
- **US4 (P4)**: Depends on US3 (responsive classes added on top of migrated components) + US1 (Sheet for mobile nav)

### Parallel Opportunities per Phase

**Phase 1**: T002, T003, T004, T006, T007, T008, T009 can all run in parallel after T001 and T005 in sequence
**Phase 2**: T010, T011, T012, T013 all parallel
**Phase 3**: T018, T019, T020, T021 can run in parallel after T016
**Phase 5**: T025, T026, T027, T028, T031, T032, T033, T035, T036, T037 all parallel; T029, T030 parallel with each other; T038 after T018
**Phase 6**: T041, T042, T043 parallel after T040

---

## Parallel Execution Example: Phase 5 (US3)

```bash
# Agent A: Form components
Task T025: LoginPage migration
Task T026: TicketForm migration
Task T027: UserForm migration

# Agent B: Card/list components
Task T029: TicketCard migration
Task T030: KanbanCard migration
Task T031: KanbanColumn migration

# Agent C: Table/data components
Task T033: ProjectTicketList → Table
Task T034: UserTable → shadcn Table
Task T035: AssigneeProgressList

# After all complete:
Task T038: TicketDetailPage full decomposition
Task T039: Remaining pages (ProjectList, ProjectPage, AdminUsers)
```

---

## Implementation Strategy

### MVP (User Stories 1 + 2 only — Phase 1–4)

1. Complete Phase 1: Toolchain install + configure
2. Complete Phase 2: Install shadcn/ui components
3. Complete Phase 3 (US1): AppShell, Navbar, Dialog migrations → accessible keyboard nav
4. Complete Phase 4 (US2): Anti-FOSC + dark mode verified
5. **STOP and VALIDATE**: Dark mode toggle works, modals keyboard-navigable, no style props in new files
6. Deploy/demo — functional improvement visible to users

### Full Delivery (All 4 stories)

1. MVP above → foundation proven
2. Phase 5 (US3): Migrate all remaining components → visual consistency
3. Phase 6 (US4): Responsive passes at 375px
4. Phase 7: Final audit → all 8 SC verified

### Agent Execution Notes

- Each task is self-contained: the file path, component name, and shadcn primitive to use are all specified
- Run `npm run typecheck` after completing each phase before starting the next
- If a shadcn component import fails, verify the component was installed in Phase 2 and `components.json` path alias is configured
- The `cn()` helper from `src/lib/utils.ts` (T007) is available via `@/lib/utils` after T006 sets up the path alias
- Do NOT edit files in `frontend/src/components/ui/` — these are shadcn-generated; wrap in domain components instead
- One permitted style prop exception: `ThemeSwitcher` swatch button `style={{ background: swatch }}` (marked `swatch-color-required`)

---

## Definition of Done

- [ ] `npm run typecheck` — zero errors
- [ ] `npm run test` — zero failures (SC-007)
- [ ] `grep -r "style=" frontend/src --include="*.tsx" | grep -v "swatch-color-required"` — zero results (SC-005)
- [ ] Dark mode toggle visible in topbar; theme persists on reload without flash (SC-003)
- [ ] All 5 pages usable at 375px without horizontal scroll (SC-004)
- [ ] Feature 002 full-palette ThemeSwitcher still functional
- [ ] All modals: focus trap active, Escape closes, focus returns to trigger (SC-001)
- [ ] axe DevTools — zero WCAG 2.1 AA violations on all 5 pages (SC-002)
