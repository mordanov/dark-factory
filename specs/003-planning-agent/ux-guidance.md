# UX Guidance: Planning Agent for Prompt Studio

**Author**: Designer Agent  
**Feature**: `003-planning-agent`  
**Date**: 2026-06-23  
**Spec**: spec.md, plan.md  

---

## 1. Summary

This document defines interaction behavior, accessibility requirements, and UX acceptance criteria for the Planning Agent UI. The primary deliverable is `PlanningModal.tsx` with four sequential states, plus `AgentConfigPanel.tsx` and inline node editing. Frontend tasks T026–T032 implement this spec; Autotester verifies the acceptance criteria.

---

## 2. Session Detail Page Changes (T030)

### 2.1 Trigger Button

When `session.status === "approved"`:
- Show one primary button labeled `planning.generate_plan` (i18n key) in the session detail action bar where the old "Approve & create ticket" button appeared.
- No secondary actions on this button (no dropdown, no tooltip).
- Button is disabled while any in-flight navigation is happening; enable once the page is settled.

When `session.status === "planning"` (generation already running from a previous page load):
- Show the modal in **generating** state automatically (see §3.1). The session is already in `planning` status so re-triggering is not allowed — the "Generate Plan" button must not appear.

When `session.status === "plan_ready"` or `"plan_confirmed"`:
- Show a "View Plan" secondary button to reopen the modal in **ready** or **confirming** state as appropriate.

When `session.status === "tickets_created"`:
- Hide the modal trigger entirely.
- Show a persistent success banner (see §4.4).

### 2.2 Success Banner (`tickets_created`)

Placement: below the session title, above session metadata. Not dismissable.

Content:
```
[✓ icon]  Tickets created successfully  ·  [N tickets created]  ·  [View in Ticket Manager ↗]
```

- "View in Ticket Manager" opens the TM project URL in a new tab.
- Banner uses success semantic color (green tone), not blue info.
- Does not replace session detail content — it sits above it.

**Accessibility**: `role="status"`, `aria-live="polite"` so it is announced when it appears dynamically.

---

## 3. PlanningModal: Four States

The modal is the central UI element. It is opened by the "Generate Plan" or "View Plan" button on `SessionDetailPage`. All four states share the same modal container; only the content changes.

**Modal container**:
- Full-screen on mobile, centered dialog (max-width 800px, max-height 90vh, scrollable body) on desktop.
- Modal header always shows the session title.
- Modal backdrop is always present.

### 3.1 State: Generating

Triggered when: user clicks "Generate Plan" or session loads in `planning` status.

**Behavior**:
- Modal opens immediately on button click (do not wait for API response).
- Immediately call `planStore.triggerGeneration()`.
- Overlay is **non-dismissable**: no ✕ close button, no backdrop click-to-close, no Escape key to close. This is intentional per spec (plan generation is async and must not be abandoned mid-flight without giving users a false sense of cancellation).
- Poll `GET /sessions/{id}/plan` every 3 seconds until `plan.status === "ready"` or an error is returned.

**Visual layout**:
```
┌────────────────────────────────────────────┐
│  [Session Title]                           │
├────────────────────────────────────────────┤
│                                            │
│         ◌  (spinner, 48px)                 │
│                                            │
│    Generating your plan…                   │
│    This may take up to 60 seconds.         │
│                                            │
└────────────────────────────────────────────┘
```

