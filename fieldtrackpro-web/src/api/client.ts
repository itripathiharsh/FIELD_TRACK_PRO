import { ENV } from '../config/env';
import {
  AccountSummary,
  Area,
  BusinessBIDashboard,
  CollectionsOverviewResponse,
  Customer,
  Employee,
  EmployeeAreaAssignment,
  EmployeeActivity,
  CollectionReportRow,
  EmployeeMasterReportRow,
  FOSEmployeeMappingRead,
  FormRender,
  FormSection,
  FormSubmission,
  FormSubmissionDetail,
  FormTemplate,
  FormTemplateSummary,
  FormQuestion,
  GeoVerificationLog,
  ImportBatchRead,
  ImportPreviewResponse,
  ImportTargetFieldConfig,
  Invoice,
  LoginResponse,
  MonthlyReportingPeriod,
  OrderRead,
  OutletMatchStrategy,
  OutletReportRow,
  OutstandingAgeingReportRow,
  OverviewReportData,
  Payment,
  PaymentMethod,
  PaymentProof,
  PaymentStatus,
  QuestionOption,
  QuestionType,
  SignatureDownloadResponse,
  Territory,
  TerritoryAssignmentCreate,
  TerritoryAssignmentHistory,
  TerritoryAssignmentRead,
  User,
  Visit,
  VisitDetailedReportRow,
  VisitMedia,
  VisitSignature,
  VisitStatus,
} from '../types';

/**
 * FT-040 & Security Hardening:
 * - Access token is held in-memory only (never localStorage - XSS risk).
 * - Refresh token is stored in HttpOnly, Secure, SameSite cookie by the backend.
 * - Requests use credentials: 'include' for secure cookie exchange.
 */
