# Design System Decisions

## What is preserved, unchanged

- **Colors.** No hex value in `tailwind.config.js`'s `colors` block was added, removed, or edited. Every color used in every fix below (`secondary-container`, `primary-container`, `surface-container-low`, `on-surface-variant`, etc.) already existed in the config before this pass.
- **Typography.** `fontFamily` and `fontSize` blocks are untouched. League Spartan (headline/label/nav/button) and Libre Baskerville (body/caption) remain the only two typefaces in the app.
- **Border radius, shadows.** Untouched.
- **Brand identity.** Sidebar brand mark, login hero panel copy/layout, navy-and-amber visual direction: untouched.

## What was extended, and why

### Spacing scale — the only token change

**Decision:** extend `theme.extend.spacing` in `tailwind.config.js` to include every `space-N` key the codebase already references, following the exact convention the original 7 keys already established (`space-N = N × 4px`):

```js
spacing: {
  "space-0.5": "2px",
  "space-1": "4px",
  "space-1.5": "6px",
  "space-2": "8px",
  "space-2.5": "10px",
  "space-3": "12px",
  "space-3.5": "14px",
  "space-4": "16px",
  "space-5": "20px",
  "space-6": "24px",
  "space-7": "28px",
  "space-8": "32px",
  "space-9": "36px",
  "space-10": "40px",
  "space-11": "44px",
  "space-12": "48px",
}
```

**Why this, and not rewriting every component:** the component and page code was already written *as if* this full scale existed — every usage (`pl-space-9`, `gap-space-1.5`, `py-space-3.5`, ...) is semantically correct and internally consistent; only the config lagged behind. Editing the config is a single-file, purely additive change (no existing key's value changes) that makes ~40 already-correct class strings across 8 shared components and 7 pages resolve to real CSS. Rewriting every `className` string instead would touch far more files, for the same visual outcome, with far more risk of introducing a new inconsistency by hand. This is the textbook "fix the root cause, not the symptom" (rule 10) reading of this defect.

**`space-7` and `space-11` were added even though nothing currently references them** — they complete the `×4px` progression started by the existing keys, so the next component author isn't the one who reintroduces this exact class of bug the next time they reach for `gap-space-7`.

### New component: `Select`

**Decision:** add one shared `components/ui/Select.tsx`, matching `Input`'s markup and class strings exactly (label block, `h-10`, `px-space-3`, `border-outline-variant`, focus ring), and point every existing `<select>` call site at it.

**Why:** Phase 2 explicitly asks to standardize "Selects." Five pages already agreed, by copy-paste, on what a select should look like — this change captures that agreement in one place instead of five, with no visual change to any of them.

### New component: `ErrorBoundary`

**Decision:** add `components/ui/ErrorBoundary.tsx`, a minimal class component wrapping `<App />`, rendering an on-brand fallback (existing tokens only) instead of a blank page on an uncaught render error.

**Why:** Phase 4 explicitly asks to "improve feedback for... errors," and the prior investigation in this repository identified the total absence of an error boundary as a structural reason a blank screen can occur with no explanation. This is additive defensive UI — it introduces no new business logic and changes no existing behavior in the non-error path.

## What was deliberately not done

- **No new color tokens.** The map-marker/legend mismatch (D-04) was fixed by pointing both sides at an *existing* token (`secondary-container`), not by inventing a new "map accent" color.
- **No new typography scale.** MapPage's normalization (D-02) reuses `font-headline-sm`/`font-caption` exactly as already defined; nothing new was added to `fontSize` or `fontFamily`.
- **No `Chip`/`SegmentedControl` extraction** for `VisitsPage`'s filter pills (D-08) — a single call site does not justify a new abstraction once its only real defect (broken spacing tokens) is fixed by D-01.
- **No change to `Button`, `Card`, `DataTable`, `StatusBadge`, `PageHeader`, `EmptyState`, `MediaThumbnail`, `ErrorBanner` markup or variants.** Their class strings were already correct; they only needed the config fix (D-01) to render as originally authored. Per rule 14, every call site of each of these components was read before concluding this (see `01_UI_UX_AUDIT.md` inventory) — none needed a markup change.
