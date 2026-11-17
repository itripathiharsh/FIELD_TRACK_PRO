import { describe, expect, it, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { OutletMappingPage } from './OutletMappingPage';
import type { ImportPreview, LedgerQueueItem, User } from '../types';
import { ADMIN_USER, baseRoutes, CUSTOMER, json, mockApi, renderWithProviders, route, signIn } from '../test/utils';

const SUPER: User = { ...ADMIN_USER, role: 'SUPER_ADMIN' };
const ledger = (over: Partial<LedgerQueueItem>): LedgerQueueItem => ({
  id: 'l1', customer_id: 'c-new', tally_guid: 'g1', name: 'Fiza Telecom (RR)', parent_group: 'Sunil Kumar',
  tally_outlet_code: null, brand: null, brand_source: 'NONE', is_primary: true, is_debtor: true,
  mapping_status: 'NEW_UNREVIEWED', opening_balance: null, closing_balance: null, closing_balance_at: null,
  gst_number: null, mobile: null, pincode: null, ...over,
});
const QUEUES = { new_unreviewed: [ledger({})], missing_brand: [ledger({ id: 'l2', name: 'Advik Home (RR)' })], missing_code: [], linked_outlets: 4 };
const PREVIEW: ImportPreview = {
  preview_id: 'pv1', expires_at: '2026-11-18T10:00:00Z', rows: 1598, confirmed_rows: 3, ignored_rows: 1595,
  links: [{ ledger_id: 'l9', ledger_name: 'Advik Home (RR)', from_customer_id: 'c9', to_outlet_id_label: 'P0009', to_customer_id: 'c8' }],
  brand_updates: [], code_updates: [], errors: [], warnings: ['1 ledger in two shops ignored'],
  outlets_before: 1598, outlets_after: 1596, totals_before: { outstanding: '1000.00' }, totals_after: { outstanding: '1000.00' },
  invariants_ok: true,
};

function routes(user: User, extra: Record<string, unknown> = {}) {
  return { ...baseRoutes(user), '/api/v1/outlet-mapping/queues': QUEUES, '/api/v1/outlet-mapping/events': [], ...extra };
}
async function upload() {
  const file = new File(['x'], 'mapping.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
  await userEvent.upload(screen.getByLabelText('Mapping workbook'), file);
  await userEvent.click(screen.getByRole('button', { name: /Preview/ }));
}

describe('OutletMappingPage', () => {
  beforeEach(() => localStorage.clear());

  it('ADMIN can preview but only a Super Admin can apply or revert', async () => {
    signIn(ADMIN_USER);
    mockApi(routes(ADMIN_USER, { '/api/v1/outlet-mapping/import/preview': PREVIEW }));
    renderWithProviders(<OutletMappingPage />);
    expect(await screen.findByRole('tab', { name: /Review queue \(1\)/ })).toBeInTheDocument();
    await upload();
    expect(await screen.findByTestId('import-preview')).toBeInTheDocument();
    expect(screen.getByTestId('outlets-before-after')).toHaveTextContent('1598 → 1596');
    expect(screen.getByTestId('superadmin-only')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Apply preview' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Batch ID to revert')).not.toBeInTheDocument();
  });

  it('Super Admin previews, applies (only via the stored preview) and gets the batch ID', async () => {
    signIn(SUPER);
    let applyBody: unknown = null;
    mockApi(routes(SUPER, {
      '/api/v1/outlet-mapping/import/preview': route((_u, init) => {
        expect(init?.body).toBeInstanceOf(FormData);
        return json(PREVIEW);
      }),
      '/api/v1/outlet-mapping/import/apply': route((_u, init) => {
        applyBody = JSON.parse(String(init?.body));
        return json({ batch_id: 'b-123', applied: 1, events: 1 });
      }),
    }));
    renderWithProviders(<OutletMappingPage />);
    await screen.findByRole('tab', { name: /Review queue \(1\)/ });
    await upload();
    await screen.findByTestId('import-preview');
    expect(screen.getByTestId('invariants')).toHaveTextContent('OK');
    await userEvent.click(screen.getByRole('button', { name: 'Apply preview' }));
    expect(await screen.findByTestId('applied-batch')).toHaveTextContent('b-123');
    expect(applyBody).toEqual({ preview_id: 'pv1' });
  });

  it('blocks apply when the preview has errors or totals would change', async () => {
    signIn(SUPER);
    mockApi(routes(SUPER, {
      '/api/v1/outlet-mapping/import/preview': {
        ...PREVIEW, invariants_ok: false, errors: [{ row: 12, tally_id: 'g', message: 'Unknown Tally ID' }],
      },
    }));
    renderWithProviders(<OutletMappingPage />);
    await screen.findByRole('tab', { name: /Review queue \(1\)/ });
    await upload();
    expect(await screen.findByTestId('import-errors')).toHaveTextContent('Unknown Tally ID');
    expect(screen.getByTestId('invariants')).toHaveTextContent('NOT OK');
    expect(screen.getByRole('button', { name: 'Apply preview' })).toBeDisabled();
  });

  it('links a new Tally ledger to a shop picked by search (never automatically)', async () => {
    signIn(ADMIN_USER);
    let linkBody: unknown = null;
    mockApi(routes(ADMIN_USER, {
      '/api/v1/customers': [{ ...CUSTOMER, id: 'c-shop', name: 'Fiza Telecom', ledger_count: 2 }],
      '/api/v1/outlet-mapping/link': route((_u, init) => {
        linkBody = JSON.parse(String(init?.body));
        return json({ id: 'e1', action: 'LINK', ledger_id: 'l1', ledger_name: 'Fiza Telecom (RR)', from_customer_id: 'c-new', to_customer_id: 'c-shop', batch_id: null, actor: 'admin', note: null, created_at: '2026-11-17T10:00:00Z' });
      }),
    }));
    renderWithProviders(<OutletMappingPage />);
    await userEvent.click(await screen.findByRole('tab', { name: /Review queue/ }));
    expect(screen.getAllByTestId('review-item')).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: /Link to shop/ }));
    await userEvent.type(screen.getByLabelText('Search outlet'), 'Fiza');
    await userEvent.click(screen.getByRole('button', { name: 'Search' }));
    await userEvent.click(await screen.findByRole('button', { name: /Fiza Telecom · .*2 ledgers/ }));
    await waitFor(() => expect(linkBody).toEqual({ ledger_id: 'l1', target_customer_id: 'c-shop' }));
  });

  it('keeps a new Tally ledger as its own outlet and removes it from the queue', async () => {
    signIn(ADMIN_USER);
    let reviewBody: unknown = null;
    mockApi(routes(ADMIN_USER, {
      '/api/v1/outlet-mapping/review': route((_u, init) => {
        reviewBody = JSON.parse(String(init?.body));
        return json({ id: 'e3', action: 'REVIEW', ledger_id: 'l1', ledger_name: 'Fiza Telecom (RR)', from_customer_id: null, to_customer_id: null, batch_id: null, actor: 'admin', note: null, created_at: '2026-11-17T10:00:00Z' });
      }),
    }));
    renderWithProviders(<OutletMappingPage />);
    await userEvent.click(await screen.findByRole('tab', { name: /Review queue/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Keep as separate outlet' }));
    await waitFor(() => expect(reviewBody).toEqual({ ledger_id: 'l1', decision: 'KEEP_SEPARATE' }));
    expect(await screen.findByTestId('review-empty')).toBeInTheDocument();
  });

  it('sets a missing brand as an explicit override', async () => {
    signIn(ADMIN_USER);
    let brandBody: unknown = null;
    mockApi(routes(ADMIN_USER, {
      '/api/v1/outlet-mapping/brand': route((_u, init) => {
        brandBody = JSON.parse(String(init?.body));
        return json({ id: 'e2', action: 'BRAND_OVERRIDE', ledger_id: 'l2', ledger_name: 'Advik Home (RR)', from_customer_id: null, to_customer_id: null, batch_id: null, actor: 'admin', note: null, created_at: '2026-11-17T10:00:00Z' });
      }),
    }));
    renderWithProviders(<OutletMappingPage />);
    await userEvent.click(await screen.findByRole('tab', { name: /Missing brand/ }));
    const save = screen.getByRole('button', { name: 'Save' });
    expect(save).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Brand for Advik Home (RR)'), 'RR');
    await userEvent.click(save);
    await waitFor(() => expect(brandBody).toEqual({ ledger_id: 'l2', brand: 'RR' }));
  });
});
