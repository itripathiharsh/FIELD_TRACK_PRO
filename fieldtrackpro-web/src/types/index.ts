/**
 * API contract types.
 *
 * These mirror the FastAPI response schemas exactly. Fields that the backend
 * does not return must not appear here: the previous version declared invented
 * fields (FT-003, FT-012) which forced `as any` casts at call sites and made
 * several table columns render permanently blank.
 */

/**
 * The backend Role enum is exactly these three members, least to most privileged:
 * EMPLOYEE < ADMIN < SUPER_ADMIN. SUPER_ADMIN is a superset of ADMIN that can also manage roles.
 * (FT-038: a frontend-only 'MANAGER' role once existed; selecting it produced a user the API would
 * never accept - do not add roles here that the backend does not have.)
 */
export type UserRole = 'SUPER_ADMIN' | 'ADMIN' | 'EMPLOYEE' | 'ACCOUNTANT';

/** Response of `GET /api/v1/auth/me`. */
export interface User {
  id: string;
  email: string | null;
  mobile_number: string | null;
  /** FT-011: employee profile name, or the account identity for admins. */
  full_name: string;
  role: UserRole;
  is_active: boolean;
  /** Present when the user has an employee profile. */
  territory_id?: string | null;
  employee_id?: string | null;
  /** True while the server requires a password change before any other action. */
  must_change_password?: boolean;
}

/** Response of `GET /api/v1/employees` (employees.id, not users.id). */
export interface Employee {
  id: string;
  user_id: string;
  full_name: string;
  territory_id: string | null;
  effective_territory_name?: string | null;
  employee_code: string | null;
  working_profile?: string | null;
  cug?: string | null;
  date_of_birth?: string | null;
  address?: string | null;
  must_change_password?: boolean;
  assigned_outlets_count?: number;
  created_at: string;
  /** Present on detail endpoints that embed the linked account. */
  user?: {
    id: string;
    email: string | null;
    mobile_number: string | null;
    role: UserRole;
    is_active: boolean;
    /** Non-secret: set while an admin-issued temporary password is pending. */
    temp_password_expires_at?: string | null;
  };
}

/** Response of `POST /api/v1/employees/{id}/reset-password`. Shown ONCE; never persisted. */
export interface AdminPasswordReset {
  employee_id: string;
  user_id: string;
  temporary_password: string;
  expires_at: string;
  expires_in_minutes: number;
  must_change_password: boolean;
}

/** One row of `GET /api/v1/security-audit-logs` (Super Admin only). No credentials are ever included. */
export interface SecurityAuditLog {
  id: string;
  created_at: string;
  event_type: string;
  outcome: 'SUCCESS' | 'DENIED' | 'FAILED' | string;
  actor_user_id: string | null;
  target_user_id: string | null;
  previous_role: string | null;
  new_role: string | null;
  reason_code: string | null;
  details: Record<string, unknown> | null;
}

/** Geographic point as exchanged with the API. */
export interface GeoPoint {
  latitude: number;
  longitude: number;
}

export type LocationStatus = 'VERIFIED' | 'NEEDS_REVIEW' | 'MISSING' | 'PENDING_APPROVAL';
export type LocationProposalStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

