# FieldTrack Pro: QA / DEMO environment

**This is a demonstration environment with fictional data. It is not production.**

- Separate database, separate service, separate secrets. It has no connection to the production backend, the production database, a Tally agent or any real Tally company.
- Every person, outlet, phone number, GSTIN, bill and amount in it is invented.
- Tally write-back is off, and e-mail/SMS/push are mocked. Nothing leaves the environment.
- The web app shows a **DEMO / TEST ENVIRONMENT** banner on every page.

## What is in it

36 fictional outlets across 2 territories and 6 areas, and 6 field officers (FOS).
- **Tally-style books:** 33 debtor ledgers, 159 sales invoices, 62 receipts, 8 credit notes and an open-bills snapshot that reconciles to the rupee.
- **70 days of field history:** visits, GPS check-ins (including geofence failures), attendance, monthly plans, collections linked to the matching Tally receipts, and a review queue.
- **Live workflows:** photos, outlet proofs, location corrections, a new-outlet request, requirements with approvals, and orders.

## Layout

| Path | Purpose |
|---|---|
| `fieldtrackpro-backend/` | The FieldTrack backend (release 3.1, unmodified) |
| `fieldtrackpro-backend/qa_asgi.py` | Serves the API (`/api/*`, `/health`) and the web app from one address |
| `fieldtrackpro-backend/web_dist/` | The QA web build (demo banner on) |
| `fieldtrackpro-backend/qa_media/` | Synthetic demo photographs |
| `render.yaml` | Render blueprint: Postgres + web service |

The database content is loaded separately (restored from a dump). It is not stored in this repository.
