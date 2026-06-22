# Contract: Theming Integration

This contract defines how the new Tailwind/shadcn/ui design system integrates with the existing
feature 002 `data-theme` CSS variable system.

---

## CSS Variable Contract

**File**: `frontend/src/styles/themes.css`

Each theme block MUST define **both** naming conventions:

```css
[data-theme="light"] {
  /* ── Legacy vars (feature 002 reads/writes these) ── */
  --color-bg: hsl(0 0% 96%);
  --color-surface: hsl(0 0% 100%);
  --color-border: hsl(0 0% 88%);
  --color-text-primary: hsl(236 30% 14%);
  --color-text-secondary: hsl(0 0% 33%);
  --color-text-inverse: hsl(0 0% 100%);
  --color-accent: hsl(211 100% 40%);
  --color-accent-hover: hsl(211 100% 32%);
  --color-accent-subtle: hsl(219 100% 95%);
  --color-danger: hsl(6 75% 46%);
  --color-success: hsl(145 63% 42%);
  --color-warning: hsl(28 80% 52%);

  /* ── shadcn/ui vars (Tailwind config references these) ── */
  /* Values are HSL channels WITHOUT hsl() wrapper (required by Tailwind opacity modifiers) */
  --background: 0 0% 96%;
  --foreground: 236 30% 14%;
  --card: 0 0% 100%;
  --card-foreground: 236 30% 14%;
  --popover: 0 0% 100%;
  --popover-foreground: 236 30% 14%;
  --primary: 211 100% 40%;
  --primary-foreground: 0 0% 100%;
  --secondary: 0 0% 94%;
  --secondary-foreground: 236 30% 14%;
  --muted: 0 0% 94%;
  --muted-foreground: 0 0% 33%;
  --accent: 219 100% 95%;
  --accent-foreground: 236 30% 14%;
  --destructive: 6 75% 46%;
  --destructive-foreground: 0 0% 100%;
  --border: 0 0% 88%;
  --input: 0 0% 88%;
  --ring: 211 100% 40%;
  --radius: 0.375rem;
}
```

The same pattern applies to all six theme blocks. Dark schemes additionally trigger the `.dark`
class on `<html>` (see Dark Mode Toggle Contract below).

## Tailwind Config Contract

**File**: `frontend/tailwind.config.ts`

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        success: "hsl(var(--color-success))",
        warning: "hsl(var(--color-warning))",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
};

export default config;
```

## Dark Mode Toggle Contract

**File**: `frontend/src/hooks/useTheme.ts`

The dark themes (`dark`, `oceanic`, `high-contrast`) MUST apply both the `data-theme` attribute
AND the `.dark` CSS class to `document.documentElement`. Light themes remove the `.dark` class.

```typescript
const DARK_THEMES: ThemeKey[] = ["dark", "oceanic", "high-contrast"];

function applyTheme(theme: ThemeKey) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.classList.toggle("dark", DARK_THEMES.includes(theme));
}
```

**Constraint**: The `.dark` class enables Tailwind's `dark:` utility variants. `data-theme`
continues to control `themes.css` CSS variable values. Both MUST be applied; neither alone
is sufficient.

## Feature 002 Compatibility

Feature 002's admin color customization writes `--color-*` CSS custom properties directly onto
`document.documentElement.style`. These overrides continue to work because:
1. They override values in `themes.css` without touching the `--background`, `--primary`, etc. vars.
2. The legacy `--color-*` vars are still present in all theme blocks.
3. Components migrated to Tailwind (`bg-primary`, `text-foreground`) use the shadcn vars, which
   are not overridden by feature 002. Only legacy-styled components continue to reflect custom colors.

**Migration note**: Full feature 002 integration with the new design system (mapping admin-set
`--color-*` values into shadcn/ui vars in real time) is out of scope for this feature.
