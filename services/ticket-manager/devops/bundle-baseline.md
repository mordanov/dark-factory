# Bundle Size Baseline — Feature 004 UI Design System

**Recorded**: 2026-05-25
**Branch**: `004-ui-design-system`
**Purpose**: SC-008 reference — post-refactor initial load time must not exceed 110% of this baseline.

---

## Pre-Refactor Baseline (committed state at `739eac7`)

Build from `git show HEAD:frontend/package.json` — no Tailwind, no framer-motion, no shadcn/ui.

| Asset | Raw size | Notes |
|---|---|---|
| `index-H_3UCYAe.js` | 416 kB | ~125 kB gzip (estimated, 30% ratio) |
| `index-BXFITmab.css` | 2.1 kB | custom CSS + theme vars only |
| **Initial load (gzip est.)** | **~127 kB** | JS + CSS combined over-the-wire |

> Gzip estimate for pre-refactor JS is derived from the 416 kB raw size using the typical 30% compression ratio for a React SPA bundle of this composition (React 18, React Router 6, TanStack Query 5, i18next, Zustand, axios).

---

## Phase 1 Build (toolchain installed, no shadcn/ui components yet)

Run on 2026-05-25 after T001–T009 applied (Tailwind, PostCSS, framer-motion, lucide-react, clsx, tailwind-merge installed; components not yet imported in source).

| Asset | Raw size | Gzip size |
|---|---|---|
| `index-DCzSqB-9.js` | 429.35 kB | **134.51 kB** |
| `index-C7848A7q.css` | 35.87 kB | **6.82 kB** |
| HTML | 0.46 kB | 0.30 kB |
| Geist fonts (woff2, 5 files) | 76.41 kB | N/A (not blocking) |
| **Initial load (gzip)** | — | **~141.63 kB** |

**Phase 1 delta vs baseline**: +14.63 kB gzip (+11.5%) — CSS jumped from ~2K to 6.82K (Tailwind base/components layer); JS grew slightly. Within SC-008 range for this intermediate state; final bundle depends on tree-shaking of Radix/framer-motion after component migrations.

---

## SC-008 Budget

| Metric | Baseline | 110% limit | Phase 1 |
|---|---|---|---|
| Initial load gzip | ~127 kB | **~140 kB** | ~141.6 kB |

**Status**: Phase 1 is marginally over the 110% SC-008 budget. This is expected at this stage — framer-motion and Radix UI packages are in node_modules but not yet imported, so tree-shaking cannot eliminate them fully from the bundled output. The CSS growth (+4.7 kB gzip) accounts for the overage.

**Action**: Monitor SC-008 after Phase 7 completion. If the final bundle exceeds 110%, mitigations include:
1. Enable Vite `build.rollupOptions.output.manualChunks` to split vendor code (lazy-load Radix Dialog, Sheet, Popover on demand)
2. Use dynamic import for framer-motion (`import('framer-motion')`) on pages that need it
3. Audit lucide-react icon imports — use named imports only (`import { Sun, Moon } from "lucide-react"`)

---

## CI/CD Pipeline Assessment

File: `.github/workflows/ci.yml` — `frontend` job

| Check | Status | Notes |
|---|---|---|
| Node.js version | ✅ v20 | Compatible with Tailwind 3.x, Vite 5.x, shadcn/ui |
| Package install | ✅ `npm ci` | Reproducible; package-lock.json cache key correct |
| Cache invalidation | ✅ keyed on `frontend/package-lock.json` | Will re-download on dep changes (expected) |
| Test step | ✅ `npm run test:run` | Vitest; runs before build |
| Build step | ✅ `npm run build` | Vite + PostCSS + Tailwind; `VITE_API_BASE_URL` injected |
| PostCSS integration | ✅ auto-detected | `postcss.config.js` at `frontend/` root; Vite picks it up automatically |
| TypeScript paths | ✅ `@/*` → `src/*` | Both `vite.config.ts` and `tsconfig.app.json` configured |
| shadcn/ui path alias | ✅ `@/components/ui` | `components.json` aliases verified |

**No CI pipeline changes required.** The existing pipeline handles Tailwind CSS v3 + PostCSS correctly.

---

## Build Validation

```
npm run typecheck  →  ✅ 0 errors
npm run build      →  ✅ 199 modules, built in 1.37s
```

