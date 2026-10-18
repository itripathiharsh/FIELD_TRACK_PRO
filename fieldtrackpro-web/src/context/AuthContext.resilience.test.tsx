import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { AuthProvider } from './AuthContext';
import { ProtectedRoute } from '../components/auth/RouteGuards';
import { ADMIN_USER } from '../test/utils';

const HINT = 'fieldtrack_session_hint';

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function renderApp(initial = '/secret') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<div>login screen</div>} />
          <Route
            path="/secret"
            element={
              <ProtectedRoute>
                <div>secret page</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

interface Backend {
  mode: 'ok' | 'down' | 'unauthorized' | 'bad-gateway';
  mustChange: boolean;
  refreshCalls: number;
}

function installBackend(b: Backend) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/auth/refresh')) {
      b.refreshCalls += 1;
      if (b.mode === 'down') throw new TypeError('Failed to fetch');
      if (b.mode === 'bad-gateway') return jsonResponse({}, 502);
      if (b.mode === 'unauthorized') return jsonResponse({ error: { code: 'AUTH_INVALID_REFRESH_TOKEN' } }, 401);
      return jsonResponse({ access_token: `tok-${b.refreshCalls}`, refresh_token: 'r', token_type: 'bearer' });
    }
    if (url.includes('/auth/me')) {
      return jsonResponse({ ...ADMIN_USER, must_change_password: b.mustChange });
    }
    return jsonResponse({});
  });
}

describe('AuthProvider - session restore resilience', () => {
  beforeEach(() => {
    localStorage.setItem(HINT, '1');
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('server down on reload: shows Reconnecting (not login), keeps the hint, and recovers automatically', async () => {
    const backend: Backend = { mode: 'down', mustChange: false, refreshCalls: 0 };
    installBackend(backend);
    renderApp();

    expect(await screen.findByRole('heading', { name: /reconnecting/i })).toBeInTheDocument();
    expect(screen.queryByText('login screen')).not.toBeInTheDocument();
    expect(localStorage.getItem(HINT)).toBe('1');

    // The backend comes back; the next automatic retry (2 s) restores the session.
    backend.mode = 'ok';
    expect(await screen.findByText('secret page', undefined, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByText('login screen')).not.toBeInTheDocument();
  });

  it('a 502/5xx on restore is also treated as reconnecting, and the Retry button works immediately', async () => {
    const backend: Backend = { mode: 'bad-gateway', mustChange: false, refreshCalls: 0 };
    installBackend(backend);
    renderApp();

    expect(await screen.findByRole('heading', { name: /reconnecting/i })).toBeInTheDocument();
    const callsBefore = backend.refreshCalls;

    backend.mode = 'ok';
    await userEvent.click(screen.getByRole('button', { name: /retry now/i }));

    expect(await screen.findByText('secret page')).toBeInTheDocument();
    expect(backend.refreshCalls).toBeGreaterThan(callsBefore);
  });

  it('retries automatically 3 times over ~10 s, then keeps polling slowly', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const backend: Backend = { mode: 'down', mustChange: false, refreshCalls: 0 };
    installBackend(backend);
    renderApp();
    await vi.waitFor(() => expect(screen.getByRole('heading', { name: /reconnecting/i })).toBeInTheDocument());
    expect(backend.refreshCalls).toBe(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    expect(backend.refreshCalls).toBe(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(backend.refreshCalls).toBe(3);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5100);
    });
    expect(backend.refreshCalls).toBe(4); // 1 initial + 3 automatic retries within ~10 s
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_100);
    });
    expect(backend.refreshCalls).toBe(5); // slow poll
    expect(localStorage.getItem(HINT)).toBe('1');
  });

  it('a definitive 401 from refresh goes to login and clears the hint', async () => {
    const backend: Backend = { mode: 'unauthorized', mustChange: false, refreshCalls: 0 };
    installBackend(backend);
    renderApp();

    expect(await screen.findByText('login screen')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /reconnecting/i })).not.toBeInTheDocument();
    expect(localStorage.getItem(HINT)).toBeNull();
  });

  it('a healthy reload restores with exactly one refresh request', async () => {
    const backend: Backend = { mode: 'ok', mustChange: false, refreshCalls: 0 };
    installBackend(backend);
    renderApp();
    expect(await screen.findByText('secret page')).toBeInTheDocument();
    expect(backend.refreshCalls).toBe(1);
  });

  it('Sign out from the Reconnecting screen leaves for login', async () => {
    const backend: Backend = { mode: 'down', mustChange: false, refreshCalls: 0 };
    installBackend(backend);
    renderApp();
    await screen.findByRole('heading', { name: /reconnecting/i });
    await userEvent.click(screen.getByRole('button', { name: /sign out/i }));
    await waitFor(() => expect(screen.getByText('login screen')).toBeInTheDocument());
    expect(localStorage.getItem(HINT)).toBeNull();
  });
});

