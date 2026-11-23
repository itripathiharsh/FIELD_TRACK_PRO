# Capture Order / MIS vs Requirement / Stock Request — audit (v2, with code evidence)

Audit only. Nothing was deleted, migrated or changed in either feature. Paths are relative to the repo root (`fieldtrackpro-android/...`, `fieldtrackpro-backend/...`).

## 1. The two features

### Capture Order / MIS
- **Purpose:** a diary entry for an order or market note, with an optional photo. The visit tile says "Record stock requirement, diary notes & order info" (`VisitDetailsScreen.kt`).
- **Users:** employees (and admins through the same media API).
- **Employee enters:** free text note, optional photo/file. No brand, product, quantity or value.
- **Android:** `MediaUploadScreen.kt` with `isOrderMode = true`; `MediaViewModel.captureOrder`; offline upload through `MediaUploadWorker.kt`.
- **API:** `POST /visits/{id}/media?is_order=true&note=...` (`app/api/v1/media.py`); validated in `file_validation_service.py` (note-only is stored as `text/plain`).
- **Storage:** `visit_media` row, `media_type = ORDER` (`app/models/visit_media.py`).
- **Approval/admin actions:** none. It has no status.
- **Tally:** none. No write-back path reads ORDER media.
- **Reporting effect:** it is counted as an "order" in the dashboards: `app/services/dashboard_service.py:195` (admin KPI) and `:313` (employee day dashboard), and in employee activity (`employee_activity_service.py`, `media_repo.py:65-86`). It does not change sales, outstanding, inventory or collections.

### Requirement / Stock Request
- **Purpose:** a structured retailer demand: what the outlet wants, from which brand, in what quantity, at what value.
- **Users:** employee submits; **admin only** decides (`AdminOnly` on decision/approve/partially-approve/reject/confirm-order in `app/api/v1/requirements.py`).
- **Employee enters:** brand, product details, quantity, expected value, priority/follow-up, notes, optional photo, multiple line items (`RequirementFormScreen.kt`, `FormFillScreen`).
- **API:** `POST /requirements`, `GET /requirements`, `POST /requirements/{id}/decision | approve | partially-approve | reject | confirm-order | photo`.
- **Storage:** `customer_requirements`, `requirement_items`, `requirement_forms`, `requirement_categories` (`app/models/`). The optional photo is a `visit_media` row via `photo_media_id`.
- **Approval:** statuses NEW/PENDING/UNDER_REVIEW/APPROVED/PARTIALLY_APPROVED/REJECTED/CONVERTED_TO_ORDER. The admin records approved quantity and value per line; the original employee request is kept.
- **Tally:** `confirm-order` (`customer_requirement_service.py:490+`) creates an `Order` (`app/models/order.py`, status `PENDING_TALLY`) and enqueues `CREATE_SALES_ORDER` in `tally_writeback_queue`. I did not inspect the Tally Agent or what it does with that queue.
- **Reporting effect:** orders list (`GET /orders`), requirement summaries. Effects on sales/outstanding appear only after Tally posts the order and the next sync.

## 2. Comparison

| Area | Capture Order / MIS | Requirement / Stock Request |
|---|---|---|
| Business purpose | Quick order/market diary note | Structured stock/order demand to be approved |
| Data fields | note + optional file | brand, product, qty, value, priority, follow-up, notes, line items |
| Brand and quantity | none | yes (brand validated, qty/value per line) |
| Photos/attachments | optional, one per entry | optional photo per requirement |
| Approval workflow | none | admin approve / partial / reject |
| Admin actions | view only | decide, edit approved qty/value, confirm order |
| Backend APIs | `/visits/{id}/media?is_order=true` | `/requirements/*`, `/orders` |
| Database models | `visit_media` (ORDER) | `customer_requirements`, `requirement_items`, `orders` |
| Reporting | counted as "orders" in dashboards and employee activity | requirement lists; orders list |
| Tally integration | none | yes: confirm-order -> `CREATE_SALES_ORDER` queue |
| Historical records | ORDER rows in `visit_media` | requirement and order rows |

## 3. Overlap and duplication
- **Same order in both:** yes. Nothing stops an employee entering the same order as a diary note and as a requirement.
- **Duplicate business records:** only in the sense of two records for one demand. The note creates no Order and no Tally entry, so it cannot double-post. The real risk is reporting: the dashboards' "orders" figure counts ORDER notes, not formal `orders` rows, so the number can be inflated by notes and miss real orders.
- **Capture Order is only a note/photo:** confirmed.
- **Requirement is structured with approval:** confirmed.
- **Which feeds Tally:** only Requirement, through confirm-order.
- **Replacement:** Requirement can replace Capture Order if it gains a quick "note only / photo only" path. Capture Order cannot replace Requirement.

## 4. Which to use

1. **Retailer asks for 20 units of a specific brand:** Requirement / Stock Request. It records brand and quantity and goes to the admin.
2. **Market observation with a photo:** Capture Order / MIS as a note and photo (or a visit attachment). It has no business effect and needs no approval.
3. **Order needing admin approval and Tally processing:** Requirement / Stock Request. After the admin approves it, confirm-order creates the Order and queues Tally.

## 5. Recommendation (needs your approval)
**Rename now, then merge later.**
1. Rename the tile to "Order Note / Market Note (no approval)" and make the Requirement tile "Stock Request / Order (goes to admin)". Add a line on the note screen: "For an order that needs approval, use Stock Request". This is a text-only change.
2. Change the dashboard "orders" KPI to count formal `orders` rows (and show requirement counts by status), keeping note counts separate. This needs your sign-off because it changes reported numbers.
3. Later, fold the note and photo into the Requirement form (optional section) and hide the standalone tile once nothing depends on it.
4. Never delete ORDER media, endpoints or tables. The history stays readable.

## 6. Missing functionality found
- No link between an ORDER note and a requirement/order (cannot tell they describe the same demand).
- No duplicate warning when the same outlet has an open requirement.
- Dashboard "orders" counts notes, not orders.
- Not verified: how the Tally Agent consumes `CREATE_SALES_ORDER` (out of scope and not touched).
