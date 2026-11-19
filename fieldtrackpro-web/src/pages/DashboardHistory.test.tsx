import { describe, expect, it, beforeEach } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';

import { DashboardPage } from './DashboardPage';
import { ADMIN_USER, baseRoutes, json, mockApi, renderWithProviders, signIn } from '../test/utils';

/**
 * Dashboard History (read-only past financial years, 19-Nov-2026).
 * The Period filter offers FY 2025-26 and its months in a separate "History (read-only)" group; choosing one asks
 * the summary for that period and shows the History banner. Current Live Data stays the default and separate.
 */
const HISTORY = {
  reporting_floor: '2026-04-01',
  periods: [
    {
      value: 'FY2025-26', label: 'FY 2025-26', start: '2025-04-01', end: '2026-03-31', invoices: 5816, payments: 3933,
      months: [
        { value: '2025-04', label: 'April 2025', invoices: 1, payments: 1 },
        { value: '2025-07', label: 'July 2025', invoices: 900, payments: 500 },
        { value: '2026-03', label: 'March 2026', invoices: 800, payments: 600 },
      ],
    },
  ],
};

describe('DashboardPage - History periods', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
  });

  it('offers FY 2025-26 as a separate read-only History group and asks for that period', async () => {
    const summaryMonths: string[] = [];
    const fetchSpy = mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/dashboard/history-periods': HISTORY,
      '/api/v1/dashboard/summary': (url: string) => {
        const month = new URL(url, 'http://x').searchParams.get('month');
        summaryMonths.push(month || 'LIVE');
        return json({
          period: month || 'LIVE', is_historical: !!month, is_history: !!month && month < '2026-04',
          kpis: { total_outlets: 0, total_sales: '0', total_collection: '0', total_collection_posted_in_tally: '0',
            total_collection_verified_awaiting_tally: '0', total_market_outstanding: '0', total_overdue_gt_90: '0',
            total_employees: 0, total_visits: 0, completed_visits: 0, pending_visits: 0, in_progress_visits: 0,
            flagged_visits: 0, gps_verified_visits: 0, total_exceptions: 0, pending_exceptions: 0,
            total_collections_count: 0, total_orders_count: 0 },
          brand_breakdown: [], fos_breakdown: [], zone_breakdown: [], area_breakdown: [],
          ageing_distribution: {}, recent_exceptions: [],
        });
      },
    });

    renderWithProviders(<DashboardPage />);

    const fyOption = await screen.findByRole('option', { name: /FY 2025-26 — full year \(History\)/ });
    expect(screen.getByRole('option', { name: /July 2025 \(History\)/ })).toBeInTheDocument();
    expect(fyOption.closest('optgroup')?.getAttribute('label')).toBe('History (read-only) · FY 2025-26');
    // Current Live Data stays the default selection; no History banner yet.
    const select = fyOption.closest('select') as HTMLSelectElement;
    expect(select.value).toBe('ALL');
    expect(screen.queryByTestId('history-banner')).not.toBeInTheDocument();

    fireEvent.change(select, { target: { value: 'FY2025-26' } });
    await waitFor(() => expect(summaryMonths).toContain('FY2025-26'));
    expect(await screen.findByTestId('history-banner')).toHaveTextContent('History (read-only) · FY 2025-26 (full year)');
    expect(screen.getByText(/📜 History · FY 2025-26 \(full year\)/)).toBeInTheDocument();

    fireEvent.change(select, { target: { value: '2025-07' } });
    await waitFor(() => expect(summaryMonths).toContain('2025-07'));
    expect(await screen.findByTestId('history-banner')).toHaveTextContent('July 2025 · FY 2025-26');

    fireEvent.change(select, { target: { value: 'ALL' } });
    await waitFor(() => expect(screen.queryByTestId('history-banner')).not.toBeInTheDocument());
    fetchSpy.mockRestore();
  });
});
