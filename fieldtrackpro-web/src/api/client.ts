import { ENV } from '../config/env';
import {
  Customer,
  Employee,
  GeoVerificationLog,
  LoginResponse,
  Territory,
  User,
  Visit,
  VisitMedia,
  VisitStatus,
} from '../types';

/**
 * FT-040: the access token is held in memory only.
 *
 * Security Design section 1 requires: "Web: access token in memory only (never
 * localStorage - XSS risk); refresh token in httpOnly, Secure, SameSite=Strict
 * cookie."
 *
 * The first half is implemented here: the short-lived access token never
 * touches persistent storage, so injected script cannot read it and it does not
 * survive the tab. The refresh token still uses localStorage, because moving it
 * to an httpOnly cookie requires backend cookie issuance plus CSRF protection
 * and would change the contract the Android client also depends on. That
 * remainder is tracked as FT-065 with the rationale in docs/REPAIR_DECISIONS.md
 * (RD-003) rather than being quietly dropped.
 */
const REFRESH_TOKEN_KEY = 'fieldtrack_refresh_token';

/**
 * Error carrying the HTTP status and the backend's error code, so callers can
 * distinguish "wrong password" from "server unreachable" and show the real
 * reason instead of a generic failure.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

export class ApiClient {
  private readonly baseUrl: string;

  /** In-memory access token. Deliberately never persisted (FT-040). */
  private accessToken: string | null = null;

  constructor() {
    // FT-055: one normalisation, applied once. VITE_API_BASE_URL may or may not
    // already include the /api/v1 suffix; every request path in this client is
    // absolute from the server root, so the suffix is stripped here and never
    // re-derived per call site.
    const raw = ENV.API_BASE_URL || 'http://127.0.0.1:8000';
    this.baseUrl = raw.replace(/\/api\/v1\/?$/, '').replace(/\/+$/, '');
  }

  /** Absolute URL for an API path. Used by callers that need a raw URL. */
  url(path: string): string {
    return `${this.baseUrl}${path.startsWith('/') ? path : `/${path}`}`;
  }

  // -- session storage -------------------------------------------------------

  getAccessToken(): string | null {
    return this.accessToken;
  }

  private getRefreshToken(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  }

  /**
   * True when a session may be restorable.
   *
   * After a page reload the in-memory access token is gone by design, so the
   * refresh token is what indicates a session worth re-establishing.
   */
  hasStoredSession(): boolean {
    return Boolean(this.accessToken || this.getRefreshToken());
  }

  private storeSession(tokens: LoginResponse): void {
    this.accessToken = tokens.access_token;
    localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  }

  clearSession(): void {
    this.accessToken = null;
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  }

  private authHeader(): Record<string, string> {
    const token = this.getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  // -- core request ----------------------------------------------------------

  private async parseError(response: Response): Promise<ApiError> {
    let message = response.statusText || `Request failed (${response.status})`;
    let code: string | undefined;
    try {
      const body = await response.json();
      // Backend error envelope: { error: { code, message } }
      if (body?.error?.message) {
        message = body.error.message;
        code = typeof body.error.code === 'string' ? body.error.code : undefined;
      } else if (typeof body?.detail === 'string') {
        message = body.detail;
      }
    } catch {
      // Non-JSON body; keep the status text.
    }
    return new ApiError(message, response.status, code);
  }

  /**
   * Perform a request, transparently refreshing the access token once on 401.
   *
   * FT-008: without this the 15-minute access token expiry ended the session
   * with no way back, because /auth/refresh was never called.
   */
  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    allowRefresh = true,
  ): Promise<T> {
    const isFormData = options.body instanceof FormData;
    const headers: Record<string, string> = {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...this.authHeader(),
      ...((options.headers as Record<string, string>) || {}),
    };

    let response: Response;
    try {
      response = await fetch(this.url(endpoint), { ...options, headers });
    } catch {
      // Network-level failure: distinguish clearly from an auth rejection.
      throw new ApiError(
        'Unable to reach the FieldTrack Pro API. Check your connection and try again.',
        0,
        'NETWORK_ERROR',
      );
    }

    if (response.status === 401 && allowRefresh && this.getRefreshToken()) {
      const refreshed = await this.tryRefresh();
      if (refreshed) {
        return this.request<T>(endpoint, options, false);
      }
    }

    if (!response.ok) {
      throw await this.parseError(response);
    }

    if (response.status === 204) {
      return undefined as T;
    }
    return response.json() as Promise<T>;
  }

  /** Exchange the refresh token for a new pair. Returns false if not possible. */
  private async tryRefresh(): Promise<boolean> {
    const refresh_token = this.getRefreshToken();
    if (!refresh_token) return false;
    try {
      const response = await fetch(this.url('/api/v1/auth/refresh'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token }),
      });
      if (!response.ok) {
        this.clearSession();
        return false;
      }
      this.storeSession((await response.json()) as LoginResponse);
      return true;
    } catch {
      return false;
    }
  }

  async getHealth(): Promise<{ status: string; service?: string }> {
    return this.request<{ status: string; service?: string }>('/health');
  }

  // -- authentication --------------------------------------------------------

  /**
   * Authenticate. Throws ApiError on failure - never returns a partial session.
   *
   * FT-010: the identity field is `mobile_number`, matching the backend schema.
   * The previous `mobile` key was silently discarded by pydantic, making mobile
   * login impossible for reasons invisible to the user.
   */
  async login(identity: string, password: string): Promise<LoginResponse> {
    const isEmail = identity.includes('@');
    const body = isEmail
      ? { email: identity, password }
      : { mobile_number: identity, password };

    const tokens = await this.request<LoginResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    this.storeSession(tokens);
    return tokens;
  }

  /**
   * Identity of the signed-in caller.
   *
   * FT-040: after a page reload there is no in-memory access token, so one is
   * minted from the refresh token first. If that fails the session is genuinely
   * over and the error propagates - no fabricated user is ever returned.
   */
  async getCurrentUser(): Promise<User> {
    if (!this.accessToken && this.getRefreshToken()) {
      const restored = await this.tryRefresh();
      if (!restored) {
        throw new ApiError('Session expired. Please sign in again.', 401, 'SESSION_EXPIRED');
      }
    }
    return this.request<User>('/api/v1/auth/me');
  }

  /**
   * End the session.
   *
   * FT-009: the refresh token is revoked server-side. Previously only local
   * storage was cleared, leaving the token usable for its full 7-day life.
   * Local state is cleared regardless of the network outcome.
   */
  async logout(): Promise<void> {
    const refresh_token = this.getRefreshToken();
    try {
      if (refresh_token) {
        await this.request<void>('/api/v1/auth/logout', {
          method: 'POST',
          body: JSON.stringify({ refresh_token }),
        });
      }
    } catch {
      // Revocation failed (offline, already revoked). Still clear locally.
    } finally {
      this.clearSession();
    }
  }

  async changePassword(oldPassword: string, newPassword: string): Promise<void> {
    return this.request<void>('/api/v1/users/me/password', {
      method: 'PATCH',
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
    });
  }

  // -- employees -------------------------------------------------------------

  /**
   * FT-006: the roster lives at /employees. The client previously called
   * GET /api/v1/users, which does not exist (405), so every employee list and
   * assignment dropdown was permanently empty.
   */
  async getEmployees(): Promise<Employee[]> {
    return this.request<Employee[]>('/api/v1/employees');
  }

  async getEmployeeById(id: string): Promise<Employee> {
    return this.request<Employee>(`/api/v1/employees/${id}`);
  }

  async getMyEmployeeProfile(): Promise<Employee> {
    return this.request<Employee>('/api/v1/employees/me');
  }

  async createEmployee(data: {
    user_id: string;
    full_name: string;
    territory_id?: string | null;
    employee_code?: string | null;
  }): Promise<Employee> {
    return this.request<Employee>('/api/v1/employees', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateEmployee(
    id: string,
    data: { full_name?: string; territory_id?: string | null; employee_code?: string | null },
  ): Promise<Employee> {
    return this.request<Employee>(`/api/v1/employees/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  // -- users -----------------------------------------------------------------

  async createUser(data: {
    email?: string | null;
    mobile_number?: string | null;
    password: string;
    role: User['role'];
  }): Promise<User> {
    return this.request<User>('/api/v1/users', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async setUserActive(userId: string, active: boolean): Promise<User> {
    return this.request<User>(
      `/api/v1/users/${userId}/${active ? 'activate' : 'deactivate'}`,
      { method: 'PATCH' },
    );
  }

  // -- customers -------------------------------------------------------------

  async getCustomers(): Promise<Customer[]> {
    return this.request<Customer[]>('/api/v1/customers');
  }

  async getCustomerById(id: string): Promise<Customer> {
    return this.request<Customer>(`/api/v1/customers/${id}`);
  }

  async createCustomer(data: {
    name: string;
    contact_number: string;
    contact_person?: string | null;
    address: string;
    location: { latitude: number; longitude: number };
    geofence_radius_m?: number;
    territory_id?: string | null;
  }): Promise<Customer> {
    return this.request<Customer>('/api/v1/customers', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateCustomer(
    id: string,
    data: Partial<{
      name: string;
      contact_number: string;
      contact_person: string | null;
      address: string;
      location: { latitude: number; longitude: number };
      geofence_radius_m: number;
      territory_id: string | null;
    }>,
  ): Promise<Customer> {
    return this.request<Customer>(`/api/v1/customers/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  // -- territories -----------------------------------------------------------

  async getTerritories(): Promise<Territory[]> {
    return this.request<Territory[]>('/api/v1/territories');
  }

  async createTerritory(name: string): Promise<Territory> {
    return this.request<Territory>('/api/v1/territories', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
  }

  async updateTerritory(id: string, name: string): Promise<Territory> {
    return this.request<Territory>(`/api/v1/territories/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    });
  }

  async deleteTerritory(id: string): Promise<void> {
    return this.request<void>(`/api/v1/territories/${id}`, { method: 'DELETE' });
  }

  // -- visits ----------------------------------------------------------------

  async getVisits(status?: VisitStatus): Promise<Visit[]> {
    const query = status ? `?status=${encodeURIComponent(status)}` : '';
    return this.request<Visit[]>(`/api/v1/visits${query}`);
  }

  async getMyTodayVisits(): Promise<Visit[]> {
    return this.request<Visit[]>('/api/v1/visits/me/today');
  }

  async getVisitById(id: string): Promise<Visit> {
    return this.request<Visit>(`/api/v1/visits/${id}`);
  }

  async getVisitGeoLogs(visitId: string): Promise<GeoVerificationLog[]> {
    return this.request<GeoVerificationLog[]>(`/api/v1/visits/${visitId}/geo-logs`);
  }

  /** FT-006: `employee_id` must be an employees.id, not a users.id. */
  async createVisit(data: {
    customer_id: string;
    employee_id: string;
    scheduled_at: string;
  }): Promise<Visit> {
    return this.request<Visit>('/api/v1/visits', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateVisitStatus(
    visitId: string,
    status: VisitStatus,
    reason?: string,
  ): Promise<Visit> {
    return this.request<Visit>(`/api/v1/visits/${visitId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, reason: reason ?? null }),
    });
  }

  async checkIn(
    visitId: string,
    data: {
      latitude: number;
      longitude: number;
      accuracy_m?: number;
      is_mock_location?: boolean;
      idempotency_key?: string;
    },
  ): Promise<Visit> {
    return this.request<Visit>(`/api/v1/visits/${visitId}/check-in`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async checkOut(
    visitId: string,
    data: {
      latitude: number;
      longitude: number;
      accuracy_m?: number;
      is_mock_location?: boolean;
    },
  ): Promise<Visit> {
    return this.request<Visit>(`/api/v1/visits/${visitId}/check-out`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // -- media -----------------------------------------------------------------

  async getVisitMedia(visitId: string): Promise<VisitMedia[]> {
    return this.request<VisitMedia[]>(`/api/v1/visits/${visitId}/media`);
  }

  async uploadMedia(visitId: string, file: File): Promise<VisitMedia> {
    const formData = new FormData();
    formData.append('file', file);
    // Routed through request() so it shares auth, refresh-on-401 and error
    // parsing; Content-Type is left to the browser for the multipart boundary.
    return this.request<VisitMedia>(`/api/v1/visits/${visitId}/media`, {
      method: 'POST',
      body: formData,
    });
  }

  async deleteMedia(mediaId: string): Promise<void> {
    return this.request<void>(`/api/v1/media/${mediaId}`, { method: 'DELETE' });
  }

  /**
   * Fetch media bytes as an object URL.
   *
   * FT-015: the download endpoint requires an Authorization header, which a
   * plain <img src> or <a href> cannot send, so previews and downloads returned
   * 403. Fetching the blob with credentials and handing back an object URL
   * keeps the endpoint protected while letting the browser render it.
   */
  async getMediaObjectUrl(mediaId: string): Promise<string> {
    const response = await fetch(this.url(`/api/v1/media/${mediaId}/download`), {
      headers: this.authHeader(),
    });
    if (!response.ok) {
      throw await this.parseError(response);
    }
    return URL.createObjectURL(await response.blob());
  }

  // -- reports ---------------------------------------------------------------

  async getEmployeeReport(startDate?: string, endDate?: string): Promise<EmployeeReportRow[]> {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    const query = params.toString();
    return this.request<EmployeeReportRow[]>(
      `/api/v1/reports/employees${query ? `?${query}` : ''}`
    );
  }

  async getCustomerVisitHistory(customerId: string): Promise<CustomerHistoryRow[]> {
    return this.request<CustomerHistoryRow[]>(`/api/v1/reports/customers/${customerId}/history`);
  }

  async getProductivityDashboard(): Promise<ProductivityDashboardData> {
    return this.request<ProductivityDashboardData>('/api/v1/reports/productivity');
  }

  async getGeoVerificationReport(startDate?: string, endDate?: string): Promise<GeoReportRow[]> {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    const query = params.toString();
    return this.request<GeoReportRow[]>(
      `/api/v1/reports/geo-verification${query ? `?${query}` : ''}`
    );
  }
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

export interface CustomerHistoryRow {
  visit_id: string;
  scheduled_at: string;
  status: string;
  employee_name: string;
  check_in_at?: string;
  check_out_at?: string;
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
  attempted_at: string;
  verification_type: string;
  is_valid: boolean;
  distance_m: number;
  failure_reason: string | null;
}

export const apiClient = new ApiClient();
