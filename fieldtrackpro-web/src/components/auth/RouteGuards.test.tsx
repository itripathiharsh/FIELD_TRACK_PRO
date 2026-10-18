import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { AdminRoute, ProtectedRoute } from './RouteGuards';
import * as AuthModule from '../../context/AuthContext';
import { ADMIN_USER, EMPLOYEE_USER } from '../../test/utils';
import type { User } from '../../types';

function renderGuard(user: User | null, extra: { isLoading?: boolean; sessionExpired?: boolean } = {}) {
  vi.spyOn(AuthModule, 'useAuth').mockReturnValue({
    user,
    isAuthenticated: !!user,
    isLoading: extra.isLoading ?? false,
    sessionExpired: extra.sessionExpired ?? false,
    reconnecting: false,
    reconnectAttempt: 0,
    reconnectChecking: false,
    retryReconnect: vi.fn(),
    mustChangePassword: user?.must_change_password === true,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
    refreshUser: vi.fn(),
  });
  return render(
    <MemoryRouter initialEntries={['/secret']}>
      <Routes>
        <Route path="/login" element={<div>login screen</div>} />
        <Route path="/secret" element={<AdminRoute><div>admin secret</div></AdminRoute>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('AdminRoute', () => {
  it('renders children for ADMIN', () => {
    renderGuard(ADMIN_USER);
    expect(screen.getByText('admin secret')).toBeInTheDocument();
  });

  it('renders children for SUPER_ADMIN (a strict superset of ADMIN)', () => {
    renderGuard({ ...ADMIN_USER, role: 'SUPER_ADMIN' });
    expect(screen.getByText('admin secret')).toBeInTheDocument();
  });

  it('never grants admin pages to a lowercase / look-alike super admin role', () => {
    renderGuard({ ...ADMIN_USER, role: 'super_admin' as unknown as User['role'] });
    expect(screen.queryByText('admin secret')).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(/not authorized/i);
  });

  it('a user who must change a temporary password never reaches an admin page', () => {
    renderGuard({ ...ADMIN_USER, role: 'SUPER_ADMIN', must_change_password: true });
    expect(screen.queryByText('admin secret')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /new password/i })).toBeInTheDocument();
  });

  it('shows a not-authorized page for EMPLOYEE', () => {
    renderGuard(EMPLOYEE_USER);
    expect(screen.queryByText('admin secret')).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(/not authorized/i);
  });

  it('never grants admin pages to an unexpected role such as MANAGER', () => {
    renderGuard({ ...ADMIN_USER, role: 'MANAGER' as unknown as User['role'] });
    expect(screen.queryByText('admin secret')).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(/not authorized/i);
  });

  it('redirects an unauthenticated visitor to login', () => {
    renderGuard(null);
    expect(screen.queryByText('admin secret')).not.toBeInTheDocument();
    expect(screen.getByText('login screen')).toBeInTheDocument();
  });

  it('shows a loading screen while auth is resolving, never the page', () => {
    renderGuard(null, { isLoading: true });
    expect(screen.queryByText('admin secret')).not.toBeInTheDocument();
    expect(screen.queryByText('login screen')).not.toBeInTheDocument();
  });
});

describe('ProtectedRoute', () => {
  function renderProtected(user: User | null) {
    vi.spyOn(AuthModule, 'useAuth').mockReturnValue({
      user,
      isAuthenticated: !!user,
      isLoading: false,
      sessionExpired: false,
      reconnecting: false,
      reconnectAttempt: 0,
      reconnectChecking: false,
      retryReconnect: vi.fn(),
      mustChangePassword: user?.must_change_password === true,
      login: vi.fn(),
      logout: vi.fn(),
      changePassword: vi.fn(),
      refreshUser: vi.fn(),
    });
    return render(
      <MemoryRouter initialEntries={['/visits']}>
        <Routes>
          <Route path="/login" element={<div>login screen</div>} />
          <Route path="/visits" element={<ProtectedRoute><div>ordinary page</div></ProtectedRoute>} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it('shows the mandatory change-password screen instead of any ordinary page while a temporary password is pending', () => {
    renderProtected({ ...EMPLOYEE_USER, must_change_password: true });
    expect(screen.queryByText('ordinary page')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /new password/i })).toBeInTheDocument();
  });

  it('renders the page once the password has been changed', () => {
    renderProtected({ ...EMPLOYEE_USER, must_change_password: false });
    expect(screen.getByText('ordinary page')).toBeInTheDocument();
  });
});
