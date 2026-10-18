import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiClient, ApiError } from './client';

/**
 * Session resilience + cross-tab refresh coordination.
 *
 * Two "tabs" are two ApiClient instances sharing one localStorage (the session
 * hint / rotation timestamp), one fake cookie jar (the fetch mock) and a mocked
 * BroadcastChannel + Web Locks implementation.
 */

const HINT = 'fieldtrack_session_hint';

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

// -- fake BroadcastChannel (delivers to OTHER instances with the same name) ----
class FakeBroadcastChannel {
  static instances: FakeBroadcastChannel[] = [];
  onmessage: ((ev: MessageEvent) => void) | null = null;
  closed = false;
  constructor(public name: string) {
    FakeBroadcastChannel.instances.push(this);
  }
  postMessage(data: unknown) {
    for (const other of FakeBroadcastChannel.instances) {
      if (other !== this && other.name === this.name && !other.closed) {
        setTimeout(() => other.onmessage?.({ data } as MessageEvent), 0);
      }
    }
  }
  close() {
    this.closed = true;
  }
}

// -- fake Web Locks: a per-name FIFO mutex -----------------------------------
function installFakeLocks() {
  const tails = new Map<string, Promise<unknown>>();
  const locks = {
    request: async <T>(name: string, _opts: unknown, cb: () => Promise<T>): Promise<T> => {
      const prev = tails.get(name) ?? Promise.resolve();
      let release!: () => void;
      const mine = new Promise<void>((r) => (release = r));
      tails.set(name, prev.then(() => mine));
      await prev;
      try {
        return await cb();
      } finally {
        release();
      }
    },
  };
  Object.defineProperty(navigator, 'locks', { configurable: true, value: locks });
}

function uninstallLocks() {
  Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined });
}

/** A fake backend: rotates the refresh cookie on every /auth/refresh and counts/overlaps calls. */
function installFakeBackend(opts: { refresh?: () => Response | Promise<Response> } = {}) {
  const state = { refreshCalls: 0, inFlight: 0, maxInFlight: 0 };
  const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/auth/refresh')) {
      state.refreshCalls += 1;
      state.inFlight += 1;
      state.maxInFlight = Math.max(state.maxInFlight, state.inFlight);
      try {
        await new Promise((r) => setTimeout(r, 20));
        if (opts.refresh) return await opts.refresh();
        return jsonResponse({ access_token: `tok-${state.refreshCalls}`, refresh_token: 'r', token_type: 'bearer' });
      } finally {
        state.inFlight -= 1;
      }
    }
    return jsonResponse({ ok: true });
  });
  return { state, spy };
}

let tabs: ApiClient[] = [];
function newTab(): ApiClient {
  const c = new ApiClient();
  c.startTabSync();
  tabs.push(c);
  return c;
}

beforeEach(() => {
  localStorage.clear();
  FakeBroadcastChannel.instances = [];
  vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel);
  installFakeLocks();
  localStorage.setItem(HINT, '1');
});

