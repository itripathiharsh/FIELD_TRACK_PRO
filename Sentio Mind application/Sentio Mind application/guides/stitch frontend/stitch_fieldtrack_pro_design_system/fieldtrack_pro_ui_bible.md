# FieldTrack Pro — UI Bible
### The Single Source of Truth for Visual & Interaction Design

**Version 1.0 — Derived from Project Master Documentation (Phases 1–11)**

---

## How to Use This Document

This is the canonical design reference for FieldTrack Pro across both surfaces — the **Android field employee app** (Kotlin + Jetpack Compose) and the **Admin Web Dashboard** (React + TypeScript + shadcn/ui + Tailwind CSS). Every value in this document is either:

1. **Locked** — taken directly from the project's Tech Stack and Phase 6/7 implementation docs (colors, frameworks, libraries), or
2. **Derived** — a deliberate extension built to be consistent with those locked choices and with the product's core emotional mandate.

That mandate, stated plainly in the Phase 2.5 User Journey doc and repeated as the design throughline for the entire product:

> **"When in doubt, design for trust and explainability over strict enforcement."**

FieldTrack Pro is a GPS-verification tool used by field employees who could easily feel surveilled, and by admins who need to make fair judgment calls fast. Every color, every copy pattern, every state in this document exists in service of that one line. A geo-verification failure should read as *troubleshooting*, never *accusation*. A flagged visit should read as *"here's what happened, judge for yourself,"* never *"caught you."* Keep that lens on every design decision that follows.

This document does not re-derive product requirements, API contracts, or screen inventories — those live in their respective phase docs (Requirements, Screen Lists, Navigation Flow). This document answers one question only: **what does it look like, and how does it behave?**

---

## Table of Contents

1. Brand Colors
2. Typography
3. Design Language & Principles
4. Grid System & Spacing
5. Border Radius
6. Shadows & Elevation
7. Icons
8. Buttons
9. Cards
10. Forms
11. Tables
12. Maps
13. Charts
14. Navigation Pattern
15. Empty States
16. Loading States
17. Animations
18. Component Library Index
19. Platform Notes (Compose ↔ Tailwind Token Mapping)

---

## 1. Brand Colors

### 1.1 Core Palette (Locked)

These three colors are locked in code today — pulled directly from `FieldTrackColors` in the Phase 6 Android theme implementation, described there as matching "the wireframe palette." They are the foundation every other color in this system extends from.

| Token | Hex | Usage |
|---|---|---|
| **Primary — Teal** | `#1D9E75` | Primary actions, active states, brand mark, success accents |
| **Secondary — Blue** | `#378ADD` | Secondary actions, links, informational accents, map pins |
| **Error — Red** | `#E24B4A` | Destructive actions, failed states, critical alerts |
| **Surface — White** | `#FFFFFF` | Base surface / card background |

**Why teal-and-blue:** a field-operations tool that tracks people's location needs to visually read as *calm and professional*, not alarmist or clinical. Teal is used deliberately over a more "corporate" navy or a more "urgent" red-orange as the primary — it reads as trustworthy without reading as cold, and it doesn't compete visually with map UI (which is blue-and-red by convention on both Google Maps SDK and Google Maps JS API, used on both platforms per the Tech Stack doc).

### 1.2 Extended Semantic Palette (Derived)

The core palette alone can't carry five visit statuses, form validation states, and report severity — so it's extended with a consistent tint/shade system. Each core color gets a 100 (light tint, for backgrounds/chips) and 700 (dark shade, for text-on-tint and hover states) built at consistent lightness offsets, so the system scales without anyone inventing a new one-off color per screen.

| Token | Hex | Pairs With |
|---|---|---|
| `primary-50` | `#EAF7F1` | Chip/background fill behind primary text |
| `primary-100` | `#CBEEDE` | Hover fill for primary-ghost buttons |
| `primary-500` | `#1D9E75` | Base — see 1.1 |
| `primary-700` | `#146B4F` | Text-on-tint, pressed state |
| `secondary-50` | `#EAF3FC` | Info banner background |
| `secondary-500` | `#378ADD` | Base — see 1.1 |
| `secondary-700` | `#215F9E` | Text-on-tint, pressed state |
| `error-50` | `#FDECEC` | Error banner / failed-state background |
| `error-500` | `#E24B4A` | Base — see 1.1 |
| `error-700` | `#A6302F` | Text-on-tint, pressed state |
| `warning-50` | `#FFF6E5` | Flagged/warning background |
| `warning-500` | `#E5A63C` | Flagged badge, geo-verification caution |
| `warning-700` | `#9C6E1F` | Text-on-tint |
| `neutral-50` | `#F7F8F9` | App/page background |
| `neutral-100` | `#EDEFF2` | Card border, divider |
| `neutral-300` | `#C7CCD3` | Disabled fill, placeholder text |
| `neutral-500` | `#8A919C` | Secondary/meta text |
| `neutral-700` | `#4A505A` | Body text |
| `neutral-900` | `#1B1E22` | Headings, highest-emphasis text |

### 1.3 Visit Status Colors (Derived, Cross-Platform Locked)

Both the Phase 6 Android doc (`VisitStatusBadge`) and Phase 7 Web doc (`KanbanBoard` with a fixed status array) reference the same five statuses by name. These must render **identically** on Android and Web — an admin comparing a flagged visit across both surfaces should never wonder if they're looking at the same thing.

