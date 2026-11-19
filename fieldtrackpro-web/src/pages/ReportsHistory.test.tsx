import { describe, expect, it, beforeEach } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';

import { ReportsPage } from './ReportsPage';
import { ADMIN_USER, baseRoutes, json, mockApi, renderWithProviders, signIn } from '../test/utils';

/**
 * Reports & Collections History (19-Nov-2026): the Month Period filter offers the same read-only
 * History group as the Dashboard (FY 2025-26 and its months). Choosing one sends that month to the
 * Financial & BI report and shows the History banner; "All Available Months" stays the default.
 */
const HISTORY = {
  reporting_floor: '2026-04-01',
  periods: [
    {
      value: 'FY2025-26', label: 'FY 2025-26', start: '2025-04-01', end: '2026-03-31', invoices: 5816, payments: 3933,
      months: [
        { value: '2025-07', label: 'July 2025', invoices: 900, payments: 500 },
        { value: '2026-03', label: 'March 2026', invoices: 800, payments: 600 },
      ],
    },
  ],
};

const emptyBI = (month: string | null) => ({
  snapshot_date: '2026-11-19', month_period: month, is_finalized: false, total_outlets: 0, total_sales: '0',
  total_collection: '0', total_collection_posted_in_tally: '0', total_collection_verified_awaiting_tally: '0',
  total_market_outstanding: '0', total_overdue_gt_90: '0', brand_summaries: [], zone_summaries: [],
  area_summaries: [], fos_summaries: [], raw_outlet_rows: [], data_source: 'LIVE_INVOICES',
  data_source_note: 'note', as_of_date: '2026-11-19',
});

describe('ReportsPage - History periods', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
  });

  it('offers FY 2025-26 in a read-only History group and asks Financial & BI for that period', async () => {
    const months: string[] = [];
    const fetchSpy = mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/dashboard/history-periods': HISTORY,
      '/api/v1/reports/monthly-periods': [],
      '/api/v1/reports/business-summary': (url: string) => {
        const month = new URL(url, 'http://x').searchParams.get('month');
        months.push(month || 'ALL');
        return json(emptyBI(month));
      },
    });

    renderWithProviders(<ReportsPage />);

    const fyOption = await screen.findByRole('option', { name: /FY 2025-26 — full year \(History\)/ });
    expect(screen.getByRole('option', { name: /July 2025 \(History\)/ })).toBeInTheDocument();
    expect(fyOption.closest('optgroup')?.getAttribute('label')).toBe('History (read-only) · FY 2025-26');
    const select = fyOption.closest('select') as HTMLSelectElement;
    expect(select.value).toBe('ALL');
    expect(screen.queryByTestId('reports-history-banner')).not.toBeInTheDocument();

    fireEvent.change(select, { target: { value: 'FY2025-26' } });
    await waitFor(() => expect(months).toContain('FY2025-26'));
    expect(await screen.findByTestId('reports-history-banner')).toHaveTextContent(
      'History (read-only) · FY 2025-26 (full year)',
    );

    fireEvent.change(select, { target: { value: '2025-07' } });
    await waitFor(() => expect(months).toContain('2025-07'));
    expect(await screen.findByTestId('reports-history-banner')).toHaveTextContent('July 2025 · FY 2025-26');

    fireEvent.change(select, { target: { value: 'ALL' } });
    await waitFor(() => expect(screen.queryByTestId('reports-history-banner')).not.toBeInTheDocument());
    fetchSpy.mockRestore();
  });
});