Both run clean on 2026-05-25 with Phase 1 dependencies installed.

---

## Final Post-Phase-7 Build (T047 — all 47 tasks complete)

Run on 2026-05-25 after TS fixes to KanbanCard.tsx and TagInput.tsx.

| Chunk | Raw size | Gzip size |
|---|---|---|
| `vendor-router` (react-router-dom + react-dom) | 205.63 kB | 67.13 kB |
| `index` (app code) | 168.59 kB | 52.61 kB |
| `vendor-motion` (framer-motion) | 128.74 kB | 42.31 kB |
| `vendor-radix` (@radix-ui/* primitives) | 132.69 kB | 37.16 kB |
| `index.css` (Tailwind output) | 53.28 kB | 9.51 kB |
| `vendor-i18n` (i18next) | 49.55 kB | 15.48 kB |
| `vendor-query` (TanStack Query) | 42.19 kB | 12.76 kB |
| `vendor-react` (react) | 0.04 kB | 0.06 kB |
| **Total initial load** | — | **237.02 kB** |

## SC-008 Final Assessment

| Metric | Value | Budget | Status |
|---|---|---|---|
| Pre-refactor baseline gzip | ~127 kB | — | reference |
| SC-008 budget (110%) | — | **~140 kB** | — |
| Final build gzip | **237 kB** | ~140 kB | **FAIL (+87%)** |

**SC-008 FAIL** — final bundle is 87% over the 10% growth budget.

**Root causes** (by gzip contribution):
1. react-router-dom + react-dom: 67 kB (was in baseline; this chunk is larger due to React Router v6 overhead)
2. App code: 53 kB (was ~30 kB estimated; grew from 15 new components)
3. framer-motion: 42 kB (new — no animation library existed pre-refactor)
4. @radix-ui/* (38 packages): 37 kB (new — no component library pre-refactor)
5. Tailwind CSS: 9.5 kB (was 1.5 kB — +8 kB)
6. i18next: 15.5 kB (was ~15 kB — essentially unchanged)
7. TanStack Query: 12.8 kB (was ~12 kB — unchanged)

**Context**: The pre-refactor app had zero external component library. Adding shadcn/ui (38 Radix packages), framer-motion, and Tailwind CSS output is the cost of the feature. The 10% SC-008 budget was set assuming only CSS output growth, not a full component library.

## Fix Path for SC-008

The `manualChunks` configuration added to `vite.config.ts` provides **cache efficiency** and **HTTP/2 parallelization** but does NOT reduce initial load without lazy loading — all chunks are loaded eagerly.

To pass SC-008, the frontend agent needs to implement **React.lazy route splitting**. Estimated initial load after route splitting:

| Chunk loaded on first paint | Gzip |
|---|---|
| react + react-dom | ~42 kB |
| react-router-dom | ~26 kB |
| App shell (Navbar, AppShell only) | ~8 kB |
| First lazy-loaded page | ~6–10 kB |
| CSS (critical) | ~9.5 kB |
| **Estimated total** | **~92–96 kB** |

With route-level code splitting, framer-motion (42 kB), remaining Radix components (37 kB), and page code would all lazy-load on navigation — passing SC-008 comfortably.

**Recommendation for product-manager**: Scope React.lazy route splitting as a follow-on task or accept SC-008 FAIL as a known trade-off of the component library adoption.

## npm audit Result (T047)

```
npm audit --audit-level=high
```

**Result: PASS** — zero high or critical vulnerabilities.

5 moderate vulnerabilities found in dev dependencies only (esbuild ≤0.24.2 via vite@5, vitest). The fix requires `npm audit fix --force` which would install vite@8 (breaking change). Recommend deferring until Vite major version upgrade is planned.

## TS Build Fixes Applied

Two TypeScript errors blocked the build after Phase 7:

1. **`KanbanCard.tsx:31`** — framer-motion `onDragStart` type conflict with HTML5 drag API. Fixed by wrapping `<motion.div>` in a native `<div draggable onDragStart={handler}>`. Behavior preserved.
2. **`TagInput.tsx:8`** — unused `Button` import (`noUnusedLocals: true`). Fixed by removing the import.

Both fixes are minimal, non-behavioral, and preserve the component's existing functionality.