afterEach(() => {
  tabs.forEach((t) => t.stopTabSync());
  tabs = [];
  uninstallLocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('cross-tab refresh (Web Locks + BroadcastChannel)', () => {
  it('two tabs restoring at the same time cause exactly ONE network refresh and share the token', async () => {
    const { state } = installFakeBackend();
    const a = newTab();
    const b = newTab();

    const [ra, rb] = await Promise.all([a.restoreSession(), b.restoreSession()]);

    expect(ra).toBe('restored');
    expect(rb).toBe('restored');
    expect(state.refreshCalls).toBe(1);
    expect(state.maxInFlight).toBe(1);
    expect(a.getAccessToken()).toBe('tok-1');
    expect(b.getAccessToken()).toBe('tok-1');
  });

  it('the shared token lives in memory only, never in storage', async () => {
    installFakeBackend();
    const a = newTab();
    newTab();
    await a.restoreSession();
    const stored = Object.keys(localStorage).map((k) => localStorage.getItem(k) ?? '');
    expect(stored.some((v) => v.includes('tok-1'))).toBe(false);
  });

  it('parallel 401s in two tabs after the token expired rotate the cookie exactly once', async () => {
    const { state, spy } = installFakeBackend();
    const a = newTab();
    const b = newTab();
    // Both tabs hold an expired token; every data call with it is a 401.
    (a as unknown as { accessToken: string }).accessToken = 'expired';
    (b as unknown as { accessToken: string }).accessToken = 'expired';
    spy.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes('/auth/refresh')) {
        state.refreshCalls += 1;
        state.inFlight += 1;
        state.maxInFlight = Math.max(state.maxInFlight, state.inFlight);
        await new Promise((r) => setTimeout(r, 20));
        state.inFlight -= 1;
        return jsonResponse({ access_token: 'fresh', refresh_token: 'r', token_type: 'bearer' });
      }
      const auth = ((init as RequestInit)?.headers as Record<string, string>)?.Authorization;
      return auth === 'Bearer fresh' ? jsonResponse({ ok: true }) : jsonResponse({}, 401);
    });

    await Promise.all([a.getHealth(), b.getHealth()]);

    expect(state.refreshCalls).toBe(1);
    expect(state.maxInFlight).toBe(1);
  });

  it('a tab whose 401 raced another tab refresh retries with the shared token instead of refreshing again', async () => {
    const { state, spy } = installFakeBackend();
    const a = newTab();
    const b = newTab();
    (b as unknown as { accessToken: string }).accessToken = 'old';
    let first = true;
    const inner = spy.getMockImplementation()!;
    spy.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes('/health')) {
        const auth = ((init as RequestInit)?.headers as Record<string, string>)?.Authorization;
        if (first) {
          first = false;
          await a.restoreSession(); // the other tab refreshes (and broadcasts) while our request is in flight
          await new Promise((r) => setTimeout(r, 5));
          return jsonResponse({}, 401);
        }
        return auth === 'Bearer tok-1' ? jsonResponse({ ok: true }) : jsonResponse({}, 401);
      }
      return inner(input, init);
    });

    await expect(b.getHealth()).resolves.toBeTruthy();
    expect(state.refreshCalls).toBe(1);
  });

  it('without BroadcastChannel the tabs still never overlap: the second tab refreshes AFTER the first, with the rotated cookie', async () => {
    vi.stubGlobal('BroadcastChannel', undefined);
    const { state } = installFakeBackend();
    const a = newTab();
    const b = newTab();

    const [ra, rb] = await Promise.all([a.restoreSession(), b.restoreSession()]);

    expect(ra).toBe('restored');
    expect(rb).toBe('restored');
    expect(state.maxInFlight).toBe(1); // never two requests with the same cookie at once
    expect(state.refreshCalls).toBe(2); // second one is a sequential retry with the new cookie
  });

  it('without Web Locks or BroadcastChannel the localStorage lease still serialises refreshes', async () => {
    uninstallLocks();
    vi.stubGlobal('BroadcastChannel', undefined);
    const { state } = installFakeBackend();
    const a = newTab();
    const b = newTab();

    const [ra, rb] = await Promise.all([a.restoreSession(), b.restoreSession()]);

    expect([ra, rb]).toEqual(['restored', 'restored']);
    expect(state.maxInFlight).toBe(1);
    await new Promise((r) => setTimeout(r, 300));
    expect(localStorage.getItem('fieldtrack_refresh_lease')).toBeNull(); // released
  });

  it('a 401 from refresh while another tab rotated the cookie is retried ONCE with the new cookie', async () => {
    let n = 0;
    const { state } = installFakeBackend({
      refresh: () => {
        n += 1;
        if (n === 1) {
          // another tab rotated the cookie while this request was in flight
          localStorage.setItem('fieldtrack_refresh_rotated_at', String(Date.now() + 5));
          return jsonResponse({ error: { code: 'AUTH_INVALID_REFRESH_TOKEN' } }, 401);
        }
        return jsonResponse({ access_token: 'second', refresh_token: 'r', token_type: 'bearer' });
      },
    });
    const a = newTab();
    expect(await a.restoreSession()).toBe('restored');
    expect(state.refreshCalls).toBe(2);
    expect(a.getAccessToken()).toBe('second');
    expect(localStorage.getItem(HINT)).toBe('1');
  });
});

