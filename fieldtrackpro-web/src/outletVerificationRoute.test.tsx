import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppContent } from './App';
import { AuthProvider } from './context/AuthContext';
import { ADMIN_USER, EMPLOYEE_USER, baseRoutes, json, mockApi, signIn } from './test/utils';
import { NotificationBell } from './components/layout/NotificationBell';
import { apiClient } from './api/client';
import { makeProof, stubObjectUrls } from './test/outletProofFixtures';

vi.mock('./components/outlet-proofs/OutletProofMap', () => ({
  OutletProofMap: () => <div data-testid="map-stub" />,
}));

function renderApp(route: string) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('/customers/outlet-verification route guard', () => {
  beforeEach(() => localStorage.clear());

  it('EMPLOYEE gets a not-authorized page, never the review queue, and no proofs request', async () => {
    signIn(EMPLOYEE_USER);
    const spy = mockApi({ ...baseRoutes(EMPLOYEE_USER), '/api/v1/visits/me/today': [] });
    renderApp('/customers/outlet-verification');
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/not authorized/i));
    expect(screen.queryByText('Outlet Verification')).not.toBeInTheDocument();
    expect(spy.mock.calls.some((c) => String(c[0]).includes('/outlet-proofs'))).toBe(false);
  });

  it('EMPLOYEE does not see the sidebar entry', async () => {
    signIn(EMPLOYEE_USER);
    mockApi({ ...baseRoutes(EMPLOYEE_USER), '/api/v1/visits/me/today': [] });
    renderApp('/');
    await waitFor(() => expect(screen.getByText('Employee Portal')).toBeInTheDocument());
    expect(screen.queryByText('Outlet Verification')).not.toBeInTheDocument();
  });

  it('ADMIN reaches the page and sees the sidebar entry', async () => {
    signIn(ADMIN_USER);
    stubObjectUrls();
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers/outlet-proofs': () =>
        new Response(JSON.stringify([makeProof()]), {
          status: 200,
          headers: { 'Content-Type': 'application/json', 'X-Total-Count': '1' },
        }),
      '/api/v1/notifications': [],
    });
    vi.spyOn(apiClient, 'getOutletProofImageUrl').mockResolvedValue('blob:x');
    renderApp('/customers/outlet-verification');
    expect(await screen.findByRole('heading', { name: 'Outlet Verification' })).toBeInTheDocument();
    expect(await screen.findByText('Acme Industrial')).toBeInTheDocument();
    expect(screen.getAllByText('Outlet Verification').length).toBeGreaterThanOrEqual(2); // sidebar + page title
  });
});

describe('NotificationBell renders outlet-location notifications', () => {
  it('shows approved / confirmed / rejected outlet location notifications', async () => {
    signIn(ADMIN_USER);
    const mk = (id: string, title: string) => ({
      id,
      user_id: 'u',
      payment_id: null,
      visit_id: null,
      type: 'REMINDER',
      title,
      message: 'Acme Industrial',
      is_read: false,
      sent_at: '2026-10-10T10:00:00Z',
    });
    mockApi({
      '/api/v1/notifications/unread-count': () => json({ unread_count: 3 }),
      '/api/v1/notifications': () =>
        json([mk('1', 'Outlet location approved'), mk('2', 'Outlet location confirmed'), mk('3', 'Outlet location rejected')]),
    });
    render(
      <MemoryRouter>
        <NotificationBell />
      </MemoryRouter>,
    );
    screen.getByRole('button', { name: /notification/i }).click();
    expect(await screen.findByText('Outlet location approved')).toBeInTheDocument();
    expect(screen.getByText('Outlet location confirmed')).toBeInTheDocument();
    expect(screen.getByText('Outlet location rejected')).toBeInTheDocument();
  });
});
