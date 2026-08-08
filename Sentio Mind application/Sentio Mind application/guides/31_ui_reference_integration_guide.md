# FieldTrack Pro — UI Reference Integration Guide
### How Antigravity should use the Stitch frontend designs — reference, not source code

The Stitch folder is static HTML/CSS mockups. They define **visual design** (layout, spacing, color, typography, component look) — they do NOT define working behavior, state management, API wiring, or validation logic. Those come from the phase docs already built (Screen Lists, Features, API Design, Business Logic). This doc exists so the agent never confuses "looks like this" with "works like this."

---

## 1. The Core Rule

**Design tokens and layout: copy the intent. Code: never copy the HTML directly.**

- Android is Kotlin + Jetpack Compose (per Tech Stack doc) — Stitch's `code.html` files are not portable to Compose. The agent extracts colors, spacing, typography, and layout structure, and rebuilds them as native Compose composables.
- Web is React + TypeScript + Tailwind + shadcn/ui (per Tech Stack doc) — Stitch's raw HTML/CSS *can* be more directly translated since it's the same web stack, but it still needs to become real React components with real state, real Tailwind classes matching the project's `tailwind.config.ts`, and real data — not an `<iframe>` or a dumped static HTML block.
- Every interactive element in a Stitch mockup (buttons, dropdowns, form fields) must be wired to the actual API endpoints from `07_api_design.md`, not left as inert HTML.

---

## 2. Design Token Extraction (Do This Once, First — Not Per Screen)

Before converting a single screen, the agent should:
1. Read `fieldtrack_pro_ui_bible.md` and `fieldtrack_pro/DESIGN.md` in full.
2. Extract: color palette, typography scale, spacing scale, corner radius conventions, shadow/elevation styles, icon set used.
3. Produce **one source of truth** for each platform:
   - Android: a Compose `Theme.kt` / `Color.kt` / `Type.kt` set (extends the placeholder `FieldTrackColors` sketched in `23_android_application.md` Section 1 — replace those placeholder hex values with the real ones from DESIGN.md).
   - Web: an updated `tailwind.config.ts` with the real design tokens as custom theme values, not ad-hoc inline styles per component.
4. **Stop and get this reviewed before touching any individual screen.** Every screen conversion downstream depends on this being right once — if the token extraction is wrong, all 40 screens inherit the same mistake.

---

## 3. Screen Mapping — Stitch → Existing Spec Docs

The Stitch designer produced **more screens than our original Screen List docs specified** (18 Android vs. our 22-item list, 22 Web vs. our 24-item list — note these are different counts in different directions, not a simple 1:1 gap, because Stitch consolidated some of our multi-state screens into single files and added others we didn't originally list). The agent should map every Stitch screen to a feature ID from `03_features.md` before building it — if a Stitch screen has no corresponding feature ID, it needs a decision (see Section 4), not silent implementation.

### Android — `a1`–`a18` Mapping

| Stitch Screen | Maps To (11_android_screen_list.md) | Notes |
|---|---|---|
| a1 Splash | Screen 1 | Direct match |
| a2 Login | Screen 2 | Direct match |
| a3 Dashboard | Screen 3 | Direct match |
| a4 Visit Details | Screen 6 | Direct match |
| a5 En-route/Geofence Waiting | Screen 8 | Direct match |
| a6 Geo-verification States | Screens 9 + 10 | Stitch combined the check-in confirmation AND the failed/retry state into one screen file with multiple states — build as one composable with state-driven UI, matching Stitch's consolidation, not two separate screens |
| a7 Requirement Form | Screen 11 | Direct match |
| a8 Photo/Doc Upload | Screens 12 + 13 | Same consolidation pattern as a6 |
| a9 Employee Signature | Screen 14 | Direct match |
| a10 Customer Signature | Screen 15 | Direct match |
| a11 Submission Success | Screen 17 | Direct match |
| a12 Notifications | Screen 5 | Direct match |
| a13 Profile | Screen 21 | Direct match |
| a14 Settings | Screen 22 | Direct match |
| a15 Offline/Sync Status | Screens 18–20 | Stitch consolidated the badge/banner/conflict states into one reference screen — implement as the distributed UI states our doc specifies (badge on cards, persistent banner), not literally one dedicated screen in the nav graph |
| a16 Navigation Overview | Screen 7 | This is the Google Maps handoff — Stitch's version is likely a preview/confirmation state before the deep-link fires, not a full custom nav UI (per the Maps & Location Services doc's explicit decision against in-app navigation) |
| a17 Forgot Password | **No feature ID exists** | New scope — see Section 4 |
| a18 Reset Password | **No feature ID exists** | New scope — see Section 4 |

### Web — `w1`–`w22` Mapping

