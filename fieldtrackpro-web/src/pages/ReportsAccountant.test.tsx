import { describe, expect, it, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';

import { ReportsPage } from './ReportsPage';
import { ADMIN_USER, baseRoutes, mockApi, renderWithProviders, signIn } from '../test/utils';
import type { User } from '../types';

/** ACCOUNTANT on Reports & Collections: financial tabs only, read-only (no month close / reopen), no staff list. */
const ACCOUNTANT_USER: User = { ...ADMIN_USER, id: '55555555-5555-5555-5555-555555555555', role: 'ACCOUNTANT' };

const PERIOD = {
  id: 'p1', period_year: 2026, period_month: 10, period_name: 'October 2026', status: 'OPEN',
  total_sales: '100', total_collection: '50', total_market_outstanding: '10', total_overdue_gt_90: '0',
  snapshot_count: 0, total_outlets: 3,
};

describe('ReportsPage - Accountant (read-only)', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ACCOUNTANT_USER);
  });

  it('hides the staff and visit tabs, never asks for the staff list, and offers no Close & Lock', async () => {
    const calls: string[] = [];
    const fetchSpy = mockApi({
      ...baseRoutes(ACCOUNTANT_USER),
      '/api/v1/reports/monthly-periods': (url: string) => {
        calls.push(url);
        return new Response(JSON.stringify([PERIOD]), { status: 200, headers: { 'Content-Type': 'application/json' } });
      },
      '/api/v1/employees': (url: string) => {
        calls.push(url);
        return new Response('{"detail":"Insufficient permissions"}', { status: 403 });
      },
    });

    renderWithProviders(<ReportsPage />, { route: '/reports?tab=monthly' });

    expect(await screen.findByRole('button', { name: 'business_bi' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'collections' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'outstanding' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'employees' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'visits' })).not.toBeInTheDocument();

    expect(await screen.findByText(/October 2026/)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Review/ }).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /Close & Lock/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Reopen/ })).not.toBeInTheDocument();

    await waitFor(() => expect(calls.some((u) => u.includes('/reports/monthly-periods'))).toBe(true));
    expect(calls.some((u) => /\/api\/v1\/employees(\?|$)/.test(u))).toBe(false);
    fetchSpy.mockRestore();
  });

  it('opening a staff tab by URL falls back to Financial & BI', async () => {
    const fetchSpy = mockApi({ ...baseRoutes(ACCOUNTANT_USER) });
    renderWithProviders(<ReportsPage />, { route: '/reports?tab=employees' });
    expect(await screen.findByRole('button', { name: 'business_bi' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'employees' })).not.toBeInTheDocument();
    fetchSpy.mockRestore();
  });
});