export interface LocationProposal {
  id: string;
  customer_id: string;
  customer_name?: string | null;
  customer_outlet_code?: string | null;
  current_latitude?: number | null;
  current_longitude?: number | null;
  proposed_latitude: number;
  proposed_longitude: number;
  gps_accuracy_meters?: number | null;
  distance_meters?: number | null;
  submitted_by: string;
  submitter_name?: string | null;
  submitted_by_employee_id?: string | null;
  submitted_at: string;
  status: LocationProposalStatus;
  reviewed_by?: string | null;
  reviewer_name?: string | null;
  reviewed_at?: string | null;
  rejection_reason?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export type RequirementStatus =
  | 'PENDING'
  | 'APPROVED'
  | 'PARTIALLY_APPROVED'
  | 'REJECTED'
  | 'FULFILLED'
  | 'CANCELLED'
  | 'OPEN'
  | 'CONVERTED_TO_ORDER';

export interface RequirementItem {
  id: string;
  requirement_id: string;
  brand_id?: string | null;
  brand_name: string;
  product_model: string;
  requested_quantity: number;
  expected_rate: number;
  requested_amount: number;
  approved_quantity?: number | null;
  approved_rate?: number | null;
  approved_amount?: number | null;
  tally_stock_item_name?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RequirementItemDecisionUpdate {
  id: string;
  approved_quantity?: number | null;
  approved_rate?: number | null;
  tally_stock_item_name?: string | null;
  notes?: string | null;
}

export interface CustomerRequirement {
  id: string;
  customer_id: string;
  customer_name?: string | null;
  outlet_code?: string | null;
  visit_id?: string | null;
  brand?: string | null;
  requirement_type?: string | null;
  product_details?: string | null;
  quantity?: number | null;
  expected_value?: number | null;
  total_requested_value?: number | null;
  total_approved_value?: number | null;
  follow_up_date?: string | null;
  notes?: string | null;
  photo_storage_key?: string | null;
  photo_media_id?: string | null;
  photo_url?: string | null;
  approved_quantity?: number | null;
  approved_value?: number | null;
  admin_notes?: string | null;
  decided_by?: string | null;
  decider_name?: string | null;
  decided_at?: string | null;
  status: RequirementStatus | string;
  created_by: string;
  creator_name?: string | null;
  employee_id?: string | null;
  employee_name?: string | null;
  created_at: string;
  updated_at: string;
  items: RequirementItem[];
}

export interface RequirementDecisionRequest {
  action: 'APPROVE' | 'PARTIALLY_APPROVE' | 'REJECT' | 'CONVERT_TO_ORDER';
  approved_quantity?: number | null;
  approved_value?: number | null;
  admin_notes?: string | null;
  items?: RequirementItemDecisionUpdate[] | null;
}

export interface RequirementConfirmOrderRequest {
  admin_notes?: string | null;
  items?: RequirementItemDecisionUpdate[] | null;
}

export interface CustomerProspectCreate {
  name: string;
  contact_number: string;
  contact_person?: string | null;
  gst_number?: string | null;
  address?: string;
  territory_id?: string | null;
  area_id?: string | null;
  outlet_code?: string | null;
  brands?: string[];
  requirement?: {
    brand?: string;
    requirement_type?: string;
    product_details?: string;
    quantity?: number;
    expected_value?: number;
    follow_up_date?: string;
    notes?: string;
  } | null;
  location?: { latitude: number; longitude: number } | null;
  gps_accuracy_meters?: number | null;
  notes?: string | null;
  force?: boolean;
}

/** Response of `GET /api/v1/customers`. */
export interface Customer {
  id: string;
  name: string;
  contact_number: string;
  /** FT-013: separate human contact, distinct from the phone number. */
  contact_person: string | null;
  gst_number?: string | null;
  address: string;
  /** FT-012: the geofence centre, optional/nullable for bulk imported records. */
  location: GeoPoint | null;
  geofence_radius_m: number;
  location_status?: LocationStatus;
  /** Zone. */
  territory_id: string | null;
  territory_name?: string | null;
  /** Zone -> Area -> Outlet. Once set, Area is the source of truth for the Zone (territory_id is kept in sync server-side, never independently editable once an Area is assigned). */
  area_id: string | null;
  area_name: string | null;
  /** External-system cross-reference (DMS Code / External MIS anchor). */
  outlet_code: string | null;
  dms_code?: string | null;
  assigned_fos_names?: string[];
  brands?: string[];
  created_by: string;
  created_at: string;
  /** True only for an outlet approved from a CustomerProspect submission - there is no
   * Tally writeback for customers, so an admin must add it to Tally by hand. */
  needs_tally_entry?: boolean;
  /** Live outlet proof (additive, filled by the backend). */
  primary_outlet_image_available?: boolean;
  primary_outlet_proof_id?: string | null;
  outlet_proof_count?: number;
  outlet_location_confirmations?: number;
  /** 2.1.0: number of Tally debtor ledgers linked to this physical outlet. */
  ledger_count?: number;
  /** 2.1.0: Tally codes of every linked ledger (search matches any of them). */
  tally_codes?: string[];
  /** 2.1.0: set when this outlet was merged into another one (hidden from lists). */
  merged_into_customer_id?: string | null;
  /** 2.1.0 (detail only): the Tally ledgers linked to this outlet. */
  ledgers?: LedgerRead[];
}

export type OutletProofKind = 'INITIAL' | 'CONFIRMATION' | 'CHANGE_REQUEST';
export type OutletProofStatus = 'UNATTACHED' | 'PENDING' | 'CONFIRMED' | 'APPROVED' | 'REJECTED' | 'SUPERSEDED';

/** One live outlet proof: a camera photo plus the GPS fix taken at the same click. */
export interface OutletProof {
  id: string;
  customer_id: string | null;
  prospect_id: string | null;
  kind: OutletProofKind;
  status: OutletProofStatus;
  is_primary: boolean;
  latitude: number;
  longitude: number;
  accuracy_m: number;
  captured_at: string;
  received_at: string;
  is_mock_location: boolean;
  device_info?: string | null;
  content_type?: string;
  size_bytes?: number;
  submitted_by: string;
  submitted_by_name?: string | null;
  distance_from_verified_m?: number | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  rejection_reason?: string | null;
  /** Short-lived signed URL (may be null). Prefer the authenticated image route. */
  image_url?: string | null;
  created_at: string;
  // admin extras
  customer_name?: string | null;
  customer_outlet_code?: string | null;
  territory_name?: string | null;
  area_name?: string | null;
  prospect_name?: string | null;
  customer_latitude?: number | null;
  customer_longitude?: number | null;
  nearby_pending_proofs?: number | null;
}

export type OutletProofStatusFilter = OutletProofStatus | 'ALL';

export type ProspectStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

export interface ProspectRequirement {
  brand?: string | null;
  requirement_type?: string | null;
  product_details?: string | null;
  quantity?: number | null;
  expected_value?: number | null;
  follow_up_date?: string | null;
  notes?: string | null;
}

/** A new outlet submitted by a field employee, held for admin review before it becomes a
 * real Customer - see POST /api/v1/customers/prospects/{id}/approve. */
export interface CustomerProspect {
  id: string;
  status: ProspectStatus;
  name: string;
  contact_number: string;
  contact_person: string | null;
  gst_number: string | null;
  address: string;
  outlet_code: string | null;
  territory_id: string | null;
  area_id: string | null;
  territory_name?: string | null;
  area_name?: string | null;
  brands: string[];
  requirement: ProspectRequirement | null;
  location: GeoPoint | null;
  gps_accuracy_meters?: number | null;
  location_notes?: string | null;
  submitted_by: string;
  submitted_by_name?: string | null;
  submitted_at: string;
  reviewed_by?: string | null;
  reviewed_by_name?: string | null;
  reviewed_at?: string | null;
  rejection_reason?: string | null;
  resulting_customer_id?: string | null;
}

export interface CustomerProspectUpdate {
  name?: string;
  contact_number?: string;
  contact_person?: string | null;
  gst_number?: string | null;
  address?: string;
  outlet_code?: string | null;
  territory_id?: string | null;
  area_id?: string | null;
  brands?: string[];
  requirement?: ProspectRequirement | null;
  proposed_latitude?: number;
  proposed_longitude?: number;
}

export interface CustomerProspectSubmitResponse {
  status: 'CREATED' | 'PENDING_APPROVAL';
  message: string;
  customer: Customer | null;
  prospect_id: string | null;
}

export interface CustomerMapLocation {
  id: string;
  name: string;
  outlet_code: string | null;
  address?: string | null;
  contact_person?: string | null;
  contact_number?: string | null;
  latitude: number;
  longitude: number;
  geofence_radius_m: number;
  location_status: string;
  territory_id: string | null;
  area_id: string | null;
}

export type TerritoryStatus = 'ACTIVE' | 'INACTIVE';

/** Response of `GET /api/v1/territories` - the Zone level of the Zone -> Area -> Outlet hierarchy. */
export interface Territory {
  id: string;
  name: string;
  center_latitude?: number | null;
  center_longitude?: number | null;
  radius_km?: number | null;
  status?: TerritoryStatus;
  created_at: string;
  updated_at?: string | null;
}

/** Response of `GET /api/v1/areas` - the geographic layer between a Zone (Territory) and an Outlet (Customer). */
export interface Area {
  id: string;
  name: string;
  territory_id: string;
  territory_name: string | null;
  created_at: string;
  updated_at?: string | null;
}

/**
 * An employee's coverage of one Area - many-to-many, brand-agnostic. One
 * employee can cover several Areas across several Zones; this is additive
 * to (not a replacement for) the older single-Zone
 * Employee.territory_id/TerritoryAssignmentHistory model.
 */
export interface EmployeeAreaAssignment {
  id: string;
  employee_id: string;
  area_id: string;
  area_name: string;
  territory_id: string;
  territory_name: string;
  created_at: string;
}

export type VisitStatus = 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'FLAGGED' | 'MISSED';
export type VisitType = 'PLANNED' | 'AD_HOC';

export type AdHocReason =
  | 'Payment Follow-up'
  | 'Cheque Bounce'
  | 'Customer Requested'
  | 'Urgent Collection'
  | 'New Business Opportunity'
  | 'Other';

/** Response of `GET /api/v1/visits`. */
export interface Visit {
  id: string;
  customer_id: string;
  employee_id: string;
  scheduled_at: string;
  status: VisitStatus;
  visit_type: VisitType;
  adhoc_reason?: string | null;
  adhoc_notes?: string | null;
  check_in_at: string | null;
  check_in_received_at?: string | null;
  check_out_at: string | null;
  check_out_received_at?: string | null;
  synced: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
  /** Denormalised labels supplied by the API for list rendering. */
  customer_name?: string | null;
  customer_address?: string | null;
  employee_name?: string | null;
  area_name?: string | null;
  territory_name?: string | null;
  geo_failure_count?: number;
  /** Always present (derived from visit_type). */
  is_adhoc?: boolean;
  /** ADMIN only - null/absent for employees. */
  outside_assignment?: boolean | null;
  /** ADMIN only - 'AD-HOC' | 'AD-HOC · OUTSIDE ASSIGNMENT' | null. */
  review_label?: string | null;
  customer_outlet_code?: string | null;
  /** The form template an employee must fill for this visit, if any. */
  required_form_id: string | null;
  required_form_name: string | null;
  required_form_status: FormStatus | null;
}

/** Response of `GET /api/v1/visits/{id}/geo-logs`. */
export interface GeoVerificationLog {
  id: string;
  visit_id: string;
  verification_type: 'CHECK_IN' | 'CHECK_OUT';
  attempted_at: string;
  latitude: number | null;
  longitude: number | null;
  distance_from_customer_m: number;
  is_valid: boolean;
  failure_reason: string | null;
  idempotency_key: string | null;
}

export type MediaType = 'PHOTO' | 'DOCUMENT' | 'ORDER';

/** Response of `GET /api/v1/visits/{id}/media`. */
export interface VisitMedia {
  id: string;
  visit_id: string;
  /** FT-015: an enum, not a MIME type. */
  media_type: MediaType;
  storage_key: string;
  file_size_bytes: number;
  original_filename?: string | null;
  /** Only meaningful for ORDER media - the optional order note/summary. */
  note?: string | null;
  uploaded_at: string;
}

// -- P1: Collections / Invoices / Payments ----------------------------------

export type InvoiceSource = 'MANUAL' | 'EXCEL_IMPORT' | 'TALLY';
export type PaymentStatusLabel = 'UNPAID' | 'PARTIALLY_PAID' | 'PAID';
export type AgingStatus = 'NORMAL' | 'WARNING' | 'OVERDUE' | 'PAID';
export type MisBucket = '0-15' | '16-30' | '31-60' | '61-90' | '90+';
/** UNSPECIFIED: a Tally receipt whose voucher states no mode (never chosen for a field collection). */
export type PaymentMethod = 'CASH' | 'CHEQUE' | 'ONLINE' | 'UNSPECIFIED';
export type PaymentStatus = 'PENDING_VERIFICATION' | 'VERIFIED' | 'REJECTED';

/** `GET /api/v1/integrations/tally/reconciliation` (admin): FieldTrack vs Tally per debtor. */
export interface TallyReconciliationDifference {
  customer_id: string;
  name: string;
  outlet_code: string | null;
  opening: string;
  invoiced: string;
  adjustments: string;
  received: string;
  closing: string;
  difference: string;
  closing_at: string | null;
}

export interface TallyReconciliation {
  totals: Record<'opening' | 'invoiced' | 'adjustments' | 'received' | 'closing' | 'open_bills' | 'difference', string>;
  counts: { debtors: number; invoices: number; receipts: number; adjustments: number; open_bills: number };
  debtors_reconciled: number;
  debtors_with_difference: number;
  differences: TallyReconciliationDifference[];
  unallocated_total: string;
  retired: { kind: string; reason: string | null; count: number; amount: string }[];
  field_collections_linked_to_retired_receipt: number;
  non_debtor_customers: number;
  latest_snapshots: Record<string, string | number | null>[];
}

export interface TallyIntegrationStatus {
  is_connected: boolean;
  agent_status: 'ONLINE' | 'OFFLINE' | 'NOT_CONFIGURED';
  tally_status?: 'ONLINE' | 'OFFLINE';
  agent_id?: string | null;
  agent_name?: string | null;
  agent_version?: string | null;
  tally_company_name?: string | null;
  tally_company_guid?: string | null;
  last_heartbeat_at?: string | null;
  last_sync_at?: string | null;
  last_successful_sync_at?: string | null;
  today_read_count?: number;
  today_write_count?: number;
  failed_operation_count?: number;
  total_invoices_synced: number;
  total_payments_synced: number;
  total_customers_synced: number;
  message?: string | null;
  /** 2.1.0: agent health from the latest heartbeat (null for older agents). */
  health?: AgentHealth | null;
  health_reported_at?: string | null;
  sync_state?: SyncState;
}

export interface TallyAuditLogItem {
  id: string;
  timestamp: string;
  direction: 'READ' | 'WRITE';
  operation: string;
  entity_type: string;
  record_count: number;
  status: 'SUCCESS' | 'FAILED' | 'PARTIAL' | 'PROCESSING' | 'PENDING';
  duration_ms?: number | null;
  error_message?: string | null;
  agent_id?: string | null;
  agent_name?: string | null;
  company_name?: string | null;
  company_guid?: string | null;
  tally_guid?: string | null;
  tally_voucher_number?: string | null;
  writeback_job_id?: string | null;
  details?: Record<string, unknown> | null;
}

export interface TallyAuditLogsResponse {
  items: TallyAuditLogItem[];
  total: number;
  skip: number;
  limit: number;
}

export interface TallyAuditLogFilterParams {
  direction?: 'READ' | 'WRITE';
  status?: string;
  entity_type?: string;
  start_date?: string;
  end_date?: string;
  sort_order?: 'desc' | 'asc';
  skip?: number;
  limit?: number;
}

/** Response of `GET /api/v1/customers/{id}/invoices` and `POST /api/v1/invoices`. */
export interface Invoice {
  id: string;
  customer_id: string;
  /** 2.1.0: the original Tally ledger of this invoice (null for non-Tally rows). */
  tally_debtor_ledger_id?: string | null;
  tally_ledger_name?: string | null;
  invoice_number: string;
  invoice_date: string;
  due_date: string | null;
  amount: string;
  brand: string | null;
  source: InvoiceSource;
  source_reference: string | null;
  created_by: string;
  created_at: string;
  // Computed aging - always from the backend, never recomputed here.
  /** POSTED-to-Tally only (or Tally-sourced). */
  verified_paid_amount: string;
  /** Verified by admin but not yet posted to Tally; does not reduce remaining. */
  verified_awaiting_tally_amount?: string;
  remaining_amount: string;
  days_outstanding: number;
  payment_status: PaymentStatusLabel;
  aging_status: AgingStatus;
  mis_bucket: MisBucket;
}

export interface PaymentProof {
  id: string;
  payment_id: string;
  storage_key: string;
  file_size_bytes: number;
  original_filename: string | null;
  uploaded_by: string | null;
  uploaded_at: string;
}

export interface PaymentBrandAllocation {
  id: string;
  payment_id: string;
  brand: string;
  allocated_amount: string;
  created_at: string;
}

export interface BrandAllocationInput {
  brand: string;
  /** Exact 2-decimal string (e.g. "1250.50"); the backend parses it as Decimal. */
  amount: string;
}

export type TallyStatus = 'NOT_APPLICABLE' | 'AWAITING_TALLY' | 'POSTED' | 'FAILED';

/** Body of the optional bank-verification record on `POST /payments/{id}/verify`. */
export interface PaymentVerifyInput {
  bank_reference?: string | null;
  bank_verified_on?: string | null;
  verified_note?: string | null;
}

/** Response of `GET/POST /api/v1/payments*` (the "Collection"). */
export interface Payment {
  id: string;
  /** 2.1.0: the original Tally ledger of this receipt (null for field collections). */
  tally_debtor_ledger_id?: string | null;
  tally_ledger_name?: string | null;
  visit_id: string;
  customer_id: string;
  employee_id: string;
  invoice_id: string | null;
  amount: string;
  payment_method: PaymentMethod;
  payment_date: string;
  cheque_number: string | null;
  cheque_bank_name: string | null;
  utr_reference: string | null;
  notes: string | null;
  /** Tally receipt details exactly as the voucher states them. */
  tally_voucher_type?: string | null;
  tally_transaction_type?: string | null;
  narration?: string | null;
  status: PaymentStatus;
  rejection_reason: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_by: string;
  created_at: string;
  proofs: PaymentProof[];
  allocations?: PaymentBrandAllocation[];
  tally_status?: TallyStatus;
  tally_voucher_number?: string | null;
  tally_posted_at?: string | null;
  /** ADMIN only. */
  tally_error?: string | null;
  /** ADMIN only: FAILED, or AWAITING_TALLY for 30+ minutes. */
  tally_stuck?: boolean | null;
  /** ADMIN only. */
  bank_reference?: string | null;
  bank_verified_on?: string | null;
  verified_note?: string | null;
  customer_name?: string | null;
  outlet_code?: string | null;
  employee_name?: string | null;
  territory_name?: string | null;
}

/** Backend ageing split of total_outstanding; the five buckets sum to it. */
export interface AgeingBreakdown {
  normal: string;
  warning: string;
  overdue: string;
  baseline_current: string;
  baseline_overdue: string;
}

/**
 * Shared money-position fields (additive; optional so an older backend that
 * omits them still type-checks). Identity:
 * opening_balance + total_invoiced - paid_in_tally == total_outstanding.
 */
export interface PositionFields {
  opening_balance?: string;
  baseline_invoiced?: string;
  baseline_collected?: string;
  paid_in_tally?: string;
  advance_credit?: string;
  ageing?: AgeingBreakdown;
  reconciles?: boolean;
  /** Net Tally credit/debit notes, journals etc. (+ increases what is owed). */
  adjustments?: string;
  /** TALLY: outstanding = Tally's own open bills + unallocated ledger balance. */
  balance_source?: 'TALLY' | 'BASELINE';
  balance_as_of?: string | null;
  tally_opening_balance?: string | null;
  tally_closing_balance?: string | null;
  /** Tally opening + invoiced + adjustments - paid - Tally closing; must be 0.00. */
  tally_difference?: string | null;
}

export interface BrandSummary extends PositionFields {
  brand: string;
  total_invoiced: string;
  total_paid: string;
  verified_awaiting_tally_amount?: string;
  total_outstanding: string;
  overdue_amount: string;
  invoice_count: number;
  payment_count: number;
  latest_invoice_date: string | null;
  latest_payment_date: string | null;
}

/** Response of `GET /api/v1/customers/{id}/account` - the Outlet Account panel. */
export interface AccountSummary extends PositionFields {
  customer_id: string;
  customer_name: string;
  outlet_code: string | null;
  total_invoiced: string;
  total_paid: string;
  verified_awaiting_tally_amount?: string;
  total_outstanding: string;
  overdue_amount: string;
  max_days_outstanding: number;
  collection_status: AgingStatus;
  most_recent_payment: Payment | null;
  /** The most recent visit that actually happened (has a check-in) - null if this outlet has never had one. */
  most_recent_visit_date: string | null;
  most_recent_visit_employee_name: string | null;
  recent_invoices: Invoice[];
  recent_payments: Payment[];
  brand_summary: BrandSummary[];
  aging_buckets?: Record<string, string>;
  /** 2.1.0: per Tally ledger position (outlet totals = sum of ledgers). */
  ledgers?: LedgerPosition[];
}

/** One row of `GET /api/v1/collections/overview` - the outlet-list financial overview (Meeting 2). */
export interface OutletCollectionRow extends PositionFields {
  customer_id: string;
  outlet_code: string | null;
  customer_name: string;
  territory_id: string | null;
  territory_name: string | null;
  area_id: string | null;
  area_name: string | null;
  /**
   * Every employee currently assigned to cover this outlet's Area
   * (brand-agnostic many-to-many - genuinely zero, one, or several, never
   * assumed to be exactly one). Falls back to the legacy single-Zone
   * derivation only for an outlet with no Area assigned yet.
   */
  assigned_employees: { id: string; name: string }[];

