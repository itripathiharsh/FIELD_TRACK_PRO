# Capture Order / MIS vs Requirement / Stock Request — audit

Status: findings only. Nothing was removed, merged or migrated. Any removal or merger needs your explicit approval.

## What each feature is today

| | Capture Order / MIS | Requirement / Stock Request |
|---|---|---|
| Android entry | Visit Details tile "Capture Order / MIS" -> `MediaUploadScreen(isOrderMode=true)` | Visit Details tile "Requirement / Stock Request" -> `RequirementFormScreen` (+ `FormFillScreen`) |
| What the employee records | A free-text diary/order note (`note`) and an optional photo of the order or invoice | Brand, product details, quantity, expected value, priority/follow-up date, notes, optional photo; multiple line items |
| Backend storage | `visit_media` row with `media_type = ORDER` (note + optional file), via `POST /visits/{id}/media?is_order=true` | `customer_requirements` (+ line items), linked to customer and visit; optional `photo_media_id` into `visit_media` |
| Structure | Unstructured text/photo. No products, quantities or values | Structured: brand, quantity, requested/approved value, per-line approval |
| Approval workflow | None. A record is a note | Yes: admin decision (approve, partially approve, reject), approved quantity/value, admin notes, `decided_by/at` |
| Downstream | None found in services or reports | Can become an `Order` (`orders.requirement_id`, status `PENDING_TALLY`, Tally sales-order write-back queue) |
| Reports | Appears only in the visit's attachment list | Requirement list/summary endpoints; feeds orders and Tally write-back |

## Overlap
- Both are launched from the same visit screen. Both answer "what does this outlet want to buy".
- The Order tile's own subtitle says "stock requirement". The overlap is the intent, not the data.
- Both can carry a photo, through `visit_media`.

## Unique to each
- **Capture Order / MIS only:** a quick unstructured diary note with no product detail. It works offline with an attachment upload.
- **Requirement only:** structured lines, an admin decision workflow, conversion to an `Order`, and the Tally write-back path.

## Dependencies and historical data
- `visit_media` rows with `media_type = ORDER` hold historical order notes. They are ordinary visit media. They must stay readable (the Android list filters on `isOrder`).
- `customer_requirements.photo_media_id` points into `visit_media`, so the two share a table. A purge of ORDER media must not touch requirement photos.
- `orders.requirement_id` ties orders to requirements, not to ORDER media.
- No report or integration found that reads ORDER media as business data.

## Risk of changes
- **Removing Capture Order / MIS now:** loses the quick note path. Historical ORDER media would become unreachable in the app unless the visit attachment list is kept. Low data risk, medium workflow risk.
- **Removing Requirement:** high risk. It breaks approvals, orders and Tally write-back.
- **Merging:** low risk if the note and photo become an optional "Notes / photo" section inside the Requirement form and old ORDER media stays readable.

## Recommendation (needs your decision)
1. Keep **Requirement / Stock Request** as the single order-intake workflow. It is the only one with structure, approval and downstream integration.
2. Fold the Capture Order note and photo into the Requirement form as optional fields. The form already supports notes and a photo.
3. Keep the Capture Order tile, relabelled "Order Note / MIS", until you approve the merger. After approval, hide the tile and leave backend endpoints, tables and history untouched.
4. Do not delete `ORDER` media, endpoints or tables. If an unstructured note is ever needed, keep it as a visit note.

Safe changes made in this pass: none to either feature (audit only).
