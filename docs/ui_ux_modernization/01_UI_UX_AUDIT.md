# UI/UX Forensic Audit — FieldTrack Pro Web

**Scope:** `fieldtrackpro-web` (React 18 + Vite + Tailwind CSS 3 + TypeScript). No backend, Android, or business-logic files were touched or altered by this audit.

**Baseline captured before any change** (git repo root: `field track pro/`):

```
Branch: master
Modified (unstaged, pre-existing, not touched by this pass): fieldtrackpro-web/src/App.test.tsx
Untracked (pre-existing, not touched): docs/FILE_MEDIA_INDEPENDENT_AUDIT.md,
  docs/final_forensic_audit/, fieldtrackpro-backend/temp_seed_data.py
Last commit: 3fc131a "phase 6: MapLibre + OpenStreetMap map stack"
```

Baseline verification run (before any UI/UX change):

| Check | Result |
|---|---|
| `tsc --noEmit` | Clean, 0 errors |
| `eslint . --ext .ts,.tsx --max-warnings 0` | 1 pre-existing error (`tileConfig.ts:45`, unrelated `Boolean` wrapper-type rule), 1 pre-existing warning (`FieldTrackMap.tsx:92`, exhaustive-deps) |
| `vitest run` | 68 passed / 1 pre-existing failure (`DashboardPage.test.tsx`, FT-019 business-logic assertion, unrelated to styling) |
| `vite build` | Succeeds (one pre-existing chunk-size advisory, not an error) |

These three pre-existing issues are **not part of this UI/UX task** (rule 15: don't change unrelated files) and are called out explicitly so they are never mistaken for something this pass introduced or silently fixed.

## Inventory — Routes / Pages

| Route | File | Shared components used |
|---|---|---|
| `/login` | `pages/LoginPage.tsx` | Input, Button |
| `/` | `pages/DashboardPage.tsx` | PageHeader, MetricCard, Card, Button, ErrorBanner, raw `<table>`, raw `<button>` (quick actions) |
| `/employees` | `pages/EmployeesPage.tsx` | PageHeader, DataTable, Modal, Input, Button, StatusBadge, EmptyState, ErrorBanner, raw `<select>` ×2 |
| `/territories` | `pages/TerritoriesPage.tsx` | PageHeader, Card, Modal, Input, Button, EmptyState, ErrorBanner |
| `/customers` | `pages/CustomersPage.tsx` | PageHeader, DataTable, Modal, Input, Button, EmptyState, ErrorBanner, raw `<select>` ×1 |
| `/visits` | `pages/VisitsPage.tsx` | PageHeader, DataTable, Modal, Input, Button, StatusBadge, EmptyState, ErrorBanner, raw `<select>` ×2, raw `<button>` filter pills |
| `/visits/:id` | `pages/VisitDetailsPage.tsx` | Card, Button, Input, StatusBadge, ErrorBanner, MediaThumbnail, raw `<input type="file">` |
| `/geo-logs` | `pages/GeoLogsPage.tsx` | PageHeader, DataTable, StatusBadge, EmptyState, ErrorBanner |
| `/map` | `pages/MapPage.tsx` | PageHeader, Card, EmptyState, FieldTrackMap |
| `/media` | `pages/MediaViewerPage.tsx` | PageHeader, Card, Input, EmptyState, ErrorBanner, MediaThumbnail |
| `/forms` | `pages/FormsPage.tsx` | PageHeader, Card, EmptyState |
| `/reports` | `pages/ReportsPage.tsx` | PageHeader, MetricCard, Card, EmptyState, ErrorBanner, raw `<table>` |
| `/settings` | `pages/SettingsPage.tsx` | PageHeader, Card |
| `/profile` | `pages/ProfilePage.tsx` | PageHeader, Card, Button, Input, StatusBadge |

Layout shell: `components/layout/{Sidebar,Header,Layout}.tsx`.

## Inventory — Shared Component Library

`Button`, `Input`, `Modal`, `Card` (+`CardHeader/Title/Subtitle`), `DataTable`, `MetricCard`, `StatusBadge`, `PageHeader`, `EmptyState`, `ErrorBanner`, `MediaThumbnail`. **No shared `Select` component exists** — five pages hand-duplicate an identical `<select>` markup/class block instead.

## Method

Every page and shared component file was read in full (not sampled). For spacing/sizing classes, every `-space-N` utility usage in `src/` was extracted and cross-checked against the actual token list defined in `tailwind.config.js`, since the reported symptoms (clipped text, overlapping icons, inconsistent button/table spacing) are exactly the signature of a Tailwind utility class silently failing to compile. Git baseline, typecheck, lint, and test suite were captured before any edit, per the change-control instructions.

## Headline finding

The reported defects (#1 login text clipped, #2 icon overlap, #3 password icon misalignment, #4 search icon overlap, and a large share of "inconsistent button/table spacing") all trace back to **one root cause**: `tailwind.config.js` defines the spacing scale `space-1, space-2, space-3, space-4, space-6, space-8, space-12` (each equal to `N × 4px`), but the shared `Input`, `Button`, `Modal`, `StatusBadge`, `Card`, `EmptyState`, and `DataTable` components — and several pages — also reference `space-0.5, space-1.5, space-2.5, space-3.5, space-5, space-9, space-10`, which were **never added to the token list**. Tailwind's JIT compiler silently drops any utility class it can't resolve against `theme.spacing` — it does not warn, error, or fall back. The class is emitted in the JSX, but zero CSS is generated for it. See `02_DEFECT_LEDGER.md` (D-01) for the full breakdown and exact file/line evidence.

Every other finding is a secondary, page- or component-scoped inconsistency layered on top of that same "design tokens vs. actual component code" gap — see the ledger for the complete list, with FIXED / VERIFIED / DEFERRED status per item.