  total_invoiced: string;
  total_paid: string;
  verified_awaiting_tally_amount?: string;
  total_outstanding: string;
  overdue_amount: string;
  max_days_outstanding: number;
  collection_status: AgingStatus;

  relevant_mis_bucket: MisBucket | null;
  relevant_bucket_amount: string;

  most_recent_payment_date: string | null;
  most_recent_payment_amount: string | null;
  most_recent_payment_employee_name: string | null;
  most_recent_visit_date: string | null;
  most_recent_visit_employee_name: string | null;
  /** Only when a date range was requested: live invoices by invoice date in the range. */
  invoiced_in_period?: string | null;
  /** Only when a date range was requested: payments POSTED to Tally by payment date in the range. */
  collected_in_period?: string | null;
}

export interface CollectionsOverviewTotals extends PositionFields {
  total_outlets: number;
  total_invoiced: string;
  total_paid: string;
  verified_awaiting_tally_amount?: string;
  total_outstanding: string;
  overdue_amount?: string;
  current_amount: string;
  bucket_0_15: string;
  bucket_16_30: string;
  bucket_31_60: string;
  bucket_61_90: string;
  bucket_90_plus: string;
  invoiced_in_period?: string | null;
  collected_in_period?: string | null;
}

/** Response of `GET /api/v1/collections/overview`. */
export interface CollectionsOverviewResponse {
  totals: CollectionsOverviewTotals;
  outlets: OutletCollectionRow[];
  total_count: number;
  skip: number;
  limit: number;
  /** Echo of the applied date range (inclusive IST dates). */
  period_start?: string | null;
  period_end?: string | null;
  /** Outstanding / overdue / ageing are always as of this date (today), never the range. */
  as_of_date?: string | null;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export type SignatureType = 'EMPLOYEE' | 'CUSTOMER';
export type SignatureCaptureMethod = 'SIGNATURE' | 'PHOTO_UPLOAD';

export interface VisitSignature {
  id: string;
  visit_id: string;
  signature_type: SignatureType;
  capture_method: SignatureCaptureMethod;
  storage_key: string;
  content_type: string | null;
  file_size_bytes: number | null;
  created_by: string | null;
  signed_at: string;
  superseded_at: string | null;
}

export interface SignatureDownloadResponse {
  download_url: string;
  expires_in_minutes: number;
}

// -- Form Template Builder ---------------------------------------------------
// Mirrors app/schemas/form_template.py exactly.

export type FormStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED';

export type QuestionType =
  | 'SHORT_TEXT'
  | 'LONG_TEXT'
  | 'MULTIPLE_CHOICE'
  | 'CHECKBOXES'
  | 'DROPDOWN'
  | 'YES_NO'
  | 'NUMBER'
  | 'DATE'
  | 'TIME'
  | 'DATE_TIME'
  | 'FILE_UPLOAD'
  | 'PHOTO_UPLOAD'
  | 'EMAIL'
  | 'PHONE'
  | 'URL'
  | 'RATING';

export type SubmissionStatus = 'DRAFT' | 'SUBMITTED' | 'IN_REVIEW' | 'APPROVED' | 'REJECTED';

export interface QuestionOption {
  id: string;
  question_id: string;
  label: string;
  value: string;
  display_order: number;
}

export interface FormQuestion {
  id: string;
  section_id: string;
  form_id: string;
  question_text: string;
  help_text: string | null;
  question_type: QuestionType;
  required: boolean;
  display_order: number;
  placeholder: string | null;
  validation_config: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  options: QuestionOption[];
}

export interface FormSection {
  id: string;
  form_id: string;
  title: string;
  description: string | null;
  display_order: number;
  created_at: string;
  updated_at: string;
  questions: FormQuestion[];
}

/** Response of `GET/POST/PATCH /api/v1/form-templates[/{id}]`. */
export interface FormTemplate {
  id: string;
  name: string;
  description: string | null;
  category_id: string | null;
  status: FormStatus;
  version: number;
  created_by: string;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  archived_at: string | null;
  sections: FormSection[];
  category_name: string | null;
  question_count: number;
}

/** Response of `GET /api/v1/form-templates` (list view - lighter than FormTemplate). */
export interface FormTemplateSummary {
  id: string;
  name: string;
  description: string | null;
  category_id: string | null;
  status: FormStatus;
  version: number;
  created_by: string;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  category_name: string | null;
  question_count: number;
  submission_count: number;
  /** How many visits currently require this template. */
  visit_count: number;
}

/** Response of `GET /api/v1/form-templates/{id}/render` - what an employee fills in. */
export interface FormRender {
  id: string;
  name: string;
  description: string | null;
  version: number;
  status: FormStatus;
  sections: FormSection[];
}

export interface FormAnswer {
  id: string;
  submission_id: string;
  question_id: string;
  answer_value: string | null;
  created_at: string;
  updated_at: string;
  question_text: string | null;
  question_type: QuestionType | null;
  options: QuestionOption[];
}

/** Response of `POST /api/v1/form-submissions` and `.../submit`. */
export interface FormSubmission {
  id: string;
  form_id: string;
  form_version: number;
  visit_id: string;
  submitted_by: string;
  status: SubmissionStatus;
  started_at: string;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
  form_name: string | null;
  employee_name: string | null;
  customer_name: string | null;
  outlet_code: string | null;
  visit_scheduled_at: string | null;
  answers: FormAnswer[];
}

/** Response of `GET /api/v1/form-submissions/{id}` - full admin review payload. */
export interface FormSubmissionDetail {
  id: string;
  form_id: string;
  form_name: string;
  form_version: number;
  visit_id: string;
  submitted_by: string;
  employee_name: string | null;
  customer_name: string | null;
  outlet_code: string | null;
  territory_name: string | null;
  visit_scheduled_at: string | null;
  status: SubmissionStatus;
  started_at: string;
  submitted_at: string | null;
  answers: FormAnswer[];
  sections: FormSection[];
}

// -- Excel/MIS Import ---------------------------------------------------------
// Mirrors app/schemas/import_batch.py and app/services/import_service.py exactly.

export type ImportStatus = 'PENDING' | 'VALIDATED' | 'COMMITTED' | 'FAILED';
export type OutletMatchStrategy = 'outlet_code' | 'name_and_territory';

/** One entry of `GET /api/v1/imports/target-fields`. */
export interface ImportTargetFieldConfig {
  label: string;
  required: boolean;
  aliases: string[];
}

/** Response of `POST /api/v1/imports/preview`. */
export interface ImportPreviewResponse {
  sheet_name: string;
  all_sheets: string[];
  columns: string[];
  sample_rows: string[][];
  total_data_rows: number;
  truncated: boolean;
  detected_type?: string;
  suggested_mapping: Record<string, string | null>;
  target_fields: Record<string, ImportTargetFieldConfig>;
  unmatched_fos_names?: string[];
  header_row_index?: number;
  is_confident?: boolean;
  matched_columns_count?: number;
  total_columns_count?: number;
  detected_entity_count?: number;
}

export interface ImportRowError {
  row: number;
  error: string;
  suggested_fix: string;
}

export interface ImportRowWarning {
  row: number;
  warning: string;
}

/** Shape of `ImportBatchRead.summary` - mirrors import_service.create_import_batch's summary dict. */
export interface ImportSummary {
  territories_created?: number;
  employees_matched?: number;
  employees_unresolved?: number;
  customers_created?: number;
  customers_updated?: number;
  invoices_created?: number;
  invoices_updated?: number;
  invoices_skipped_duplicate?: number;
  payments_created?: number;
  duplicate_outlet_codes_with_inconsistent_names?: { outlet_code: string; names_seen: string[] }[];
  warnings?: ImportRowWarning[];
  rows_with_warnings?: number;
  plan_rows?: ImportPlanRow[];
  detected_type?: string;
  unmatched_fos_names?: string[];
  total_rows?: number;
  valid_rows?: number;
  [key: string]: unknown;
}

/** One row of an import plan preview (employee master or outlet/market data). All values are strings from the sheet. */
export interface ImportPlanRow {
  employee_code?: string | null;
  full_name?: string | null;
  working_profile?: string | null;
  dms_code?: string | null;
  outlet_name?: string | null;
  zone_name?: string | null;
  area_name?: string | null;
  raw_fos_name?: string | null;
  market_outstanding?: string | null;
  bucket_gt_90?: string | null;
  [key: string]: string | null | undefined;
}

/** Response of `POST /api/v1/imports/validate`, `.../commit`, `GET /api/v1/imports[/{id}]`. */
export interface ImportBatchRead {
  id: string;
  filename: string;
  sheet_name: string;
  uploaded_by: string;
  uploaded_at: string;
  column_mapping: Record<string, string>;
  outlet_match_strategy: OutletMatchStrategy;
  status: ImportStatus;
  summary: ImportSummary | null;
  error_report: ImportRowError[] | null;
  rows_processed: number;
  rows_created: number;
  rows_updated: number;
  rows_skipped: number;
  rows_error: number;
  committed_at: string | null;
  committed_by: string | null;
  failure_reason: string | null;
  uploaded_by_email: string | null;
}

// -- P2-B: Order capture (visit media photos) ----------------------------------
// Mirrors app/schemas/media.py's OrderRead exactly.

/** Response of `GET /api/v1/customers/{id}/orders` - old visit photo/media orders. */
export interface VisitOrderPhotoRead {
  id: string;
  visit_id: string;
  media_type: MediaType;
  storage_key: string;
  file_size_bytes: number;
  checksum_sha256: string | null;
  original_filename: string | null;
  note: string | null;
  uploaded_by: string | null;
  uploaded_at: string;
  visit_scheduled_at: string | null;
  employee_name: string | null;
}

// -- Formal Customer Orders (Requirement → Order → Tally Sales Order) --------

export type OrderStatus =
  | 'PENDING_TALLY'
  | 'SENT_TO_TALLY'
  | 'TALLY_CONFIRMED'
  | 'TALLY_FAILED'
  | 'CANCELLED';

export interface OrderItem {
  id: string;
  order_id: string;
  brand_name: string;
  product_model: string;
  stock_item_name: string;
  quantity: number;
  unit: string;
  rate: number;
  amount: number;
  created_at: string;
}

/** Formal confirmed order — created from an approved CustomerRequirement. */
export interface Order {
  id: string;
  order_number: string;
  customer_id: string;
  customer_name?: string | null;
  outlet_code?: string | null;
  requirement_id?: string | null;
  visit_id?: string | null;
  employee_id?: string | null;
  employee_name?: string | null;
  total_amount: number;
  status: OrderStatus | string;
  tally_guid?: string | null;
  tally_master_id?: string | null;
  tally_voucher_number?: string | null;
  admin_notes?: string | null;
  created_by: string;
  creator_name?: string | null;
  created_at: string;
  updated_at: string;
  items: OrderItem[];
}

// -- P2-C: Employee Activity ----------------------------------------------------
// Mirrors app/schemas/employee_activity.py exactly.

export interface EmployeeActivityVisit {
  id: string;
  customer_id: string;
  customer_name: string;
  outlet_code: string | null;
  scheduled_at: string;
  check_in_at: string | null;
  check_out_at: string | null;
  duration_minutes: number | null;
  status: VisitStatus;
  visit_type?: VisitType;
  adhoc_reason?: string | null;
  adhoc_notes?: string | null;
  geo_failure_count: number;
}

export interface EmployeeActivityCollection {
  id: string;
  customer_id: string;
  customer_name: string | null;
  amount: string;
  payment_method: PaymentMethod;
  payment_date: string;
  status: PaymentStatus;
}

export interface EmployeeActivityOrder {
  id: string;
  visit_id: string;
  note: string | null;
  uploaded_at: string;
}

/** Response of `GET /api/v1/employees/{id}/activity`. */
export interface EmployeeActivity {
  employee_id: string;
  full_name: string;
  employee_code: string | null;
  territory_id: string | null;
  territory_name: string | null;
  is_active: boolean;

