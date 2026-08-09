# Defect Ledger

Status legend: **FIXED** (change applied), **VERIFIED** (fix confirmed via typecheck/test/build and/or live render), **NOT VERIFIED** (change applied but not independently confirmed), **DEFERRED** (real defect, intentionally not touched this pass), **BLOCKED** (cannot be fixed without violating a non-negotiable rule or without backend/product input).

---

### D-01 — CRITICAL — Missing Tailwind spacing tokens break icon/text layout app-wide
**Status: FIXED / VERIFIED**

`tailwind.config.js` only defines `spacing: { space-1(4px), space-2(8px), space-3(12px), space-4(16px), space-6(24px), space-8(32px), space-12(48px) }`. Component and page code additionally uses `space-0.5, space-1.5, space-2.5, space-3.5, space-5, space-9, space-10`, all following the same `N × 4px` naming pattern but never added to the config. Tailwind's JIT compiler drops any utility whose token doesn't resolve — silently, with no build warning — so these classes compile to nothing.

Directly explains the four reported symptoms:
- **"Login email/username text is visually cut/clipped on the left"** — `Input.tsx:51` (`pl-space-9` when an icon is present) resolves to no left padding at all, so typed/placeholder text starts at the input's left edge, directly under the absolutely-positioned icon at `left-space-3`.
- **"Input icons appear incorrectly positioned or overlap with input content"** — same root cause, same line.
- **"Password/input icons have inconsistent alignment"** — `Input.tsx:52` (`pr-space-9` for password/clearable fields) has the identical failure on the right side, so the eye-toggle icon sits on top of the value.
- **"Search input icon overlaps or appears above the placeholder/text"** — the search box in `DataTable.tsx:51-64` and `MediaViewerPage.tsx:60-66` is the same shared `Input` component, so it inherits the identical bug.

Also silently broke, discovered during the audit (not previously reported by name, but the same class of defect):
- `Button.tsx:39,41` — `gap-space-1.5` (sm) / `gap-space-2.5` (lg) icon-to-label gap → icons sit flush against button labels on small/large buttons, while `md` (which correctly uses the valid `gap-space-2`) looks fine — an *inconsistency between button sizes*, matching the reported "buttons... inconsistent... alignment."
- `Modal.tsx:49` (`py-space-5` header padding), `Modal.tsx:56` (`p-space-1.5` close-button hit target)
- `StatusBadge.tsx:40` (`gap-space-1.5` between status dot and label — dot touches the text)
- `DataTable.tsx:83,123` — `py-space-3.5` header/cell vertical padding → collapsed, cramped table rows (reported "tables... need visual hierarchy and spacing")
- `EmptyState.tsx:18,24` — `p-space-10` outer padding, `mt-space-5` action spacing
- `Card.tsx:39` — `mt-space-0.5` (`CardSubtitle` gap under `CardTitle`)
- Duplicated in page code: `DashboardPage.tsx` (×6), `ReportsPage.tsx` (×3), `VisitsPage.tsx` (filter pills, ×3), `VisitDetailsPage.tsx` (×4), `CustomersPage.tsx`, `EmployeesPage.tsx`

**Fix applied:** extended `tailwind.config.js`'s `spacing` block with the missing keys, following the project's own existing `N × 4px` convention exactly (`space-0.5`→2px, `space-1.5`→6px, `space-2.5`→10px, `space-3.5`→14px, `space-5`→20px, `space-7`→28px, `space-9`→36px, `space-10`→40px, `space-11`→44px). Zero component or page files needed to change — every one of the ~40 already-correct-looking `className` strings across the codebase now resolves to real CSS exactly as originally intended. This is a one-file, additive, non-breaking change: no existing valid token was modified, no color/typography changed.

---

### D-02 — MEDIUM — MapPage uses raw/default Tailwind scale instead of the app's design tokens
**Status: FIXED / VERIFIED**

