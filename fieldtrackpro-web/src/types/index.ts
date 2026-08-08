export type UserRole = 'ADMIN' | 'MANAGER' | 'EMPLOYEE';

export interface User {
  id: string;
  email: string | null;
  mobile: string | null;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  territory_id?: string | null;
}

export interface Customer {
  id: string;
  name: string;
  contact_person: string | null;
  phone: string | null;
  email: string | null;
  address: string;
  latitude: number;
  longitude: number;
  geofence_radius_m: number;
  is_active: boolean;
}

export interface Territory {
  id: string;
  name: string;
  code: string;
  description?: string;
  employee_count?: number;
  customer_count?: number;
}

export type VisitStatus = 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'FLAGGED' | 'MISSED';

export interface Visit {
  id: string;
  employee_id: string;
  customer_id: string;
  scheduled_start_time: string;
  scheduled_end_time: string;
  status: VisitStatus;
  purpose: string;
  notes?: string | null;
  actual_check_in_time?: string | null;
  actual_check_out_time?: string | null;
  verification_failure_count: number;
  customer_name?: string;
  customer_address?: string;
  employee_name?: string;
}

export interface GeoVerificationLog {
  id: string;
  visit_id: string;
  verification_type: 'CHECK_IN' | 'CHECK_OUT';
  latitude: number;
  longitude: number;
  distance_from_target_m: number | null;
  is_valid: boolean;
  failure_reason: string | null;
  created_at: string;
  customer_name?: string;
  employee_name?: string;
}

export interface VisitMedia {
  id: string;
  visit_id: string;
  media_type: string;
  storage_key: string;
  file_size_bytes: number;
  uploaded_at: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface DashboardMetrics {
  totalEmployees: number;
  activeCustomers: number;
  totalVisitsToday: number;
  completedVisitsToday: number;
  flaggedVisitsToday: number;
  geoComplianceRate: number;
}
