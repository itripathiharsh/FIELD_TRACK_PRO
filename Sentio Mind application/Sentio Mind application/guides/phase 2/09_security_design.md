# FieldTrack Pro — Security Design
### Phase 2.4 — System Design

Security decisions consolidated into one doc — most were already touched on in Architecture/API Design, this is the authoritative reference so nothing drifts when different agent sessions build Auth (Phase 3), Android (Phase 6), and Deployment (Phase 9) separately.

---

## 1. Authentication

- **JWT access tokens**: short-lived (15 min), signed with a strong secret (HS256 minimum, RS256 preferred if key rotation matters later).
- **Refresh tokens**: longer-lived (7 days), stored server-side in `refresh_tokens` table (hashed, never plaintext) so they can be **revoked** — critical for the "deactivate employee" flow (B1) to actually take effect immediately, not just wait for token expiry.
- **Password hashing**: bcrypt (cost factor 10–12) or Argon2id — never MD5/SHA in any form.
- **Login rate-limiting**: max 5 failed attempts per identifier per 15 minutes, then temporary lockout (A6) — prevents brute force without permanently locking out a legitimate employee who fat-fingered their password.
- **Token storage**:
  - Android: Android Keystore-backed encrypted storage (never SharedPreferences in plaintext).
  - Web: access token in memory only (never localStorage — XSS risk); refresh token in httpOnly, Secure, SameSite=Strict cookie.

---

## 2. Authorization

- **Role-based access control (RBAC)** enforced at the **service layer**, not just `@PreAuthorize` on controllers — defense in depth in case a controller-level annotation is missed on a new endpoint.
- **Resource-ownership checks**: every `{id}`-scoped endpoint (e.g., `/visits/{id}/check-in`) verifies the authenticated employee actually owns that visit — an EMPLOYEE-role JWT alone is not sufficient authorization, it must also match `visit.employeeId`.
- **No client-trusted role claims for sensitive actions**: even though the JWT carries `role`, high-stakes endpoints (geo-verification, employee deactivation) re-check against the DB record, not just the token payload, in case a token is valid but the underlying account was deactivated mid-session.

---

## 3. Transport & Network Security

- **TLS everywhere**, including on-prem — self-signed/internal CA acceptable for pilot, but HTTPS is not optional even on a private network (per Architecture Section 4).
- **CORS** locked to the known web dashboard origin(s) only — no wildcard `*` in production.
- **Nginx reverse proxy** terminates TLS, adds security headers: `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`.

---

## 4. Data Protection

- **PII fields** (employee/customer contact numbers, names) — no special encryption-at-rest beyond standard PostgreSQL disk encryption (on-prem disk encryption assumed to be a Phase 9 infra task, not application-level).
- **Signatures and photos**: stored in MinIO, access only via backend-issued pre-signed URLs with short expiry — never expose MinIO directly to clients, so unauthorized users can't guess/enumerate object keys.
- **GPS coordinates**: treated as sensitive — an employee's location history is effectively a movement record. Only visible to: the employee themselves, and ADMIN role. Never exposed in any public or unauthenticated endpoint.
- **Audit trail immutability**: `geo_verification_logs` rows are insert-only — no UPDATE/DELETE permission granted to the application's DB role for this table, enforced at the database grant level, not just application logic. This is what makes the "anti-fake-visit" claim actually defensible, not just a UI restriction.

---

## 5. File Upload Security

- Server validates **actual file content** (magic bytes), not just client-declared MIME type or file extension (per G5).
- Max file size enforced server-side (e.g., 10MB per image, 20MB per document) — reject before it reaches MinIO, not after.
- Uploaded filenames are never trusted as storage keys — backend generates its own storage key (e.g., `visits/{visitId}/media/{uuid}.jpg`), original filename stored separately as metadata only. Prevents path traversal and collision attacks.

---

## 6. Input Validation & Injection Protection

- All request DTOs validated server-side with Jakarta Bean Validation (`@NotNull`, `@Size`, `@Pattern`) — client-side validation is UX only, never the security boundary.
- **Spring Data JPA** parameterized queries by default — no raw string-concatenated SQL anywhere in the codebase (relevant for the PostGIS geo-queries too, since those are easy to write unsafely if hand-rolled).
- Standard XSS protection on the React dashboard — React escapes by default, but any `dangerouslySetInnerHTML` usage (e.g., rendering admin-entered notes) needs explicit review, flagged here so it's not missed.

---

## 7. Mobile-Specific Hardening

- **Certificate pinning** (OkHttp) recommended for the Android app talking to the on-prem backend — reduces MITM risk on field networks (public WiFi, unknown cellular towers). Flag as a Phase 6 task, not Phase 3.
- **Root/emulator detection**: not a hard blocker for MVP (would need business sign-off — could lock out legitimate employees with rooted personal phones), but logging root-detected check-ins as a `SUSPICIOUS` flag in `geo_verification_logs.reason` is low-cost and worth including given the product's core anti-fraud purpose.
- **Mock-location detection**: Android's `Location.isFromMockProvider()` should be checked at check-in time — if true, reject with a specific reason code so admins can see "mock GPS suspected" distinctly from "genuinely out of radius" in the Geo-verification Report.

---

## 8. Secrets Management

- No secrets (DB passwords, JWT signing key, Maps API key, MinIO credentials) committed to any repo — `.env` files gitignored, `.env.example` committed with placeholder values only.
- Production secrets injected via environment variables at container runtime (Docker Compose `env_file` pointing to a non-committed file on the on-prem server).
- **Google Maps API key** restricted at the Google Cloud Console level: Android key restricted by package name + SHA-1 fingerprint, web key restricted by HTTP referrer — prevents key theft/abuse even if a key leaks client-side (Maps keys are inherently client-visible).

---

## 9. Logging & Monitoring

- Application logs **never** log full JWTs, passwords, or raw GPS coordinates at INFO level (coordinates are fine at DEBUG for troubleshooting, gated off in production).
- Failed geo-verification attempts and repeated login failures should be logged distinctly enough to support the admin alert requirement (FR-28) without needing a separate monitoring tool for MVP — a scheduled query/job checking `geo_verification_logs` is sufficient at this scale.

---

## Summary — Non-Negotiables Carried Into Later Phases

These aren't optional/nice-to-have — they're the items that, if skipped, undermine the product's actual value proposition:

1. Server-side geo-verification, never client-trusted (already flagged in Architecture/API Design, restated here as a security item).
2. Insert-only, immutable `geo_verification_logs`.
3. Resource-ownership checks on every visit-scoped endpoint.
4. Mock-location detection at check-in.

---

**Next up:** ER Diagrams (Phase 2.5) — the final piece of Phase 2, visualizing the schema relationships from Database Design.
