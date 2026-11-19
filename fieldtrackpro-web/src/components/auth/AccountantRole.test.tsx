import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { AccountantScope, AdminRoute, FinanceRoute } from './RouteGuards';
import { Sidebar } from '../layout/Sidebar';
import { Layout } from '../layout/Layout';
import * as AuthModule from '../../context/AuthContext';
import { ADMIN_USER, EMPLOYEE_USER } from '../../test/utils';
import { accountantCanWriteOn, canViewAdmin, isAccountant, isAdmin, roleLabel, sanitizeUser } from '../../utils/roles';
import type { User } from '../../types';

/**
 * ACCOUNTANT (policy 19-Nov-2026): sees every admin page; writes only employees (field staff), territories,
 * customers, outlet mapping and outlet verification. Never an admin, never a field employee. The backend
 * enforces every rule; the UI decides what to show.
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
          <Route path="/employees" element={<AdminRoute><div>employees page</div></AdminRoute>} />
          <Route path="/payments" element={<AdminRoute><div>payments page</div></AdminRoute>} />
          <Route path="/visit-planning" element={<div>employee planning page</div>} />
          <Route path="/visits/:visitId/forms/:formId" element={<div>form fill page</div>} />
        </Routes>
      </AccountantScope>
    </MemoryRouter>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe('ACCOUNTANT role helpers', () => {
  it('views admin pages, is never an admin, writes only on employees / territories / customers pages', () => {
    expect(sanitizeUser(ACCOUNTANT_USER).role).toBe('ACCOUNTANT');
    expect(isAccountant(ACCOUNTANT_USER)).toBe(true);
    expect(isAdmin(ACCOUNTANT_USER)).toBe(false);
    expect(canViewAdmin(ACCOUNTANT_USER)).toBe(true);
    expect(canViewAdmin(EMPLOYEE_USER)).toBe(false);
    expect(roleLabel('ACCOUNTANT')).toBe('Accountant');
    for (const p of ['/employees', '/employees/x', '/territories/x', '/customers', '/customers/outlet-mapping', '/customers/outlet-verification']) {
      expect(accountantCanWriteOn(p)).toBe(true);
    }
    for (const p of ['/', '/payments', '/reports', '/visits', '/settings', '/forms', '/requirements']) {
      expect(accountantCanWriteOn(p)).toBe(false);
    }
  });
});

describe('ACCOUNTANT routing', () => {
  it.each([
    ['/', 'dashboard page'],
    ['/reports', 'reports page'],
    ['/employees', 'employees page'],
    ['/payments', 'payments page'],
  ])('opens admin page %s', (path, text) => {
    mockAuth(ACCOUNTANT_USER);
    renderAt(path);
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it.each(['/visit-planning', '/visits/v1/forms/f1'])('keeps the accountant out of the field-app page %s', (path) => {
    mockAuth(ACCOUNTANT_USER);
    renderAt(path);
    expect(screen.getByText('dashboard page')).toBeInTheDocument();
  });

  it('a pending password change still comes first', () => {
    mockAuth({ ...ACCOUNTANT_USER, must_change_password: true });
    renderAt('/employees');
    expect(screen.queryByText('employees page')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /new password/i })).toBeInTheDocument();
  });

  it('admin pages stay closed to employees; admins are never redirected', () => {
    mockAuth(EMPLOYEE_USER);
    renderAt('/employees');
    expect(screen.getByRole('alert')).toHaveTextContent(/not authorized/i);
    vi.restoreAllMocks();
    mockAuth(ADMIN_USER);
    renderAt('/visit-planning');
    expect(screen.getByText('employee planning page')).toBeInTheDocument();
  });
});

describe('ACCOUNTANT sidebar and read-only notice', () => {
  it('shows every admin item and Settings, labelled Accountant', () => {
    mockAuth(ACCOUNTANT_USER);
    render(
      <MemoryRouter initialEntries={['/reports']}>
        <Sidebar />
      </MemoryRouter>,
    );
    const links = screen.getAllByRole('link').map((a) => a.textContent?.trim());
    for (const item of ['Dashboard', 'Employees', 'Territories', 'Customers', 'Outlet Mapping', 'Payment Collections', 'Reports & Collections', 'Settings']) {
      expect(links).toContain(item);
    }
    expect(screen.getByText('Accountant')).toBeInTheDocument();
  });

  it('shows the read-only notice on read pages only', () => {
    mockAuth(ACCOUNTANT_USER);
    const { unmount } = render(
      <MemoryRouter initialEntries={['/payments']}>
        <Layout><div>payments</div></Layout>
      </MemoryRouter>,
    );
    expect(screen.getByTestId('accountant-read-only')).toBeInTheDocument();
    unmount();
    render(
      <MemoryRouter initialEntries={['/customers/outlet-mapping']}>
        <Layout><div>mapping</div></Layout>
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('accountant-read-only')).not.toBeInTheDocument();
  });

  it('admins never see the notice', () => {
    mockAuth(ADMIN_USER);
    render(
      <MemoryRouter initialEntries={['/payments']}>
        <Layout><div>payments</div></Layout>
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('accountant-read-only')).not.toBeInTheDocument();
  });
});
