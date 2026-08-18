import { describe, expect, it, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';

import { DashboardPage } from './DashboardPage';
import {
  ADMIN_USER,
  CUSTOMER,
  EMPLOYEE,
  EMPLOYEE_USER,
  VISIT,
  baseRoutes,
  json,
  mockApi,
  renderWithProviders,
  signIn,
} from '../test/utils';

/**
 * DashboardPage behaviour.
 *
 * Covers FT-028 (metrics were fabricated with `|| 12` style fallbacks, so the
 * dashboard reported 12 representatives and 48 customers on a database holding
 * one of each), FT-019 (an employee should see their own day) and FT-045
 * (admin-only destinations were offered to field staff).
 */
describe('DashboardPage - admin', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
  });

  it('shows real counts, never invented fallbacks (FT-028)', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [VISIT],
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderWithProviders(<DashboardPage />);

    // Wait for the data to land, not merely for the card to mount.
    await waitFor(() => {
      const card = screen.getByText('Field Representatives').closest('div.rounded-xl');
      expect(card?.querySelector('.font-headline-lg')?.textContent).toBe('1');
    });

    // One of each in the mocked data. The removed fallbacks were 12, 48 and 24.
    expect(screen.queryByText('12')).not.toBeInTheDocument();
    expect(screen.queryByText('48')).not.toBeInTheDocument();
    expect(screen.queryByText('24')).not.toBeInTheDocument();

    // Each of the three count cards shows the true value of 1. The value is
    // read from the card's own value element rather than the whole card text,
    // so an unrelated digit in the subtitle cannot satisfy the assertion.
    for (const label of ['Field Representatives', 'Customer Accounts', 'Visits']) {
      const card = screen.getByText(label).closest('div.rounded-xl');
      expect(card, `metric card "${label}" should render`).not.toBeNull();
      const value = card!.querySelector('.font-headline-lg');
      expect(value, `metric card "${label}" should show a value`).not.toBeNull();
      expect(value!.textContent).toBe('1');
    }
  });

  it('shows zero rather than a flattering placeholder when there is no data', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [],
      '/api/v1/customers': [],
      '/api/v1/employees': [],
    });

    renderWithProviders(<DashboardPage />);

    await waitFor(() => expect(screen.getByText('Field Representatives')).toBeInTheDocument());
    expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(3);
    // Geo compliance is unknown, not "100%".
    expect(screen.getByText('No visits recorded yet')).toBeInTheDocument();
  });

  it('computes geo compliance from actual visit statuses', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [
        { ...VISIT, id: 'v1', status: 'COMPLETED' },
        { ...VISIT, id: 'v2', status: 'FLAGGED' },
        { ...VISIT, id: 'v3', status: 'COMPLETED' },
        { ...VISIT, id: 'v4', status: 'PENDING' },
      ],
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderWithProviders(<DashboardPage />);

    // 3 of 4 visits are not flagged => 75%.
    await waitFor(() => expect(screen.getByText('75%')).toBeInTheDocument());
    expect(screen.getByText(/1 location anomaly flagged/i)).toBeInTheDocument();
  });

  it('reports a load failure instead of rendering placeholder numbers', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': () => json({ error: { code: 'X', message: 'Backend unavailable' } }, 503),
      '/api/v1/customers': [],
      '/api/v1/employees': [],
    });

    renderWithProviders(<DashboardPage />);
    await waitFor(() => expect(screen.getByText('Backend unavailable')).toBeInTheDocument());
  });
});

describe('DashboardPage - employee', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(EMPLOYEE_USER);
  });

  it("requests today's own visits rather than the whole roster (FT-019)", async () => {
    const fetchSpy = mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/visits/me/today': [VISIT],
      '/api/v1/customers': [CUSTOMER],
    });

    renderWithProviders(<DashboardPage />);
    await waitFor(() => expect(screen.getByText('My Day')).toBeInTheDocument());
    await waitFor(() =>
      expect(fetchSpy.mock.calls.some(([u]) => String(u).includes('/visits/me/today'))).toBe(true),
    );

    const urls = fetchSpy.mock.calls.map(([u]) => String(u));
    expect(urls.some((u) => u.includes('/api/v1/employees'))).toBe(false);
  });

  it('hides admin-only metrics and quick actions (FT-045)', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/visits/me/today': [VISIT],
      '/api/v1/customers': [CUSTOMER],
    });

    renderWithProviders(<DashboardPage />);
    await waitFor(() => expect(screen.getByText('My Day')).toBeInTheDocument());

    expect(screen.queryByText('Field Representatives')).not.toBeInTheDocument();
    expect(screen.queryByText('Geo Audit Trail')).not.toBeInTheDocument();
    expect(screen.queryByText('Media Attachments')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /new dispatch/i })).not.toBeInTheDocument();
  });

  it('offers a calm empty state when nothing is scheduled', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/visits/me/today': [],
      '/api/v1/customers': [],
    });

    renderWithProviders(<DashboardPage />);
    await waitFor(() =>
      expect(screen.getByText(/nothing scheduled for today/i)).toBeInTheDocument(),
    );
  });
});

