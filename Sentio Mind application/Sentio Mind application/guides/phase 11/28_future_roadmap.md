# FieldTrack Pro — Future Roadmap (Post-MVP)
### What's deliberately out of scope for the 10 phases above, and why

Every item here was explicitly deferred, not forgotten — each ties back to a specific MVP decision that would need to change first.

---

## 1. AI Visit Summaries
Auto-generate a written summary of a visit from the requirement form + notes. Deferred because MVP's structured form (category, priority, description) already captures the essential data in queryable form — an AI summary would be a presentation layer on top of data that doesn't exist yet in enough volume to be useful. Natural next step **after** a few months of real visit data accumulates.

## 2. AI Productivity Insights
Pattern detection across the Productivity Dashboard's raw numbers (e.g., "Employee X's visit duration has been trending up — possible sign of a scheduling problem"). Depends on having enough historical data (Phase 3's `geo_verification_logs` and `visits` tables are already structured to support this later) and, honestly, on the MVP's basic Productivity Dashboard (K3) proving useful first — no point building insights on top of a report nobody's using yet.

## 3. Route Optimization
Auto-suggesting the most efficient order for a day's multiple visits. Directly blocked by the **point-in-time location decision from Phase 4** — meaningful route optimization needs either the Directions API's routing intelligence (a real cost/complexity addition, explicitly deferred in the Route Navigation section) or actual road-network distance data, neither of which MVP's straight-line distance calculation provides.

## 4. Push Notifications *(clarification: this refers to richer notification types)*
MVP already has core notifications (new visit, reminder, overdue, geo-alert) built in Phase 3/6. This roadmap item covers what's genuinely deferred: rich notification actions (e.g., admin approving a flagged visit directly from the notification), notification preferences/quiet hours, and digest-style daily summaries instead of individual pings.

## 5. ERP/CRM Integrations
Connecting FieldTrack Pro's customer/visit data to external business systems. No specific ERP/CRM was named in the original proposal, so building integration now would mean guessing at an integration target — genuinely needs your input on which system(s) matter before this becomes buildable, not a technical deferral.

## 6. Face Verification
Adding biometric confirmation alongside GPS check-in, for even stronger anti-fraud assurance. Deferred because it's a meaningfully larger scope addition (camera-based liveness detection, biometric data storage with its own privacy/compliance considerations distinct from GPS data) — worth evaluating only if geo-verification alone proves insufficient in practice, not built pre-emptively for a problem MVP hasn't actually encountered yet.

## 7. Voice Notes
Letting employees record a spoken note instead of/alongside the typed requirement form. Straightforward addition once MVP's file upload infrastructure (Phase 5) is live — audio is just another file type through the same `MediaStorageService`. Deferred purely for MVP scope discipline, not technical difficulty.

## 8. Offline Sync Improvements
MVP's offline handling (Phase 6) covers the common case: queue while offline, replay on reconnect, idempotency-protected. This roadmap item covers the genuinely harder edge cases — true conflict resolution (e.g., a visit reassigned to a different employee while the original employee was offline and already completed it), multi-device sync if an employee ever uses more than one device, and partial-sync recovery if a sync job is interrupted halfway through a batch. Deferred because MVP's simpler "last write wins, admin resolves flagged conflicts manually" approach (per the Business Logic doc) is a reasonable tradeoff at pilot scale.

---

## What Would Need to Change First (Reading This Roadmap Against the MVP Decisions)

If you find yourself wanting to pull any of these forward, check which locked MVP decision it depends on first — pulling forward Route Optimization without revisiting the point-in-time location decision, for instance, wouldn't actually be buildable with what MVP produces. This roadmap is ordered roughly by how independent each item is from MVP's architecture — Voice Notes and richer Push Notifications are the cheapest to add later; Route Optimization and Face Verification are the ones that genuinely require revisiting earlier locked decisions, not just additive work.

---

## Full Plan — Complete

**Phase 1** (Requirements → Architecture) → **Phase 2** (Database → ER Diagrams) → **Phase 2.5** (Screen Lists → Navigation Flow) → **Phase 3** (Spring Boot Setup → Smoke Test) → **Phase 4** (Maps & Location) → **Phase 5** (File & Media) → **Phase 6** (Android) → **Phase 7** (Web Dashboard) → **Phase 8** (Testing & QA) → **Phase 9** (Deployment) → **Phase 10** (Documentation) → **this Future Roadmap**.

28 documents, zero open questions left unresolved as ambiguity — every gap that came up got either a locked product decision or an explicit flag for something only you can answer (VPN access, MDM vs. sideload, backup restore testing). This is the complete grounding context to feed Antigravity, phase by phase, from here.