const LEGACY_REFRESH_TOKEN_KEY = 'fieldtrack_refresh_token';

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

    // Cleanup any legacy plaintext refresh tokens in localStorage
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.removeItem(LEGACY_REFRESH_TOKEN_KEY);
      }
    } catch {
      // Ignore in environments without localStorage
    }
  }

  /** Absolute URL for an API path. Used by callers that need a raw URL. */
  url(path: string): string {
    return `${this.baseUrl}${path.startsWith('/') ? path : `/${path}`}`;
  }

  // -- session storage -------------------------------------------------------

  getAccessToken(): string | null {
    return this.accessToken;
  }

  /**
   * True when an in-memory session or refresh token indicator exists.
   */
  hasStoredSession(): boolean {
    try {
      return Boolean(this.accessToken || (typeof localStorage !== 'undefined' && localStorage.getItem(LEGACY_REFRESH_TOKEN_KEY)));
    } catch {
      return Boolean(this.accessToken);
    }
  }

  private storeSession(tokens: LoginResponse): void {
    this.accessToken = tokens.access_token;
  }

  clearSession(): void {
    this.accessToken = null;
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.removeItem(LEGACY_REFRESH_TOKEN_KEY);
      }
    } catch {
      // Ignore
    }
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
      response = await fetch(this.url(endpoint), {
        credentials: 'include',
        ...options,
        headers,
      });
    } catch {
      // Network-level failure: distinguish clearly from an auth rejection.
      throw new ApiError(
        'Unable to reach the FieldTrack Pro API. Check your connection and try again.',
        0,
        'NETWORK_ERROR',
      );
    }

    if (response.status === 401 && allowRefresh) {
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

  /** Request helper that extracts the X-Total-Count response header for server-side pagination. */
  async requestWithTotal<T>(
    endpoint: string,
    options: RequestInit = {},
    allowRefresh = true,
  ): Promise<{ data: T; total: number }> {
    const token = this.getAccessToken();
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };

    let response: Response;
    try {
      response = await fetch(this.url(endpoint), {
        credentials: 'include',
        ...options,
        headers,
      });
    } catch {
      throw new ApiError(
        'Unable to reach the FieldTrack Pro API. Check your connection and try again.',
        0,
        'NETWORK_ERROR',
      );
    }

    if (response.status === 401 && allowRefresh) {
      const refreshed = await this.tryRefresh();
      if (refreshed) {
        return this.requestWithTotal<T>(endpoint, options, false);
      }
    }

    if (!response.ok) {
      throw await this.parseError(response);
    }

    const totalHeader = response.headers.get('X-Total-Count');
    const data = (await response.json()) as T;
    const total = totalHeader ? parseInt(totalHeader, 10) : (Array.isArray(data) ? data.length : 0);
    return { data, total };
  }

  /** Exchange the HttpOnly refresh token cookie for a new pair. Returns false if not possible. */
  private async tryRefresh(): Promise<boolean> {
    try {
      const response = await fetch(this.url('/api/v1/auth/refresh'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!response.ok) {
        this.clearSession();
        return false;
      }
      const tokens = (await response.json()) as LoginResponse;
      this.storeSession(tokens);
      return true;
    } catch {
      this.clearSession();
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

    const tokens = await this.request<LoginResponse>(
      '/api/v1/auth/login',
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
      false,
    );
    this.storeSession(tokens);
    return tokens;
  }

  /**
   * Identity of the signed-in caller.
   *
   * FT-040 & Hardening: after a page reload there is no in-memory access token,
   * so one is minted from the HttpOnly refresh token cookie first. If that fails
   * the session is genuinely over and the error propagates.
   */
  async getCurrentUser(): Promise<User> {
    if (!this.accessToken) {
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
   * FT-009: the refresh token is revoked server-side and HttpOnly cookie cleared.
   * Local state is cleared regardless of the network outcome.
   */
  async logout(): Promise<void> {
    try {
      await this.request<void>(
        '/api/v1/auth/logout',
        {
          method: 'POST',
          body: JSON.stringify({}),
        },
        false,
      );
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


  async forgotPassword(email: string): Promise<{ message: string }> {
    return this.request<{ message: string }>('/api/v1/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
      // Do not try to refresh token since we're not logged in
    }, false);
  }

  async resetPassword(email: string, otp: string, newPassword: string): Promise<{ message: string }> {
    return this.request<{ message: string }>('/api/v1/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ email, otp, new_password: newPassword }),
    }, false);
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

  async registerEmployee(data: {
    user: {
      email?: string | null;
      mobile_number?: string | null;
      password: string;
      role: User['role'];
    };
    full_name: string;
    territory_id?: string | null;
    employee_code?: string | null;
  }): Promise<Employee> {
    return this.request<Employee>('/api/v1/employees/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateEmployee(
    id: string,
    data: { full_name?: string; territory_id?: string | null; employee_code?: string | null; email?: string },
  ): Promise<Employee> {
    return this.request<Employee>(`/api/v1/employees/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  // -- P2-C: employee activity -------------------------------------------------

  async getEmployeeActivity(employeeId: string): Promise<EmployeeActivity> {
    return this.request<EmployeeActivity>(`/api/v1/employees/${employeeId}/activity`);
  }

  // -- P2-D: territory reassignment ---------------------------------------------

  async getTerritoryAssignmentHistory(employeeId: string): Promise<TerritoryAssignmentHistory> {
    return this.request<TerritoryAssignmentHistory>(`/api/v1/employees/${employeeId}/territory-assignments`);
  }

  async createTerritoryAssignment(
    employeeId: string,
    data: TerritoryAssignmentCreate,
  ): Promise<TerritoryAssignmentRead> {
    return this.request<TerritoryAssignmentRead>(`/api/v1/employees/${employeeId}/territory-assignments`, {
      method: 'POST',
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

  async getUserById(userId: string): Promise<User> {
    return this.request<User>(`/api/v1/users/${userId}`);
  }

  // -- customers -------------------------------------------------------------

  async getCustomers(params?: {
    territory_id?: string;
    area_id?: string;
    skip?: number;
    limit?: number;
  }): Promise<Customer[]> {
    const query = params
      ? '?' +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : '?limit=200';
    return this.request<Customer[]>(`/api/v1/customers${query}`);
  }

  async getCustomerById(id: string): Promise<Customer> {
    return this.request<Customer>(`/api/v1/customers/${id}`);
  }

  async createCustomer(data: {
    name: string;
    contact_number: string;
    contact_person?: string | null;
    address?: string;
    location?: { latitude: number; longitude: number } | null;
    geofence_radius_m?: number;
    territory_id?: string | null;
    area_id?: string | null;
    outlet_code?: string | null;
    location_status?: string | null;
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
      location: { latitude: number; longitude: number } | null;
      geofence_radius_m: number;
      territory_id: string | null;
      area_id: string | null;
      outlet_code: string | null;
      location_status: string | null;
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

  async getTerritoryById(id: string): Promise<Territory> {
    return this.request<Territory>(`/api/v1/territories/${id}`);
  }

  async createTerritory(
    data:
      | string
      | {
          name: string;
          center_latitude?: number | null;
          center_longitude?: number | null;
          radius_km?: number | null;
          status?: string;
        },
  ): Promise<Territory> {
    const payload = typeof data === 'string' ? { name: data } : data;
    return this.request<Territory>('/api/v1/territories', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async updateTerritory(
    id: string,
    data:
      | string
      | {
          name?: string;
          center_latitude?: number | null;
          center_longitude?: number | null;
          radius_km?: number | null;
          status?: string;
        },
  ): Promise<Territory> {
    const payload = typeof data === 'string' ? { name: data } : data;
    return this.request<Territory>(`/api/v1/territories/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  }

  async deleteTerritory(id: string): Promise<void> {
    return this.request<void>(`/api/v1/territories/${id}`, { method: 'DELETE' });
  }

  // -- areas (Zone -> Area -> Outlet) -----------------------------------------

  async getAreas(territoryId?: string): Promise<Area[]> {
    const query = territoryId ? `?territory_id=${encodeURIComponent(territoryId)}` : '';
    return this.request<Area[]>(`/api/v1/areas${query}`);
  }

  async createArea(data: { name: string; territory_id: string }): Promise<Area> {
    return this.request<Area>('/api/v1/areas', { method: 'POST', body: JSON.stringify(data) });
  }

  async updateArea(id: string, data: { name: string }): Promise<Area> {
    return this.request<Area>(`/api/v1/areas/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
  }

  async deleteArea(id: string): Promise<void> {
    return this.request<void>(`/api/v1/areas/${id}`, { method: 'DELETE' });
  }

  // -- employee <-> area coverage (brand-agnostic many-to-many) ---------------

  async getEmployeeAreaCoverage(employeeId: string): Promise<EmployeeAreaAssignment[]> {
    return this.request<EmployeeAreaAssignment[]>(`/api/v1/employees/${employeeId}/areas`);
  }

  async assignEmployeeArea(employeeId: string, areaId: string): Promise<EmployeeAreaAssignment> {
    return this.request<EmployeeAreaAssignment>(`/api/v1/employees/${employeeId}/areas`, {
      method: 'POST',
      body: JSON.stringify({ area_id: areaId }),
    });
  }

  async unassignEmployeeArea(employeeId: string, areaId: string): Promise<void> {
    return this.request<void>(`/api/v1/employees/${employeeId}/areas/${areaId}`, { method: 'DELETE' });
  }

  // -- visits ----------------------------------------------------------------

  async getVisits(status?: VisitStatus): Promise<Visit[]> {
    const query = status ? `?status=${encodeURIComponent(status)}` : '';
    return this.request<Visit[]>(`/api/v1/visits${query}`);
  }

  async getVisitsPaginated(params?: {
    status?: VisitStatus | VisitStatus[];
    employee_id?: string;
    territory_id?: string;
    area_id?: string;
    from_date?: string;
    to_date?: string;
    search?: string;
    sort_order?: 'asc' | 'desc';
    skip?: number;
    limit?: number;
  }): Promise<{ items: Visit[]; total: number }> {
    const searchParams = new URLSearchParams();
    if (params) {
      if (params.search) searchParams.set('search', params.search);
      if (params.employee_id) searchParams.set('employee_id', params.employee_id);
      if (params.territory_id) searchParams.set('territory_id', params.territory_id);
      if (params.area_id) searchParams.set('area_id', params.area_id);
      if (params.from_date) searchParams.set('from_date', params.from_date);
      if (params.to_date) searchParams.set('to_date', params.to_date);
      if (params.sort_order) searchParams.set('sort_order', params.sort_order);
      if (params.skip !== undefined) searchParams.set('skip', String(params.skip));
      if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
      if (params.status) {
        if (Array.isArray(params.status)) {
          params.status.forEach((s) => searchParams.append('status', s));
        } else {
          searchParams.set('status', params.status);
        }
      }
    }
    const query = searchParams.toString();
    const { data, total } = await this.requestWithTotal<Visit[]>(
      `/api/v1/visits${query ? `?${query}` : ''}`,
    );
    return { items: data, total };
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
    required_form_id?: string | null;
  }): Promise<Visit> {
    return this.request<Visit>('/api/v1/visits', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async bulkCreateVisits(data: {
    customer_ids: string[];
    employee_id: string;
    scheduled_at: string;
    required_form_id?: string | null;
  }): Promise<Visit[]> {
    return this.request<Visit[]>('/api/v1/visits/bulk', {
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

  /** Admin: assign/change/clear ("no form required") the form a visit requires. */
  async setVisitRequiredForm(visitId: string, requiredFormId: string | null): Promise<Visit> {
    return this.request<Visit>(`/api/v1/visits/${visitId}/required-form`, {
      method: 'PATCH',
      body: JSON.stringify({ required_form_id: requiredFormId }),
    });
  }

  async checkIn(
    visitId: string,
    data: {
      latitude: number;
      longitude: number;
      accuracy_m?: number;
      is_mock_location?: boolean;
      // When the device actually captured this GPS fix - required by the
      // backend's freshness check (rejects fixes older than 24h).
      captured_at: string;
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
      captured_at: string;
      idempotency_key?: string;
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
   *
   * /media/{id}/download itself only returns a JSON `{ download_url }`
   * pointer (a pre-signed link, short-lived and separately authorized) - the
   * actual file bytes live at that second URL. This previously blob-ified the
   * JSON response itself, so every preview/download was a broken image
   * containing the metadata text instead of the photo.
   */
  async getMediaObjectUrl(mediaId: string): Promise<string> {
    const metaResponse = await fetch(this.url(`/api/v1/media/${mediaId}/download`), {
      headers: this.authHeader(),
    });
    if (!metaResponse.ok) {
      throw await this.parseError(metaResponse);
    }
    const { download_url } = (await metaResponse.json()) as { download_url: string };

    const fileResponse = await fetch(download_url);
    if (!fileResponse.ok) {
      throw new Error(`Failed to download media file (${fileResponse.status})`);
    }
    return URL.createObjectURL(await fileResponse.blob());
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

  async getOverviewReport(params?: {
    brand?: string;
    zone_id?: string;
    area_id?: string;
    employee_id?: string;
    month?: string;
  }): Promise<OverviewReportData> {
    const query = params
      ? '?' +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : '';
    return this.request<OverviewReportData>(`/api/v1/reports/overview${query}`);
  }

  async getBusinessSummary(
    brand?: string,
    zone_id?: string,
    area_id?: string,
    employee_id?: string,
    month?: string,
  ): Promise<BusinessBIDashboard> {
    const params = new URLSearchParams();
    if (brand && brand !== 'ALL') params.set('brand', brand);
    if (zone_id && zone_id !== 'ALL') params.set('zone_id', zone_id);
    if (area_id && area_id !== 'ALL') params.set('area_id', area_id);
    if (employee_id && employee_id !== 'ALL') params.set('employee_id', employee_id);
    if (month && month !== 'ALL') params.set('month', month);
    const query = params.toString();
    return this.request<BusinessBIDashboard>(
      `/api/v1/reports/business-summary${query ? `?${query}` : ''}`
    );
  }

  async getEmployeesMasterReport(params?: {
    working_profile?: string;
    role?: string;
    is_active?: boolean;
    query?: string;
  }): Promise<EmployeeMasterReportRow[]> {
    const q = params
      ? '?' +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : '';
    return this.request<EmployeeMasterReportRow[]>(`/api/v1/reports/employees/master${q}`);
  }

  async getOutletsReport(params?: {
    brand?: string;
    zone_id?: string;
    area_id?: string;
    employee_id?: string;
    location_status?: string;
    query?: string;
  }): Promise<OutletReportRow[]> {
    const q = params
      ? '?' +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : '';
    return this.request<OutletReportRow[]>(`/api/v1/reports/outlets${q}`);
  }

  async getOutstandingReport(params?: {
    brand?: string;
    zone_id?: string;
    area_id?: string;
    employee_id?: string;
    ageing_bucket?: string;
    month?: string;
    query?: string;
  }): Promise<OutstandingAgeingReportRow[]> {
    const q = params
      ? '?' +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : '';
    return this.request<OutstandingAgeingReportRow[]>(`/api/v1/reports/outstanding${q}`);
  }

  async getCollectionsReport(params?: {
    brand?: string;
    zone_id?: string;
    area_id?: string;
    employee_id?: string;
    month?: string;
    query?: string;
  }): Promise<CollectionReportRow[]> {
    const q = params
      ? '?' +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : '';
    return this.request<CollectionReportRow[]>(`/api/v1/reports/collections${q}`);
  }

  async getVisitsDetailedReport(params?: {
    start_date?: string;
    end_date?: string;
    employee_id?: string;
    zone_id?: string;
    area_id?: string;
    status?: string;
  }): Promise<VisitDetailedReportRow[]> {
    const q = params
      ? '?' +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : '';
    return this.request<VisitDetailedReportRow[]>(`/api/v1/reports/visits${q}`);
  }

  async getMonthlyPeriods(): Promise<MonthlyReportingPeriod[]> {
    return this.request<MonthlyReportingPeriod[]>('/api/v1/reports/monthly-periods');
  }

  async finalizeMonthlyPeriod(periodId: string): Promise<MonthlyReportingPeriod> {
    return this.request<MonthlyReportingPeriod>(`/api/v1/reports/monthly-periods/${periodId}/finalize`, {
      method: 'POST',
    });
  }

  async reopenMonthlyPeriod(periodId: string): Promise<MonthlyReportingPeriod> {
    return this.request<MonthlyReportingPeriod>(`/api/v1/reports/monthly-periods/${periodId}/reopen`, {
      method: 'POST',
    });
  }

  async exportOverviewExcelObjectUrl(params?: {
    brand?: string;
    zone_id?: string;
    area_id?: string;
    employee_id?: string;
    month?: string;
  }): Promise<string> {
    const q = params
      ? '?' +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : '';
    const res = await fetch(this.url(`/api/v1/reports/overview/export${q}`), {
      headers: this.authHeader(),
    });
    if (!res.ok) throw await this.parseError(res);
    return URL.createObjectURL(await res.blob());
  }

  async exportBusinessSummaryExcelObjectUrl(
    brand?: string,
    zone_id?: string,
    area_id?: string,
    employee_id?: string,
    month?: string,
  ): Promise<string> {
    const params = new URLSearchParams();
    if (brand && brand !== 'ALL') params.set('brand', brand);
    if (zone_id && zone_id !== 'ALL') params.set('zone_id', zone_id);
    if (area_id && area_id !== 'ALL') params.set('area_id', area_id);
    if (employee_id && employee_id !== 'ALL') params.set('employee_id', employee_id);
    if (month && month !== 'ALL') params.set('month', month);
    const q = params.toString();
    const res = await fetch(this.url(`/api/v1/reports/business-summary/export${q ? `?${q}` : ''}`), {
      headers: this.authHeader(),
    });
    if (!res.ok) throw await this.parseError(res);
    return URL.createObjectURL(await res.blob());
  }

  async exportEmployeesMasterExcelObjectUrl(params?: {
    working_profile?: string;
    role?: string;
    is_active?: boolean;
    query?: string;
  }): Promise<string> {
    const q = params
      ? '?' +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : '';
    const res = await fetch(this.url(`/api/v1/reports/employees/master/export${q}`), {
      headers: this.authHeader(),
    });
    if (!res.ok) throw await this.parseError(res);
    return URL.createObjectURL(await res.blob());
  }

  async exportOutletsExcelObjectUrl(params?: {
    brand?: string;
    zone_id?: string;
    area_id?: string;
    employee_id?: string;
    query?: string;
  }): Promise<string> {
    const q = params
      ? '?' +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : '';
    const res = await fetch(this.url(`/api/v1/reports/outlets/export${q}`), {
      headers: this.authHeader(),
    });
    if (!res.ok) throw await this.parseError(res);
    return URL.createObjectURL(await res.blob());
  }

  async exportOutstandingExcelObjectUrl(params?: {
    brand?: string;
    zone_id?: string;
    area_id?: string;
    employee_id?: string;
    ageing_bucket?: string;
    month?: string;
    query?: string;
  }): Promise<string> {
    const q = params
      ? '?' +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : '';
    const res = await fetch(this.url(`/api/v1/reports/outstanding/export${q}`), {
      headers: this.authHeader(),
    });
    if (!res.ok) throw await this.parseError(res);
    return URL.createObjectURL(await res.blob());
  }

  async exportCollectionsExcelObjectUrl(params?: {
    brand?: string;
    zone_id?: string;
    area_id?: string;
    employee_id?: string;
    month?: string;
    query?: string;
  }): Promise<string> {
    const q = params
      ? '?' +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : '';
    const res = await fetch(this.url(`/api/v1/reports/collections/export${q}`), {
      headers: this.authHeader(),
    });
    if (!res.ok) throw await this.parseError(res);
    return URL.createObjectURL(await res.blob());
  }

  async exportVisitsDetailedExcelObjectUrl(params?: {
    start_date?: string;
    end_date?: string;
    employee_id?: string;
    zone_id?: string;
    area_id?: string;
  }): Promise<string> {
    const q = params
      ? '?' +
        new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : '';
    const res = await fetch(this.url(`/api/v1/reports/visits/export${q}`), {
      headers: this.authHeader(),
    });
    if (!res.ok) throw await this.parseError(res);
    return URL.createObjectURL(await res.blob());
  }


  // -- signatures -------------------------------------------------------------

  async getVisitSignatures(visitId: string): Promise<VisitSignature[]> {
    return this.request<VisitSignature[]>(`/api/v1/visits/${visitId}/signatures`);
  }

  async getSignatureDownloadUrl(signatureId: string): Promise<SignatureDownloadResponse> {
    return this.request<SignatureDownloadResponse>(`/api/v1/signatures/${signatureId}/download`);
  }

  // -- P1: outlet account / invoices / payments (Collections) -----------------

  async getCustomerAccount(customerId: string): Promise<AccountSummary> {
    return this.request<AccountSummary>(`/api/v1/customers/${customerId}/account`);
  }

  /** The outlet-list financial overview (Meeting 2) - totals + per-outlet rows, server-side filtered/paginated. */
  async getCollectionsOverview(params?: {
    search?: string;
    territory_id?: string;
    area_id?: string;
    employee_id?: string;
    collection_status?: string;
    skip?: number;
    limit?: number;
  }): Promise<CollectionsOverviewResponse> {
    const query = params
      ? '?' + new URLSearchParams(
          Object.entries(params)
            .filter(([, v]) => v !== undefined && v !== '')
            .map(([k, v]) => [k, String(v)]),
        ).toString()
      : '';
    return this.request<CollectionsOverviewResponse>(`/api/v1/collections/overview${query}`);
  }

  async getCustomerInvoices(customerId: string): Promise<Invoice[]> {
    return this.request<Invoice[]>(`/api/v1/customers/${customerId}/invoices`);
  }

  /** Every order captured across this outlet's full visit history (P2-B). */
  async getCustomerOrders(customerId: string): Promise<OrderRead[]> {
    return this.request<OrderRead[]>(`/api/v1/customers/${customerId}/orders`);
  }

  async createInvoice(data: {
    customer_id: string;
    invoice_number: string;
    invoice_date: string;
    due_date?: string | null;
    amount: number;
    brand?: string | null;
    source_reference?: string | null;
  }): Promise<Invoice> {
    return this.request<Invoice>('/api/v1/invoices', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async createPayment(data: {
    visit_id: string;
    invoice_id?: string | null;
    amount: number;
    payment_method: PaymentMethod;
    payment_date: string;
    cheque_number?: string | null;
    cheque_bank_name?: string | null;
    utr_reference?: string | null;
    notes?: string | null;
  }): Promise<Payment> {
    return this.request<Payment>('/api/v1/payments', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getPayment(paymentId: string): Promise<Payment> {
    return this.request<Payment>(`/api/v1/payments/${paymentId}`);
  }

  async uploadPaymentProof(paymentId: string, file: File): Promise<PaymentProof> {
    const formData = new FormData();
    formData.append('file', file);
    return this.request<PaymentProof>(`/api/v1/payments/${paymentId}/proof`, {
      method: 'POST',
      body: formData,
    });
  }

  /** Mirrors getMediaObjectUrl's two-step fetch: metadata JSON, then the real file bytes. */
  async getPaymentProofObjectUrl(proofId: string): Promise<string> {
    const metaResponse = await fetch(this.url(`/api/v1/payments/proofs/${proofId}/download`), {
      headers: this.authHeader(),
    });
    if (!metaResponse.ok) {
      throw await this.parseError(metaResponse);
    }
    const { download_url } = (await metaResponse.json()) as { download_url: string };
    const fileResponse = await fetch(download_url);
    if (!fileResponse.ok) {
      throw new Error(`Failed to download payment proof (${fileResponse.status})`);
    }
    return URL.createObjectURL(await fileResponse.blob());
  }

  async getPaymentReviewQueue(status?: PaymentStatus): Promise<Payment[]> {
    const query = status ? `?status=${status}` : '';
    return this.request<Payment[]>(`/api/v1/payments/queue${query}`);
  }

  async verifyPayment(paymentId: string): Promise<Payment> {
    return this.request<Payment>(`/api/v1/payments/${paymentId}/verify`, { method: 'POST' });
  }

  async rejectPayment(paymentId: string, rejectionReason: string): Promise<Payment> {
    return this.request<Payment>(`/api/v1/payments/${paymentId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ rejection_reason: rejectionReason }),
    });
  }

  /** Order capture: a photographed diary order + optional short note - reuses the media upload path. */
  async uploadOrderCapture(visitId: string, file: File, note?: string): Promise<VisitMedia> {
    const formData = new FormData();
    formData.append('file', file);
    const params = new URLSearchParams({ is_order: 'true' });
    if (note) params.set('note', note);
    return this.request<VisitMedia>(`/api/v1/visits/${visitId}/media?${params.toString()}`, {
      method: 'POST',
      body: formData,
    });
  }

  // -- requirement forms -----------------------------------------------------

  async getRequirementCategories(): Promise<RequirementCategory[]> {
    return this.request<RequirementCategory[]>('/api/v1/requirement-categories');
  }

  async createRequirementCategory(name: string): Promise<RequirementCategory> {
    return this.request<RequirementCategory>('/api/v1/requirement-categories', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
  }

  async submitRequirementForm(
    visitId: string,
    data: {
      category_id: string;
      description: string;
      priority: string;
      expected_timeline: string;
      budget_range?: string;
      notes?: string;
    },
  ): Promise<RequirementForm> {
    return this.request<RequirementForm>(`/api/v1/visits/${visitId}/requirement-form`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getRequirementForm(visitId: string): Promise<RequirementForm | null> {
    try {
      return await this.request<RequirementForm>(`/api/v1/visits/${visitId}/requirement-form`);
    } catch {
      return null;
    }
  }

  // -- form template builder --------------------------------------------------

  async createFormTemplate(data: { name: string; description?: string | null; category_id?: string | null }): Promise<FormTemplate> {
    return this.request<FormTemplate>('/api/v1/form-templates', { method: 'POST', body: JSON.stringify(data) });
  }

  async getFormTemplates(params?: { status?: string; category_id?: string }): Promise<FormTemplateSummary[]> {
    const query = params
      ? '?' + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined) as [string, string][]).toString()
      : '';
    return this.request<FormTemplateSummary[]>(`/api/v1/form-templates${query}`);
  }

  async getFormTemplate(id: string): Promise<FormTemplate> {
    return this.request<FormTemplate>(`/api/v1/form-templates/${id}`);
  }

  async updateFormTemplate(id: string, data: { name?: string; description?: string | null; category_id?: string | null }): Promise<FormTemplate> {
    return this.request<FormTemplate>(`/api/v1/form-templates/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
  }

  async deleteFormTemplate(id: string): Promise<void> {
    return this.request<void>(`/api/v1/form-templates/${id}`, { method: 'DELETE' });
  }

  async publishFormTemplate(id: string): Promise<FormTemplate> {
    return this.request<FormTemplate>(`/api/v1/form-templates/${id}/publish`, { method: 'POST' });
  }

  async unpublishFormTemplate(id: string): Promise<FormTemplate> {
    return this.request<FormTemplate>(`/api/v1/form-templates/${id}/unpublish`, { method: 'POST' });
  }

  async archiveFormTemplate(id: string): Promise<FormTemplate> {
    return this.request<FormTemplate>(`/api/v1/form-templates/${id}/archive`, { method: 'POST' });
  }

  async duplicateFormTemplate(id: string): Promise<FormTemplate> {
    return this.request<FormTemplate>(`/api/v1/form-templates/${id}/duplicate`, { method: 'POST' });
  }

  /** Employee-facing: the published structure to render and fill in. */
  async getFormRender(id: string): Promise<FormRender> {
    return this.request<FormRender>(`/api/v1/form-templates/${id}/render`);
  }

  async addFormSection(formId: string, data: { title: string; description?: string | null; display_order?: number }): Promise<FormSection> {
    return this.request<FormSection>(`/api/v1/form-templates/${formId}/sections`, { method: 'POST', body: JSON.stringify(data) });
  }

  async updateFormSection(sectionId: string, data: { title?: string; description?: string | null; display_order?: number }): Promise<FormSection> {
    return this.request<FormSection>(`/api/v1/sections/${sectionId}`, { method: 'PATCH', body: JSON.stringify(data) });
  }

  async deleteFormSection(sectionId: string): Promise<void> {
    return this.request<void>(`/api/v1/sections/${sectionId}`, { method: 'DELETE' });
  }

  async addFormQuestion(
    formId: string,
    data: {
      section_id: string;
      question_text: string;
      question_type: QuestionType;
      required?: boolean;
      help_text?: string | null;
      placeholder?: string | null;
      display_order?: number;
      validation_config?: Record<string, unknown> | null;
      options?: { label: string; value: string; display_order?: number }[];
    },
  ): Promise<FormQuestion> {
    return this.request<FormQuestion>(`/api/v1/form-templates/${formId}/questions`, { method: 'POST', body: JSON.stringify(data) });
  }

  async updateFormQuestion(
    questionId: string,
    data: Partial<{
      section_id: string;
      question_text: string;
      question_type: QuestionType;
      required: boolean;
      help_text: string | null;
      placeholder: string | null;
      display_order: number;
      validation_config: Record<string, unknown> | null;
      options: { label: string; value: string; display_order?: number }[];
    }>,
  ): Promise<FormQuestion> {
    return this.request<FormQuestion>(`/api/v1/questions/${questionId}`, { method: 'PATCH', body: JSON.stringify(data) });
  }

  async deleteFormQuestion(questionId: string): Promise<void> {
    return this.request<void>(`/api/v1/questions/${questionId}`, { method: 'DELETE' });
  }

  async duplicateFormQuestion(questionId: string): Promise<FormQuestion> {
    return this.request<FormQuestion>(`/api/v1/questions/${questionId}/duplicate`, { method: 'POST' });
  }

  async addQuestionOption(questionId: string, data: { label: string; value?: string; display_order?: number }): Promise<QuestionOption> {
    return this.request<QuestionOption>(`/api/v1/questions/${questionId}/options`, { method: 'POST', body: JSON.stringify(data) });
  }

  async updateQuestionOption(optionId: string, data: { label?: string; value?: string; display_order?: number }): Promise<QuestionOption> {
    return this.request<QuestionOption>(`/api/v1/question-options/${optionId}`, { method: 'PATCH', body: JSON.stringify(data) });
  }

  async deleteQuestionOption(optionId: string): Promise<void> {
    return this.request<void>(`/api/v1/question-options/${optionId}`, { method: 'DELETE' });
  }

  // -- form submissions ---------------------------------------------------

  /** Upserts a draft: same (form, visit, employee) triple always resolves to one submission. */
  async saveFormSubmission(data: { form_id: string; visit_id: string; answers: { question_id: string; answer_value: string | null }[] }): Promise<FormSubmission> {
    return this.request<FormSubmission>('/api/v1/form-submissions', { method: 'POST', body: JSON.stringify(data) });
  }

  async submitFormSubmission(submissionId: string): Promise<FormSubmission> {
    return this.request<FormSubmission>(`/api/v1/form-submissions/${submissionId}/submit`, { method: 'POST' });
  }

  async getFormSubmission(submissionId: string): Promise<FormSubmissionDetail> {
    return this.request<FormSubmissionDetail>(`/api/v1/form-submissions/${submissionId}`);
  }

  async getFormSubmissions(params?: { form_id?: string; visit_id?: string }): Promise<FormSubmission[]> {
    const query = params
      ? '?' + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined) as [string, string][]).toString()
      : '';
    return this.request<FormSubmission[]>(`/api/v1/form-submissions${query}`);
  }

  /**
   * The PDF endpoint requires the Authorization header, which a plain
   * `<a href>` cannot send (same reason MediaThumbnail fetches bytes itself -
   * see FT-015). Returns an object URL the caller must revoke after use.
   */
  async getSubmissionPdfObjectUrl(submissionId: string): Promise<string> {
    const response = await fetch(this.url(`/api/v1/form-submissions/${submissionId}/pdf`), {
      headers: this.authHeader(),
    });
    if (!response.ok) {
      throw await this.parseError(response);
    }
    return URL.createObjectURL(await response.blob());
  }

  // -- Excel/MIS import --------------------------------------------------------

  async getImportTargetFields(): Promise<Record<string, ImportTargetFieldConfig>> {
    return this.request<Record<string, ImportTargetFieldConfig>>('/api/v1/imports/target-fields');
  }

  async previewImportFile(file: File, sheetName?: string): Promise<ImportPreviewResponse> {
    const formData = new FormData();
    formData.append('file', file);
    if (sheetName) formData.append('sheet_name', sheetName);
    return this.request<ImportPreviewResponse>('/api/v1/imports/preview', {
      method: 'POST',
      body: formData,
    });
  }

  async validateImportFile(
    file: File,
    request: {
      sheet_name: string;
      column_mapping: Record<string, string>;
      outlet_match_strategy: OutletMatchStrategy;
      allow_generated_invoice_numbers: boolean;
      fos_mapping_overrides?: Record<string, string>;
    },
  ): Promise<ImportBatchRead> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('request', JSON.stringify(request));
    return this.request<ImportBatchRead>('/api/v1/imports/validate', {
      method: 'POST',
      body: formData,
    });
  }

  async commitImportBatch(batchId: string): Promise<ImportBatchRead> {
    return this.request<ImportBatchRead>(`/api/v1/imports/${batchId}/commit`, { method: 'POST' });
  }

  async getImportBatches(skip = 0, limit = 50): Promise<ImportBatchRead[]> {
    return this.request<ImportBatchRead[]>(`/api/v1/imports?skip=${skip}&limit=${limit}`);
  }

  async getImportBatch(batchId: string): Promise<ImportBatchRead> {
    return this.request<ImportBatchRead>(`/api/v1/imports/${batchId}`);
  }

  /** Mirrors getSubmissionPdfObjectUrl's authorized-blob-fetch pattern for a CSV download. */
  async getImportErrorsCsvObjectUrl(batchId: string): Promise<string> {
    const response = await fetch(this.url(`/api/v1/imports/${batchId}/errors.csv`), {
      headers: this.authHeader(),
    });
    if (!response.ok) {
      throw await this.parseError(response);
    }
    return URL.createObjectURL(await response.blob());
  }

  async getImportCredentialsExcelObjectUrl(batchId: string): Promise<string> {
    const response = await fetch(this.url(`/api/v1/imports/${batchId}/credentials.xlsx`), {
      headers: this.authHeader(),
    });
    if (!response.ok) {
      throw await this.parseError(response);
    }
    return URL.createObjectURL(await response.blob());
  }

  async getFOSMappings(): Promise<FOSEmployeeMappingRead[]> {
    return this.request<FOSEmployeeMappingRead[]>('/api/v1/imports/fos-mappings');
  }

  async setFOSMapping(rawFosName: string, employeeId: string): Promise<FOSEmployeeMappingRead> {
    return this.request<FOSEmployeeMappingRead>('/api/v1/imports/fos-mappings', {
      method: 'POST',
      body: JSON.stringify({ raw_fos_name: rawFosName, employee_id: employeeId }),
    });
  }

  // -- Phase 5 Field Exceptions ----------------------------------------------

  async createFieldException(data: import('../types').FieldExceptionCreate): Promise<import('../types').FieldException> {
    return this.request<import('../types').FieldException>('/api/v1/field-exceptions', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getFieldExceptions(params?: {
    status?: string;
    employee_id?: string;
    customer_id?: string;
    skip?: number;
    limit?: number;
  }): Promise<import('../types').FieldException[]> {
    const q: Record<string, string> = {};
    if (params?.status && params.status !== 'ALL') q.status = params.status;
    if (params?.employee_id && params.employee_id !== 'ALL') q.employee_id = params.employee_id;
    if (params?.customer_id) q.customer_id = params.customer_id;
    if (params?.skip !== undefined) q.skip = String(params.skip);
    if (params?.limit !== undefined) q.limit = String(params.limit);
    const qs = new URLSearchParams(q).toString();
    return this.request<import('../types').FieldException[]>(`/api/v1/field-exceptions${qs ? `?${qs}` : ''}`);
  }

  async reviewFieldException(
    exceptionId: string,
    data: import('../types').FieldExceptionReview
  ): Promise<import('../types').FieldException> {
    return this.request<import('../types').FieldException>(`/api/v1/field-exceptions/${exceptionId}/review`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  // -- Phase 6 Dashboard BI & My-Day -----------------------------------------

  async getDashboardSummary(params?: {
    brand?: string;
    zone_id?: string;
    area_id?: string;
    employee_id?: string;
    ageing_bucket?: string;
    month?: string;
  }): Promise<import('../types').DashboardSummaryResponse> {
    const p: Record<string, string> = {};
    if (params?.brand && params.brand !== 'ALL') p.brand = params.brand;
    if (params?.zone_id && params.zone_id !== 'ALL') p.zone_id = params.zone_id;
    if (params?.area_id && params.area_id !== 'ALL') p.area_id = params.area_id;
    if (params?.employee_id && params.employee_id !== 'ALL') p.employee_id = params.employee_id;
    if (params?.ageing_bucket && params.ageing_bucket !== 'ALL') p.ageing_bucket = params.ageing_bucket;
    if (params?.month && params.month !== 'ALL') p.month = params.month;
    const qs = new URLSearchParams(p).toString();
    return this.request<import('../types').DashboardSummaryResponse>(`/api/v1/dashboard/summary${qs ? `?${qs}` : ''}`);
  }

  async getEmployeeDayDashboard(): Promise<import('../types').EmployeeDayDashboardResponse> {
    return this.request<import('../types').EmployeeDayDashboardResponse>('/api/v1/dashboard/my-day');
  }
}

export interface RequirementCategory {
  id: string;
  name: string;
  is_active: boolean;
}

export interface RequirementForm {
  id: string;
  visit_id: string;
  category_id: string;
  category_name: string | null;
  description: string;
  priority: string;
  expected_timeline: string;
  budget_range: string | null;
  notes: string | null;
  submitted_at: string;
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
