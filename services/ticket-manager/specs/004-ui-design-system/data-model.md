# Design System Data Model

This feature has no backend schema changes. The "data model" here is the **design token system**
and **component architecture** — the structural entities that make up the new design system.

---

## Design Token Entities

### ColorToken

A CSS custom property that maps a semantic color role to a concrete value.

| Attribute | Type | Notes |
|-----------|------|-------|
| `name` | `--{role}` CSS var | Semantic name (e.g. `--primary`, `--background`) |
| `value` | HSL channel string | e.g. `"211 100% 40%"` — no `hsl()` wrapper (Tailwind opacity modifier syntax) |
| `scheme` | `light \| dark \| solarized \| oceanic \| high-contrast \| warm` | Which theme block defines this value |
| `tailwindAlias` | Tailwind config key | e.g. `primary`, `background`, `muted` |

**All color tokens** (dual naming — existing `--color-*` + new shadcn aliases):

| Existing var | shadcn/ui alias | Tailwind key | Light value (HSL) |
|--------------|----------------|-------------|-------------------|
| `--color-bg` | `--background` | `background` | `0 0% 96%` |
| `--color-surface` | `--card` | `card` | `0 0% 100%` |
| `--color-border` | `--border` | `border` | `0 0% 88%` |
| `--color-text-primary` | `--foreground` | `foreground` | `236 30% 14%` |
| `--color-text-secondary` | `--muted-foreground` | `muted-foreground` | `0 0% 33%` |
| `--color-text-inverse` | `--primary-foreground` | `primary-foreground` | `0 0% 100%` |
| `--color-accent` | `--primary` | `primary` | `211 100% 40%` |
| `--color-accent-hover` | — | — | `211 100% 32%` |
| `--color-accent-subtle` | `--accent` | `accent` | `219 100% 95%` |
| `--color-danger` | `--destructive` | `destructive` | `6 75% 46%` |
| `--color-success` | — | `success` | `145 63% 42%` |
| `--color-warning` | — | `warning` | `28 80% 52%` |
| — | `--input` | `input` | same as `--border` |
| — | `--ring` | `ring` | same as `--primary` |
| — | `--muted` | `muted` | `0 0% 94%` |
| — | `--secondary` | `secondary` | `0 0% 94%` |
| — | `--secondary-foreground` | `secondary-foreground` | `236 30% 14%` |
| — | `--radius` | — | `0.375rem` (border-radius base) |

---

### SpacingToken

The spacing scale used by Tailwind (already built-in, no custom overrides needed). Reference only.

| Scale step | rem value | px equivalent |
|-----------|-----------|---------------|
| `1` | `0.25rem` | 4px |
| `2` | `0.5rem` | 8px |
| `3` | `0.75rem` | 12px |
| `4` | `1rem` | 16px |
| `6` | `1.5rem` | 24px |
| `8` | `2rem` | 32px |
| `12` | `3rem` | 48px |
| `16` | `4rem` | 64px |

---

### TypographyToken

Font sizes used across components (Tailwind built-in scale, no custom sizes):

| Token | Class | rem | Usage |
|-------|-------|-----|-------|
| `xs` | `text-xs` | 0.75rem | badges, captions, timestamps |
| `sm` | `text-sm` | 0.875rem | body secondary, table cells |
| `base` | `text-base` | 1rem | body primary |
| `lg` | `text-lg` | 1.125rem | section labels |
| `xl` | `text-xl` | 1.25rem | card titles |
| `2xl` | `text-2xl` | 1.5rem | page headings |
| `3xl` | `text-3xl` | 1.875rem | main page title |

Font weight: `normal` (400) for body, `medium` (500) for labels, `semibold` (600) for headings/buttons.
Font family: System font stack via Tailwind `font-sans`.

---

### ComponentVariant

The set of named visual variants for each reusable UI component.

**Button**:
| Variant | Usage |
|---------|-------|
| `default` | Primary action (accent color fill) |
| `destructive` | Delete / irreversible actions (danger color) |
| `outline` | Secondary action (bordered, transparent fill) |
| `secondary` | Tertiary action (muted fill) |
| `ghost` | Navigation links, icon-only actions |
| `link` | Inline text links |

**Button size**:
| Size | Usage |
|------|-------|
| `default` | Standard form actions |
| `sm` | Compact contexts (table rows, cards) |
| `lg` | Primary CTA (login page) |
| `icon` | Icon-only buttons (24×24px) |

**Badge**:
| Variant | Usage |
|---------|-------|
| `default` | Tags, labels |
| `secondary` | Neutral info |
| `destructive` | Error states |
| `outline` | Ticket status in low-emphasis context |

---

### ThemeScheme

The six named themes managed by `useTheme`:

| Key | Base Palette | Type |
|-----|-------------|------|
| `light` | Blue accent on light grey | Light |
| `dark` | Blue accent on dark navy | Dark |
| `solarized` | Solarized warm beige | Light |
| `oceanic` | Cool dark blue-grey | Dark |
| `high-contrast` | Black/white WCAG AAA | Dark |
| `warm` | Warm terracotta accent | Light |

**Dark schemes** (`dark`, `oceanic`, `high-contrast`): `useTheme` adds `.dark` class to `<html>`.
**Light schemes** (`light`, `solarized`, `warm`): `.dark` class removed from `<html>`.

---

## Component Architecture

### Layout Components (`src/components/layout/`)

| Component | Props | Responsibility |
|-----------|-------|----------------|
| `AppShell` | `children: ReactNode` | Top-level authenticated layout: renders `<Navbar>` + `<main>` content area |
| `Navbar` | — | Top navigation bar: brand, nav links, dark mode toggle, language switcher, user menu |

### UI Primitives (`src/components/ui/`)

Generated by shadcn/ui CLI. Each is a thin wrapper over Radix UI primitive with Tailwind classes.
No custom business logic inside `ui/` components.

### Domain Components

Existing components refactored to use `ui/` primitives. Business logic stays in domain components;
visual rendering delegated to `ui/` primitives.

### Utility (`src/lib/utils.ts`)

```typescript
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

The `cn()` helper is the single utility for conditional class concatenation throughout the codebase.