| Stitch Screen | Maps To (12_web_dashboard_screen_list.md) | Notes |
|---|---|---|
| w1 Login | Screen 1 | Direct match |
| w2 Dashboard Overview | Screen 2 | Direct match |
| w3 Employee List | Screen 4 | Direct match |
| w4 Add/Edit Employee | Screens 5 + 6 | Stitch combined add/edit into one form screen — matches standard practice, build as one component with create/edit mode |
| w5 Employee Details | Screen 7 | Direct match |
| w6 Customer List | Screen 8 | Direct match |
| w7 Add/Edit Customer | Screens 9 + 10 | Same combine pattern as w4 |
| w8 Customer Details | Screen 11 | Direct match |
| w9 Visit List | Screen 12 | Note: check whether this is the Kanban board or a flat list — if Stitch built a flat list, this may be a genuine alternate/additional view alongside the Kanban board, not a replacement. Flag for your review before deciding which (or both) ships. |
| w10 Create Visit | Screen 13 | Direct match |
| w11 Visit Details (Admin) | Screen 15 | Direct match |
| w12 Live Operations Map | Screen 3 | Direct match |
| w13 Visit Status Board | Screen 12 | The Kanban board itself — see w9 note above, these two Stitch screens may represent two views of the same data |
| w14 Employee Productivity Report | Screen 19 | Direct match |
| w15 Customer Visit History Report | Screen 18 | Direct match |
| w16 Geo-verification Report | Screens 16 + 20 | Direct match |
| w17 Export Options | Screen 21 | Direct match |
| w18 Notifications Center | **No feature ID exists** | New scope — see Section 4 |
| w19 Settings/Profile | Screen 24 | Direct match |
| w20 Productivity Dashboard | Screen 19 | Likely the same underlying screen as w14 with a different name — confirm with the agent before building both as separate pages |
| w21 System States (404/Access Denied) | **No feature ID — but this is good practice, not scope creep** | Standard error-state screens every real app needs; build these regardless, no product decision required |
| w22 System Maintenance | **No feature ID exists** | New scope — see Section 4 |

---

## 4. New Screens Not in Original Spec — Decisions (Locked, Same Discipline as Every Other Gap in This Project)

Rather than leaving these as open questions for the agent to guess at:

1. **Forgot/Reset Password (a17, a18)** — **In scope, add to Module A.** This is a standard, expected feature for any login system, not a scope-creep addition. Implementation: `POST /auth/forgot-password` (sends a reset link/OTP to registered email/phone), `POST /auth/reset-password` (validates token, sets new password). Add as **A8** and **A9** to `03_features.md`'s Module A. Needs its own small Alembic migration for a `password_reset_tokens` table (mirror the `refresh_tokens` pattern — hashed token, expiry, single-use).

2. **Web Notifications Center (w18)** — **In scope, small addition to Module L.** Admin-side equivalent of what Android already has — a page listing the same `notifications` table rows already modeled in Database Design, filtered to the admin's own `userId`. No new backend work needed beyond exposing `GET /notifications/me` to the web client too (it's already role-agnostic in the API Design doc). Add as **L5**.

3. **System Maintenance (w22)** — **Deferred, not in MVP scope.** This implies a maintenance-mode toggle/banner system (admin can put the app in maintenance mode, users see a friendly downtime message) — a genuinely new capability requiring backend state (a global "maintenance mode" flag) and middleware to check it on every request. This wasn't in the original proposal or any locked requirement. Decision: **defer to Future Roadmap** as a new item, don't build for MVP. If you disagree and want this in MVP, say so explicitly — this is the one item in this doc I'm actively deferring rather than absorbing, since it's genuinely new backend infrastructure, not just a screen.

4. **w21 System States (404/Access Denied)** — build regardless of feature-ID mapping; this is baseline engineering hygiene, not a product decision.

---

## 5. Conversion Prompt Template (Per Screen)

```
Context:
- Stitch reference: stitch frontend/.../a4._visit_details/code.html + screen.png
- Functional spec: 11_android_screen_list.md (Screen 6), 02_user_flows.md (Section 1.3),
  17_core_apis.md (Visit endpoints), 23_android_application.md (Section 3)
- Design tokens: [the Theme.kt/Color.kt/Type.kt files produced in Section 2 — already built, reference not rebuild]

Task: Build the Visit Detail screen as a native Jetpack Compose composable.

Constraints:
- Match the Stitch design's visual layout, spacing, and component styling as closely as
  Compose allows — this defines LOOK.
- All behavior (data loading, button actions, navigation, geofence-based enable/disable state
  on the Start Visit button) comes from the functional spec docs listed above — this defines
  BEHAVIOR. Where the two conflict (e.g., Stitch shows a button that doesn't exist in our
  feature spec), functional spec wins — flag the discrepancy rather than silently adding
  unspecced functionality.
- Use the theme tokens already established — do not hardcode new colors/spacing for this screen.
- Do not treat the static screen.png as proof of correct interactive behavior — it's a single
  frozen state, not a demonstration of the loading/error/empty states this screen also needs
  per the Reusable Components section (23_android_application.md Section 1).
```

---

## 6. Verification — This Feeds Directly Into the Definition of Done Doc

Once a screen is converted, it goes through the same `30_definition_of_done.md` checklist as everything else — matching the Stitch screenshot visually is necessary but not sufficient. A pixel-perfect screen that doesn't actually call the real API, doesn't persist data, or doesn't handle the failure states is still a FAIL under that doc's rules.

---

## 7. Sequencing — Where This Fits Into the Existing Phase Plan

This doesn't add a new phase — it modifies **how** Phase 6 (Android) and Phase 7 (Web) get executed, per the task-boundary discipline in `29_antigravity_execution_guide.md`:

```
Task 6.1 (UI/UX shell) — NOW INCLUDES: Section 2 token extraction first, before any screen work
Task 6.3 (Dashboard + Visit Detail) — NOW REFERENCES: a3, a4 Stitch designs alongside existing spec
Task 6.6 (Requirement form) — NOW REFERENCES: a7 Stitch design
Task 6.7 (Uploads) — NOW REFERENCES: a8, a9, a10 Stitch designs
```
Same pattern applies to every Phase 7 task — add the relevant `w#` Stitch reference to each existing task's context, don't restructure the task breakdown itself.

**One new task, inserted at the start of both Phase 6 and Phase 7**: "Task 6.0 / 7.0 — Design token extraction" (Section 2 of this doc), which must complete and be reviewed before Task 6.1/7.1 begins.
