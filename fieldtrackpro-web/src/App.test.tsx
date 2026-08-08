import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppContent } from './App';
import { AuthProvider } from './context/AuthContext';
import {
  ADMIN_USER,
  EMPLOYEE_USER,
  baseRoutes,
  mockApi,
  signIn,
} from './test/utils';

/**
 * Routing and route-level authorization.
 *
 * These assert the client-side guards only. Server-side enforcement is the
 * real security boundary and is covered by the backend integration suite
 * (test_authorization_integration.py); the UI guard exists so a user is not
 * shown a page that will only produce a 403.
 */
function renderApp(route: string) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Routing - unauthenticated', () => {
  beforeEach(() => localStorage.clear());

  it('redirects a protected route to the login screen', async () => {
    mockApi({ '/health': { status: 'UP' } });

    renderApp('/customers');

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in to command center/i })).toBeInTheDocument(),
    );
  });

  it('does not render the application shell', async () => {
    mockApi({ '/health': { status: 'UP' } });

    renderApp('/');

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in to command center/i })).toBeInTheDocument(),
    );
    expect(screen.queryByText('Media Vault')).not.toBeInTheDocument();
  });

  it('offers no demo role presets on the login screen (FT-060)', async () => {
    mockApi({ '/health': { status: 'UP' } });

    renderApp('/login');

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /sign in to command center/i })).toBeInTheDocument(),
    );
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(screen.queryByText(/demo presets/i)).not.toBeInTheDocument();
    // Both credential fields must start empty - no prefilled demo password.
    expect(screen.getByLabelText(/work email or mobile/i)).toHaveValue('');
    expect(document.querySelector('input[type="password"]')).toHaveValue('');
  });
});

describe('Routing - admin', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
  });

  it('shows the full navigation set', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [],
      '/api/v1/customers': [],
      '/api/v1/employees': [],
    });

    renderApp('/');

    // Scope to the sidebar: page content also contains words like "Visits".
    const nav = await screen.findByRole('navigation');
    await waitFor(() => expect(within(nav).getByText('Employees')).toBeInTheDocument());
    for (const item of ['Dashboard', 'Employees', 'Territories', 'Customers', 'Visits', 'Geo Logs']) {
      expect(within(nav).getByText(item)).toBeInTheDocument();
    }
  });

  it('allows access to an admin-only route', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers': [],
      '/api/v1/territories': [],
      '/api/v1/employees': [],
      '/api/v1/visits': [],
    });

    renderApp('/customers');

    await waitFor(() =>
      expect(screen.getByText('Customer Accounts Directory')).toBeInTheDocument(),
    );
  });
});

describe('Routing - employee (RBAC guards)', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(EMPLOYEE_USER);
  });

  it('hides admin-only navigation items', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/visits/me/today': [],
      '/api/v1/customers': [],
    });

    renderApp('/');

    await waitFor(() => expect(screen.getByText('Employee Portal')).toBeInTheDocument());
    expect(screen.queryByText('Employees')).not.toBeInTheDocument();
    expect(screen.queryByText('Territories')).not.toBeInTheDocument();
    expect(screen.queryByText('Geo Logs')).not.toBeInTheDocument();
    expect(screen.queryByText('Media Vault')).not.toBeInTheDocument();
    // ...but the routes they DO own remain available.
    expect(screen.getByText('Visits')).toBeInTheDocument();
  });

  it.each(['/customers', '/employees', '/territories', '/geo-logs', '/media', '/settings'])(
    'redirects away from admin-only route %s',
    async (route) => {
      mockApi({
        ...baseRoutes(EMPLOYEE_USER),
        '/api/v1/visits/me/today': [],
        '/api/v1/customers': [],
      });

      renderApp(route);

      // Lands on the dashboard rather than the admin page.
      await waitFor(() => expect(screen.getByText('My Day')).toBeInTheDocument());
      expect(screen.queryByText('Customer Accounts Directory')).not.toBeInTheDocument();
      expect(screen.queryByText('Field Representatives & Staff')).not.toBeInTheDocument();
    },
  );

  it('shows the employee portal label rather than the admin label', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/visits/me/today': [],
      '/api/v1/customers': [],
    });

    renderApp('/');

    await waitFor(() => expect(screen.getByText('Employee Portal')).toBeInTheDocument());
    expect(screen.queryByText('Admin Dashboard')).not.toBeInTheDocument();
  });
});

