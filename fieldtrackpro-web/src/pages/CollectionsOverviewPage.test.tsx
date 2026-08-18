import { describe, expect, it, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';

import { CollectionsOverviewPage } from './CollectionsOverviewPage';
import {
  ADMIN_USER,
  CUSTOMER,
  EMPLOYEE,
  TERRITORY,
  baseRoutes,
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
    expect(screen.getAllByText('₹6,000').length).toBeGreaterThan(0);
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
});
