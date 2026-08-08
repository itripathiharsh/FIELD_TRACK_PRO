import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

import { AuthProvider, useAuth } from './AuthContext';

/**
 * FT-001 (CRITICAL) - authentication bypass.
 *
 * The security contract these tests defend:
 *
 *   1. A failed login NEVER produces an authenticated session.
 *   2. A failed login NEVER fabricates a user (and never an ADMIN).
 *   3. A failed login NEVER writes a token to storage.
 *   4. An unusable stored token NEVER restores a fabricated session.
 *   5. The real backend error is surfaced to the caller, not swallowed.
 *
 * These are behavioural assertions on AuthContext only; the backend's own
 * 401 behaviour is covered by tests/integration/test_auth_integration.py.
 */

const TOKEN_KEY = 'fieldtrack_access_token';
const REFRESH_KEY = 'fieldtrack_refresh_token';

function AuthProbe() {
  const { user, isAuthenticated, isLoading, login, logout } = useAuth();
  const [error, setError] = React.useState<string | null>(null);

  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="role">{user?.role ?? 'none'}</span>
      <span data-testid="email">{user?.email ?? 'none'}</span>
      <span data-testid="error">{error ?? 'none'}</span>
      <button
        onClick={async () => {
          setError(null);
          try {
            await login('attacker@nowhere.invalid', 'wrong-password');
          } catch (e) {
            setError(e instanceof Error ? e.message : 'unknown');
          }
        }}
      >
        do-login
      </button>
      <button onClick={() => logout()}>do-logout</button>
    </div>
  );
}

function renderAuth() {
  return render(
    <AuthProvider>
      <AuthProbe />
    </AuthProvider>,
  );
}

/** Simulate the real backend rejecting credentials with 401. */
function mockRejectedLogin() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/auth/login')) {
      return new Response(JSON.stringify({ error: { code: 'AUTH_INVALID_CREDENTIALS' } }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.includes('/auth/me')) {
      return new Response('', { status: 401 });
    }
    return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
}

describe('AuthContext - failed login must not create a session (FT-001)', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('does not mark the user as authenticated when the backend rejects login', async () => {
    mockRejectedLogin();
    renderAuth();
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));

    await userEvent.click(screen.getByText('do-login'));

    await waitFor(() => {
      expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
    });
  });

  it('does not fabricate an ADMIN user on failure', async () => {
    mockRejectedLogin();
    renderAuth();
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));

    await userEvent.click(screen.getByText('do-login'));

    await waitFor(() => {
      expect(screen.getByTestId('role')).toHaveTextContent('none');
    });
  });

  it('does not write any token to localStorage on failure', async () => {
    mockRejectedLogin();
    renderAuth();
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));

    await userEvent.click(screen.getByText('do-login'));

    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('false'));
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
  });

  it('never stores the literal demo token', async () => {
    mockRejectedLogin();
    renderAuth();
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));

    await userEvent.click(screen.getByText('do-login'));

    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('false'));
    expect(localStorage.getItem(TOKEN_KEY)).not.toBe('demo_access_token');
  });

  it('surfaces the authentication error to the caller', async () => {
    mockRejectedLogin();
    renderAuth();
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));

    await userEvent.click(screen.getByText('do-login'));

    await waitFor(() => {
      expect(screen.getByTestId('error')).not.toHaveTextContent('none');
    });
  });

  it('does not grant a session when the network is unreachable', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Failed to fetch'));
    renderAuth();
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));

    await userEvent.click(screen.getByText('do-login'));

    await waitFor(() => expect(screen.getByTestId('error')).not.toHaveTextContent('none'));
    expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
    expect(screen.getByTestId('role')).toHaveTextContent('none');
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });
});

describe('AuthContext - session restore must not fabricate a user (FT-001)', () => {
  it('clears an unusable stored token instead of inventing an ADMIN', async () => {
    localStorage.setItem(TOKEN_KEY, 'eyJhbGciOiJIUzI1NiJ9.INVALID.SIGNATURE');
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).includes('/auth/me')) return new Response('', { status: 401 });
      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    renderAuth();

    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
    expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
    expect(screen.getByTestId('role')).toHaveTextContent('none');
  });

  it('does not treat the literal demo token as a valid session', async () => {
    localStorage.setItem(TOKEN_KEY, 'demo_access_token');
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).includes('/auth/me')) return new Response('', { status: 401 });
      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    renderAuth();

    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
    expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
    expect(screen.getByTestId('role')).toHaveTextContent('none');
  });
});

describe('AuthContext - successful login (positive path)', () => {
  function mockSuccessfulLogin(role: 'ADMIN' | 'EMPLOYEE') {
    return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/auth/login')) {
        return new Response(
          JSON.stringify({
            access_token: 'real.access.token',
            refresh_token: 'real-refresh-token',
            token_type: 'bearer',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url.includes('/auth/me')) {
        return new Response(
          JSON.stringify({
            id: '11111111-1111-1111-1111-111111111111',
            email: 'real.user@fieldtrack.test',
            mobile_number: null,
            full_name: 'Real User',
            role,
            is_active: true,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
  }

  it('authenticates and stores the real token', async () => {
    mockSuccessfulLogin('ADMIN');
    renderAuth();
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));

    await userEvent.click(screen.getByText('do-login'));

    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('true'));
    expect(screen.getByTestId('role')).toHaveTextContent('ADMIN');
    expect(localStorage.getItem(TOKEN_KEY)).toBe('real.access.token');
  });

  it('honours the role returned by the backend rather than guessing from the email', async () => {
    mockSuccessfulLogin('EMPLOYEE');
    renderAuth();
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));

    await userEvent.click(screen.getByText('do-login'));

    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('true'));
    expect(screen.getByTestId('role')).toHaveTextContent('EMPLOYEE');
  });

  it('logout clears the session and stored tokens', async () => {
    mockSuccessfulLogin('ADMIN');
    renderAuth();
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
    await userEvent.click(screen.getByText('do-login'));
    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('true'));

    await userEvent.click(screen.getByText('do-logout'));

    await waitFor(() => expect(screen.getByTestId('authenticated')).toHaveTextContent('false'));
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
  });
});
