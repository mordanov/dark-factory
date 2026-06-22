# Contract: Component API Conventions

This contract defines the prop interface conventions for reusable components in this design system.
All `src/components/ui/` components follow shadcn/ui conventions exactly. Domain components
(`tickets/`, `admin/`, `layout/`) follow the conventions below.

---

## `cn()` Utility — Required Import Pattern

Every component that accepts a `className` prop MUST use `cn()` to merge classes:

```typescript
import { cn } from "@/lib/utils";

interface Props {
  className?: string;
}

function MyComponent({ className, ...props }: Props) {
  return <div className={cn("base-classes", className)} {...props} />;
}
```

---

## AppShell

**File**: `src/components/layout/AppShell.tsx`

```typescript
interface AppShellProps {
  children: React.ReactNode;
}
```

Renders: `<div className="min-h-screen bg-background">` containing `<Navbar />` and
`<main className="container mx-auto px-4 py-6">`.

---

## Navbar

**File**: `src/components/layout/Navbar.tsx`

No public props. Reads from `useAuthStore` and `useTheme`. Contains:
- Brand logo/name (left)
- Navigation links: Projects, Admin (role-gated) (centre/left)
- Dark mode toggle icon button (right)
- Language switcher (right)
- User menu dropdown (right)

Dark mode toggle: renders a `<Button variant="ghost" size="icon">` containing `<Sun />` or `<Moon />`
from Lucide React, toggling only between `light` and `dark` themes. Full multi-theme selection
remains in the existing `ThemeSwitcher` component for users who want it.

---

## ThemeSwitcher (updated)

**File**: `src/components/common/ThemeSwitcher.tsx`

Refactored to use `Button` and `cn()`. Swatch buttons become Radix `ToggleGroup` items.
No style prop usage. Props unchanged (no public props — reads from `useTheme`).

---

## TicketCard

**File**: `src/components/tickets/TicketCard.tsx`

```typescript
interface TicketCardProps {
  ticket: TicketResponse;
  onClick?: () => void;
  className?: string;
}
```

Wraps shadcn `<Card>` with `<motion.div whileHover={{ y: -2 }}>`. Uses `<Badge>` for status and type.

---

## StatusTransitionButton (updated)

**File**: `src/components/tickets/StatusTransitionButton.tsx`

Props unchanged. Internal modal migrated from custom overlay to shadcn `<Dialog>`.
All inline `style` props replaced with Tailwind classes.

---

## TicketForm (updated)

**File**: `src/components/tickets/TicketForm.tsx`

Props unchanged. All inputs replaced with shadcn `<Input>`, `<Textarea>`, `<Label>`, `<Select>`.
Tag input integrated with shadcn `<Popover>`.

---

## AdminAssignModal (extracted)

**File**: `src/components/tickets/AdminAssignModal.tsx` (new — extracted from TicketDetailPage)

```typescript
interface AdminAssignModalProps {
  open: boolean;
  onClose: () => void;
  ticketId: string;
  currentUserId?: string;
  onAssigned: (updated: TicketResponse) => void;
}
```

Uses shadcn `<Dialog>` instead of custom overlay.

---

## UserTable (updated)

**File**: `src/components/admin/UserTable.tsx`

Props unchanged. Migrated to shadcn `<Table>`, `<Badge>` for role display, `<Button>` for actions.

---

## FilterBar (updated)

**File**: `src/components/common/FilterBar.tsx`

Props unchanged. Search input migrated to shadcn `<Input>`. Filter chips use `<Badge>` + `<Button variant="ghost">`.

---

## Animation Variants

Shared Framer Motion variants — define once in `src/lib/motion.ts`:

```typescript
export const pageVariants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.2 } },
  exit: { opacity: 0, y: -4, transition: { duration: 0.15 } },
};

export const dialogVariants = {
  initial: { opacity: 0, scale: 0.96 },
  animate: { opacity: 1, scale: 1, transition: { duration: 0.15 } },
  exit: { opacity: 0, scale: 0.96, transition: { duration: 0.1 } },
};

export const cardHover = {
  whileHover: { y: -2 },
  transition: { duration: 0.15 },
};
```

---

## No-Style-Prop Rule

**Contract**: Zero React `style` prop usage is permitted in any component file after migration.
This includes:
- Direct inline: `style={{ color: "red" }}`
- Named objects: `const s: React.CSSProperties = {...}; ... style={s}`
- Dynamic expressions: `style={{ ...(condition && { color: x }) }}`

All styling MUST use Tailwind utility classes, optionally composed with `cn()`. The only exception
is third-party library integration where a style prop is the API-mandated approach (e.g.,
virtualized list item positioning) — document with a `// layout-api-required` comment.