- Spinner: a simple indefinite CSS animation, not a progress bar (we don't know progress).
- Text uses i18n keys `planning.generating` and `planning.generating_hint`.
- No cancel or close control is shown.

**Transition**: When the API returns `status === "ready"`, animate a cross-fade into the **Ready** state. If `status === "error"` or network fails after 3 retries, show the **Error** sub-state.

**Error sub-state (generation failed)**:
```
┌────────────────────────────────────────────┐
│  [Session Title]                        ✕  │
├────────────────────────────────────────────┤
│                                            │
│   ⚠  Plan generation failed               │
│   The service is temporarily unavailable. │
│   Your session is unchanged — you can     │
│   try again.                              │
│                                           │
│             [Try again]    [Close]        │
└────────────────────────────────────────────┘
```

- "Try again" calls `planStore.triggerGeneration()` again.
- "Close" dismisses the modal; session stays in `approved` status.
- i18n key: `planning.error_generation`.

**Accessibility (generating state)**:
- `role="dialog"`, `aria-modal="true"`, `aria-label` set to the session title.
- Initial focus is on the dialog container itself (no focusable element inside).
- `aria-live="polite"` region wraps the status text so screen readers announce "Generating your plan…" on entry and any status change.
- When error sub-state appears, focus moves to the "Try again" button.

---

### 3.2 State: Ready (Plan Review & Edit)

Triggered when: plan is generated and `plan.status === "ready"`.

**Visual layout**:
```
┌──────────────────────────────────────────────────┐
│  [Session Title]               [Regenerate ↺]    │
├──────────────────────────────────────────────────┤
│  EPIC                                            │
│  ┌────────────────────────────────────────────┐  │
│  │ [Epic title — editable]                    │  │
│  │ [Epic description — editable]              │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  STORIES (N)                                     │
│  ▼ Story 1: [title — editable]   [3 tasks] [🗑]  │
│    [description — editable]                      │
│    ┌──── Task 1.1 ──────────────────────────┐   │
│    │ [title — editable]  [M] [task]          │   │
│    │ [description — editable]                │   │
│    │ depends on: task-1-0  ×                 │   │
│    │                                  [🗑]   │   │
│    └─────────────────────────────────────────┘  │
│    [+ more tasks…]                               │
│                                                  │
│  ▶ Story 2: [title]              [2 tasks] [🗑]  │
│                                                  │
│  ─────────────────────────────────────────────  │
│  ▶ Agent configuration for this project          │  ← AgentConfigPanel (collapsed by default)
│                                                  │
├──────────────────────────────────────────────────┤
│  [Cancel]          [Confirm plan & create tickets]│
└──────────────────────────────────────────────────┘
```

**Story expand/collapse**:
- Click the ▶/▼ chevron or the story title row to toggle.
- First story is expanded by default; others collapsed.
- Collapsed state shows: story title (editable), task count badge, delete button.
- Expanded state shows: title (editable), description (editable), all tasks.

**Badges**:
- Complexity badge: `S | M | L | XL` — pill with neutral color. Not editable (read-only).
- Ticket type badge: `task | implementation | investigation` — pill with neutral color. Not editable.
- `depends_on` chips: read-only chips showing local IDs of dependencies. No interaction.

**"Regenerate" button** (top-right):
- Ghost/secondary style, not primary.
- Opens a confirmation dialog before regenerating: "Regenerating will replace your current plan. This cannot be undone. Continue?"
- If confirmed: calls `planStore.triggerGeneration()` again, modal transitions to **Generating** state.
- i18n key: `planning.regenerate`.

**"Cancel" button** (footer, left):
- Ghost/link style.
- Closes the modal. Session stays in `plan_ready` status. Plan is preserved.
- No confirmation dialog needed — data is already persisted.
- i18n key: `planning.cancel`.

**"Confirm plan & create tickets" button** (footer, right):
- Primary CTA. Disabled only while an update is being saved.
- On click: calls `planStore.confirmPlan()`, modal transitions to **Confirming** state.
- i18n key: `planning.confirm_plan`.

**Accessibility (ready state)**:
- `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing to modal title.
- Initial focus on the first editable field (Epic title).
- Focus trap: Tab cycles through all interactive elements; Escape key triggers Cancel behavior (same as Cancel button — no confirmation needed).
- Delete buttons must have `aria-label="Delete Story: [story title]"` or `aria-label="Delete Task: [task title]"` (not just an icon).
- Complexity and type badges: wrapped in `<span>` with visible text, not icon-only.
- `depends_on` chip list: `aria-label="Depends on"` on the chip container.
- Confirm button: `aria-describedby` points to a visually-hidden hint "Plan will be submitted to create tickets in Ticket Manager."

---

### 3.3 Inline Editing Behavior

Applies to: Epic title, Epic description, Story title, Story description, Task title, Task description.

**Interaction pattern**: Click-to-edit (not always-editable).

**Default (view mode)**:
- Text renders as styled text (not an `<input>`).
- On hover: show a subtle edit cursor and a faint highlight border to signal editability.
- On focus (keyboard Tab): same visual as hover.

**Editing mode**:
- Click or Enter/Space on focused element activates an `<input>` (single-line, for titles) or `<textarea>` (multi-line, for descriptions).
- Input is pre-filled with the current value.
- On blur OR Enter (for single-line inputs) OR Shift+Enter (for textarea): auto-save by calling `planStore.updateNode()` → `planningApi.update()`.
- On Escape: discard changes, revert to last saved value, return to view mode.
- While saving: input shows a faint loading spinner inside the field. Field remains editable.
- On save error: restore previous value, show inline error text below the field ("Failed to save. Try again."), field remains editable.

**Constraints enforced at input level**:
- Title: `maxLength={200}` on the input element. Show character counter only when within 20 chars of limit.
- Description: `maxLength={500}` on the textarea. Show character counter when within 50 chars of limit.
- Empty title: if user clears title and blurs, revert to last saved value (titles are required).

**Accessibility (inline editing)**:
- `aria-label` on each field: "Epic title", "Story 1 title", "Task 1.1 description", etc.
- `aria-required="true"` on all title fields.
- When character limit is near: `aria-describedby` pointing to the counter element.
- Error messages: `role="alert"` and `aria-live="assertive"` so screen readers announce save failures immediately.
- Input/textarea: associated `<label>` or `aria-label`; never label-less.

**When plan is read-only** (status is `confirmed`, `tickets_created`, or `error` after partial creation):
- Fields render as plain text with no hover/focus edit affordance.
- Delete buttons are hidden.
- Confirm and Cancel buttons are replaced by context-appropriate controls.
- The plan tree itself is still visible and keyboard-navigable for reading.

---

### 3.4 Delete Behavior

**Delete Story**:
- Click the 🗑 (trash) icon on a story row.
- Confirmation dialog: "Delete Story "[title]" and all its tasks? This cannot be undone."
- On confirm: call `planStore.updateNode()` with the story removed from `plan_content.stories`.
- If the plan has only one story, the delete button should still be shown (spec allows zero-story plans as an edge case the validator handles).

**Delete Task**:
- Click the 🗑 icon on a task row.
- No confirmation dialog needed (task is smaller scope; undo via Escape is not available but the cost is lower).
- Immediately call `planStore.updateNode()` with the task removed.
- If other tasks have `depends_on` referencing the deleted task's local_id, remove those references before saving.

**Accessibility**:
- Confirmation dialogs: focus moves to the "Confirm" button on open; Escape cancels.
- After deletion, focus returns to the nearest remaining element (next task, or parent story, or Confirm button).

---

### 3.5 State: Confirming (Ticket Creation in Progress)

Triggered when: user clicks "Confirm plan & create tickets" and API returns 202.

**Behavior**:
- Non-dismissable: no ✕, no Escape, no backdrop click. (Same rationale as generating — partial ticket creation in flight.)
- Poll `GET /sessions/{id}/plan/status` every 3 seconds. `created_count` increments; stop when `status === "tickets_created"` or `status === "error"`.

**Visual layout**:
```
┌──────────────────────────────────────────────────┐
│  [Session Title]                                  │
├──────────────────────────────────────────────────┤
│  [Plan tree rendered, all fields read-only,       │
│   greyed out with opacity 0.5]                    │
│                                                   │
├──────────────────────────────────────────────────┤
│  Creating tickets…                                │
│  ████████████░░░░░░░░░  5 / 11                   │  ← determinate progress bar
│                                                   │
└──────────────────────────────────────────────────┘
```

- Progress bar is **determinate**: `value = created_count`, `max = total_count` (1 epic + N stories + M tasks).
- Label: `planning.creating_tickets` with interpolated `X / N`.
- Plan tree remains visible but greyed (opacity 0.5, `aria-disabled="true"` on all interactive elements).
- No buttons except the implicit "please wait" state.

**On partial failure (ticket creation error)**:
```
┌──────────────────────────────────────────────────┐
│  [Session Title]                              ✕   │
├──────────────────────────────────────────────────┤
│  [Plan tree read-only]                           │
├──────────────────────────────────────────────────┤
│  ⚠  Ticket creation stopped                      │
│  3 of 11 tickets were created.                   │
│  Already-created tickets will not be duplicated  │
│  when you retry.                                 │
│                                                  │
│    [Close]              [Retry]                  │
└──────────────────────────────────────────────────┘
```

- ✕ and "Close" are available on error (can dismiss to return to session detail).
- "Retry" calls `planStore.confirmPlan()` again; the modal returns to **Confirming** state.
- i18n key: `planning.error_creation`, `planning.retry_creation`.

**Accessibility (confirming state)**:
- `aria-live="polite"` region announces each polling update: "Creating tickets: 5 of 11".
- Progress bar: `<progress>` element with `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, and `aria-label="Ticket creation progress"`.
- Non-dismissable: no focusable close controls present. Focus stays on the progress region.
- On error transition: `role="alert"` on the error message so it is immediately announced; focus moves to "Retry" button.

---

### 3.6 State: Done (All Tickets Created)

Triggered when: `GET /plan/status` returns `status === "tickets_created"`.

**Visual layout**:
```
┌──────────────────────────────────────────────────┐
│  [Session Title]                              ✕   │
├──────────────────────────────────────────────────┤
│                                                  │
│            ✓  (large success icon)               │
│                                                  │
│     Tickets created successfully                 │
│     11 tickets created                           │
│                                                  │
│     [View in Ticket Manager ↗]                   │
│                                                  │
│              [Back to sessions]                  │
│                                                  │
└──────────────────────────────────────────────────┘
```

- ✕ and "Back to sessions" both close the modal and navigate back to the session list (or simply close the modal if already on the session detail page).
- "View in Ticket Manager" opens the TM project URL in a new tab (`rel="noopener noreferrer"`).
- i18n keys: `planning.tickets_created`, `planning.view_in_tm`.

**Accessibility (done state)**:
- `role="alert"` or `aria-live="assertive"` on the success message so it is announced immediately.
- Focus moves to "View in Ticket Manager" button on state entry.
- ✕ button: `aria-label="Close"`.

---

## 4. AgentConfigPanel (T028)

### 4.1 Behavior

- Placed below the plan tree, above the modal footer, inside the **Ready** state only.
- Collapsed by default. The toggle trigger is a full-width clickable row:
  ```
  ▶  Agent configuration for this project
  ```
- Expanded state shows a two-column table: **Agent** | **Configuration override**.
- Read-only in v1: no editing affordance.
- Hidden entirely (not collapsed, not rendered) when `agentConfig === null`.

### 4.2 Table Layout

| Agent | Configuration override |
|-------|----------------------|
| backend | [override_text] |
| frontend | [override_text] |
| … | … |

- If `override_text` is longer than ~200 characters, show a truncated preview with "Show more" inline toggle.
- No sorting, filtering, or pagination needed (max ~10 rows).

### 4.3 XSS Safety (SR-001)

All agent name and override_text values come from LLM-generated content stored in the database. These values **must be rendered as React text nodes** — never via `dangerouslySetInnerHTML`. This is the primary XSS vector for this feature. The same rule applies to all plan node titles and descriptions in `PlanningModal`.

> **Implementation note for T028, T029**: Never use `dangerouslySetInnerHTML`. Render all LLM-sourced strings as `{text}` inside React elements. This applies unconditionally — there is no safe subset of HTML to allow.

### 4.4 Accessibility (AgentConfigPanel)

- Toggle button: `aria-expanded="true|false"`, `aria-controls="agent-config-panel"`.
- Panel: `id="agent-config-panel"`, `role="region"`, `aria-label="Agent configuration"`.
- Table: `<table>` with `<thead>` containing `<th scope="col">` headers.
- "Show more" toggles: `aria-expanded` and `aria-controls` for each row.

---

## 5. i18n Keys (T032)

Both `en.json` and `ru.json` must contain a `"planning"` namespace with these keys:

| Key | English value | Notes |
|-----|---------------|-------|
| `planning.generate_plan` | Generate Plan | Button on session detail |
| `planning.generating` | Generating your plan… | Spinner state heading |
| `planning.generating_hint` | This may take up to 60 seconds. | Spinner state subtext |
| `planning.plan_title` | Plan | Modal header label |
| `planning.epic_label` | Epic | Badge / section label |
| `planning.story_label` | Story | Badge / section label |
| `planning.task_label` | Task | Badge / section label |
| `planning.complexity` | Complexity | Badge prefix or aria-label |
| `planning.depends_on` | Depends on | Chip group label |
| `planning.confirm_plan` | Confirm plan & create tickets | Primary CTA |
| `planning.regenerate` | Regenerate | Secondary button |
| `planning.regenerate_confirm` | Regenerating will replace your current plan. This cannot be undone. Continue? | Confirmation dialog body |
| `planning.creating_tickets` | Creating tickets: {{created}} / {{total}} | Progress label; interpolated |
| `planning.tickets_created` | Tickets created successfully | Done state heading |
| `planning.tickets_count` | {{count}} tickets created | Done state sub-line |
| `planning.view_in_tm` | View in Ticket Manager | External link label |
| `planning.agent_config_title` | Agent configuration for this project | Panel toggle label |
| `planning.agent_config_hint` | Configuration overrides generated for each agent | Panel subtext |
| `planning.retry_creation` | Retry | Error state button |
| `planning.cancel` | Cancel | Modal cancel button |
| `planning.back_to_sessions` | Back to sessions | Done state close button |
| `planning.error_generation` | Plan generation failed. The service is temporarily unavailable. Your session is unchanged — you can try again. | Error banner text |
| `planning.error_validation` | The generated plan contains errors and cannot be shown. Please try generating again. | Validation error banner |
| `planning.error_creation` | Ticket creation stopped. {{created}} of {{total}} tickets were created. Already-created tickets will not be duplicated when you retry. | Partial failure text; interpolated |
| `planning.delete_story_confirm` | Delete Story "{{title}}" and all its tasks? This cannot be undone. | Delete confirmation |
| `planning.save_error` | Failed to save. Try again. | Inline edit error |
| `planning.view_plan` | View Plan | Secondary button on session detail (plan exists) |

**Russian translations** follow the same keys. Values must be written by a Russian-fluent agent or human reviewer; placeholder translations (e.g. `[RU] Generate Plan`) are not acceptable for ship.

---

## 6. UX Acceptance Criteria

These are testable criteria derived from the spec acceptance scenarios. Autotester should verify all of them. Frontend developer must ensure each is demonstrable before marking T029/T030 complete.

### 6.1 US1 — Plan Generation

| ID | Criterion | How to test |
|----|-----------|-------------|
| UAC-001 | Clicking "Generate Plan" opens the modal immediately (< 200ms) and shows the spinner without waiting for the API response | Manual or Vitest fake-timer test |
| UAC-002 | The generating modal cannot be closed by pressing Escape, clicking the backdrop, or using a ✕ button | Keyboard test + DOM assertion (no close control rendered) |
| UAC-003 | Within 60 seconds of triggering, the plan tree is visible with at least 1 Epic, 1 Story, 1 Task | E2E / manual with real API |
| UAC-004 | After browser close and reopen on the same session, the plan is shown without re-generating | Manual: reload page, confirm no new API POST |
| UAC-005 | On generation error, an error banner appears with "Try again" and "Close" buttons; the session status is still `approved` | Mock API error, verify banner and button presence |
| UAC-006 | Screen reader announces "Generating your plan…" on modal open (aria-live region) | NVDA/VoiceOver / automated axe audit |

### 6.2 US2 — Plan Review & Edit

| ID | Criterion | How to test |
|----|-----------|-------------|
| UAC-007 | Clicking a story title activates an inline `<input>` with the current value pre-filled | Vitest component test: click → assert input visible |
| UAC-008 | Typing a new title and pressing Enter saves it (PUT /plan called, response reflects new title) | Vitest with mocked API |
| UAC-009 | Pressing Escape during editing discards changes and restores the previous value | Vitest component test |
| UAC-010 | Character counter appears on title when ≥ 181 chars entered; appears on description when ≥ 451 chars | Vitest component test |
| UAC-011 | Entering an empty title and blurring reverts to the previous value (titles are required) | Vitest component test |
| UAC-012 | Saving an edit while network is slow shows a loading spinner inside the field | Vitest fake-timer: delay mock response, assert spinner |
| UAC-013 | Delete Story shows a confirmation dialog with story title in the message | Vitest component test |
| UAC-014 | After deleting a task that another task depends_on, the deleted task's local_id is removed from the other task's depends_on before saving | Vitest unit test on store logic |
| UAC-015 | Clicking "Cancel" closes the modal without destroying the plan; reopening shows the same plan | Vitest: close → reopen → assert plan unchanged |
| UAC-016 | Clicking "Confirm plan & create tickets" transitions the modal to the Confirming state and calls POST /confirm | Vitest with mocked API |
| UAC-017 | Plan tree is read-only when `plan.status` is `confirmed` or `tickets_created` | Vitest: render with read-only status, assert no editable elements |

### 6.3 US3 — Ticket Creation Progress

| ID | Criterion | How to test |
|----|-----------|-------------|
| UAC-018 | Confirming state is non-dismissable (no close control, Escape does nothing) | DOM assertion: no button with close role present |
| UAC-019 | Progress bar `aria-valuenow` updates as `created_count` increases via polling | Vitest fake-timer: advance polls, assert attribute changes |
| UAC-020 | Progress label shows "Creating tickets: X / N" with correct interpolated values | Vitest component test |
| UAC-021 | On successful completion, done state shows ticket count and a "View in Ticket Manager" link | Vitest with mocked `tickets_created` response |
| UAC-022 | "View in Ticket Manager" link opens in a new tab (`target="_blank"`, `rel="noopener noreferrer"`) | DOM assertion |
| UAC-023 | On partial failure, error banner shows correct counts: already-created and total | Vitest with mocked partial failure response |
| UAC-024 | "Retry" button in error state calls confirm again and transitions to Confirming state | Vitest component test |
| UAC-025 | Screen reader announces "Ticket creation stopped" immediately on error (role="alert") | axe audit + NVDA/VoiceOver |
| UAC-026 | The confirming overlay cannot be dismissed mid-creation (modal remains open if user tries Alt+F4 browser shortcut — verified by absence of close affordance) | DOM assertion |

### 6.4 US4 — Agent Config Panel

| ID | Criterion | How to test |
|----|-----------|-------------|
| UAC-027 | AgentConfigPanel is collapsed by default when `agentConfig` is non-null | Vitest: render ready state, assert panel collapsed |
| UAC-028 | Clicking the toggle expands the panel and shows agent names and override text | Vitest component test |
| UAC-029 | When `agentConfig` is null, the panel is not rendered at all (not collapsed — absent) | Vitest: render with `agentConfig=null`, assert panel not in DOM |
| UAC-030 | Panel toggle button has `aria-expanded` that updates on click | Vitest component test |

### 6.5 Accessibility (cross-cutting)

| ID | Criterion | How to test |
|----|-----------|-------------|
| UAC-031 | All modal states pass axe-core automated accessibility audit (zero violations) | `@axe-core/react` in Vitest |
| UAC-032 | Focus is trapped inside the modal while it is open | Vitest keyboard navigation test |
| UAC-033 | All interactive elements (buttons, inputs, delete icons) are keyboard-reachable via Tab | Manual keyboard walkthrough + Vitest |
| UAC-034 | All delete icon buttons have descriptive `aria-label` (not just icon) | DOM assertion in Vitest |
| UAC-035 | Error messages for inline edit failures are announced immediately by screen reader (`role="alert"`) | axe audit |
| UAC-036 | No plan node title or description is rendered with `dangerouslySetInnerHTML` | Code review gate (Code Reviewer must verify in T029/T030 review) |

### 6.6 Security (XSS — SR-001)

| ID | Criterion | How to test |
|----|-----------|-------------|
| UAC-037 | A plan node title containing `<script>alert(1)</script>` renders as literal text, not executed JavaScript | Vitest: render node with XSS payload, assert text content equals literal string |
| UAC-038 | An agent config `override_text` containing `<img onerror="alert(1)">` renders as literal text | Vitest: render AgentConfigPanel with XSS payload, assert text content |

---

## 7. State Machine Summary

```
Session status:    approved → planning → plan_ready → plan_confirmed → tickets_created
Modal state:       [closed]  Generating    Ready       Confirming         Done

Plan status:       (none)    draft→ready   ready       confirmed          tickets_created
```

- Modal auto-opens in Generating state when session transitions to `planning`.
- Modal can be closed (Cancel) only from Ready state; doing so leaves session in `plan_ready`.
- Confirming and Generating states are non-dismissable.
- Done state modal can be closed; session detail then shows the success banner.

---

## 8. Edge Cases

| Scenario | Expected behavior |
|----------|------------------|
| User opens modal on `plan_ready` session (plan already exists) | Modal opens directly in Ready state; no generation triggered; plan loaded from store/API |
| User edits a plan node but loses network mid-save | Save error appears inline; field shows previous value; user can retry |
| User triggers "Regenerate" after a plan exists | Confirmation dialog shown; on confirm, plan replaced, all edits lost; modal returns to Generating |
| User leaves the tab open during ticket creation (browser stays open) | Polling continues; done state is reached normally |
| Plan has 10 stories × 10 tasks (max size, 101 nodes) | UI renders all nodes; tree is tall but scrollable; no layout breakage; performance target: < 500ms render |
| `plan_content` returns with 0 stories | UI shows Epic with empty story list and an informational message "No stories were generated." No crash. |
| TM project link is null or empty | "View in Ticket Manager" link is hidden; success state still shows ticket count |

---

## 9. Out of Scope (v1)

- Adding new Stories or Tasks to a plan (FR-005: editing only, no create).
- Reordering Stories or Tasks via drag-and-drop.
- Editing `depends_on` relationships via UI (read-only chips).
- Editing `ticket_type` or `complexity` via UI (read-only badges).
- Multi-user collaborative plan editing.
- Re-planning after `tickets_created` status.
- Mobile-optimized layout beyond responsive basics.
