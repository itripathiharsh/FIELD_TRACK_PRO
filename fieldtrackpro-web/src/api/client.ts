import { ENV } from '../config/env';
import {
  Customer,
  GeoVerificationLog,
  LoginResponse,
  User,
  Visit,
  VisitMedia,
  VisitStatus
} from '../types';

export class ApiClient {
  private baseUrl: string;

  constructor() {
    this.baseUrl = ENV.API_BASE_URL || 'http://127.0.0.1:8000';
  }

  private getAuthHeader(): Record<string, string> {
    const token = localStorage.getItem('fieldtrack_access_token');
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const cleanBase = this.baseUrl.replace(/\/api\/v1\/?$/, '').replace(/\/+$/, '');
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${cleanBase}${cleanEndpoint}`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...this.getAuthHeader(),
      ...(options.headers as Record<string, string> || {}),
    };

    const response = await fetch(url, { ...options, headers });
    if (!response.ok) {
      const errText = await response.text().catch(() => '');
      throw new Error(`API Error (${response.status}): ${errText || response.statusText}`);
    }
    return response.json();
  }

  async getHealth(): Promise<{ status: string; service?: string }> {
    return this.request<{ status: string; service?: string }>('/health');
  }

  // Authentication
  async login(identity: string, pass: string): Promise<LoginResponse> {
    const isEmail = identity.includes('@');
    const body = {
      email: isEmail ? identity : null,
      mobile: !isEmail ? identity : null,
      password: pass,
    };
    const tokens = await this.request<LoginResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    localStorage.setItem('fieldtrack_access_token', tokens.access_token);
    localStorage.setItem('fieldtrack_refresh_token', tokens.refresh_token);
    return tokens;
  }

  async getCurrentUser(): Promise<User> {
    return this.request<User>('/api/v1/auth/me');
  }

  logout(): void {
    localStorage.removeItem('fieldtrack_access_token');
    localStorage.removeItem('fieldtrack_refresh_token');
  }

  // Users & Employees
  async getUsers(): Promise<User[]> {
    return this.request<User[]>('/api/v1/users');
  }

  async createUser(userData: Partial<User> & { password: string }): Promise<User> {
    return this.request<User>('/api/v1/users', {
      method: 'POST',
      body: JSON.stringify(userData),
    });
  }

  // Customers
  async getCustomers(): Promise<Customer[]> {
    return this.request<Customer[]>('/api/v1/customers');
  }

  async getCustomerById(id: string): Promise<Customer> {
    return this.request<Customer>(`/api/v1/customers/${id}`);
  }

  async createCustomer(cust: Partial<Customer>): Promise<Customer> {
    return this.request<Customer>('/api/v1/customers', {
      method: 'POST',
      body: JSON.stringify(cust),
    });
  }

  // Territories
  async getTerritories(): Promise<{ id: string; name: string; code: string }[]> {
    return this.request<{ id: string; name: string; code: string }[]>('/api/v1/territories');
  }

  // Visits
  async getVisits(status?: VisitStatus): Promise<Visit[]> {
    const query = status ? `?status=${status}` : '';
    return this.request<Visit[]>(`/api/v1/visits${query}`);
  }

  async getVisitById(id: string): Promise<Visit> {
    return this.request<Visit>(`/api/v1/visits/${id}`);
  }

  async getVisitGeoLogs(visitId: string): Promise<GeoVerificationLog[]> {
    return this.request<GeoVerificationLog[]>(`/api/v1/visits/${visitId}/geo-logs`);
  }

  async createVisit(data: { customer_id: string; employee_id: string; scheduled_at: string }): Promise<Visit> {
    return this.request<Visit>('/api/v1/visits', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async checkIn(visitId: string, data: { latitude: number; longitude: number; accuracy_m?: number; is_mock_location?: boolean }): Promise<Visit> {
    return this.request<Visit>(`/api/v1/visits/${visitId}/check-in`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async checkOut(visitId: string, data: { latitude: number; longitude: number; accuracy_m?: number; is_mock_location?: boolean }): Promise<Visit> {
    return this.request<Visit>(`/api/v1/visits/${visitId}/check-out`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Media
  async getVisitMedia(visitId: string): Promise<VisitMedia[]> {
    return this.request<VisitMedia[]>(`/api/v1/visits/${visitId}/media`);
  }

  async uploadMedia(visitId: string, file: File): Promise<VisitMedia> {
    const url = `${this.baseUrl}/api/v1/visits/${visitId}/media`;
    const formData = new FormData();
    formData.append('file', file);

    const token = localStorage.getItem('fieldtrack_access_token');
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      const errText = await response.text().catch(() => '');
      throw new Error(`Media Upload Error (${response.status}): ${errText || response.statusText}`);
    }
    return response.json();
  }
}

export const apiClient = new ApiClient();

