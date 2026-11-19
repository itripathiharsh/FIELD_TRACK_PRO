import { describe, expect, it, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { OutletMappingPage } from './OutletMappingPage';
import type { LedgerQueueItem, OutletCodeQueueItem, User } from '../types';
import { ADMIN_USER, baseRoutes, json, mockApi, renderWithProviders, signIn } from '../test/utils';

/**
 * Missing brand / Missing outlet code tabs (19-Nov-2026 fix): every row shows which shop and which Tally ledger it
 * is (the old rows rendered the name at 0 px width next to a full-width input), the outlet-code list is one row per
 * OUTLET, and Save calls the right action for that exact ledger / outlet.
 */
const brandRow = (over: Partial<LedgerQueueItem>): LedgerQueueItem => ({
  id: 'l1', customer_id: 'c1', tally_guid: 'g1', name: 'A to Z Grasthi Bhandar (RR)', parent_group: 'Dharmendra (RR)',
  tally_outlet_code: null, brand: null, brand_source: 'NONE', is_primary: true, is_debtor: true,
  mapping_status: 'AUTO_1TO1', opening_balance: null, closing_balance: null, closing_balance_at: null,
  gst_number: '09ASKPK3606N1ZB', mobile: '8787233875', pincode: '208027',
  outlet_name: 'A to Z Grasthi Bhandar', outlet_address: '12 Kidwai Nagar', outlet_code: null,
  area_name: 'Kidwai Nagar', territory_name: 'Kanpur', ...over,
});
const codeRow: OutletCodeQueueItem = {
  customer_id: 'c7', outlet_name: 'Dreamland Electricals (ZBR)', outlet_address: 'Bilhaur Road', outlet_code: null,
  area_name: null, territory_name: 'Kanpur Dehat',
  ledgers: [
    { id: 'l7', name: 'Dreamland Electricals (ZBR)', brand: 'Zebronics', brand_source: 'TALLY', parent_group: 'Yogesh Shrivastav ZBR',
      tally_outlet_code: null, gst_number: '09BOCPG5472B1Z7', mobile: null, pincode: '209801', is_primary: true },
    { id: 'l8', name: 'Dreamland Electricals (SINGER)', brand: null, brand_source: 'NONE', parent_group: 'Yogesh Shrivastav Singer',
      tally_outlet_code: 'UPDD123', gst_number: '09BOCPG5472B1Z7', mobile: null, pincode: '209801', is_primary: false },
  ],
};
const QUEUES = {
  new_unreviewed: [],
  missing_brand: [brandRow({}), brandRow({ id: 'l2', customer_id: 'c2', name: 'Khatri Agencies (Philips)', outlet_name: 'Khatri Agencies', parent_group: 'Sundry Debtors- PH.', gst_number: null })],
  missing_code: [codeRow],
  linked_outlets: 2,
};

describe('Outlet Mapping - Missing brand / Missing outlet code', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER as User);
  });

  it('brand rows show outlet, ledger, location and status; search filters; Save sends that ledger', async () => {
    const posts: { url: string; body: unknown }[] = [];
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/outlet-mapping/queues': QUEUES,
      '/api/v1/outlet-mapping/events': [],
      '/api/v1/outlet-mapping/brand': (url: string, init?: RequestInit) => {
        posts.push({ url, body: JSON.parse(String(init?.body ?? '{}')) });
        return json({ id: 'e1', action: 'BRAND_OVERRIDE', created_at: '2026-11-19T10:00:00Z' });
      },
    });
    renderWithProviders(<OutletMappingPage />);
    await userEvent.click(await screen.findByRole('tab', { name: /Missing brand \(2\)/ }));

    const rows = await screen.findAllByTestId('fill-brand');
    expect(rows).toHaveLength(2);
    const first = within(rows[0]);
    expect(first.getByText('A to Z Grasthi Bhandar')).toBeInTheDocument();
    expect(first.getByText('A to Z Grasthi Bhandar (RR)')).toBeInTheDocument();
    expect(first.getByText(/Dharmendra \(RR\) · GST 09ASKPK3606N1ZB · 8787233875/)).toBeInTheDocument();
    expect(first.getByText(/12 Kidwai Nagar · Kidwai Nagar, Kanpur · 208027/)).toBeInTheDocument();
    expect(first.getByText('No brand in Tally')).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText('Search ledgers without a brand'), 'khatri');
    expect(screen.getAllByTestId('fill-brand')).toHaveLength(1);
    expect(screen.getByTestId('fill-count')).toHaveTextContent('1 of 2');

    await userEvent.type(screen.getByLabelText('Brand for Khatri Agencies (Philips)'), 'Philips');
    await userEvent.click(within(screen.getByTestId('fill-brand')).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].body).toEqual({ ledger_id: 'l2', brand: 'Philips' });
  });

  it('outlet-code rows are per outlet with all its ledgers; Save sends that outlet', async () => {
    const posts: unknown[] = [];
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/outlet-mapping/queues': QUEUES,
      '/api/v1/outlet-mapping/events': [],
      '/api/v1/outlet-mapping/outlet-code': (_url: string, init?: RequestInit) => {
        posts.push(JSON.parse(String(init?.body ?? '{}')));
        return json({ id: 'e2', action: 'OUTLET_CODE', created_at: '2026-11-19T10:00:00Z' });
      },
    });
    renderWithProviders(<OutletMappingPage />);
    await userEvent.click(await screen.findByRole('tab', { name: /Missing outlet code \(1\)/ }));

    const rows = await screen.findAllByTestId('fill-code');
    expect(rows).toHaveLength(1);
    const row = within(rows[0]);
    expect(row.getAllByText('Dreamland Electricals (ZBR)').length).toBeGreaterThan(0);
    expect(row.getByText(/Dreamland Electricals \(SINGER\)/)).toBeInTheDocument();
    expect(row.getByText('No brand')).toBeInTheDocument();
    expect(row.getByText('None')).toBeInTheDocument();
    expect(row.getByText(/Tally alias: UPDD123 \(not applied\)/)).toBeInTheDocument();
    expect(row.getByText(/Bilhaur Road · Kanpur Dehat · 209801/)).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText('Outlet code for Dreamland Electricals (ZBR)'), 'updd555');
    await userEvent.click(row.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]).toEqual({ customer_id: 'c7', outlet_code: 'UPDD555' });
  });
});