| Status | Color Token | Hex | Rationale |
|---|---|---|---|
| **Pending** | `neutral-500` on `neutral-100` | `#8A919C` / `#EDEFF2` | Neutral — nothing has happened yet, no judgment implied |
| **In Progress** | `secondary-500` on `secondary-50` | `#378ADD` / `#EAF3FC` | Active, informational, not urgent |
| **Completed** | `primary-500` on `primary-50` | `#1D9E75` / `#EAF7F1` | Success, resolution |
| **Missed** | `neutral-700` on `neutral-100` | `#4A505A` / `#EDEFF2` | Deliberately **not** red. A missed visit is an operational gap, not a security failure — reserving red exclusively for Flagged keeps the one true "something needs review" signal from being diluted. |
| **Flagged** | `warning-500` on `warning-50` | `#E5A63C` / `#FFF6E5` | Amber, not red. This is the single highest-trust-risk state in the product per the User Journey doc — amber signals "needs a human look" rather than "guilty," matching the mandated troubleshooting tone. |

> **Non-negotiable rule:** Flagged is never rendered in `error-500` red. Red is reserved for confirmed system failures (upload failed, network error, form validation). Flagged is a *pending judgment call for the admin*, not a verdict — the color must not pre-judge it.

### 1.4 Accessibility

All text/background pairings above meet WCAG AA contrast (4.5:1 for body text, 3:1 for large text/UI components) at their listed combinations. Do not pair a `-500` text color directly on a `-50` background without checking contrast if new combinations are introduced — the `-700` shade exists specifically for text-on-tint use.

---

## 2. Typography

### 2.1 Typefaces (Derived from Locked Frameworks)

Neither the Requirements nor Tech Stack docs specify a typeface, so this is derived directly from what each platform's locked UI framework ships with by default — deliberately, since custom web font loading adds a network dependency this on-prem, field-network-conscious product doesn't need (per the Non-Functional Requirements' emphasis on performance under normal network conditions, and the offline-first mandate for the field app).

| Platform | Typeface | Why |
|---|---|---|
| **Web Dashboard** | **Inter** | Default typeface of shadcn/ui, the Tech Stack's locked UI library. Using it as-shipped (rather than swapping in a custom font) avoids fighting the component library's defaults, per the Tech Stack's stated preference for "boring, mainstream" choices that won't fight an agent mid-build. |
| **Android App** | **Roboto** (Compose Material 3 default) | Ships with Jetpack Compose Material 3 at zero extra weight or download — matters directly for the offline-capable field app running on variable Android hardware in the field. |

Both typefaces are geometric, highly legible sans-serifs with near-identical x-height and numeral proportions — visually, a status badge or metric number looks like "the same product" switching between Android and Web, even though the underlying font differs.

### 2.2 Type Scale

One shared scale, expressed in each platform's native unit (`rem` for web, `sp` for Android — both are user-accessibility-scalable units, which matters for field employees who may have increased system font sizes set for outdoor visibility).

| Role | Size (Web / rem) | Size (Android / sp) | Weight | Line Height | Usage |
|---|---|---|---|---|---|
| **Display** | 2.25rem (36px) | 32sp | 700 (Bold) | 1.2 | Report/dashboard hero numbers only |
| **H1** | 1.875rem (30px) | 28sp | 700 | 1.25 | Page titles ("Employees", "Reports") |
| **H2** | 1.5rem (24px) | 22sp | 600 (Semibold) | 1.3 | Section headers, card titles |
| **H3** | 1.25rem (20px) | 18sp | 600 | 1.35 | Sub-section headers, list item titles |
| **Body** | 1rem (16px) | 16sp | 400 (Regular) | 1.5 | Default body text, form labels, table cells |
| **Body Emphasis** | 1rem (16px) | 16sp | 600 | 1.5 | Field values, key data points |
| **Caption** | 0.875rem (14px) | 14sp | 400 | 1.4 | Meta text, timestamps, helper text |
| **Micro** | 0.75rem (12px) | 12sp | 500 (Medium) | 1.3 | Badge text, table headers (uppercased) |

**Minimum size floor: 12sp/0.75rem.** Nothing in this product ever renders smaller — field employees frequently read the screen in direct sunlight or while walking; Micro is the absolute floor and is reserved for badges/labels only, never for anything a decision depends on (e.g., never shrink a geofence radius value or a reason code below Caption size).

### 2.3 Voice & Copy Tone (Carried Forward from Product Docs)

Typography isn't just size and weight — the actual words matter as much as the font, and this system is explicit about it because the Phase 2.5 User Journey doc calls out copy tone as a first-class design decision, not an afterthought for engineers to improvise.

- **Never accusatory.** "Location verification failed" → **"Let's get you checked in — try moving closer or check your GPS signal."**
- **Never a raw exception.** Errors always map to a specific, human sentence (see Phase 6 `LoginViewModel`: `RateLimitException` → *"Too many attempts — try again in 15 minutes,"* never a stack trace or generic "An error occurred").
- **Reason codes are always translated.** `OUTSIDE_RADIUS`, `MOCK_LOCATION_SUSPECTED`, `GPS_UNAVAILABLE` are internal enum values — they are never rendered as-is in any UI. See §10 and §13 for the exact human-readable mapping.
- **Meaningful actions say what they do.** Deactivating an employee doesn't just show a generic "Are you sure?" — it states the real consequence: *"This employee will be logged out immediately and won't be able to log back in."*

---

## 3. Design Language & Principles

### 3.1 Five Principles

**1. Explainable over enforced.**
Every automated decision (a flag, a rejection, a status change) must be paired with a visible, human-readable *reason* somewhere the relevant person can see it within one tap/click. Never leave a status changed with no accessible "why."

**2. Calm by default, clear when it matters.**
Baseline UI (dashboards, lists, badges) stays quiet and low-saturation — this is a background tool employees glance at, not a game they engage with. Saturation and motion budget are spent only on moments that matter: a successful check-in, a submission confirmation, a flagged review.

**3. One state, one visual language, both platforms.**
A "Flagged" badge, an empty state, a loading skeleton — whatever the component, it must look and behave the same conceptually on Android and Web even where the native idiom differs (Compose vs. Tailwind). See §19 for the literal token mapping that enforces this.

**4. Linear where the work is linear, dense where the work is broad.**
The Android app is a single forward-moving stack (per the locked Navigation Flow doc — no bottom tab bar, because the app is fundamentally "one visit at a time"). The Web dashboard is a persistent-sidebar, multi-section tool because an admin's job is broad oversight, not a linear task. The design language respects this rather than forcing one navigation metaphor onto both.

**5. Boring is a feature.**
Matches the Tech Stack doc's own stated philosophy — "deliberately boring/mainstream" choices reduce risk. This UI Bible follows the same logic: no bespoke iconography, no novel interaction patterns, no custom illustration style that needs upkeep. Recognizable, standard patterns (shadcn defaults, Material 3 defaults) win over cleverness every time.

### 3.2 The "Field Test" for Every Screen

Before any screen ships, it should pass this check, adapted directly from the Phase 2.5 User Journey's core risk table:

> *Would this screen make a hardworking field employee feel accused, or an overwhelmed admin feel unable to make a fair call? If yes to either — redesign before shipping, regardless of how "correct" the underlying logic is.*

---

## 4. Grid System & Spacing

### 4.1 Base Unit

**4px base unit**, scaling in a standard geometric progression. This aligns natively with Tailwind's default spacing scale (used as-is per the Tech Stack's Tailwind CSS choice) and maps cleanly onto Compose's `dp` unit at 1:1, so a "16" in the spec means the same physical space on both platforms.

