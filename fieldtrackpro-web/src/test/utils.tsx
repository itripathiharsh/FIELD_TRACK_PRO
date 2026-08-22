import React from 'react';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { AuthProvider } from '../context/AuthContext';
import { Customer, Employee, Territory, User, Visit, VisitMedia } from '../types';
import { apiClient } from '../api/client';

/**
 * Shared test helpers.
 *
 * These build realistic API payloads that match the REAL backend schemas, so a
 * future contract drift shows up as a type error here rather than as a silent
 * runtime bug in the browser.
 */

export const ADMIN_USER: User = {
  id: '11111111-1111-1111-1111-111111111111',
  email: 'admin@fieldtrack.test',
  mobile_number: null,
  full_name: 'Test Administrator',
  role: 'ADMIN',
  is_active: true,
  territory_id: null,
  employee_id: null,
};

export const EMPLOYEE_USER: User = {
  id: '22222222-2222-2222-2222-222222222222',
  email: 'rep@fieldtrack.test',
  mobile_number: null,
  full_name: 'Test Field Rep',
  role: 'EMPLOYEE',
  is_active: true,
  territory_id: '44444444-4444-4444-4444-444444444444',
  employee_id: '33333333-3333-3333-3333-333333333333',
};

export const TERRITORY: Territory = {
  id: '44444444-4444-4444-4444-444444444444',
  name: 'North Region',
  created_at: '2026-01-01T00:00:00Z',
};

export const EMPLOYEE: Employee = {
  id: '33333333-3333-3333-3333-333333333333',
  user_id: EMPLOYEE_USER.id,
  full_name: 'Test Field Rep',
  territory_id: TERRITORY.id,
  employee_code: 'EMP-001',
  created_at: '2026-01-01T00:00:00Z',
  user: {
    id: EMPLOYEE_USER.id,
    email: EMPLOYEE_USER.email,
    mobile_number: null,
    role: 'EMPLOYEE',
    is_active: true,
  },
};

export const CUSTOMER: Customer = {
  id: '55555555-5555-5555-5555-555555555555',
  name: 'Acme Industrial',
  contact_number: '+919876543210',
  contact_person: 'Jane Smith',
  address: '100 Tech Park Blvd',
  location: { latitude: 12.9716, longitude: 77.5946 },
  geofence_radius_m: 75,
  outlet_code: 'OUT-001',
  territory_id: TERRITORY.id,
  area_id: null,
  area_name: null,
  created_by: ADMIN_USER.id,
  created_at: '2026-01-01T00:00:00Z',
};

export const VISIT: Visit = {
  id: '66666666-6666-6666-6666-666666666666',
  customer_id: CUSTOMER.id,
  employee_id: EMPLOYEE.id,
  scheduled_at: '2026-08-09T10:00:00Z',
  status: 'PENDING',
  check_in_at: null,
  check_out_at: null,
  synced: false,
  created_by: ADMIN_USER.id,
  created_at: '2026-08-08T10:00:00Z',
  updated_at: '2026-08-08T10:00:00Z',
  required_form_id: null,
  required_form_name: null,
  required_form_status: null,
};

export const MEDIA: VisitMedia = {
  id: '77777777-7777-7777-7777-777777777777',
  visit_id: VISIT.id,
  media_type: 'PHOTO',
  storage_key: `visits/${VISIT.id}/77777777_site.jpg`,
  file_size_bytes: 2048,
  uploaded_at: '2026-08-08T11:00:00Z',
};

/** JSON Response helper. */
export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** A route handler, or a literal body to serialise as JSON. */
export type RouteHandler = (url: string, init?: RequestInit) => Response | Promise<Response>;

/** A literal JSON body, or a handler for dynamic responses. */
export type RouteValue = RouteHandler | object | unknown[] | null;

export type RouteMap = Record<string, RouteValue>;

/**
 * Wrap a route handler so its parameters are inferred at the call site.
 *
 * Without this, a union-typed map entry widens to `unknown` and every inline
 * handler needs explicit annotations.
 */
export const route = (handler: RouteHandler): RouteHandler => handler;

/**
 * Install a fetch stub that answers by URL substring.
 *
 * Unmatched URLs return 404 rather than silently succeeding, so a test cannot
 * accidentally pass because a call it forgot to model returned an empty object.
 */
export function mockApi(routes: RouteMap) {
  // Longest pattern first, so a specific route such as `/api/v1/visits/me/today`
  // is never swallowed by the more general `/api/v1/visits`.
  const ordered = Object.entries(routes).sort((a, b) => b[0].length - a[0].length);

  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = String(input);
    // Compare against the path only, so a query string cannot defeat matching.
    const path = url.split('?')[0];

    for (const [pattern, value] of ordered) {
      // The pattern must match the END of the path, or be followed by a path
      // separator. `/api/v1/visits` therefore matches `/api/v1/visits` and
      // `/api/v1/visits/{id}`, while `/api/v1/employees` can never be
      // satisfied by an unrelated route that merely contains the substring.
      const index = path.indexOf(pattern);
      if (index === -1) continue;
      const next = path.charAt(index + pattern.length);
      const isMatch = next === '' || next === '/';
      if (!isMatch) continue;

      if (typeof value === 'function') {
        return (value as (u: string, i?: RequestInit) => Response | Promise<Response>)(url, init);
      }
      return json(value);
    }
    return json({ error: { code: 'NOT_MOCKED', message: `Unmocked request: ${url}` } }, 404);
  });
}

/**
 * Routes every page needs.
 *
 * `/auth/refresh` is included because FT-040 keeps the access token in memory
 * only: on a fresh mount the client legitimately mints one from the stored
 * refresh token before calling `/auth/me`. Omitting it would make every page
 * test render a signed-out shell.
 */
export function baseRoutes(user: User): RouteMap {
  return {
    '/health': { status: 'UP', service: 'FieldTrack Pro API' },
    '/api/v1/auth/refresh': {
      access_token: 'test-access-token',
      refresh_token: 'test-refresh-token',
      token_type: 'bearer',
    },
    '/api/v1/auth/me': user,
  };
}

/** Render a component inside a router and an authenticated provider. */
export function renderWithProviders(
  ui: React.ReactElement,
  { route = '/' }: { route?: string } = {},
) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>{ui}</AuthProvider>
    </MemoryRouter>,
  );
}

/** Seed a session so AuthProvider resolves to the given user. */
export function signIn(user: User) {
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('fieldtrack_refresh_token', 'test-refresh-token');
    }
  } catch {
    // Ignore
  }
  try {
    if (typeof (apiClient as unknown as { storeSession?: (tokens: unknown) => void })?.storeSession === 'function') {
      (apiClient as unknown as { storeSession: (tokens: unknown) => void }).storeSession({
        access_token: 'test-access-token',
        refresh_token: 'test-refresh-token',
        token_type: 'bearer',
      });
    }
  } catch {
    // Ignore
  }
  return user;
}
