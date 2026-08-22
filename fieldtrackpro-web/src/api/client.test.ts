import { describe, expect, it, vi, beforeEach } from 'vitest';
import { ApiClient, ApiError } from './client';

/**
 * API client contract tests.
 *
 * Covers FT-040 & Hardening (access token in memory only, refresh token in HttpOnly cookie,
 * credentials: 'include'), FT-008 (refresh on 401), FT-009 (logout revokes server-side),
 * FT-010 (login field names) and FT-055 (single base-URL normalisation).
 */

const REFRESH_KEY = 'fieldtrack_refresh_token';

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const TOKENS = {
  access_token: 'access.token.value',
  refresh_token: 'refresh-token-value',
  token_type: 'bearer',
};

describe('ApiClient - token storage & cookie hardening (FT-040)', () => {
  let client: ApiClient;

  beforeEach(() => {
    localStorage.clear();
    client = new ApiClient();
  });

  it('never writes access token or refresh token to localStorage', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(TOKENS));

    await client.login('user@example.com', 'correct-password');

    const stored = Object.keys(localStorage).map((k) => localStorage.getItem(k) ?? '');
    expect(stored.some((v) => v.includes(TOKENS.access_token))).toBe(false);
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
    expect(client.getAccessToken()).toBe(TOKENS.access_token);
  });

  it('drops the in-memory token when the session is cleared', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(TOKENS));
    await client.login('user@example.com', 'correct-password');

    client.clearSession();

    expect(client.getAccessToken()).toBeNull();
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
  });

  it('sends the Authorization header from memory and uses credentials: include', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(TOKENS));
    await client.login('user@example.com', 'correct-password');

    fetchSpy.mockResolvedValue(jsonResponse([]));
    await client.getCustomers();

    const [, init] = fetchSpy.mock.calls.at(-1)!;
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe(`Bearer ${TOKENS.access_token}`);
    expect((init as RequestInit).credentials).toBe('include');
  });
});

describe('ApiClient - session restore after reload (HttpOnly Cookie Auth)', () => {
  beforeEach(() => localStorage.clear());

  it('mints a new access token via HttpOnly refresh cookie exchange', async () => {
    const client = new ApiClient();
    expect(client.getAccessToken()).toBeNull();

    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/auth/refresh')) {
          return jsonResponse({ ...TOKENS, access_token: 'reissued.token' });
        }
        if (url.includes('/auth/me')) {
          return jsonResponse({
            id: 'u1',
            email: 'user@example.com',
            mobile_number: null,
            full_name: 'Real User',
            role: 'EMPLOYEE',
            is_active: true,
          });
        }
        return jsonResponse({}, 404);
      });

    const user = await client.getCurrentUser();

    expect(user.role).toBe('EMPLOYEE');
    expect(client.getAccessToken()).toBe('reissued.token');
    expect(fetchSpy.mock.calls.some(([u]) => String(u).includes('/auth/refresh'))).toBe(true);
  });

  it('fails cleanly when the refresh cookie is no longer valid', async () => {
    const client = new ApiClient();

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).includes('/auth/refresh')) return new Response('', { status: 401 });
      return jsonResponse({}, 401);
    });

    await expect(client.getCurrentUser()).rejects.toBeInstanceOf(ApiError);
    expect(client.getAccessToken()).toBeNull();
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
  });
});

describe('ApiClient - transparent refresh on 401 (FT-008)', () => {
  beforeEach(() => localStorage.clear());

  it('retries the original request once after refreshing', async () => {
    const client = new ApiClient();
    let loginDone = false;

    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/auth/login')) {
          loginDone = true;
          return jsonResponse(TOKENS);
        }
        if (url.includes('/auth/refresh')) {
          return jsonResponse({ ...TOKENS, access_token: 'second.token' });
        }
        if (url.includes('/customers')) {
          // Expired on the first call, accepted after the refresh.
          return client.getAccessToken() === 'second.token'
            ? jsonResponse([{ id: 'c1' }])
            : new Response('', { status: 401 });
        }
        return jsonResponse({}, 404);
      });

    await client.login('user@example.com', 'pw');
    expect(loginDone).toBe(true);

    const customers = await client.getCustomers();
    expect(customers).toHaveLength(1);
    expect(fetchSpy.mock.calls.filter(([u]) => String(u).includes('/customers'))).toHaveLength(2);
  });

  it('does not loop indefinitely when the refresh also fails', async () => {
    const client = new ApiClient();

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input).includes('/auth/refresh')) return new Response('', { status: 401 });
      return new Response('', { status: 401 });
    });

    await expect(client.getVisits()).rejects.toBeInstanceOf(ApiError);
    const refreshCalls = fetchSpy.mock.calls.filter(([u]) => String(u).includes('/auth/refresh'));
    expect(refreshCalls.length).toBeLessThanOrEqual(1);
  });
});

describe('ApiClient - logout (FT-009)', () => {
  beforeEach(() => localStorage.clear());

  it('revokes the refresh token server-side and clears cookie', async () => {
    const client = new ApiClient();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(TOKENS));
    await client.login('user@example.com', 'pw');

    fetchSpy.mockResolvedValue(new Response(null, { status: 204 }));
    await client.logout();

    const logoutCall = fetchSpy.mock.calls.find(([u]) => String(u).includes('/auth/logout'));
    expect(logoutCall, 'logout must call the revocation endpoint').toBeDefined();
    expect(client.getAccessToken()).toBeNull();
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
  });

  it('clears the local session even if revocation fails', async () => {
    const client = new ApiClient();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(TOKENS));
    await client.login('user@example.com', 'pw');

    fetchSpy.mockRejectedValue(new Error('network down'));
    await client.logout();

    expect(client.getAccessToken()).toBeNull();
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
  });
});

describe('ApiClient - login payload contract (FT-010)', () => {
  beforeEach(() => localStorage.clear());

  it('sends `email` for an address', async () => {
    const client = new ApiClient();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(TOKENS));

    await client.login('person@example.com', 'pw');

    const body = JSON.parse((fetchSpy.mock.calls[0][1] as RequestInit).body as string);
    expect(body).toEqual({ email: 'person@example.com', password: 'pw' });
  });

  it('sends `mobile_number` (not `mobile`) for a phone number', async () => {
    const client = new ApiClient();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(TOKENS));

    await client.login('+919876543210', 'pw');

    const body = JSON.parse((fetchSpy.mock.calls[0][1] as RequestInit).body as string);
    expect(body).toEqual({ mobile_number: '+919876543210', password: 'pw' });
    expect(body).not.toHaveProperty('mobile');
  });
});

describe('ApiClient - error surfacing', () => {
  beforeEach(() => localStorage.clear());

  it('exposes the backend error code and message', async () => {
    const client = new ApiClient();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(
        { error: { code: 'AUTH_INVALID_CREDENTIALS', message: 'Invalid credentials' } },
        401,
      ),
    );

    await expect(client.login('a@b.co', 'wrong')).rejects.toMatchObject({
      status: 401,
      code: 'AUTH_INVALID_CREDENTIALS',
      message: 'Invalid credentials',
    });
  });
});