| Token | Value | Common Usage |
|---|---|---|
| `space-1` | 4px | Icon-to-label gap, tight badge padding |
| `space-2` | 8px | Form field internal padding, chip padding |
| `space-3` | 12px | Compact card padding, list item vertical gap |
| `space-4` | 16px | Standard card padding, standard section gap |
| `space-6` | 24px | Section-to-section spacing, page margin (mobile) |
| `space-8` | 32px | Page margin (web), major section breaks |
| `space-12` | 48px | Page top padding on Web dashboard layouts |

### 4.2 Web Dashboard Grid

- **12-column grid**, max content width **1280px**, centered, `space-8` (32px) outer gutter.
- Sidebar: fixed **240px** width, persistent (per the locked Navigation Flow doc's "persistent sidebar layout" decision).
- Content region: fluid within the remaining grid, using CSS Grid/Flexbox with `space-4`–`space-6` gaps between cards.
- Report/analytics grids (Productivity Dashboard) use a **2-column** metric-card grid on desktop, collapsing to 1 column below 768px.

### 4.3 Android App Grid

- Single-column layouts throughout — the linear, one-visit-at-a-time navigation model doesn't need multi-column density.
- Standard screen padding: `space-4` (16px) horizontal.
- List item vertical rhythm: `space-3` (12px) between cards, `space-4` (16px) internal card padding.
- Touch targets: minimum **48dp** height on every interactive element (buttons, list rows, form fields) — this is a hard floor, not a suggestion, given the Usability non-functional requirement that the core visit flow be completable in under 5 taps/screens per step without fumbling.

### 4.4 Breakpoints (Web)

| Name | Width | Behavior |
|---|---|---|
| `sm` | < 640px | Not a primary target (admin dashboard is desktop-first per its persistent-sidebar pattern), but sidebar collapses to icon-only |
| `md` | 640–1024px | 2-column grids collapse to 1, tables become horizontally scrollable |
| `lg` | 1024–1280px | Full sidebar + content, standard experience |
| `xl` | > 1280px | Content max-width caps at 1280px, extra space becomes margin, not stretched content |

---

## 5. Border Radius

A single consistent radius scale, applied by component *weight* — heavier, more contained components (cards, modals) get a slightly larger radius than lightweight inline components (badges, inputs), which keeps the interface feeling coherent without being uniform-to-the-point-of-flat.

| Token | Value | Usage |
|---|---|---|
| `radius-sm` | 6px | Input fields, small buttons, table cell chips |
| `radius-md` | 8px | Standard buttons, form controls, list items |
| `radius-lg` | 12px | Cards, modals, dialogs, the Visit Detail summary panel |
| `radius-xl` | 16px | Large feature cards (Dashboard Overview summary cards, MetricCards) |
| `radius-full` | 9999px | Status badges/chips, avatar images, the primary FAB-style "Start Visit" button on Android |

This maps directly onto shadcn/ui's default `--radius` token system on Web (set the base `--radius: 0.5rem` and let `sm`/`md`/`lg` derive from it, per shadcn convention) and onto Compose `Shapes()` on Android using the same pixel values converted to `dp`.

---

## 6. Shadows & Elevation

Elevation communicates hierarchy, not decoration — used sparingly, consistent with the "calm by default" principle in §3.

| Token | Web (box-shadow) | Android (Compose elevation) | Usage |
|---|---|---|---|
| `elevation-0` | none | 0dp | Page background, flat list rows |
| `elevation-1` | `0 1px 2px rgba(16,24,32,0.06)` | 1dp | Default resting card (Visit card, Employee row) |
| `elevation-2` | `0 2px 8px rgba(16,24,32,0.08)` | 3dp | Hover/focus state on interactive cards, dropdown menus |
| `elevation-3` | `0 4px 16px rgba(16,24,32,0.10)` | 6dp | Modals, dialogs, the Check-in Confirmation dialog |
| `elevation-4` | `0 8px 32px rgba(16,24,32,0.14)` | 8dp | Toasts/snackbars, the Offline Banner when it first appears |

**Rule:** nothing in this product exceeds `elevation-4`. Flat, low-shadow design keeps the tool feeling like calm infrastructure rather than a flashy consumer app — appropriate for something used dozens of times a day as a work tool, not a novelty.

---

## 7. Icons

### 7.1 Library (Locked by Framework Choice)

- **Web:** **Lucide** icons — the default icon set shipped with and styled for shadcn/ui, the Tech Stack's locked component library. No mixing in a second icon set.
- **Android:** **Material Symbols** (Material 3's default icon set in Compose) — visually a close cousin of Lucide (both are clean, 1.5–2px stroke-weight line icons), keeping the two platforms feeling related without requiring a literal shared asset pipeline.

### 7.2 Sizing & Weight

| Context | Size | Stroke Weight |
|---|---|---|
| Inline with body text (e.g., bell icon) | 20px / 20dp | 1.5px |
| Standalone nav icon (sidebar, tab) | 24px / 24dp | 1.5px |
| Empty-state illustration icon | 48px / 48dp | 1.5px |
| Status/badge icon (e.g., checkmark on Completed) | 16px / 16dp | 2px |

### 7.3 Core Icon Mapping

A fixed vocabulary so the same concept always uses the same icon everywhere it appears — critical for the cross-platform consistency principle in §3.

| Concept | Icon (Lucide name) |
|---|---|
| Notifications | `bell` |
| Profile | `user-circle` |
| Navigate/directions | `navigation` |
| Check-in / location verified | `map-pin-check` |
| Flagged / needs review | `flag-triangle-right` |
| Offline | `wifi-off` |
| Pending sync | `refresh-cw` (animated, see §17) |
| Photo attachment | `camera` |
| Document attachment | `file-text` |
| Signature | `pen-line` |
| Export | `download` |
| Filter | `sliders-horizontal` |
| Search | `search` |
| Territory | `map` |
| Settings | `settings` |
| Logout | `log-out` |

Icons are never used as the *sole* indicator of state or meaning without an accompanying text label or color — color-blind and low-vision usability both depend on this, and it reinforces the "explainable" principle: an icon alone can be ambiguous, an icon plus a plain-language label cannot.

---

## 8. Buttons

### 8.1 Variants

| Variant | Appearance | Usage |
|---|---|---|
| **Primary** | `primary-500` fill, white text, `radius-md` | The one main action per screen: "Add employee," "Submit," "Start visit," "Approve as completed" |
| **Secondary** | White fill, `neutral-300` border, `neutral-700` text | Alternate actions alongside a primary: "Mark as resolved" next to "Approve as completed" |
| **Destructive** | `error-500` fill, white text | Deactivate, delete — always paired with a confirmation dialog stating the real consequence (see §2.3) |
| **Ghost** | Transparent, `primary-700` text, `primary-50` hover fill | Tertiary/low-emphasis actions: "Cancel," inline "Edit" links |
| **Icon-only** | 40×40px/dp tap target, `radius-md`, transparent until hover/press | Table row actions, app bar icons |

### 8.2 Sizing

| Size | Height | Horizontal Padding | Usage |
|---|---|---|---|
| Large | 48px/dp | 24px | Primary mobile CTAs ("Start visit," "Submit") — matches the 48dp minimum touch target from §4.3 |
| Default | 40px/dp | 16px | Standard web dashboard buttons |
| Small | 32px/dp | 12px | Inline table actions, compact toolbars |

### 8.3 States

Every button defines four states explicitly — default, hover (web only), pressed/active, and disabled. Disabled buttons use `neutral-300` fill with `neutral-500` text and **must never be the only indicator of why an action is unavailable** — e.g., the Android "Start visit" button is disabled outside the geofence (per the Phase 6 `VisitDetailScreen` code, gated on `isWithinGeofence`), but the screen also shows the Geo-fence Waiting/Arrival state text explaining why, per §14.

### 8.4 Loading State

Buttons triggering an async action (login, submit, upload) replace their label with a centered spinner at the same size, keeping button dimensions fixed to avoid layout shift, and are disabled for the duration — directly matching the Phase 6 `LoginViewModel`'s `isLoading` pattern.

---

## 9. Cards

Cards are the primary content container across both platforms — the Visit card, Employee row (in its expanded state), MetricCard, ChartCard, and the Flagged Visit Review panel are all built from one base card component with content-specific slots.

### 9.1 Base Card Anatomy

- Background: `surface` white
- Border: 1px `neutral-100`
- Radius: `radius-lg` (12px)
- Padding: `space-4` (16px) default, `space-6` (24px) for feature cards (MetricCard, Overview summary cards)
- Elevation: `elevation-1` at rest, `elevation-2` on hover if interactive/clickable

### 9.2 Card Variants

| Variant | Distinguishing Feature | Example |
|---|---|---|
| **Visit Card** | Left-edge 4px color bar matching status color (§1.3), status badge top-right | Dashboard list (Android), Kanban board (Web) |
| **MetricCard** | Large `Display`-scale number, small label below, optional trend icon | Productivity Dashboard, Overview summary cards |
| **ChartCard** | Header row (title + optional filter), chart body, no internal padding around the chart itself so axes align edge-to-edge | Productivity Dashboard's `BarChart` panels |
| **Detail Card** | No left color bar, houses grouped info rows (label/value pairs) | Employee Detail, Customer Detail, Visit Detail |
| **Review Card** | Includes an embedded `MapView`, a `ReasonList`, and an `ActionBar` footer | Flagged Visit Review — the highest-trust-risk surface in the product, given its own variant deliberately (see §3.2) |

### 9.3 Kanban Card (Web Visit Status Board)

A specialized Visit Card variant: compact (`space-3` padding), draggable-looking affordance even if drag-and-drop isn't implemented in MVP, shows customer name, employee name, scheduled time, and the status-colored left bar. Columns match the five statuses from §1.3 exactly, in this fixed order: **Pending → In Progress → Completed → Missed → Flagged**, matching the literal array order in the Phase 7 `VisitStatusBoard` implementation.

---

## 10. Forms

### 10.1 Field Anatomy

Every form field, on both platforms, follows the same stack order: **Label → Input → Helper/Error text.** No exceptions — a field with an error never loses its label, and helper text is always reserved space (not something that shifts layout when it appears), preventing the layout-jump that makes error states feel jarring.

| Element | Style |
|---|---|
| Label | `Body` weight 600, `neutral-700`, `space-1` above input |
| Input | 40px/dp height (48px/dp on Android per the touch-target floor), `radius-sm`, 1px `neutral-300` border, `neutral-900` text |
| Input — focused | Border becomes `secondary-500`, 2px |
| Input — error | Border becomes `error-500`, 2px, helper text switches to `error-700` |
| Helper text | `Caption` size, `neutral-500` (or `error-700` when showing a validation error) |

### 10.2 Field Types Used in This Product

- **Text input** — names, addresses, descriptions
- **Dropdown/Select** — Requirement Category (admin-editable, populated live from `GET /requirement-categories` per the locked Phase 6 implementation — the dropdown component must support dynamic option refresh, not a hardcoded enum)
- **Number input** — Check-in radius (meters), defaulting to 75 per the locked backend default
- **Toggle** — "Set exact location on map instead," per the Phase 7 `AddCustomerForm`
- **Date range picker** — all four Reports screens
- **Map picker** — embedded pin-drop, used alongside address text entry (dual-input pattern, not a replacement for it)
- **Signature canvas** — see §10.4, a distinct non-standard field type

### 10.3 Validation & Error Copy

Client-side validation mirrors backend rules for immediate feedback, but per the Phase 7 doc's explicit note, **backend validation remains the actual security/correctness boundary** — the UI reflects this by never claiming success before a server response confirms it (no optimistic "Saved" toast before the request actually resolves on anything that touches geofence radius, credentials, or check-in data).

Error copy is always specific (see §2.3): never "Invalid input," always what's actually wrong and, where possible, how to fix it.

### 10.4 Local Auto-Save (Requirement Form)

The Requirement Capture form auto-saves locally on every field change (debounced), per the locked `RequirementFormViewModel` implementation, restoring a draft even after a force-close of the app. Visually, this needs **no visible "Saving..." indicator** for every keystroke (would be noisy) — but does show a subtle, brief "Draft saved" caption-text confirmation the first time a draft is restored on form re-entry, so the employee has quiet confidence nothing was lost, tying back to the "biggest fear is redoing work" risk named in the User Journey doc.

### 10.5 Reason Code Translation Table (Applies to Forms, Badges, and Reports)

Internal reason codes are never shown raw anywhere in the UI. This is the single canonical translation table — every surface that shows a geo-verification reason (Check-in Failed state, Flagged Visit Review, Geo-verification Report) pulls from this exact wording:

| Reason Code | Displayed As |
|---|---|
| `OUTSIDE_RADIUS` | "Outside check-in range" |
| `MOCK_LOCATION_SUSPECTED` | "Unusual location signal detected" |
| `GPS_UNAVAILABLE` | "GPS signal unavailable" |

Note the deliberate wording gap between `MOCK_LOCATION_SUSPECTED` and its display text: it never says "fraud," "fake," or "spoofed" — it states the technical signal and lets the admin, with the distance/history context also visible on the Flagged Visit Review card, form their own judgment. This is the literal design implementation of the "explainable, not enforced" principle.

---

## 11. Tables

### 11.1 Structure (Web Only — Android Uses Lists, Not Tables)

Tables are a Web Dashboard–only pattern; the Android app never renders tabular data (its content is fundamentally list/card-based per the linear navigation model in §3/§14). All `DataTable` instances (Employee List, Customer List, all four Reports) share one component.

| Element | Style |
|---|---|
| Header row | `Micro` size, uppercase, `neutral-500`, `neutral-50` background, sticky on scroll |
| Body row | `Body` size, `neutral-700`, 1px `neutral-100` bottom border, `space-3` vertical padding |
| Row — hover | `neutral-50` background (only if row is clickable, e.g., navigates to a Detail page) |
| Row — clickable | `cursor: pointer`, entire row is the tap target, not just the first cell |
| Empty column value | An em-dash (`—`) in `neutral-300`, never a blank cell — blank cells read as a loading bug, not "no data" |

### 11.2 Filters & Pagination

A `FilterBar` sits directly above every table (territory/status filters on Employee List, date range on all Reports), always visible, never hidden behind a collapsed "Advanced filters" toggle — these are used constantly enough (per the daily-use nature of the product) that hiding them would add friction to a routine task.

Pagination: standard "Previous / Page X of Y / Next," positioned bottom-right beneath the table, with page size fixed at 25 rows.

### 11.3 Report Tables Specifically

Report tables (Employee Visit, Customer Visit History, Geo-verification) additionally require:
- Numbers that carry real weight (visit counts, completion rates) get `Body Emphasis` weight to visually separate data from labels.
- The Productivity Dashboard's distance figures always carry the **"Approx."** label directly in the column header or chart title — never dropped, per the explicit honesty flag carried through from the Maps & Location doc (§13 covers the chart version of this same rule).
- Geo-verification Report reason codes use the exact translation table in §10.5 — never the raw enum.

---

## 12. Maps

Maps appear in three distinct contexts, each with different needs — treated as three variants of one `MapView` component rather than three separate implementations, per the same "shared component" discipline used for the Export Modal.

| Variant | Where | Behavior |
|---|---|---|
| **Mini Preview** | Visit Detail (Android) | Static, small (~120dp height), single customer pin, tap to open full navigation handoff to the external Google Maps app — not an interactive map itself |
| **Live Map (Web)** | Dashboard Overview + full Live Map view | Interactive, shows last-known employee locations (event-based, updated at check-in/check-out — **never a moving dot**, per the locked "point-in-time, not continuous tracking" product decision). Markers cluster when employees are geographically close, using standard cluster-count bubble styling rather than overlapping pins illegibly |
| **Review Map** | Flagged Visit Review | Shows the customer's true geofence location **and** the employee's attempted check-in location(s) as two distinct pin styles, with the geofence radius rendered as a visible translucent circle overlay — this visual is what actually lets an admin judge "15 meters over" vs. "340 meters away in a different part of town" at a glance, which is the entire functional point of this screen |

### 12.1 Map Styling

- Pins: `secondary-500` blue for customer/default locations, `error-500` red only for an actual failed check-in attempt pin, `primary-500` teal for a successful check-in.
- Geofence radius circle: `secondary-500` at 15% opacity fill, 1.5px solid stroke at full opacity — visible without dominating the map.
- Map tile style: standard Google Maps default styling (no custom map theme) — another deliberate "boring is a feature" choice; a custom-styled map adds visual maintenance burden with no functional benefit here, and default styling is instantly familiar to every user.

---

## 13. Charts

**Library:** Recharts (locked, Tech Stack §5) — used for the Productivity Dashboard's bar charts and any future report visualizations.

### 13.1 Chart Color Rules

- One series per chart in most cases (visits per employee, distance per employee) — uses `primary-500`. Charts never introduce a rainbow of colors for a single-series bar chart; color is reserved to carry meaning, not decoration.
- Where a second comparison series is needed (e.g., completed vs. missed side-by-side), the second series uses `secondary-500` — reusing the same two-color relationship established everywhere else in the product, not a new chart-specific palette.
- Grid lines: `neutral-100`, axis labels: `Caption` size in `neutral-500`.
- Tooltips on hover: white background, `elevation-2`, `radius-sm`, showing the exact value plus its unit.

### 13.2 The "Approx." Rule (Chart-Specific)

Per the locked Phase 7 implementation note, the distance-traveled chart's title/axis label must always visibly include **"Approx."** — this is a straight-line estimate between check-in/check-out points, not GPS-tracked road mileage, and the UI must never let that number look more precise than it is. Any future chart built on estimated (vs. exact) data follows this same disclosure pattern.

### 13.3 Empty & Loading Chart States

See §15–§16 — charts follow the same empty/loading rules as any other data component, with one addition: a chart with zero data points renders the empty-state illustration *inside* the chart card's body area (not a blank axis grid with nothing on it, which reads as a bug rather than "no visits in this range").

---

## 14. Navigation Pattern

The two platforms use intentionally different, locked navigation patterns — this is a documented decision in the Navigation Flow doc, not an inconsistency to fix.

### 14.1 Android — Single-Stack Push Navigation

- **No bottom tab bar.** Dashboard (Today's Visits) is the one true home screen; every other screen is a forward path that eventually returns to it.
- Back navigation is always a system/app-bar back arrow, never a swipe-only gesture as the sole affordance (accessibility — always give an explicit tappable target).
- The one exception to "no lateral navigation": the top app bar's bell (Notifications) and profile icons, available from the Dashboard only, both push forward and return via back — they don't become a persistent tab structure.
- Modal-style screens (Check-in Confirmation dialog, Export-equivalent flows) present as dialogs/bottom sheets, not full-screen pushes, when the interaction is a quick confirm/cancel rather than a multi-field task.

### 14.2 Web — Persistent Sidebar

- **Fixed 240px sidebar**, always visible at `lg` breakpoint and above, containing: Dashboard Overview, Employees, Customers, Visits, Reports, Settings — matching the exact sidebar structure in the locked Navigation Flow doc.
- Active section is indicated with a `primary-50` background fill behind the nav item and `primary-700` text/icon — not just a color change on text alone, for stronger at-a-glance orientation.
- Reports use **tabs**, not separate page navigations, since all four report screens share the same filter/export chrome (per the locked design decision) — tab bar sits directly below the page header, above the shared `ReportLayout`.
- Below `lg` breakpoint, sidebar collapses to icon-only with tooltips on hover, expandable via a toggle — full text labels return above `lg`.

### 14.3 Cross-App Consistency Note

The two apps never deep-link into each other (no Android-to-Web or Web-to-Android navigation in MVP) — they're connected only through shared data, not shared screens. Design-wise, this means: don't build any "open in other app" affordance that doesn't actually exist yet; the connection is implicit (a visit scheduled on Web simply appears on the Android Dashboard next sync) and should feel that way, not be over-explained in the UI.

---

## 15. Empty States

Every list/table/chart in this product has a defined empty state — the Android Screen List doc explicitly calls out "Empty State — No Visits Today" as its own named screen entry specifically because it deserves deliberate design attention, not a default "No data" fallback.

### 15.1 Anatomy

- Centered within the content area (not top-aligned, which reads as broken/incomplete)
- 48px/dp line icon (see §7.2) in `neutral-300`
- `H3` headline, `neutral-700`
- `Body` supporting line, `neutral-500`, one sentence
- Optional primary-button call to action, only when there's a real next action to take

### 15.2 Empty States in This Product

| Screen | Icon | Headline | Supporting Line |
|---|---|---|---|
| Dashboard — No Visits Today | `calendar-check` | "Nothing scheduled for today" | "Enjoy the breather — check back tomorrow, or pull down to refresh." |
| Notifications — none | `bell-off` | "No notifications yet" | "You'll see new visit assignments and reminders here." |
| Employee List — no results | `search-x` | "No employees match these filters" | "Try adjusting your territory or status filter." |
| Customer List — none yet | `users` | "No customers added yet" | "Add your first customer to start scheduling visits." *(with "Add customer" primary button)* |
| Reports — zero visits in range | `calendar-x` | "No visits in this date range" | "Try a wider range, or check back once visits are scheduled." |
| Geo-verification Report — no flags | `shield-check` | "No flagged check-ins" | "Nothing to review — every check-in in this range passed verification." *(intentionally positive framing — an empty geo-verification report is good news, and the copy should say so)* |

Note the last row specifically: an empty state isn't always neutral. A zero-results Geo-verification Report is a *good* outcome, and the copy is written to read that way, rather than the generic "no data" tone used elsewhere — another direct application of the trust-and-explainability principle, applied even to an edge case as small as an empty table.

---

## 16. Loading States

### 16.1 Skeleton Loading (Primary Pattern)

Skeleton screens — not spinners — for anything that loads structured content (lists, cards, tables), per the Phase 6 doc's own named `LoadingState` composable existing as a shared, reusable component rather than an ad-hoc per-screen treatment.

- Skeleton blocks use `neutral-100` fill, `radius-sm`, matching the approximate shape/size of the real content that will replace them (a skeleton Visit Card is card-shaped with placeholder bars, not a generic gray rectangle).
- Skeletons never take longer than ~1.5s to resolve into real content or an error/empty state under normal network conditions — matching the Non-Functional Requirement that GPS check-in verification resolves in under 3 seconds; nothing in this product should feel like it's stalling.

### 16.2 Spinners (Secondary Pattern — Buttons & Inline Actions)

Reserved for actions with no "shape" to skeleton — button submissions (§8.4), file uploads, the check-in verification moment itself. A centered spinner, `primary-500`, sized to the button/element it's replacing.

### 16.3 Pull-to-Refresh (Android)

Standard platform-native pull-to-refresh gesture on the Dashboard, per the locked `I4` feature — shows the native Compose refresh indicator, no custom animation needed (again, "boring is a feature").

### 16.4 Upload Progress

Photo/document uploads (§9, §12 of the Requirements) show an inline progress state on the attachment thumbnail itself (a subtle overlay ring or bar), not a separate modal — the employee should be able to keep working (e.g., start the next form field) while an upload completes in the background, especially important given uploads may retry via WorkManager on poor field networks.

---

## 17. Animations

Animation in this product is used exclusively to **communicate state change**, never for decoration — consistent with the calm-by-default principle in §3. If an animation doesn't help the user understand that something just changed, it doesn't belong.

### 17.1 Motion Values

| Token | Duration | Easing | Usage |
|---|---|---|---|
| `motion-fast` | 120ms | ease-out | Button press feedback, checkbox/toggle flips |
| `motion-base` | 200ms | ease-in-out | Card hover elevation change, badge color transitions |
| `motion-slow` | 320ms | ease-in-out | Screen transitions (push/pop), modal open/close |
| `motion-status` | 400ms | ease-out | Status badge changing color/value (e.g., Pending → In Progress) |

### 17.2 Specific Animated Moments

- **Check-in success:** the "Start visit" button briefly transitions to a filled `primary-500` checkmark state (`motion-status`) before navigating forward — a small, satisfying confirmation for the single highest-stakes moment in the employee's day, per the User Journey doc's framing of this exact moment as "where trust in the tool is won or lost."
- **Offline Banner:** slides down from the top (`motion-slow`) when connectivity is lost, slides back up when restored — never appears/disappears instantly, since an abrupt state change here could read as alarming rather than reassuring.
- **Pending Sync icon:** the `refresh-cw` icon (§7.3) rotates continuously at a slow, steady rate while a record is queued — stops immediately and the badge swaps to Completed styling the moment sync confirms, with a brief `motion-status` cross-fade rather than a hard cut.
- **Toast/snackbar:** enters from the bottom (mobile) or top-right (web) over `motion-base`, holds 4 seconds, exits over `motion-fast`.
- **Skeleton-to-content:** a single `motion-base` cross-fade, never a jarring pop-in.

### 17.3 What Never Animates

- Error/warning color changes on form fields — these appear **instantly**, no fade-in. A validation error is information the user needs immediately; softening its appearance with a slow transition works against usability.
- The Flagged Visit Review screen's reason list and map — this screen renders fully and immediately on load. No staggered reveal animations here; an admin making a fair, fast judgment call shouldn't wait through a choreographed entrance on the product's most trust-sensitive surface.

---

## 18. Component Library Index

A flat reference list of every named, reusable component this system defines — cross-referenced to the section that specifies it and the platform(s) it appears on.

| Component | Platform(s) | Spec Section |
|---|---|---|
| `VisitStatusBadge` | Android + Web | §1.3, §8 |
| `LoadingState` / `ErrorState` / `EmptyState` | Android + Web | §15, §16 |
| `OfflineBanner` | Android | §16, §17 |
| `Button` (Primary/Secondary/Destructive/Ghost/Icon) | Android + Web | §8 |
| `Card` (Visit/MetricCard/ChartCard/Detail/Review) | Android + Web | §9 |
| `KanbanBoard` / `KanbanColumn` | Web | §9.3, §14 |
| `FormField` (Text/Dropdown/Number/Toggle/Date Range/Map Picker) | Android + Web | §10 |
| `SignatureCanvas` | Android | §10.4 |
| `DataTable` | Web | §11 |
| `FilterBar` | Web | §11.2 |
| `ReportLayout` | Web | §11.3 |
| `MapView` (Mini/Live/Review variants) | Android + Web | §12 |
| `BarChart` (via Recharts) | Web | §13 |
| `NavGraph` (single-stack) | Android | §14.1 |
| `Sidebar` | Web | §14.2 |
| `ReasonList` / `ReasonRow` | Web | §10.5, §12 |
| `ActionBar` | Web | §9.2 |
| `Toast` / `Snackbar` | Android + Web | §17.2 |
| `ExportModal` | Web | §11.3, §13 |

---

## 19. Platform Notes — Compose ↔ Tailwind Token Mapping

For whoever is implementing this system in code: every token in this document is expressed in a form that maps 1:1 to both platforms' native theming systems, so the same design intent produces the same design outcome regardless of who builds which screen.

### 19.1 Web — Tailwind / shadcn `globals.css` Token Targets

```css
:root {
  --radius: 0.5rem; /* 8px, matches radius-md */

  --primary: 158 68% 37%;     /* #1D9E75 */
  --secondary: 209 66% 55%;   /* #378ADD */
  --destructive: 1 68% 60%;   /* #E24B4A */

  --background: 220 14% 98%;  /* neutral-50 */
  --foreground: 220 12% 12%;  /* neutral-900 */
  --muted-foreground: 220 8% 57%; /* neutral-500 */
}
```

### 19.2 Android — Compose `Theme.kt` Token Targets

```kotlin
val FieldTrackColors = lightColorScheme(
    primary = Color(0xFF1D9E75),
    secondary = Color(0xFF378ADD),
    error = Color(0xFFE24B4A),
    surface = Color(0xFFFFFFFF),
    background = Color(0xFFF7F8F9),   // neutral-50
    onSurface = Color(0xFF1B1E22)     // neutral-900
)

val FieldTrackShapes = Shapes(
    small = RoundedCornerShape(6.dp),   // radius-sm
    medium = RoundedCornerShape(8.dp),  // radius-md
    large = RoundedCornerShape(12.dp)   // radius-lg
)
```

### 19.3 Governance

Any new color, spacing value, or component variant introduced during build that isn't in this document should be treated as a gap in the UI Bible, not a one-off decision — add it back here (with the same "locked vs. derived, and why" reasoning used throughout) so the document stays the single source of truth it's meant to be, rather than drifting out of sync with what actually ships.

---

*End of UI Bible v1.0 — derived from FieldTrack Pro Master Documentation, Phases 1–11.*
