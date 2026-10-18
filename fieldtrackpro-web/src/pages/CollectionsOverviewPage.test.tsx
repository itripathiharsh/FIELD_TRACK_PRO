import { describe, expect, it, beforeEach, vi } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { CollectionsOverviewPage } from './CollectionsOverviewPage';
import {
  ADMIN_USER,
  CUSTOMER,
  EMPLOYEE,
  TERRITORY,
  baseRoutes,
  json,
  mockApi,
  renderWithProviders,
  route,
  signIn,
} from '../test/utils';

const OUTLET_ROW = {
  customer_id: CUSTOMER.id,
  outlet_code: CUSTOMER.outlet_code,
  customer_name: CUSTOMER.name,
  territory_id: TERRITORY.id,
  territory_name: TERRITORY.name,
  area_id: null,
  area_name: null,
  assigned_employees: [{ id: EMPLOYEE.id, name: EMPLOYEE.full_name }],
  total_invoiced: '10000.00',
  total_paid: '4000.00',
  total_outstanding: '6000.00',
  overdue_amount: '6000.00',
  max_days_outstanding: 30,
  collection_status: 'OVERDUE',
  relevant_mis_bucket: '16-30',
  relevant_bucket_amount: '6000.00',
  most_recent_payment_date: '2026-08-01',
  most_recent_payment_amount: '4000.00',
  most_recent_payment_employee_name: EMPLOYEE.full_name,
  most_recent_visit_date: '2026-08-05T09:00:00Z',
  most_recent_visit_employee_name: EMPLOYEE.full_name,
};

const OVERVIEW_RESPONSE = {
  totals: {
    total_outlets: 1,
    total_invoiced: '10000.00',
    total_paid: '4000.00',
    total_outstanding: '6000.00',
    current_amount: '0.00',
    bucket_0_15: '0.00',
    bucket_16_30: '6000.00',
    bucket_31_60: '0.00',
    bucket_61_90: '0.00',
    bucket_90_plus: '0.00',
  },
  outlets: [OUTLET_ROW],
  total_count: 1,
  skip: 0,
  limit: 10,
};

describe('CollectionsOverviewPage', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
  });

  it('renders the summary totals and outlet row from the backend response', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/employees': [EMPLOYEE],
      '/api/v1/territories': [TERRITORY],
      '/api/v1/collections/overview': OVERVIEW_RESPONSE,
    });

    renderWithProviders(<CollectionsOverviewPage />);

    expect(await screen.findByText('Acme Industrial')).toBeInTheDocument();
    expect(screen.getByText('OUT-001')).toBeInTheDocument();
    // "North Region"/"Test Field Rep" also appear as <option> text in the
    // filter dropdowns, so at least one match (not exactly one) is the
    // correct assertion here.
    expect(screen.getAllByText('North Region').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Test Field Rep').length).toBeGreaterThan(0);
    // Total Outstanding summary tile reflects the backend total, not a client sum.
    expect(screen.getAllByText('₹6,000.00').length).toBeGreaterThan(0);
  });

  it('shows "no outlets" empty state when the backend returns none', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/employees': [],
      '/api/v1/territories': [],
      '/api/v1/collections/overview': {
        totals: {
          total_outlets: 0, total_invoiced: '0', total_paid: '0', total_outstanding: '0',
          current_amount: '0', bucket_0_15: '0', bucket_16_30: '0', bucket_31_60: '0',
          bucket_61_90: '0', bucket_90_plus: '0',
        },
        outlets: [], total_count: 0, skip: 0, limit: 10,
      },
    });

    renderWithProviders(<CollectionsOverviewPage />);

    expect(await screen.findByText(/no outlets match the current filters/i)).toBeInTheDocument();
  });

  it('applying a filter refetches with the selected query params, not before', async () => {
    let lastUrl = '';
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/employees': [EMPLOYEE],
      '/api/v1/territories': [TERRITORY],
      '/api/v1/collections/overview': route((url) => {
        lastUrl = url;
        return new Response(JSON.stringify(OVERVIEW_RESPONSE), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }),
    });

    renderWithProviders(<CollectionsOverviewPage />);
    await screen.findByText('Acme Industrial');
    expect(lastUrl).not.toContain('collection_status=');

    fireEvent.change(screen.getByPlaceholderText('Search outlets...'), { target: { value: 'Acme' } });
    // Typing alone must not refetch yet - only "Apply Filters" commits it.
    expect(lastUrl).not.toContain('search=Acme');

    fireEvent.click(screen.getByText('Apply Filters'));

    await waitFor(() => expect(lastUrl).toContain('search=Acme'));
  });

  it('a rejected/errored fetch shows an error banner, not a blank page', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/employees': [],
      '/api/v1/territories': [],
      '/api/v1/collections/overview': () => new Response(
        JSON.stringify({ error: { code: 'INTERNAL', message: 'boom' } }), { status: 500 },
      ),
    });

    renderWithProviders(<CollectionsOverviewPage />);

    expect(await screen.findByText(/boom/i)).toBeInTheDocument();
  });

  it('shows per-outlet position columns, totals equation and a WARNING chip when the backend sends them', async () => {
    const pos = { opening_balance: '5000.00', paid_in_tally: '4000.00', reconciles: true };
    const ageing = { normal: '0.00', warning: '11000.00', overdue: '0.00', baseline_current: '0.00', baseline_overdue: '0.00' };
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/employees': [EMPLOYEE],
      '/api/v1/territories': [TERRITORY],
      '/api/v1/collections/overview': {
        ...OVERVIEW_RESPONSE,
        totals: { ...OVERVIEW_RESPONSE.totals, ...pos, total_outstanding: '11000.00', ageing },
        outlets: [{ ...OUTLET_ROW, ...pos, total_outstanding: '11000.00', collection_status: 'WARNING', verified_awaiting_tally_amount: '700.00', ageing }],
      },
    });
    renderWithProviders(<CollectionsOverviewPage />);
    expect(await screen.findByText('Acme Industrial')).toBeInTheDocument();
    expect(screen.getByTestId('row-opening')).toHaveTextContent('₹5,000');
    expect(screen.getByTestId('row-paid')).toHaveTextContent('₹4,000');
    expect(screen.getByTestId('pos-outstanding')).toHaveTextContent('₹11,000.00');
    expect(screen.getByTestId('ageing-total')).toBeInTheDocument();
    expect(screen.getByText('WARNING').closest('span[class*="amber"]')).not.toBeNull();
  });
});


