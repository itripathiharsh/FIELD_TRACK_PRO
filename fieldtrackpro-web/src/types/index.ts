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
  created_at: string;
  /** Present on detail endpoints that embed the linked account. */
  user?: {
    id: string;
    email: string | null;
    mobile_number: string | null;
    role: UserRole;
  };
}

/** Geographic point as exchanged with the API. */
export interface GeoPoint {
  latitude: number;
  longitude: number;
}

/** Response of `GET /api/v1/customers`. */
export interface Customer {
  id: string;
  name: string;
  contact_number: string;
  /** FT-013: separate human contact, distinct from the phone number. */
  contact_person: string | null;
  address: string;
  /** FT-012: the geofence centre, required by the customers table. */
  location: GeoPoint;
  geofence_radius_m: number;
  territory_id: string | null;
  created_by: string;
  created_at: string;
}

/** Response of `GET /api/v1/territories`. */
export interface Territory {
  id: string;
  name: string;
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
  check_out_at: string | null;
  synced: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
  /** Denormalised labels supplied by the API for list rendering. */
  customer_name?: string | null;
  employee_name?: string | null;
  geo_failure_count?: number;
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

export type MediaType = 'PHOTO' | 'DOCUMENT';

/** Response of `GET /api/v1/visits/{id}/media`. */
export interface VisitMedia {
  id: string;
  visit_id: string;
  /** FT-015: an enum, not a MIME type. */
  media_type: MediaType;
  storage_key: string;
  file_size_bytes: number;
  uploaded_at: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}