  visits_total: number;
  visits_planned?: number;
  visits_adhoc?: number;
  visits_completed: number;
  visits_missed: number;
  visits_flagged: number;
  visits: EmployeeActivityVisit[];

  collections_total: number;
  collections_pending: number;
  collections_verified: number;
  collections_rejected: number;
  collections_verified_amount: string;
  collections: EmployeeActivityCollection[];

  orders_total: number;
  orders: EmployeeActivityOrder[];
}

// -- P2-D: Territory Reassignment ------------------------------------------------
// Mirrors app/schemas/territory_assignment.py exactly.

export type AssignmentType = 'PERMANENT' | 'TEMPORARY';

export interface TerritoryAssignmentCreate {
  territory_id: string;
  assignment_type: AssignmentType;
  start_date: string;
  end_date?: string | null;
}

export interface TerritoryAssignmentRead {
  id: string;
  employee_id: string;
  territory_id: string;
  territory_name: string;
  assignment_type: AssignmentType;
  start_date: string;
  end_date: string | null;
  created_by: string;
  created_by_email: string | null;
  created_at: string;
  is_current: boolean;
}

/** Response of `GET /api/v1/employees/{id}/territory-assignments`. */
export interface TerritoryAssignmentHistory {
  employee_id: string;
  effective_territory_id: string | null;
  effective_territory_name: string | null;
  assignments: TerritoryAssignmentRead[];
}

// -- Real Business BI & Financial Snapshots ----------------------------------

export interface BusinessSummaryRow {
  brand: string;
  dimension_name: string;
  dms_code?: string | null;
  outlet_name?: string | null;
  zone_name?: string | null;
  area_name?: string | null;
  fos_name?: string | null;
  outlets_count: number;
  sales: string;
  collection: string;
  market_outstanding: string;
  bucket_lt_15: string;
  bucket_15_30: string;
  bucket_30_45: string;
  bucket_45_60: string;
  bucket_60_75: string;
  bucket_75_90: string;
  bucket_gt_90: string;
  /** Latest snapshot date of a raw outlet row's stock figures. */
  as_of_date?: string | null;
}

export interface BusinessBIDashboard {
  snapshot_date?: string | null;
  month_period?: string | null;
  /** SNAPSHOT (outlet financial snapshots) or LIVE_INVOICES (fallback when the period has no snapshot). */
  data_source?: 'SNAPSHOT' | 'LIVE_INVOICES';
  data_source_note?: string | null;
  /** Latest snapshot date backing the stock figures (market OS / ageing). */
  as_of_date?: string | null;
  period_start?: string | null;
  period_end?: string | null;
  period_source?: 'DATES' | 'MONTH' | 'ALL';
  month_ignored?: boolean;
  total_outlets: number;
  total_sales: string;
  total_collection: string;
  total_market_outstanding: string;
  total_overdue_gt_90: string;
  brand_summaries: BusinessSummaryRow[];
  zone_summaries: BusinessSummaryRow[];
  area_summaries: BusinessSummaryRow[];
  fos_summaries: BusinessSummaryRow[];
  raw_outlet_rows: BusinessSummaryRow[];
}

export interface FOSEmployeeMappingRead {
  id: string;
  raw_fos_name: string;
  employee_id: string;
  employee_name?: string | null;
  employee_code?: string | null;
  created_at: string;
}

export interface EmployeeReportRow {
  employee_id: string;
  employee_code?: string | null;
  employee_name: string;
  total_visits: number;
  completed_visits: number;
  pending_visits: number;
  missed_visits: number;
  flagged_visits: number;
  completion_rate: number;
}

export interface ProductivityDashboardData {
  total_employees: number;
  active_employees: number;
  total_visits_today: number;
  completed_visits_today: number;
  pending_visits_today: number;
  missed_visits_today: number;
  flagged_visits_today: number;
  avg_visits_per_employee: number;
}

export interface GeoReportRow {
  visit_id: string;
  employee_name: string;
  customer_name: string;
  dms_code?: string;
  attempted_at: string;
  verification_type: string;
  is_valid: boolean;
  distance_m: number;
  failure_reason: string | null;
}

export interface OverviewReportData {
  total_employees: number;
  total_outlets: number;
  total_sales: string;
  total_collection: string;
  total_market_outstanding: string;
  total_overdue_gt_90: string;
  total_visits: number;
  completed_visits: number;
  completion_rate: number;
  brand_breakdown: BusinessSummaryRow[];
  zone_breakdown: BusinessSummaryRow[];
  fos_breakdown: BusinessSummaryRow[];
}

export interface EmployeeMasterReportRow {
  employee_id: string;
  employee_code: string;
  full_name: string;
  email?: string;
  phone_number?: string;
  cug?: string;
  working_profile?: string;
  role: string;
  is_active: boolean;
  assigned_outlets_count: number;
  zone_names: string[];
}

export interface OutletReportRow {
  customer_id: string;
  dms_code?: string;
  outlet_name: string;
  contact_person?: string;
  contact_number?: string;
  address?: string;
  zone_name?: string;
  area_name?: string;
  fos_name?: string;
  brand?: string;
  latitude?: number | null;
  longitude?: number | null;
  geofence_radius_m: number;
  location_status: string;
  sales: string;
  collection: string;
  market_outstanding: string;
  overdue_gt_90: string;
  as_of_date?: string | null;
}

export interface OutstandingAgeingReportRow {
  customer_id: string;
  dms_code?: string;
  outlet_name: string;
  brand: string;
  zone_name?: string;
  area_name?: string;
  fos_name?: string;
  market_outstanding: string;
  bucket_lt_15: string;
  bucket_15_30: string;
  bucket_30_45: string;
  bucket_45_60: string;
  bucket_60_75: string;
  bucket_75_90: string;
  bucket_gt_90: string;
  highest_overdue_bucket: string;
  as_of_date?: string | null;
}

export interface CollectionReportRow {
  customer_id: string;
  dms_code?: string;
  outlet_name: string;
  brand: string;
  zone_name?: string;
  area_name?: string;
  fos_name?: string;
  collection_amount: string;
  sales_amount: string;
  snapshot_date: string;
}

export interface VisitDetailedReportRow {
  visit_id: string;
  scheduled_at: string;
  employee_name: string;
  customer_name: string;
  dms_code?: string;
  zone_name?: string;
  area_name?: string;
  status: string;
  check_in_at?: string | null;
  check_out_at?: string | null;
  duration_minutes?: number | null;
  is_gps_verified: boolean;
}

export interface MonthlyReportingPeriod {
  id: string;
  period_year: number;
  period_month: number;
  period_name: string;
  status: 'OPEN' | 'PENDING_CLOSE' | 'FINALIZED';
  snapshot_count: number;
  total_outlets: number;
  total_sales: string;
  total_collection: string;
  /** null when the month has no balance snapshot (see outstanding_available / outstanding_note). */
  total_market_os: string | null;
  total_overdue_gt_90: string | null;
  outstanding_available?: boolean;
  outstanding_note?: string | null;
  opened_at?: string | null;
  finalized_at?: string | null;
  finalized_by?: string | null;
  reopened_at?: string | null;
  reopened_by?: string | null;
  reopen_reason?: string | null;
  created_at: string;
  updated_at: string;
}

export interface MonthlyPeriodReviewSummary {
  period_id: string;
  period_year: number;
  period_month: number;
  period_name: string;
  status: 'OPEN' | 'PENDING_CLOSE' | 'FINALIZED';
  visits_completed: number;
  visits_adhoc: number;
  visits_total: number;
  collections_submitted_amount: string;
  collections_verified_amount: string;
  collections_pending_amount: string;
  collections_count: number;
  /** null when the month has no balance snapshot. */
  total_outstanding: string | null;
  outstanding_available?: boolean;
  total_invoices_count: number;
  total_outlets_count: number;
  can_finalize: boolean;
}

export type ExceptionType =
  | 'VEHICLE_BREAKDOWN'
  | 'GPS_UNAVAILABLE'
  | 'OUTLET_CLOSED'
  | 'CUSTOMER_UNAVAILABLE'
  | 'OTHER';

export type ExceptionStatus = 'PENDING_REVIEW' | 'APPROVED' | 'REJECTED';

export interface FieldException {
  id: string;
  visit_id: string | null;
  employee_id: string;
  employee_name: string | null;
  customer_id: string;
  customer_name: string | null;
  dms_code: string | null;
  exception_type: ExceptionType;
  description: string;
  status: ExceptionStatus;
  admin_notes: string | null;
  reviewed_by: string | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface FieldExceptionCreate {
  visit_id?: string | null;
  customer_id: string;
  exception_type: ExceptionType;
  description: string;
}

export interface FieldExceptionReview {
  status: ExceptionStatus;
  admin_notes?: string;
}

export interface DashboardExecutiveKPIs {
  total_outlets: number;
  total_sales: string;
  total_collection: string;
  total_collection_posted_in_tally?: string;
  total_collection_verified_awaiting_tally?: string;
  total_market_outstanding: string;
  total_overdue_gt_90: string;
  total_employees: number;
  total_visits: number;
  completed_visits: number;
  pending_visits: number;
  in_progress_visits?: number;
  flagged_visits: number;
  gps_verified_visits: number;
  total_exceptions: number;
  pending_exceptions: number;
  total_collections_count: number;
  total_orders_count: number;
}

export interface DashboardSummaryResponse {
  period: string;
  is_historical: boolean;
  /** True for a past financial year (before the reporting floor): read-only History, apart from live data. */
  is_history?: boolean;
  kpis: DashboardExecutiveKPIs;
  brand_breakdown: BusinessSummaryRow[];
  fos_breakdown: BusinessSummaryRow[];
  zone_breakdown: BusinessSummaryRow[];
  area_breakdown: BusinessSummaryRow[];
  ageing_distribution: Record<string, string>;
  recent_exceptions: FieldException[];
}

export interface DashboardHistoryMonth {
  value: string; // "2025-07"
  label: string; // "July 2025"
  invoices: number;
  payments: number;
}

export interface DashboardHistoryPeriod {
  value: string; // "FY2025-26"
  label: string; // "FY 2025-26"
  start: string;
  end: string;
  invoices: number;
  payments: number;
  months: DashboardHistoryMonth[];
}

export interface DashboardHistoryPeriodsResponse {
  reporting_floor: string;
  periods: DashboardHistoryPeriod[];
}

export interface EmployeeDayDashboardResponse {
  employee_id: string;
  employee_name: string;
  assigned_outlets_count: number;
  today_visits_count: number;
  completed_visits_count: number;
  pending_visits_count: number;
  in_progress_visits_count?: number;
  collections_today_count: number;
  collections_today_amount: string;
  orders_today_count: number;
}

export type WorkSessionStatus = 'NOT_STARTED' | 'STARTED' | 'COMPLETED';

export interface WorkSession {
  id: string;
  employee_id: string;
  work_date: string;
  status: WorkSessionStatus;
  start_time: string | null;
  start_latitude: number | null;
  start_longitude: number | null;
  start_accuracy_meters: number | null;
  end_time: string | null;
  end_latitude: number | null;
  end_longitude: number | null;
  end_accuracy_meters: number | null;
  start_notes: string | null;
  end_notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface DailyFieldActivitySummary {
  work_date: string;
  total_visits: number;
  planned_visits: number;
  adhoc_visits: number;
  completed_visits: number;
  missed_visits: number;
  flagged_visits: number;
  collections_count: number;
  collections_total_amount: string;
  collections_verified_amount: string;
}

export interface EmployeeWorkdayResponse {
  employee_id: string;
  employee_name: string | null;
  work_date: string;
  session: WorkSession | null;
  summary: DailyFieldActivitySummary;
}

export interface EmployeeWorkdaySessionItem {
  employee_id: string;
  employee_name: string;
  employee_code: string | null;
  work_date: string;
  status: WorkSessionStatus;
  start_time: string | null;
  end_time: string | null;
  start_latitude: number | null;
  start_longitude: number | null;
  start_accuracy_meters: number | null;
  end_latitude: number | null;
  end_longitude: number | null;
  end_accuracy_meters: number | null;
  visits_total: number;
  visits_planned: number;
  visits_adhoc: number;
  visits_completed: number;
  collections_amount: string;
}

export interface RequirementFollowUpItem {
  id: string;
  customer_id: string;
  customer_name: string;
  brand: string | null;
  product_details: string | null;
  expected_value: string | null;
  follow_up_date: string | null;
}

export interface TodayFieldActivityOverview {
  work_date: string;
  total_employees: number;
  employees_started: number;
  employees_completed: number;
  employees_active: number;
  employees_not_started: number;
  total_visits: number;
  planned_visits: number;
  adhoc_visits: number;
  completed_visits: number;
  total_collections_amount: string;
  collections_pending_verification: string;
  collections_verified: string;
  pending_location_proposals_count: number;
  pending_payments_count: number;
  recent_prospects_count: number;
  upcoming_follow_ups: RequirementFollowUpItem[];
  sessions: EmployeeWorkdaySessionItem[];
}

export interface OrganizationProfile {
  organization_name: string;
  operational_hub: string;
  divisions: string;
  contact_email: string;
  contact_phone: string;
  gstin: string;
  timezone: string;
  currency: string;
  total_employees: number;
  total_customers: number;
  total_territories: number;
  total_areas: number;
  master_brands: string[];
}

export interface Brand {
  id: string;
  name: string;
  normalized_name: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}
export interface RequirementForm {
  id: string;
  visit_id: string;
  category_id: string;
  category_name?: string | null;
  description: string;
  priority: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string;
  expected_timeline: string;
  budget_range?: string | null;
  notes?: string | null;
  submitted_at: string;
}

// -- Monthly Visit Planning Types (Phase 2) --------------------------------

export type Priority = 'LOW' | 'MEDIUM' | 'HIGH';
export type MonthlyPlanStatus = 'ACTIVE' | 'LOCKED';
export type PlannedVisitStatus = 'PLANNED' | 'CANCELLED' | 'COMPLETED' | 'MISSED';

export interface PlannedVisit {
  id: string;
  monthly_plan_id: string;
  employee_id: string;
  customer_id: string;
  planned_date: string; // YYYY-MM-DD
  visit_type: VisitType;
  priority: Priority;
  notes?: string | null;
  status: PlannedVisitStatus;
  created_at: string;
  updated_at: string;
  customer_name?: string | null;
  customer_outlet_code?: string | null;
  customer_address?: string | null;
  employee_name?: string | null;
  employee_code?: string | null;
  area_name?: string | null;
  territory_name?: string | null;
}

export interface MonthlyVisitPlan {
  id: string;
  employee_id: string;
  year: number;
  month: number;
  status: MonthlyPlanStatus;
  notes?: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  employee_name?: string | null;
  employee_code?: string | null;
  planned_visits: PlannedVisit[];
  total_planned_visits: number;
  active_days_count: number;
}

export interface MonthlyPlanSummary {
  id: string;
  employee_id: string;
  employee_name: string;
  employee_code?: string | null;
  year: number;
  month: number;
  status: MonthlyPlanStatus;
  total_planned_visits: number;
  active_days_count: number;
}

export interface TeamMonthlyPlan {
  year: number;
  month: number;
  total_planned_visits: number;
  active_days_count: number;
  active_employees_count: number;
  planned_visits: PlannedVisit[];
}

// -- Planning Analytics Types (Phase 2D) -----------------------------------

export interface EmployeeMonthlyAnalytics {
  employee_id: string;
  employee_name: string;
  employee_code?: string | null;
  year: number;
  month: number;
  total_planned: number;
  completed: number;
  missed: number;
  cancelled: number;
  extra_unplanned: number;
  completion_rate: number | null;
  active_planned_days: number;
  active_execution_days: number;
  avg_planned_per_active_day: number | null;
  avg_completed_per_execution_day: number | null;
  behind_schedule: boolean;
}

export interface DailyAnalytics {
  date: string;
  employee_id: string;
  employee_name: string;
  planned: number;
  completed: number;
  missed: number;
  extra_unplanned: number;
}

export interface TeamMonthlyAnalytics {
  year: number;
  month: number;
  employees: EmployeeMonthlyAnalytics[];
  team_total_planned: number;
  team_completed: number;
  team_missed: number;
  team_cancelled: number;
  team_extra: number;
  team_completion_rate: number | null;
}

// -- Planning Warnings & Notifications (Phase 2E) ----------------------------

export type NotificationType =
  | 'NEW_VISIT'
  | 'RESCHEDULED'
  | 'CANCELLED'
  | 'REMINDER'
  | 'OVERDUE'
  | 'COMPLETED'
  | 'GEO_FAILURE_ALERT'
  | 'GEO_ALERT'
  | 'PLANNED_VISIT_MISSED'
  | 'EMPLOYEE_SCHEDULE_CHANGED'
  | 'PLANNED_VISIT_CANCELLED';

export interface NotificationItem {
  id: string;
  user_id: string;
  visit_id?: string | null;
  planned_visit_id?: string | null;
  payment_id?: string | null;
  type: NotificationType;
  title?: string | null;
  message: string;
  is_read: boolean;
  sent_at: string;
}



// ---------------------------------------------------------------------------
// 2.1.0: physical outlet <-> Tally debtor ledgers, account history, mapping, sync health
// (contract: release_v2/final_agent/CONTRACTS_2.1.0.md C3-C5)
// ---------------------------------------------------------------------------

export type LedgerMappingStatus = 'AUTO_1TO1' | 'NEW_UNREVIEWED' | 'CONFIRMED' | 'REVIEW';
export type LedgerBrandSource = 'TALLY' | 'OVERRIDE' | 'NONE';

/** One Tally debtor ledger linked to a physical outlet. Balances in receivable sign (+ = owed). */
export interface LedgerRead {
  id: string;
  tally_guid: string;
  name: string;
  parent_group: string | null;
  tally_outlet_code: string | null;
  brand: string | null;
  brand_source: LedgerBrandSource;
  is_primary: boolean;
  is_debtor: boolean | null;
  mapping_status: LedgerMappingStatus;
  opening_balance: string | null;
  closing_balance: string | null;
  closing_balance_at: string | null;
  gst_number: string | null;
  mobile: string | null;
  pincode: string | null;
}

/** Queue entries carry the outlet the ledger currently belongs to. */
/** A Tally ledger in an Outlet Mapping queue, with the outlet (physical shop) it currently belongs to. */
export interface LedgerQueueItem extends LedgerRead {
  customer_id: string;
  outlet_name?: string | null;
  outlet_address?: string | null;
  outlet_code?: string | null;
  area_name?: string | null;
  territory_name?: string | null;
}

/** One ledger of an outlet in the Missing outlet code queue. */
export interface OutletQueueLedger {
  id: string;
  name: string;
  brand: string | null;
  brand_source: string;
  parent_group: string | null;
  tally_outlet_code: string | null;
  gst_number: string | null;
  mobile: string | null;
  pincode: string | null;
  is_primary: boolean;
}

/** An OUTLET without an outlet code (the code is stored on the outlet, not on a ledger). */
export interface OutletCodeQueueItem {
  customer_id: string;
  outlet_name: string;
  outlet_address: string | null;
  outlet_code: string | null;
  area_name: string | null;
  territory_name: string | null;
  ledgers: OutletQueueLedger[];
}

/** Per-ledger position inside an outlet's account (receivable sign). */
export interface LedgerPosition {
  ledger_id: string;
  tally_guid: string;
  name: string;
  brand: string | null;
  tally_outlet_code: string | null;
  opening_balance: string | null;
  closing_balance: string | null;
  invoiced: string;
  paid_in_tally: string;
  adjustments: string;
  outstanding: string;
  open_bills_total: string;
  unallocated: string;
  tally_difference: string | null;
  reconciles: boolean;
}

export type AccountHistoryKind = 'INVOICE' | 'PAYMENT' | 'ADJUSTMENT';

export interface AccountHistoryItem {
  date: string;
  kind: AccountHistoryKind;
  voucher_type: string | null;
  voucher_number: string | null;
  amount: string;
  brand: string | null;
  ledger_id: string | null;
  ledger_name: string | null;
  bill_name: string | null;
  narration: string | null;
  retired: boolean;
  retired_reason: string | null;
}

export interface AccountHistoryResponse {
  items: AccountHistoryItem[];
  total: number;
}

export type LinkEventAction =
  | 'LINK' | 'UNLINK' | 'SET_PRIMARY' | 'BRAND_OVERRIDE' | 'OUTLET_CODE' | 'RENAME' | 'BULK_APPLY' | 'BULK_REVERT' | 'REVIEW';

export interface LinkEventRead {
  id: string;
  action: LinkEventAction;
  ledger_id: string | null;
  ledger_name: string | null;
  from_customer_id: string | null;
  to_customer_id: string | null;
  batch_id: string | null;
  actor: string | null;
  note: string | null;
  created_at: string;
}

export interface OutletMappingQueues {
  new_unreviewed: LedgerQueueItem[];
  missing_brand: LedgerQueueItem[];
  missing_code: OutletCodeQueueItem[];
  linked_outlets: number;
}

export interface ImportPreviewLink {
  ledger_id: string;
  ledger_name: string;
  from_customer_id: string;
  to_outlet_id_label: string;
  to_customer_id: string | null;
}

export interface ImportPreviewIssue {
  row: number;
  tally_id: string | null;
  message: string;
}

export interface ImportPreview {
  preview_id: string;
  expires_at: string;
  rows: number;
  confirmed_rows: number;
  ignored_rows: number;
  links: ImportPreviewLink[];
  brand_updates: { ledger_id: string; brand: string }[];
  code_updates: { customer_id: string; outlet_code: string }[];
  errors: ImportPreviewIssue[];
  warnings: (ImportPreviewIssue | string)[];
  outlets_before: number;
  outlets_after: number;
  totals_before: { outstanding: string };
  totals_after: { outstanding: string };
  invariants_ok: boolean;
}

export interface ImportApplyResult {
  batch_id: string;
  applied: number;
  events: number;
}

export interface ImportRevertResult {
  batch_id: string;
  reverted: number;
}

export type SyncState = 'NOT_CONFIGURED' | 'OFFLINE' | 'TALLY_UNAVAILABLE' | 'SYNCING' | 'STALLED' | 'DEGRADED' | 'OK';
export type AgentPhase = 'IDLE' | 'CYCLE' | 'INITIAL_LOAD' | 'MANIFEST' | 'SNAPSHOT';

/** `_health` reported by Agent 2.1.0 in its heartbeat. */
export interface AgentHealth {
  instance?: string;
  agent_version?: string;
  phase?: AgentPhase;
  phase_detail?: string | null;
  cycle_started_at?: string | null;
  cycle_running_seconds?: number;
  last_cycle_completed_at?: string | null;
  last_cycle_status?: string | null;
  last_cycle_duration_seconds?: number | null;
  last_success?: Partial<Record<'vouchers' | 'masters' | 'ledgers' | 'bills' | 'manifest', string | null>>;
  retry_queue?: {
    pending: number;
    oldest_age_seconds: number | null;
    max_attempts: number;
    rejected_4xx: number;
    last_error: string | null;
  };
  quarantine?: { unresolved: number; oldest_guid: string | null };
  last_error?: { at: string; message: string } | null;
  interval_seconds?: number;
  error?: string;
}