describe('CollectionsOverviewPage - date range, period columns and exports', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
  });

  const PERIOD_RESPONSE = {
    ...OVERVIEW_RESPONSE,
    totals: { ...OVERVIEW_RESPONSE.totals, invoiced_in_period: '2500.00', collected_in_period: '900.00' },
    outlets: [{ ...OUTLET_ROW, invoiced_in_period: '2500.00', collected_in_period: '900.00' }],
    period_start: '2026-09-01',
    period_end: '2026-09-30',
    as_of_date: '2026-10-11',
  };

  const stubApi = (calls: string[], body: unknown = PERIOD_RESPONSE, extra: Record<string, unknown> = {}) =>
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/employees': [EMPLOYEE],
      '/api/v1/territories': [TERRITORY],
      '/api/v1/collections/overview': route((url) => {
        calls.push(url);
        return json(body);
      }),
      ...extra,
    });

  it('sends start_date/end_date only after Apply, and shows the Invoiced / Collected in period columns and totals', async () => {
    const calls: string[] = [];
    stubApi(calls);
    renderWithProviders(<CollectionsOverviewPage />);
    await screen.findByText('Acme Industrial');
    const before = calls.length;
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-09-30' } });
    expect(calls.length).toBe(before); // draft only

    fireEvent.click(screen.getByText('Apply Filters'));
    await waitFor(() => expect(calls[calls.length - 1]).toContain('start_date=2026-09-01'));
    expect(calls[calls.length - 1]).toContain('end_date=2026-09-30');

    expect(await screen.findAllByText('Invoiced in period')).not.toHaveLength(0);
    expect(screen.getAllByText('Collected in period (posted to Tally)').length).toBeGreaterThan(0);
    expect(screen.getByTestId('row-invoiced-period')).toHaveTextContent('₹2,500');
    expect(screen.getByTestId('row-collected-period')).toHaveTextContent('₹900');
    // stock figures are labelled as of today, not the range
    expect(screen.getByTestId('collections-asof')).toHaveTextContent('as of 11/10/2026');
    expect(screen.getByTestId('collections-asof')).toHaveTextContent('not the date range');
    // applied filters strip is derived from the params
    expect(screen.getByTestId('applied-filters')).toHaveTextContent('01/09/2026 to 30/09/2026');
  });

  it('without a date range there are no period columns', async () => {
    const calls: string[] = [];
    stubApi(calls, OVERVIEW_RESPONSE);
    renderWithProviders(<CollectionsOverviewPage />);
    await screen.findByText('Acme Industrial');
    expect(screen.queryByText('Invoiced in period')).not.toBeInTheDocument();
    expect(screen.getByTestId('applied-filters')).toHaveTextContent(/none - showing all data/i);
  });

  it('rejects an end date before the start date', async () => {
    stubApi([]);
    renderWithProviders(<CollectionsOverviewPage />);
    await screen.findByText('Acme Industrial');
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-09-30' } });
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-09-01' } });
    fireEvent.click(screen.getByText('Apply Filters'));
    expect(await screen.findByText(/end date must be after start date/i)).toBeInTheDocument();
  });

  it('Excel and PDF export the SAME filters as the table (all rows, not the page) and use the server file name', async () => {
    const calls: string[] = [];
    const exportCalls: string[] = [];
    stubApi(calls, PERIOD_RESPONSE, {
      '/api/v1/collections/overview/export': route((url) => {
        exportCalls.push(url);
        const pdf = url.includes('format=pdf');
        return new Response(new Blob(['x']), {
          status: 200,
          headers: {
            'Content-Type': pdf ? 'application/pdf' : 'application/octet-stream',
            'Content-Disposition': `attachment; filename="Collections_Overview_20261011_1500_filtered.${pdf ? 'pdf' : 'xlsx'}"`,
          },
        });
      }),
    });
    const names: string[] = [];
    if (!URL.createObjectURL) URL.createObjectURL = vi.fn();
    if (!URL.revokeObjectURL) URL.revokeObjectURL = vi.fn();
    const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:x');
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      names.push(this.download);
    });
    renderWithProviders(<CollectionsOverviewPage />);
    await screen.findByText('Acme Industrial');
    fireEvent.change(screen.getByPlaceholderText('Search outlets...'), { target: { value: 'Acme' } });
    fireEvent.change(screen.getByLabelText('Start date'), { target: { value: '2026-09-01' } });
    fireEvent.change(screen.getByLabelText('End date'), { target: { value: '2026-09-30' } });
    fireEvent.click(screen.getByText('Apply Filters'));
    await waitFor(() => expect(calls[calls.length - 1]).toContain('search=Acme'));
    const tableParams = new URL(calls[calls.length - 1], 'http://x').searchParams;

    await userEvent.click(await screen.findByRole('button', { name: /export excel/i }));
    await waitFor(() => expect(exportCalls).toHaveLength(1));
    await userEvent.click(screen.getByRole('button', { name: /export pdf/i }));
    await waitFor(() => expect(exportCalls).toHaveLength(2));

    for (const [i, fmt] of [[0, 'xlsx'], [1, 'pdf']] as const) {
      const p = new URL(exportCalls[i], 'http://x').searchParams;
      expect(p.get('format')).toBe(fmt);
      expect(p.get('search')).toBe('Acme');
      expect(p.get('start_date')).toBe('2026-09-01');
      expect(p.get('end_date')).toBe('2026-09-30');
      // no pagination parameters on an export: it must contain every filtered row
      expect(p.has('skip')).toBe(false);
      expect(p.has('limit')).toBe(false);
      expect(tableParams.get('search')).toBe(p.get('search'));
    }
    await waitFor(() =>
      expect(names).toEqual([
        'Collections_Overview_20261011_1500_filtered.xlsx',
        'Collections_Overview_20261011_1500_filtered.pdf',
      ]),
    );
    create.mockRestore();
    click.mockRestore();
  });

  it('export buttons are disabled (with a reason) when no outlets match', async () => {
    stubApi([], { ...OVERVIEW_RESPONSE, outlets: [], total_count: 0 });
    renderWithProviders(<CollectionsOverviewPage />);
    await screen.findByText(/no outlets match the current filters/i);
    const excel = screen.getByRole('button', { name: /export excel/i });
    expect(excel).toBeDisabled();
    expect(excel).toHaveAttribute('title', expect.stringMatching(/nothing to export/i));
  });

  it('embedded mode (Reports workbench): no own filter card, loads with the request it is given', async () => {
    const calls: string[] = [];
    stubApi(calls);
    renderWithProviders(
      <CollectionsOverviewPage
        hideHeader
        externalRequest={{ report: 'collections_overview', params: { territory_id: 'z9', start_date: '2026-09-01', collection_status: 'OVERDUE' } }}
      />,
    );
    await screen.findByText('Acme Industrial');
    expect(screen.queryByPlaceholderText('Search outlets...')).not.toBeInTheDocument();
    expect(screen.queryByText('Apply Filters')).not.toBeInTheDocument();
    const p = new URL(calls[calls.length - 1], 'http://x').searchParams;
    expect(p.get('territory_id')).toBe('z9');
    expect(p.get('start_date')).toBe('2026-09-01');
    expect(p.get('collection_status')).toBe('OVERDUE');
    expect(p.get('limit')).toBe('10');
  });
});
