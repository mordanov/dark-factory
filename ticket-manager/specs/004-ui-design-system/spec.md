# Feature Specification: Frontend Design System

**Feature Branch**: `004-ui-design-system`
**Created**: 2026-05-25
**Status**: Implementation Complete — Pending Final Verification

## Clarifications

### Session 2026-05-25

- Q: Where should the dark mode / color scheme toggle be placed in the UI? → A: Top navigation bar (always visible from any page)
- Q: Does SC-005 "zero inline style prop overrides" cover named CSS constant objects (e.g., `const s: CSSProperties`) as well as direct inline `style={{...}}`? → A: Yes — all React `style` prop usage eliminated, including named constant objects; all styling via design-token utility classes
- Q: Which interaction categories should use Framer Motion animations? → A: Page transitions, modal/dialog/sheet enter+exit, and interactive feedback (button press, hover lift on cards)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Accessible & Keyboard-Navigable Interface (Priority: P1)

A user navigating the ticket management system can operate every feature — forms, dropdowns, dialogs, menus, tabs — using only a keyboard, without needing a mouse. Screen reader users receive meaningful announcements at every interactive state change. The interface meets WCAG 2.1 AA accessibility standards across all pages and components.

**Why this priority**: Accessibility is foundational. Without it, a segment of users cannot use the product at all. It also unblocks keyboard power-users (common among developers and agent operators) who rely on Tab/Enter/Escape navigation. All other stories build on this foundation.

**Independent Test**: Can be tested by tab-navigating the full ticket management workflow — create ticket, transition status, assign user, submit progress update — verifying every element is reachable, focusable, and actionable without mouse interaction.

**Acceptance Scenarios**:

1. **Given** the ticket list page is open, **When** a user presses Tab repeatedly, **Then** every interactive element (buttons, links, inputs, dropdowns) receives visible focus in a logical order.
2. **Given** a modal dialog is open, **When** the user presses Escape, **Then** the dialog closes and focus returns to the triggering element.
3. **Given** a dropdown menu is triggered, **When** the user navigates with arrow keys, **Then** menu items are traversed and Enter selects the highlighted item.
4. **Given** a screen reader is active, **When** a form validation error appears, **Then** the error is announced without requiring page reload.
5. **Given** any interactive component, **When** inspected with an automated accessibility checker, **Then** no WCAG 2.1 AA violations are reported.

---

### User Story 2 - Dark Mode Support (Priority: P2)

A user can switch the entire application between a light and a dark color scheme. Their preference is remembered and applied consistently across all pages without any visual inconsistencies, flashes, or partially-themed components.

**Why this priority**: Dark mode is a standard expectation for modern SaaS tools, particularly for developer-facing products used in low-light environments for extended periods. The existing theming infrastructure already supports `data-theme` but is inconsistently applied.

**Independent Test**: Can be tested by toggling dark mode and verifying every visible surface — backgrounds, text, borders, input fields, modals, popovers, tooltips — uses the dark palette consistently.

**Acceptance Scenarios**:

1. **Given** light mode is active, **When** the user switches to dark mode, **Then** all backgrounds, text, and borders update immediately without a full page reload.
2. **Given** dark mode was last selected, **When** the user returns to the application, **Then** dark mode is applied on first render without a visible flash of light mode.
3. **Given** dark mode is active, **When** a modal, dropdown, or popover is opened, **Then** it renders with the dark color scheme, not the light default.
4. **Given** any theme is active, **When** interactive states (hover, focus, active, disabled) are triggered, **Then** contrast ratios remain WCAG 2.1 AA compliant.

---

### User Story 3 - Consistent Visual Design System (Priority: P3)

All pages and components share a unified visual language: consistent spacing scale, typography hierarchy, color palette, border radius, and shadow depth. No component looks visually out of place relative to others. The interface has a clean, modern SaaS aesthetic with intentional use of whitespace.

**Why this priority**: The existing UI was generated incrementally and lacks visual consistency. Inconsistent spacing, mixed font sizes, and inline styles make the interface feel unpolished and harder to extend. A unified design system prevents future divergence.

**Independent Test**: Can be tested by visual comparison across all pages, verifying uniform heading sizes, consistent button styles, aligned form inputs, and matching card/panel spacing without per-component overrides.

**Acceptance Scenarios**:

1. **Given** any two buttons of the same variant on different pages, **When** compared visually, **Then** they have identical appearance, sizing, and spacing.
2. **Given** any form in the application, **When** inspected, **Then** labels, inputs, validation messages, and submit buttons follow a consistent visual pattern.
3. **Given** all pages are viewed at 1280px width, **When** spacing between sections is measured, **Then** the same vertical rhythm is applied throughout.
4. **Given** the component library, **When** a developer adds a new feature using existing components, **Then** no custom CSS overrides or inline styles are needed to match the existing visual style.

---

### User Story 4 - Responsive Layout for All Screen Sizes (Priority: P4)

A user on a tablet or mobile device can use the ticket management system without horizontal scrolling, broken layouts, or content overflow. Navigation, ticket lists, forms, and detail views adapt fluidly to smaller viewports.

**Why this priority**: While the primary users are developers on desktops, mobile/tablet access is needed for on-the-go ticket review. Broken layouts are a significant quality signal even if the usage volume is low.

**Independent Test**: Can be tested by resizing the browser to 375px (mobile) and 768px (tablet) widths and confirming all primary workflows — view ticket list, open ticket, submit update, change status — are fully functional without horizontal scroll.

**Acceptance Scenarios**:

1. **Given** the app is viewed at 375px width, **When** the ticket list is displayed, **Then** all content fits within the viewport without horizontal scrolling.
2. **Given** the app is viewed on tablet, **When** a modal dialog opens, **Then** it is properly sized and does not extend beyond the viewport.
3. **Given** the navigation sidebar is present on desktop, **When** viewed on mobile, **Then** navigation collapses into a usable mobile-friendly pattern.
4. **Given** a form with multiple fields, **When** viewed on mobile, **Then** inputs are full-width and tap targets meet minimum size requirements.

---

### Edge Cases

- What happens when a user has both OS dark mode preference and an explicit in-app selection? (App setting takes priority; OS preference is the default if no in-app selection exists.)
- How does keyboard navigation handle dynamically added content (e.g., a new assignee row appearing after an API call)? (Focus must be managed explicitly when new interactive content appears.)
- What happens when a custom color theme (from feature 002) is active alongside dark mode? (Custom color tokens must be applied on top of the dark base palette, not replace it.)
- How are loading and empty states presented in the new design system? (Skeleton loaders and empty state illustrations use the same design tokens as all other components.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every interactive element MUST be operable via keyboard alone (Tab, Enter, Space, Escape, arrow keys as appropriate per element type).
- **FR-002**: Every interactive element MUST have a visible focus indicator that meets WCAG 2.1 AA contrast requirements.
- **FR-003**: All form inputs MUST have accessible labels programmatically associated with their controls.
- **FR-004**: All dialogs, popovers, and modals MUST trap focus while open and restore focus to the trigger element on close.
- **FR-005**: Dynamic state changes (loading, error, success, new content) MUST be announced to screen reader users without requiring page navigation.
- **FR-006**: The application MUST provide a light and a dark color scheme selectable via a toggle in the top navigation bar, always visible from any page.
- **FR-007**: The selected color scheme MUST persist across browser sessions.
- **FR-008**: Color scheme MUST be applied to 100% of visible surfaces — no partially-themed components.
- **FR-009**: All text and interactive elements MUST meet WCAG 2.1 AA contrast ratios in both color schemes.
- **FR-010**: All pages MUST be usable on viewport widths from 375px (mobile) to 1920px (wide desktop) without horizontal scrolling.
- **FR-011**: Touch targets on mobile MUST be at minimum 44×44px.
- **FR-012**: The design system MUST expose a consistent spacing scale, typography hierarchy, and color palette applicable across all components.
- **FR-013**: No component MAY use arbitrary magic numbers for spacing — all spacing MUST reference design tokens.
- **FR-014**: All React `style` prop usage MUST be eliminated — this includes both direct inline `style={{...}}` expressions and named CSS constant objects (e.g., `const s: React.CSSProperties = {...}`) applied via `style={s}`. All styling MUST use design-token-based utility classes.
- **FR-015**: Form components (inputs, selects, checkboxes, text areas) MUST follow a single consistent visual pattern across all pages.
- **FR-016**: Business logic in existing components MUST be preserved unchanged — only UI structure and styling are in scope.

### Key Entities

- **Design Token**: A named variable representing a discrete value in the visual language (color, spacing, radius, shadow, font size). Tokens are the single source of truth for all visual decisions.
- **Component Variant**: A pre-defined visual style of a component (e.g., button variants: primary, secondary, destructive, ghost). Variants are composable and cover all use cases without per-instance overrides.
- **Color Scheme**: A named theme (light, dark) that maps design tokens to concrete color values. Switching schemes updates all token values simultaneously.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero mouse-only interactions remain — all workflows completable via keyboard alone in under the same number of steps as mouse navigation.
- **SC-002**: Automated accessibility scan reports zero WCAG 2.1 AA violations across all pages.
- **SC-003**: Both light and dark color schemes are applied to 100% of visible surfaces with no exceptions.
- **SC-004**: All pages render correctly at 375px, 768px, 1024px, and 1440px viewport widths without horizontal scroll.
- **SC-005**: Zero inline `style` prop overrides remain in component files after refactoring.
- **SC-006**: A new UI feature can be built using only existing design system components and tokens, requiring no new CSS files or style blocks.
- **SC-007**: All business logic tests (if any exist) continue passing — no functional regression introduced.
- **SC-008**: Lighthouse LCP (Largest Contentful Paint) on the login page does not increase by more than 10% relative to the pre-refactor baseline measured in the same environment. Raw gzip bundle size is a contributing signal but not the primary metric — vendor chunk caching and HTTP/2 parallelisation are not captured by raw gzip comparison. *(Criterion recalibrated 2026-05-25: original raw-gzip proxy did not account for the planned framer-motion and @radix-ui/* dependency footprint; see research.md Decision 5 and ADR.)*

## Assumptions

- The refactoring is a pure UI layer change; no backend API contracts, data models, or business logic are in scope.
- The existing custom color theming system (feature 002, `data-theme` attribute on `<html>`) is the integration point for dark mode — the new design system extends it rather than replacing it.
- The primary target users are developers and AI agents using desktop browsers; mobile is a P4 enhancement.
- Existing translation/i18n keys and localization files are out of scope — text content is preserved as-is.
- The refactoring will be done incrementally by component/page; the application remains functional throughout the process.
- Framer Motion animations are additive enhancements only — removing them would not break functionality. Animation scope covers three categories: page transitions, modal/dialog/sheet enter+exit, and interactive feedback (button press, hover lift on cards).
- Feature 003 (agent API SDLC) implementation work on `main` is the baseline; this refactor applies on top.