describe('only a definitive 401/403 from /auth/refresh ends the session', () => {
  it.each([401, 403])('HTTP %s clears the hint and token and reports rejected', async (status) => {
    installFakeBackend({ refresh: () => jsonResponse({}, status) });
    const a = newTab();
    expect(await a.restoreSession()).toBe('rejected');
    expect(localStorage.getItem(HINT)).toBeNull();
    expect(a.getAccessToken()).toBeNull();
  });

  it.each([500, 502, 503, 504, 429])('HTTP %s keeps the hint and reports transient', async (status) => {
    installFakeBackend({ refresh: () => jsonResponse({}, status) });
    const a = newTab();
    expect(await a.restoreSession()).toBe('transient');
    expect(localStorage.getItem(HINT)).toBe('1');
  });

  it('a network error keeps the hint, keeps the in-memory token, and surfaces a retryable error', async () => {
    const a = newTab();
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse({ access_token: 'live', refresh_token: 'r', token_type: 'bearer' }),
    );
    await a.login('u@example.com', 'pw');

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input).includes('/auth/refresh')) throw new TypeError('Failed to fetch');
      return jsonResponse({}, 401);
    });
    const onExpired = vi.fn();
    a.onSessionExpired(onExpired);

    const err = await a.getHealth().catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).retryable).toBe(true);
    expect((err as ApiError).code).toBe('REFRESH_UNAVAILABLE');
    expect(onExpired).not.toHaveBeenCalled();
    expect(a.getAccessToken()).toBe('live');
    expect(localStorage.getItem(HINT)).toBe('1');
    expect(fetchSpy).toHaveBeenCalled();
  });

  it('a refresh that hangs is aborted after the timeout and treated as transient', async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      (_input, init) =>
        new Promise((_resolve, reject) => {
          (init as RequestInit).signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
        }),
    );
    const a = newTab();
    const p = a.restoreSession();
    await vi.advanceTimersByTimeAsync(21_000);
    expect(await p).toBe('transient');
    expect(localStorage.getItem(HINT)).toBe('1');
  });

  it('a real 401 on the data call + 401 on refresh DOES end the session and notifies once', async () => {
    const a = newTab();
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse({ access_token: 'live', refresh_token: 'r', token_type: 'bearer' }),
    );
    await a.login('u@example.com', 'pw');
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => jsonResponse({}, 401));
    const onExpired = vi.fn();
    a.onSessionExpired(onExpired);
    await expect(a.getHealth()).rejects.toBeInstanceOf(ApiError);
    expect(onExpired).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(HINT)).toBeNull();
  });

  it('getCurrentUser distinguishes an unreachable server from a rejected session', async () => {
    const a = newTab();
    installFakeBackend({ refresh: () => jsonResponse({}, 503) });
    const err = await a.getCurrentUser().catch((e: unknown) => e);
    expect((err as ApiError).retryable).toBe(true);
    expect(localStorage.getItem(HINT)).toBe('1');
  });
});

describe('logout propagates across tabs', () => {
  it('logging out in tab A logs out tab B and clears the hint', async () => {
    const a = newTab();
    const b = newTab();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ access_token: 'live', refresh_token: 'r', token_type: 'bearer' }),
    );
    await a.login('u@example.com', 'pw');
    (b as unknown as { accessToken: string }).accessToken = 'live';
    const onRemote = vi.fn();
    b.onRemoteLogout(onRemote);

    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }));
    await a.logout();
    await new Promise((r) => setTimeout(r, 10));

    expect(onRemote).toHaveBeenCalledTimes(1);
    expect(b.getAccessToken()).toBeNull();
    expect(localStorage.getItem(HINT)).toBeNull();
  });

  it('falls back to the storage event when BroadcastChannel is unavailable', async () => {
    vi.stubGlobal('BroadcastChannel', undefined);
    const b = newTab();
    const onRemote = vi.fn();
    b.onRemoteLogout(onRemote);
    window.dispatchEvent(new StorageEvent('storage', { key: 'fieldtrack_logout_at', newValue: String(Date.now()) }));
    expect(onRemote).toHaveBeenCalledTimes(1);
  });
});

describe('PASSWORD_CHANGE_REQUIRED', () => {
  it('notifies listeners and maps to a friendly message', async () => {
    const a = newTab();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      jsonResponse({ error: { code: 'PASSWORD_CHANGE_REQUIRED', message: 'backend text' } }, 403),
    );
    const listener = vi.fn();
    a.onPasswordChangeRequired(listener);
    const err = (await a.getHealth().catch((e: unknown) => e)) as ApiError;
    expect(err.code).toBe('PASSWORD_CHANGE_REQUIRED');
    expect(err.message).toMatch(/set a new password/i);
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