describe('AuthProvider - forced password change', () => {
  beforeEach(() => {
    localStorage.setItem(HINT, '1');
  });

  it('must_change_password === true shows the full-screen Set a new password page instead of the route', async () => {
    installBackend({ mode: 'ok', mustChange: true, refreshCalls: 0 });
    renderApp();
    expect(await screen.findByRole('heading', { name: /set a new password/i })).toBeInTheDocument();
    expect(screen.queryByText('secret page')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument();
  });

  it('a 403 PASSWORD_CHANGE_REQUIRED from any call flips the guard to the change page', async () => {
    const backend: Backend = { mode: 'ok', mustChange: false, refreshCalls: 0 };
    const spy = installBackend(backend);
    const { apiClient } = await import('../api/client');
    renderApp();
    expect(await screen.findByText('secret page')).toBeInTheDocument();

    spy.mockImplementation(async () =>
      jsonResponse({ error: { code: 'PASSWORD_CHANGE_REQUIRED', message: 'x' } }, 403),
    );
    await act(async () => {
      await apiClient.getHealth().catch(() => undefined);
    });

    expect(await screen.findByRole('heading', { name: /set a new password/i })).toBeInTheDocument();
  });

  it('validates client-side, submits PATCH /users/me/password, re-signs in and continues to the page', async () => {
    const backend: Backend = { mode: 'ok', mustChange: true, refreshCalls: 0 };
    const spy = installBackend(backend);
    renderApp();
    await screen.findByRole('heading', { name: /set a new password/i });

    const submit = screen.getByRole('button', { name: /set new password/i });
    await userEvent.type(screen.getByLabelText('Current Password'), 'Temp#1234');
    await userEvent.type(screen.getByLabelText('New Password'), 'short');
    await userEvent.type(screen.getByLabelText('Confirm New Password'), 'short');
    expect(submit).toBeDisabled();
    expect(screen.getByText(/at least 8 characters/i, { selector: 'p' })).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText('New Password'));
    await userEvent.type(screen.getByLabelText('New Password'), 'Temp#1234');
    expect(screen.getByText(/different from the current one/i)).toBeInTheDocument();

    await userEvent.clear(screen.getByLabelText('New Password'));
    await userEvent.type(screen.getByLabelText('New Password'), 'Brand-New-Pass9');
    await userEvent.clear(screen.getByLabelText('Confirm New Password'));
    await userEvent.type(screen.getByLabelText('Confirm New Password'), 'Brand-New-Pass8');
    expect(screen.getByText(/do not match/i)).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText('Confirm New Password'));
    await userEvent.type(screen.getByLabelText('Confirm New Password'), 'Brand-New-Pass9');
    expect(screen.getByTestId('password-strength')).toBeInTheDocument();

    // Backend: the change succeeds and clears the flag; login then works.
    spy.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes('/users/me/password')) {
        expect((init as RequestInit).method).toBe('PATCH');
        expect(JSON.parse(String((init as RequestInit).body))).toEqual({
          old_password: 'Temp#1234',
          new_password: 'Brand-New-Pass9',
        });
        backend.mustChange = false;
        return new Response(null, { status: 204 });
      }
      if (url.includes('/auth/login')) {
        return jsonResponse({ access_token: 'new-tok', refresh_token: 'r', token_type: 'bearer' });
      }
      if (url.includes('/auth/me')) return jsonResponse({ ...ADMIN_USER, must_change_password: false });
      return jsonResponse({});
    });
    await userEvent.click(submit);

    expect(await screen.findByText('secret page')).toBeInTheDocument();
  });

  it('when PATCH /users/me/password returns a fresh token pair the session is kept without a re-login', async () => {
    const backend: Backend = { mode: 'ok', mustChange: true, refreshCalls: 0 };
    const spy = installBackend(backend);
    renderApp();
    await screen.findByRole('heading', { name: /set a new password/i });
    let loginCalled = false;
    spy.mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes('/users/me/password')) {
        return jsonResponse({ access_token: 'pair-tok', refresh_token: 'r', token_type: 'bearer' });
      }
      if (url.includes('/auth/login')) loginCalled = true;
      if (url.includes('/auth/me')) return jsonResponse({ ...ADMIN_USER, must_change_password: false });
      return jsonResponse({});
    });
    await userEvent.type(screen.getByLabelText('Current Password'), 'Temp#1234');
    await userEvent.type(screen.getByLabelText('New Password'), 'Brand-New-Pass9');
    await userEvent.type(screen.getByLabelText('Confirm New Password'), 'Brand-New-Pass9');
    await userEvent.click(screen.getByRole('button', { name: /set new password/i }));
    expect(await screen.findByText('secret page')).toBeInTheDocument();
    expect(loginCalled).toBe(false);
  });

  it('shows the server error when the current password is wrong', async () => {
    const backend: Backend = { mode: 'ok', mustChange: true, refreshCalls: 0 };
    const spy = installBackend(backend);
    renderApp();
    await screen.findByRole('heading', { name: /set a new password/i });
    spy.mockImplementation(async (input) => {
      if (String(input).includes('/users/me/password')) {
        return jsonResponse({ error: { code: 'AUTH_INVALID_CREDENTIALS', message: 'Current password is incorrect' } }, 400);
      }
      return jsonResponse({ ...ADMIN_USER, must_change_password: true });
    });
    await userEvent.type(screen.getByLabelText('Current Password'), 'wrong-one');
    await userEvent.type(screen.getByLabelText('New Password'), 'Brand-New-Pass9');
    await userEvent.type(screen.getByLabelText('Confirm New Password'), 'Brand-New-Pass9');
    await userEvent.click(screen.getByRole('button', { name: /set new password/i }));
    expect(await screen.findByText(/current password is incorrect/i)).toBeInTheDocument();
    expect(screen.queryByText('secret page')).not.toBeInTheDocument();
  });
});
