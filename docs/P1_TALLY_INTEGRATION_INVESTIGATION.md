# P1 Technical Investigation — Tally Prime Integration

Status: **investigation only, no code**. This document exists to inform a
build decision, not to describe something already built. Nothing in
FieldTrack currently talks to Tally in any way — confirmed by a repo-wide
search (`grep -ri tally`) across the backend, web, and Android codebases,
which returned zero genuine hits (only unrelated substring matches like
"horizontally" and "accidentally").

## Current Tally setup

Unknown at the FieldTrack-repo level — there is no record of which Tally
Prime edition, version, or network topology the client runs, and that
information wasn't available during this investigation. The rest of this
document describes what Tally Prime is *capable of* in general, which
governs what's possible regardless of the client's specific deployment;
confirming the client's actual setup (LAN-only vs. exposed, single site vs.
multi-branch, Tally version) is a prerequisite before building anything.

## Possible API / interface

Tally Prime has **no modern REST/JSON API**. Two integration surfaces exist:

1. **XML-over-HTTP ("ODBC/HTTP Server").** Tally can expose a local HTTP
   listener (commonly port `9000`) that accepts an XML request envelope
   describing a TDL (Tally Definition Language) report or collection, and
   returns the matching data as XML. This is the standard way third-party
   tools ("Tally connectors") pull ledger/voucher/outstanding data
   programmatically. It must be explicitly enabled in Tally (Gateway of
   Tally → F1 Help → Settings → Connectivity, or via `tally.ini`).
2. **Native ODBC driver.** Tally ships a Windows ODBC driver that exposes
   its internal data as SQL-queryable tables via a DSN. This is the other
   common path, often driven by a scheduled script (e.g. Python `pyodbc`)
   rather than a live request/response API.

There is **no push/webhook mechanism** in either case — Tally never
initiates outbound calls. Any integration is FieldTrack (or an intermediary)
**pulling** from Tally on a schedule or on demand.

3. **Manual/scheduled export (the fallback already anticipated by the
   client).** Tally can export any report (Ledger Outstanding, Bills
   Receivable, Day Book, etc.) to Excel/CSV/XML directly from its UI, or via
   a script driving the same export mechanism. This produces a file a human
   or a script then delivers to FieldTrack.

## Authentication

**None, by default, on the HTTP/XML interface.** Tally's HTTP listener has
no login step — it trusts any request that can reach the port. This is a
real risk (see below), not an oversight to work around; it means the
integration's security boundary has to be the *network*, not the
application. The ODBC driver similarly has no meaningful auth beyond
whatever Windows/network access control guards the machine running Tally.

## Data available

Via either the XML/HTTP or ODBC path, in principle: ledger vouchers (sales,
receipts), each carrying voucher date, voucher number, party ledger name,
amount, and narration; ledger-level outstanding/bills-receivable reports;
party (customer) ledger master data. Via manual export: whatever report the
client already runs today, in whatever column shape that report happens to
have — which is exactly the file this investigation cannot assume the shape
of (see the Excel/MIS import architecture doc).

## Required FieldTrack fields

For the aging/collections feature actually built in this P1 pass, the
minimum required per invoice is: outlet identity, invoice number, invoice
date (the sole authoritative aging input — see `aging_service.py`), amount,
and optionally due date and brand. See `Invoice` in
`app/models/invoice.py`.

## Mapping

**Not resolved in this pass, and not invented.** The single hardest mapping
problem, regardless of transport (API or Excel), is **party identity**:
Tally identifies a customer by **ledger name** (a free-text string), not a
stable ID. This is precisely the "Balaji Enterprises" vs. "Balaji
Electrical" ambiguity the client described. FieldTrack's `Customer.
outlet_code` field (added this pass) exists specifically to be the anchor
for this mapping — but it only works if Tally's ledger names (or a Tally
ledger alias/code field, if the client uses one) can be reliably matched to
`outlet_code` values, which requires either (a) the client maintaining that
correspondence in Tally itself, or (b) a one-time manual reconciliation pass
when historical data is first imported. This must be confirmed with the
client before any automated mapping is built.

## Sync direction

One-way, Tally → FieldTrack, for invoices/outstanding. FieldTrack does not
attempt to write back into Tally in this design — the P1 spec's own
workflow ends at "this verified data can be reconciled with Tally," i.e.
reconciliation happens on the Tally/accounting side, using FieldTrack's
verified-payment records as an input, not as an automatic two-way sync.

## Sync frequency

Not decided — depends entirely on which transport is chosen:
- Excel/MIS export: whatever cadence the client already runs that report at
  (likely daily or weekly), imported manually or via a scheduled upload.
- XML/HTTP or ODBC pull: could run more frequently (e.g. nightly), but see
  the network-exposure risk below before assuming this is trivial to
  automate unattended.

## Risks

1. **No authentication on the HTTP/XML interface.** Exposing Tally's port
   9000 beyond a trusted LAN (e.g. to let a cloud-hosted FieldTrack backend
   reach it directly) would let anyone who can reach that port read/query
   the client's accounting data. A real integration would need either (a)
   FieldTrack and Tally on the same trusted network, (b) a VPN/tunnel, or
   (c) a small on-premise agent that pulls from Tally locally and pushes
   the result to FieldTrack's API over normal authenticated HTTPS. Option
   (c) is the safest pattern used in practice for this kind of integration.
2. **Party-identity ambiguity** (above) is not a transport problem — it
   exists identically whether the data arrives via API or Excel, and it's
   the client's own stated pain point.
3. **No TDL/ODBC access confirmed.** Whether the client's specific Tally
   installation has these interfaces enabled, and whether their IT
   environment permits any external process to reach them, is unknown and
   must be confirmed on their end before scoping real engineering work.
4. **Version drift.** TDL/XML report definitions can differ across Tally
   Prime versions; a report definition built against one client's version
   may not work unmodified against another's.

## Recommendation: **Hybrid, Excel-first**

- **Now:** ship the Excel/MIS import path (see the companion architecture
  doc). It requires no access to the client's Tally instance, no network
  exposure risk, and matches what the client's own meetings already
  described as the fallback. `Invoice.source = EXCEL_IMPORT` and
  `source_reference` (both already in the schema) exist specifically to
  make this traceable.
- **Later, if justified:** if the client confirms their Tally installation
  can safely expose the XML/HTTP or ODBC interface (network topology
  permitting) and is willing to maintain an outlet-code correspondence in
  Tally, build a small on-premise pull agent as described in risk #1,
  writing into the same `Invoice`/`Payment` tables with
  `source = TALLY`. The data model already supports this without any
  schema change — the work would be entirely in a new sync job/agent, not
  in FieldTrack's core schema.
- Do **not** attempt a direct, unauthenticated, internet-facing connection
  from FieldTrack straight to a client-premises Tally HTTP port. That is
  the one option this investigation actively advises against.
