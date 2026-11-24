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
  pickMultiOption,
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

/** A /dashboard/summary answer with the given KPI counts (everything else empty). */
function summary(k: Partial<Record<string, number>> = {}) {
  return {
    period: 'LIVE', is_historical: false, is_history: false, data_source: 'LIVE_INVOICES', as_of_date: '2026-11-23',
    kpis: {
      total_outlets: 0, total_sales: '0', total_collection: '0', total_collection_posted_in_tally: '0',
      total_collection_verified_awaiting_tally: '0', total_market_outstanding: '0', total_overdue_gt_90: '0',
      total_employees: 0, total_visits: 0, completed_visits: 0, pending_visits: 0, in_progress_visits: 0,
      flagged_visits: 0, gps_verified_visits: 0, total_exceptions: 0, pending_exceptions: 0,
      total_collections_count: 0, total_orders_count: 0, ...k,
    },
    brand_breakdown: [], fos_breakdown: [], zone_breakdown: [], area_breakdown: [],
    ageing_distribution: { '<15': '0', '15-30': '0', '30-45': '0', '45-60': '0', '60-75': '0', '75-90': '0', '>90': '0' },
    recent_exceptions: [],
  };
}

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
      '/api/v1/dashboard/summary': summary({ total_employees: 1, total_outlets: 1, total_visits: 1 }),
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
      '/api/v1/dashboard/summary': summary(),
    });

    renderWithProviders(<DashboardPage />);

    await waitFor(() => expect(screen.getByText('Field Representatives')).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(3));
    // Geo compliance is unknown, not "100%".
    expect(screen.getByText('No visits recorded yet')).toBeInTheDocument();
  });

  it('shows a dash, not 0, when the dashboard figures fail to load', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [],
      '/api/v1/customers': [],
      '/api/v1/employees': [],
      '/api/v1/dashboard/summary': () => json({ error: { code: 'BOOM', message: 'database unavailable' } }, 500),
    });
    renderWithProviders(<DashboardPage />);
    await waitFor(() => expect(screen.getByText(/Executive dashboard figures could not be loaded/i)).toBeInTheDocument());
    for (const label of ['Field Representatives', 'Customer Accounts', 'Visits']) {
      const card = screen.getByText(label).closest('div.rounded-xl');
      expect(card!.querySelector('.font-headline-lg')!.textContent).toBe('—');
    }
  });

  it('ageing buckets are buttons: a click filters every widget, a second click clears it', async () => {
    const seen: string[] = [];
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [],
      '/api/v1/customers': [],
      '/api/v1/employees': [],
      '/api/v1/dashboard/summary': (url: string) => {
        seen.push(new URL(url, 'http://x').searchParams.get('ageing_bucket') ?? '');
        return json(summary({ total_market_outstanding: 0 }));
      },
    });
    renderWithProviders(<DashboardPage />);
    const bucket = await screen.findByTestId('ageing-bucket->90');
    expect(bucket).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('ageing-explainer')).toHaveTextContent(/days from the Tally bill/i);
    bucket.click();
    await waitFor(() => expect(seen).toContain('>90'));
    await waitFor(() => expect(screen.getByTestId('ageing-bucket->90')).toHaveAttribute('aria-pressed', 'true'));
    expect(screen.getByText(/Showing only money aged/)).toHaveTextContent('Over 90 days');
    screen.getByTestId('ageing-bucket->90').click();
    await waitFor(() => expect(screen.getByTestId('ageing-bucket->90')).toHaveAttribute('aria-pressed', 'false'));
    expect(seen[seen.length - 1]).toBe('');
  });

  it('multi-select brand and FOS reach the API together, with chips that remove one value', async () => {
    const calls: URLSearchParams[] = [];
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [],
      '/api/v1/customers': [],
      '/api/v1/employees': [EMPLOYEE, { ...EMPLOYEE, id: 'emp-2', full_name: 'Second Rep', employee_code: 'E2' }],
      '/api/v1/brands/filter-options': [
        { name: 'Samsung', records: 3, unattributed: false },
        { name: 'Oppo', records: 9, unattributed: false },
        { name: 'Unattributed', records: 2, unattributed: true },
      ],
      '/api/v1/dashboard/summary': (url: string) => {
        calls.push(new URL(url, 'http://x').searchParams);
        return json(summary());
      },
    });
    renderWithProviders(<DashboardPage />);
    await pickMultiOption('Brand', 'Samsung');
    await pickMultiOption('Brand', 'Oppo');
    await pickMultiOption('FOS / Field Officer', EMPLOYEE.id);
    await pickMultiOption('FOS / Field Officer', 'emp-2');
    await waitFor(() => {
      const p = calls[calls.length - 1];
      expect(p.get('brand')).toBe('Samsung,Oppo');
      expect(p.get('employee_id')).toBe(`${EMPLOYEE.id},emp-2`);
    });
    screen.getByRole('button', { name: 'Remove Samsung' }).click();
    await waitFor(() => expect(calls[calls.length - 1].get('brand')).toBe('Oppo'));
    screen.getByRole('button', { name: /^Reset$/i }).click();
    await waitFor(() => {
      const p = calls[calls.length - 1];
      expect(p.get('brand')).toBeNull();
      expect(p.get('employee_id')).toBeNull();
    });
  });

  it('a slower, older request never overwrites the figures of the filter just selected (stale data)', async () => {
    let slowUnfiltered = false;
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [],
      '/api/v1/customers': [],
      '/api/v1/employees': [],
      '/api/v1/dashboard/summary': async (url: string) => {
        const bucket = new URL(url, 'http://x').searchParams.get('ageing_bucket');
        if (!bucket && slowUnfiltered) await new Promise((r) => setTimeout(r, 300));
        return json(summary({ total_outlets: bucket ? 7 : 99, total_employees: 1 }));
      },
    });
    renderWithProviders(<DashboardPage />);
    const outlets = () =>
      screen.getByText('Customer Accounts').closest('div.rounded-xl')!.querySelector('.font-headline-lg')!.textContent;
    await waitFor(() => expect(outlets()).toBe('99'));
    slowUnfiltered = true;
    window.dispatchEvent(new Event('focus'));          // starts an unfiltered refetch that answers late
    (await screen.findByTestId('ageing-bucket->90')).click();
    await waitFor(() => expect(outlets()).toBe('7'));
    await new Promise((r) => setTimeout(r, 450));      // the late unfiltered answer arrives...
    expect(outlets()).toBe('7');                      // ...and is ignored
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
      '/api/v1/dashboard/summary': summary({ total_visits: 4, completed_visits: 2, flagged_visits: 1 }),
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

