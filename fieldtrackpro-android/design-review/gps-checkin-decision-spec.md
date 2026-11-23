# GPS check-in decision specification (single source of truth)

Implemented twice, deterministically, and tested against one shared vector file:
- Backend: `fieldtrackpro-backend/app/services/geo_decision.py`
- Android: `fieldtrackpro-android/app/src/main/java/com/fieldtrackpro/android/utils/GeoDecision.kt`
- Shared vectors: `fieldtrackpro-android/app/src/test/resources/gps_decision_vectors.json` (read by both test suites)

## Constants
| Name | Value | Notes |
|---|---|---|
| `R` | outlet `geofence_radius_m` (75 m) | never widened to hide GPS error |
| `K` | 0.5 | weight of uncertainty on the inside test |
| `MAX_ACCURACY_M` | 100 | above this (or unknown) there is no decision |
| `LIVE_MAX_AGE_S` | 120 | a live fix must be at most this old when it reaches the server |
| `EPS` | 1e-9 | tolerance on the two comparisons |

## Inputs
`d` distance device to saved pin (metres), `a` reported accuracy, `p` pin accuracy (optional), `age_s` fix age, `coords_valid`.

## Algorithm (in this order)
1. `coords_valid == false` -> **POOR_FIX** (`INVALID_COORDINATES`).
2. `a` missing, NaN, `<= 0` or `Float.MAX` -> **POOR_FIX** (`ACCURACY_UNKNOWN`).
3. `a > 100` -> **POOR_FIX** (`ACCURACY_TOO_LOW`).
4. `age_s > LIVE_MAX_AGE_S` (or more than 5 min in the future) -> **POOR_FIX** (`STALE`). Offline-queued check-ins skip this test and are flagged instead.
5. `u = sqrt(a^2 + p^2)` when `p` is known and `> 0`, otherwise `u = a`.
6. `d + K*u <= R + EPS` -> **INSIDE**.
7. else `d - u > R + EPS` -> **OUTSIDE**.
8. else -> **UNCERTAIN**. `point_inside = d <= R`.

Mock location is a hard rejection before this algorithm. It is not a GPS-quality outcome.

## What each outcome does
| Outcome | Check-in endpoint | Android |
|---|---|---|
| INSIDE | accepted, confidence HIGH | submits |
| OUTSIDE | 422 `GEO_VERIFICATION_FAILED` with the distance | shows the distance, does not submit |
| UNCERTAIN and `point_inside` | accepted, confidence LOW, review `CONDITIONAL` PENDING | after the 45 s window, submits; says it is flagged for review |
| UNCERTAIN and not `point_inside` | 422 `GEO_UNCERTAIN` (verification available) | offers Request Admin Verification |
| POOR_FIX | 422 `GEO_VERIFICATION_FAILED` (reason), no decision | retry guidance |

The phone collects fresh fused fixes for up to 45 s (stopping early on INSIDE/OUTSIDE), keeps the best fix by accuracy then freshness, and submits that one. The server always re-decides.

## Offline-queued check-ins
`age_s > LIVE_MAX_AGE_S` and `<= 24 h`: the freshness test is skipped, the geofence outcome is applied as above, and the check-in is recorded with confidence `OFFLINE` plus a review row of kind `OFFLINE`. Older than 24 h is rejected as before.

## Admin review
- `CONDITIONAL` and `OFFLINE` reviews: approve -> confidence `ADMIN_CONFIRMED`; reject -> the visit is `FLAGGED`.
- `VERIFICATION_REQUEST` (employee asked): approve -> the visit is checked in with confidence `ADMIN_VERIFIED`, using the employee's recorded fix; reject -> the visit stays unchanged.
- Reviews never modify the outlet pin. Check-in never modifies the outlet pin.
- Rate limits for requests: one pending per visit, at most 3 per visit, at most 5 per employee per hour, at least 60 s between requests.
