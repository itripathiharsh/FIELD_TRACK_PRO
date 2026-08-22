/**
 * API contract types.
 *
 * These mirror the FastAPI response schemas exactly. Fields that the backend
 * does not return must not appear here: the previous version declared invented
 * fields (FT-003, FT-012) which forced `as any` casts at call sites and made
 * several table columns render permanently blank.
 */

/**
 * FT-038: the backend Role enum has exactly two members. A third 'MANAGER'
 * role existed only in the frontend; selecting it produced a user the API
 * would never accept.
 */
export type UserRole = 'ADMIN' | 'EMPLOYEE';

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
}

/** Response of `GET /api/v1/employees` (employees.id, not users.id). */
export interface Employee {
  id: string;
  user_id: string;
  full_name: string;
  territory_id: string | null;
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
  };
}

/** Geographic point as exchanged with the API. */
export interface GeoPoint {
  latitude: number;
  longitude: number;
}

export type LocationStatus = 'VERIFIED' | 'NEEDS_REVIEW' | 'MISSING';

/** Response of `GET /api/v1/customers`. */
export interface Customer {
  id: string;
  name: string;
  contact_number: string;
  /** FT-013: separate human contact, distinct from the phone number. */
  contact_person: string | null;
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
  created_by: string;
  created_at: string;
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

/** Response of `GET /api/v1/visits`. */
export interface Visit {
  id: string;
  customer_id: string;
  employee_id: string;
  scheduled_at: string;
  status: VisitStatus;
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
export type PaymentMethod = 'CASH' | 'CHEQUE' | 'ONLINE';
export type PaymentStatus = 'PENDING_VERIFICATION' | 'VERIFIED' | 'REJECTED';

/** Response of `GET /api/v1/customers/{id}/invoices` and `POST /api/v1/invoices`. */
export interface Invoice {
  id: string;
  customer_id: string;
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
  verified_paid_amount: string;
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

/** Response of `GET/POST /api/v1/payments*` (the "Collection"). */
export interface Payment {
  id: string;
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
  status: PaymentStatus;
  rejection_reason: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_by: string;
  created_at: string;
  proofs: PaymentProof[];
  customer_name?: string | null;
  outlet_code?: string | null;
  employee_name?: string | null;
  territory_name?: string | null;
}

export interface BrandSummary {
  brand: string;
  total_invoiced: string;
  total_paid: string;
  total_outstanding: string;
  overdue_amount: string;
  invoice_count: number;
  payment_count: number;
  latest_invoice_date: string | null;
  latest_payment_date: string | null;
}

/** Response of `GET /api/v1/customers/{id}/account` - the Outlet Account panel. */
export interface AccountSummary {
  customer_id: string;
  customer_name: string;
  outlet_code: string | null;
  total_invoiced: string;
  total_paid: string;
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
}

/** One row of `GET /api/v1/collections/overview` - the outlet-list financial overview (Meeting 2). */
export interface OutletCollectionRow {
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
}

export interface CollectionsOverviewTotals {
  total_outlets: number;
  total_invoiced: string;
  total_paid: string;
  total_outstanding: string;
  current_amount: string;
  bucket_0_15: string;
  bucket_16_30: string;
  bucket_31_60: string;
  bucket_61_90: string;
  bucket_90_plus: string;
}

/** Response of `GET /api/v1/collections/overview`. */
export interface CollectionsOverviewResponse {
  totals: CollectionsOverviewTotals;
  outlets: OutletCollectionRow[];
  total_count: number;
  skip: number;
  limit: number;
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
  plan_rows?: any[];
  detected_type?: string;
  unmatched_fos_names?: string[];
  total_rows?: number;
  valid_rows?: number;
  [key: string]: any;
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

// -- P2-B: Order capture -------------------------------------------------------
// Mirrors app/schemas/media.py's OrderRead exactly.

/** Response of `GET /api/v1/customers/{id}/orders`. */
export interface OrderRead {
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
}

export interface BusinessBIDashboard {
  snapshot_date?: string | null;
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
  status: 'OPEN' | 'FINALIZED';
  snapshot_count: number;
  total_outlets: number;
  total_sales: string;
  total_collection: string;
  total_market_os: string;
  total_overdue_gt_90: string;
  finalized_at?: string | null;
  finalized_by?: string | null;
  created_at: string;
  updated_at: string;
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
  total_market_outstanding: string;
  total_overdue_gt_90: string;
  total_employees: number;
  total_visits: number;
  completed_visits: number;
  pending_visits: number;
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
  kpis: DashboardExecutiveKPIs;
  brand_breakdown: BusinessSummaryRow[];
  fos_breakdown: BusinessSummaryRow[];
  zone_breakdown: BusinessSummaryRow[];
  area_breakdown: BusinessSummaryRow[];
  ageing_distribution: Record<string, string>;
  recent_exceptions: FieldException[];
}

export interface EmployeeDayDashboardResponse {
  employee_id: string;
  employee_name: string;
  assigned_outlets_count: number;
  today_visits_count: number;
  completed_visits_count: number;
  pending_visits_count: number;
  collections_today_count: number;
  collections_today_amount: string;
  orders_today_count: number;
}