`pages/MapPage.tsx` is the one page that doesn't use the app's typographic and spacing tokens: `space-y-6`, `mb-2`, `gap-4`, `gap-2` (default Tailwind numeric scale, not `-space-N`) and, more visibly, `text-lg font-bold text-on-surface` / `text-sm text-on-surface-variant` for its card headings (line 107, 120) instead of the `font-headline-sm text-headline-sm text-primary font-bold` pattern every other card heading in the app uses (see `CardTitle` in `Card.tsx`, and identical headings in `SettingsPage.tsx`, `VisitDetailsPage.tsx`, `ProfilePage.tsx`). Because `font-headline-*` classes set the League Spartan font-family (not just a weight), MapPage's "Legend" and selected-customer headings render in the browser's default sans-serif font, at a different size, in a different color — a visible typographic mismatch unique to this one page.

**Fix applied:** normalized `MapPage.tsx` headings/spacing to the same token classes used by every other page's `Card` headings (`font-headline-sm text-headline-sm text-primary font-bold`, `font-caption text-xs text-on-surface-variant`, `space-y-space-6`, `gap-space-4`, `gap-space-2`, `mb-space-2`). No color, no new size scale — reuse only.

---

### D-03 — MEDIUM — MapPage error state bypasses the shared ErrorBanner
**Status: FIXED / VERIFIED**

Every other page (`DashboardPage`, `EmployeesPage`, `TerritoriesPage`, `CustomersPage`, `VisitsPage`, `GeoLogsPage`, `MediaViewerPage`, `ReportsPage`) surfaces load failures through the shared `ErrorBanner` (icon, message, retry button, dismiss). `MapPage.tsx:71-75` instead rendered a bare `<Card><p className="text-error">{error}</p></Card>` with no retry action — a different, less capable, visually inconsistent error affordance on exactly the page category ("Error states") the audit was asked to inventory.

**Fix applied:** `MapPage.tsx` now renders `<ErrorBanner message={error} onRetry={loadCustomers} onDismiss={() => setError(null)} />`, matching every other page. No new error-handling logic — `loadCustomers` already existed and was already the correct retry action.

---

### D-04 — MEDIUM — Map markers/legend use an off-palette color, and internal map loading/error UI bypasses the design system entirely
**Status: FIXED / VERIFIED**

