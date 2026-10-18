import { describe, expect, it, vi, beforeEach } from 'vitest';
import { ApiClient, ApiError } from './client';

/**
 * API client contract tests.
 *
 * Covers FT-040 & Hardening (access token in memory only, refresh token in HttpOnly cookie,
 * credentials: 'include'), FT-008 (refresh on 401), FT-009 (logout revokes server-side),
 * FT-010 (login field names), FT-055 (single base-URL normalisation), and WEB-H-1 (export token refresh).
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

describe('ApiClient - export token refresh (WEB-H-1)', () => {
  beforeEach(() => {
    localStorage.clear();
    if (!URL.createObjectURL) URL.createObjectURL = vi.fn().mockReturnValue('blob:test-url');
  });

  it('retries export request after transparent token refresh on 401', async () => {
    const client = new ApiClient();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/auth/login')) {
        return jsonResponse(TOKENS);
      }
      if (url.includes('/auth/refresh')) {
        return jsonResponse({ ...TOKENS, access_token: 'fresh.token' });
      }
      if (url.includes('/reports/overview/export')) {
        return client.getAccessToken() === 'fresh.token'
          ? new Response(new Blob(['col1,col2\nval1,val2']), { status: 200 })
          : new Response('', { status: 401 });
      }
      return jsonResponse({}, 404);
    });

    await client.login('user@example.com', 'pw');
    const objectUrl = await client.exportOverviewExcelObjectUrl();
    expect(objectUrl).toBe('blob:test-url');
  });

  it('throws ApiError and cleans up when refresh fails during export', async () => {
    const client = new ApiClient();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/auth/refresh')) return new Response('', { status: 401 });
      return new Response('', { status: 401 });
    });

    await expect(client.exportOverviewExcelObjectUrl()).rejects.toBeInstanceOf(ApiError);
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

describe('ApiClient - expired session notification', () => {
  beforeEach(() => localStorage.clear());

  it('notifies listeners when a 401 cannot be refreshed mid-session', async () => {
    const client = new ApiClient();
    const listener = vi.fn();
    client.onSessionExpired(listener);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    fetchSpy.mockResolvedValueOnce(jsonResponse(TOKENS)); // login
    await client.login('user@example.com', 'pw');

    fetchSpy.mockResolvedValueOnce(jsonResponse({ detail: 'expired' }, 401)); // data call
    fetchSpy.mockResolvedValueOnce(jsonResponse({ detail: 'nope' }, 401)); // refresh fails

    await expect(client.getHealth()).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(client.getAccessToken()).toBeNull();
  });

  it('does not notify when there was no session (plain unauthenticated 401)', async () => {
    const client = new ApiClient();
    const listener = vi.fn();
    client.onSessionExpired(listener);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ detail: 'x' }, 401));

    await expect(client.getHealth()).rejects.toBeInstanceOf(ApiError);
    expect(listener).not.toHaveBeenCalled();
  });

  it('does NOT log out on a transient refresh failure (5xx / Render cold start)', async () => {
    const client = new ApiClient();
    const listener = vi.fn();
    client.onSessionExpired(listener);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    fetchSpy.mockResolvedValueOnce(jsonResponse(TOKENS)); // login
    await client.login('user@example.com', 'pw');

    fetchSpy.mockResolvedValueOnce(jsonResponse({ detail: 'expired' }, 401)); // data call
    fetchSpy.mockResolvedValueOnce(jsonResponse({ detail: 'bad gateway' }, 502)); // refresh: transient

    await expect(client.getHealth()).rejects.toBeInstanceOf(ApiError);
    expect(listener).not.toHaveBeenCalled();
    // Session is NOT cleared on a transient failure - still "logged in" in-memory.
    expect(client.getAccessToken()).toBe(TOKENS.access_token);
  });

  it('does NOT log out on a network error during refresh', async () => {
    const client = new ApiClient();
    const listener = vi.fn();
    client.onSessionExpired(listener);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    fetchSpy.mockResolvedValueOnce(jsonResponse(TOKENS)); // login
    await client.login('user@example.com', 'pw');

    fetchSpy.mockResolvedValueOnce(jsonResponse({ detail: 'expired' }, 401)); // data call
    fetchSpy.mockRejectedValueOnce(new TypeError('network error')); // refresh: network failure

    await expect(client.getHealth()).rejects.toBeInstanceOf(ApiError);
    expect(listener).not.toHaveBeenCalled();
    expect(client.getAccessToken()).toBe(TOKENS.access_token);
  });

  it('DOES log out when the refresh is genuinely rejected (403 account disabled)', async () => {
    const client = new ApiClient();
    const listener = vi.fn();
    client.onSessionExpired(listener);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    fetchSpy.mockResolvedValueOnce(jsonResponse(TOKENS)); // login
    await client.login('user@example.com', 'pw');

    fetchSpy.mockResolvedValueOnce(jsonResponse({ detail: 'expired' }, 401)); // data call
    fetchSpy.mockResolvedValueOnce(jsonResponse({ detail: 'disabled' }, 403)); // refresh: rejected

    await expect(client.getHealth()).rejects.toBeInstanceOf(ApiError);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(client.getAccessToken()).toBeNull();
  });
});


describe('ApiClient - payment Tally lifecycle & ad-hoc review endpoints', () => {
  let client: ApiClient;
  beforeEach(() => {
    localStorage.clear();
    client = new ApiClient();
  });

  it('verifyPayment sends no body when the bank fields are blank, and trimmed fields otherwise', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => jsonResponse({ id: 'p1' }));
    await client.verifyPayment('p1', { bank_reference: '  ', verified_note: '' });
    let [url, init] = fetchSpy.mock.calls.at(-1)!;
    expect(String(url)).toContain('/api/v1/payments/p1/verify');
    expect((init as RequestInit).body).toBeUndefined();

    await client.verifyPayment('p1', { bank_reference: ' R1 ', bank_verified_on: '2026-08-01' });
    [url, init] = fetchSpy.mock.calls.at(-1)!;
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      bank_reference: 'R1',
      bank_verified_on: '2026-08-01',
    });
  });

  it('getPaymentReviewQueue sends tally_status and stuck; retryPaymentTally POSTs to /tally-retry', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => jsonResponse([]));
    await client.getPaymentReviewQueue('VERIFIED', { tally_status: 'FAILED', stuck: true });
    expect(String(fetchSpy.mock.calls.at(-1)![0])).toContain(
      '/api/v1/payments/queue?status=VERIFIED&tally_status=FAILED&stuck=true',
    );

    await client.retryPaymentTally('p9');
    const [url, init] = fetchSpy.mock.calls.at(-1)!;
    expect(String(url)).toContain('/api/v1/payments/p9/tally-retry');
    expect((init as RequestInit).method).toBe('POST');
  });

  it('getAdhocReviewVisits reads X-Total-Count and sends outside_assignment', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () =>
        new Response(JSON.stringify([{ id: 'v1' }]), {
          status: 200,
          headers: { 'Content-Type': 'application/json', 'X-Total-Count': '42' },
        }),
    );
    const res = await client.getAdhocReviewVisits({ outside_assignment: true, skip: 20, limit: 20 });
    expect(res.total).toBe(42);
    expect(res.items).toHaveLength(1);
    expect(String(fetchSpy.mock.calls.at(-1)![0])).toContain(
      '/api/v1/visits/adhoc-review?outside_assignment=true&skip=20&limit=20',
    );
  });
});

describe('ApiClient - single-flight refresh & session hint', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('shares ONE network refresh between N concurrent restore calls', async () => {
    localStorage.setItem('fieldtrack_session_hint', '1');
    const client = new ApiClient();
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      await gate;
      return jsonResponse(TOKENS);
    });

    const calls = Array.from({ length: 6 }, () => client.tryRestoreSession());
    release();
    const results = await Promise.all(calls);

    expect(results.every(Boolean)).toBe(true);
    const refreshCalls = fetchSpy.mock.calls.filter(([u]) => String(u).includes('/auth/refresh'));
    expect(refreshCalls).toHaveLength(1);
  });

  it('clears the in-flight promise so a later refresh sends a new request', async () => {
    localStorage.setItem('fieldtrack_session_hint', '1');
    const client = new ApiClient();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => jsonResponse(TOKENS));
    await client.tryRestoreSession();
    (client as unknown as { accessToken: string | null }).accessToken = null;
    await client.tryRestoreSession();
    const refreshCalls = fetchSpy.mock.calls.filter(([u]) => String(u).includes('/auth/refresh'));
    expect(refreshCalls).toHaveLength(2);
  });

  it('parallel 401s trigger exactly one refresh', async () => {
    const client = new ApiClient();
    let refreshed = false;
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/auth/refresh')) {
        refreshed = true;
        return jsonResponse(TOKENS);
      }
      return refreshed ? jsonResponse({ ok: true }) : new Response('{}', { status: 401 });
    });
    await Promise.all([client.getHealth(), client.getHealth(), client.getHealth()]);
    const refreshCalls = fetchSpy.mock.calls.filter(([u]) => String(u).includes('/auth/refresh'));
    expect(refreshCalls).toHaveLength(1);
  });

  it('anonymous restore (no session hint) sends no refresh request', async () => {
    const client = new ApiClient();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(TOKENS));
    expect(await client.tryRestoreSession()).toBe(false);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('login sets the hint and clearSession removes it', async () => {
    const client = new ApiClient();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(TOKENS));
    await client.login('u@example.com', 'pw');
    expect(localStorage.getItem('fieldtrack_session_hint')).toBe('1');
    client.clearSession();
    expect(localStorage.getItem('fieldtrack_session_hint')).toBeNull();
  });
});
