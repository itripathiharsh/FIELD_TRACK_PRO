import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { AccountantScope, AdminRoute, FinanceRoute } from './RouteGuards';
import { Sidebar } from '../layout/Sidebar';
import * as AuthModule from '../../context/AuthContext';
import { ADMIN_USER, EMPLOYEE_USER } from '../../test/utils';
import { canViewFinance, isAccountant, isAdmin, roleLabel, sanitizeUser } from '../../utils/roles';
import type { User } from '../../types';

/**
 * ACCOUNTANT (19-Nov-2026): web-only, read-only access to Reports & Collections. Never an admin, never a
 * field employee; every other page redirects to Reports. The backend enforces the same rules.
 */
const ACCOUNTANT_USER: User = { ...ADMIN_USER, id: '55555555-5555-5555-5555-555555555555', role: 'ACCOUNTANT' };

function mockAuth(user: User | null) {
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
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AccountantScope>
        <Routes>
          <Route path="/" element={<div>dashboard page</div>} />
          <Route path="/reports" element={<FinanceRoute><div>reports page</div></FinanceRoute>} />
          <Route path="/profile" element={<div>profile page</div>} />
          <Route path="/employees" element={<AdminRoute><div>employees page</div></AdminRoute>} />
          <Route path="/visits" element={<div>visits page</div>} />
        </Routes>
      </AccountantScope>
    </MemoryRouter>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe('ACCOUNTANT role helpers', () => {
  it('is a valid role, read-only finance, never an admin', () => {
    expect(sanitizeUser(ACCOUNTANT_USER).role).toBe('ACCOUNTANT');
    expect(isAccountant(ACCOUNTANT_USER)).toBe(true);
    expect(isAdmin(ACCOUNTANT_USER)).toBe(false);
    expect(canViewFinance(ACCOUNTANT_USER)).toBe(true);
    expect(canViewFinance(ADMIN_USER)).toBe(true);
    expect(canViewFinance(EMPLOYEE_USER)).toBe(false);
    expect(roleLabel('ACCOUNTANT')).toBe('Accountant');
  });
});

describe('ACCOUNTANT routing', () => {
  it('opens Reports & Collections and the own profile', () => {
    mockAuth(ACCOUNTANT_USER);
    renderAt('/reports');
    expect(screen.getByText('reports page')).toBeInTheDocument();
  });

  it.each(['/', '/employees', '/visits'])('redirects %s to Reports', (path) => {
    mockAuth(ACCOUNTANT_USER);
    renderAt(path);
    expect(screen.getByText('reports page')).toBeInTheDocument();
    expect(screen.queryByText(/dashboard page|employees page|visits page/)).not.toBeInTheDocument();
  });

  it('keeps the own profile reachable', () => {
    mockAuth(ACCOUNTANT_USER);
    renderAt('/profile');
    expect(screen.getByText('profile page')).toBeInTheDocument();
  });

  it('a pending password change still comes first', () => {
    mockAuth({ ...ACCOUNTANT_USER, must_change_password: true });
    renderAt('/reports');
    expect(screen.queryByText('reports page')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /new password/i })).toBeInTheDocument();
  });

  it('Reports stays closed to employees and open to admins; admins are not redirected', () => {
    mockAuth(EMPLOYEE_USER);
    renderAt('/reports');
    expect(screen.getByRole('alert')).toHaveTextContent(/not authorized/i);
    vi.restoreAllMocks();
    mockAuth(ADMIN_USER);
    renderAt('/employees');
    expect(screen.getByText('employees page')).toBeInTheDocument();
  });
});

describe('ACCOUNTANT sidebar', () => {
  it('shows only Reports & Collections, labelled read-only, and no Settings', () => {
    mockAuth(ACCOUNTANT_USER);
    render(
      <MemoryRouter initialEntries={['/reports']}>
        <Sidebar />
      </MemoryRouter>,
    );
    const links = screen.getAllByRole('link').map((a) => a.textContent?.trim());
    expect(links).toContain('Reports & Collections');
    for (const hidden of ['Dashboard', 'Employees', 'Customers', 'Payment Collections', 'Visits', 'Settings']) {
      expect(links).not.toContain(hidden);
    }
    expect(screen.getByText('Accountant (read-only)')).toBeInTheDocument();
  });
});