Non-negotiable rule 1 is "preserve the existing color palette." `FieldTrackMap.tsx` hardcodes marker color `#1976D2` (a generic Google-Maps blue that does not appear anywhere in `tailwind.config.js`'s palette), while `MapPage.tsx`'s own Legend swatch uses the token `bg-primary` (`#000a24`, navy) — so the Legend key **does not match the actual dot color rendered on the map**, a directly-checkable, real inconsistency. Separately, `FieldTrackMap.tsx`'s own loading spinner and "Map unavailable" fallback are built entirely from inline `style={{ color: '#666', backgroundColor: '#f5f5f5', ... }}` — none of it uses the app's Tailwind tokens, so this one component's loading/error chrome looks like a different, generic product bolted onto FieldTrack Pro.

**Fix applied:**
- Marker default color changed from the off-palette `#1976D2` to the existing token hex for `secondary-container` (`#ffa515`, the app's amber accent — already used for active-state highlights, badges, and CTAs), and `MapPage.tsx`'s Legend swatch and marker mapping both now reference the same token, so they visually agree.
- `FieldTrackMap.tsx`'s loading spinner now reuses the exact spinner classes used everywhere else in the app (`border-primary-container border-t-secondary-container`, matching `Layout.tsx`'s `AuthLoadingFallback`), and its text/background use `bg-surface-container-low`, `text-on-surface-variant` tokens instead of hardcoded hex. No new colors were introduced — every value used already exists in `tailwind.config.js`.

---

### D-05 — LOW — No shared `Select` component; five pages hand-duplicate identical markup
**Status: FIXED / VERIFIED**

`CustomersPage.tsx:319`, `EmployeesPage.tsx:292` and `:313`, `VisitsPage.tsx:258` and `:286` each independently re-type the same label + `<select>` block and the same Tailwind class string (`w-full h-10 bg-surface border border-outline-variant rounded-lg px-space-3 ... focus:ring-2 focus:ring-primary-container/20`). They already render consistently with each other and with `Input` (same height, padding, border, focus ring) — this was not a visible bug today — but it is exactly the duplication Phase 2 ("Standardize... Selects") asks to be consolidated, and one small pre-existing inconsistency was hiding inside the duplication: `EmployeesPage.tsx:309` labels the Role field with `text-label-md` (14px) while every other field label in the app uses `text-xs` (12px) — a real, if minor, mismatched label size specific to that one field.

**Fix applied:** added `components/ui/Select.tsx`, mirroring `Input`'s visual language (same label markup, height, padding, border, focus ring, optional `helperText`/`error`). Replaced all five raw `<select>` blocks with `<Select>`, passing through the exact same `value`/`onChange`/`required`/options — no behavior change. This also fixed the stray `text-label-md` role-label size automatically, since the label now renders through the same shared markup as every other field.

---

### D-06 — LOW — `Modal` has no dialog semantics; no application-wide error boundary
**Status: FIXED / VERIFIED**

Two accessibility/robustness gaps found during the "modals/dialogs" and "error states" inventory pass (rule 11: "maintain accessibility and keyboard usability"):
- `Modal.tsx` already handles Escape-to-close and click-outside-to-close, but the dialog `<div>` carries no `role="dialog"`, `aria-modal`, or `aria-labelledby` — a screen reader has no signal that focus has entered a modal context.
- There is no React error boundary anywhere in the app (`src/main.tsx` → `App.tsx`). Any uncaught render exception unmounts the entire tree with zero fallback UI, i.e. the "completely white screen" failure mode investigated in the prior session.

**Fix applied:**
- `Modal.tsx`: added `role="dialog" aria-modal="true" aria-labelledby={titleId}` and wired the existing title `<h3>` to that id. No visual change, no behavior change.
- Added `components/ui/ErrorBoundary.tsx` (class component, the only pattern React supports for this), wrapping `<App />` in `main.tsx`. On an uncaught error it renders a small, on-brand fallback card (reusing existing `bg-background`/`text-on-surface` tokens and the `Button` component for a "Reload" action) instead of a blank page. No product/business logic involved — pure defensive UI.

---

### D-07 — DEFERRED — Pre-existing lint error, pre-existing test failure, pre-existing bundle-size advisory
**Status: DEFERRED (intentionally not fixed this pass)**

Confirmed present in the baseline *before* any UI/UX change (see `01_UI_UX_AUDIT.md`):
- `tileConfig.ts:45` — `@typescript-eslint/no-wrapper-object-types` (`Boolean` should be `boolean`). Pure TS hygiene, unrelated to any visual defect, not a file this task needed to touch.
- `FieldTrackMap.tsx:92` — `react-hooks/exhaustive-deps` warning on the marker-rendering `useEffect`. Fixing it means changing effect dependency/behavior (a functional change to map re-render logic), which is explicitly out of scope for a "not a backend rewrite... don't change verified functionality" visual-repair pass.
- `DashboardPage.test.tsx` — one pre-existing failing assertion (FT-019, an API-call-pattern test), unrelated to styling.
- The production build's "chunk larger than 500kB" advisory (MapLibre GL is heavy) — a bundling/perf concern, not a UI/UX defect, and out of scope for a visual pass.

Rule 15 ("do not change files unrelated to the UI/UX task") and rule 8 ("do not weaken tests") both argue for leaving these exactly as found. They are documented here so they are never mistaken for a regression introduced by this pass — the baseline in `01_UI_UX_AUDIT.md` proves they predate it.

---

### D-08 — DEFERRED — `VisitsPage` status filter pills are a bespoke inline pattern, not a reusable component
**Status: DEFERRED**

`VisitsPage.tsx:190-204` implements a segmented-control-style filter row with its own inline conditional classes rather than a `Chip`/`SegmentedControl` component. Once D-01's tokens are fixed, this renders with correct, consistent padding (`px-space-3.5 py-space-1.5` now resolve) and looks correct — there is no remaining visible defect. Extracting a reusable component for a single call site would be introducing an abstraction the task's own ground rules caution against ("don't design for hypothetical future requirements... three similar lines is better than a premature abstraction"). Left as-is by design, not by omission.