describe('DashboardPage - Tally collection split', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
  });

  it('shows Posted in Tally vs Verified, awaiting Tally and an alert chip linking to stuck payments', async () => {
    const kpis = {
      total_outlets: 1, total_sales: '1000', total_collection: '700',
      total_collection_posted_in_tally: '500', total_collection_verified_awaiting_tally: '200',
      total_market_outstanding: '300', total_overdue_gt_90: '0', total_employees: 1, total_visits: 1,
      completed_visits: 1, pending_visits: 0, flagged_visits: 0, gps_verified_visits: 1, total_exceptions: 0,
      pending_exceptions: 0, total_collections_count: 2, total_orders_count: 0,
    };
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [VISIT],
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
      '/api/v1/dashboard/summary': {
        period: 'LIVE', is_historical: false, kpis, brand_breakdown: [], fos_breakdown: [],
        zone_breakdown: [], area_breakdown: [], ageing_distribution: {}, recent_exceptions: [],
      },
    });

    renderWithProviders(<DashboardPage />);
    const split = await screen.findByTestId('collection-tally-split');
    expect(split).toHaveTextContent('Posted in Tally');
    expect(split).toHaveTextContent('₹500');
    expect(split).toHaveTextContent('Verified, awaiting Tally');
    expect(split).toHaveTextContent('₹200');
    expect(screen.getByRole('button', { name: /awaiting tally - review stuck posts/i })).toBeInTheDocument();
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

