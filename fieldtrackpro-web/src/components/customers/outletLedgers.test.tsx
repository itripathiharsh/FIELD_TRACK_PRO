import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { TallyLedgersPanel } from './TallyLedgersPanel';
import { AccountHistoryTable } from './AccountHistoryTable';
import type { AccountHistoryItem, LedgerPosition, LedgerRead } from '../../types';
import { ADMIN_USER, baseRoutes, json, mockApi, route, signIn } from '../../test/utils';

const pos = (over: Partial<LedgerPosition>): LedgerPosition => ({
  ledger_id: 'l1', tally_guid: 'g1', name: 'Advik Home (USHA)', brand: 'USHA', tally_outlet_code: 'SGRGUS1',
  opening_balance: '100.00', closing_balance: '150.00', invoiced: '50.00', paid_in_tally: '0.00', adjustments: '0.00',
  outstanding: '150.00', open_bills_total: '150.00', unallocated: '0.00', tally_difference: '0.00', reconciles: true,
  ...over,
});
const meta = (over: Partial<LedgerRead>): LedgerRead => ({
  id: 'l1', tally_guid: 'g1', name: 'Advik Home (USHA)', parent_group: null, tally_outlet_code: null, brand: 'USHA',
  brand_source: 'TALLY', is_primary: false, is_debtor: true, mapping_status: 'CONFIRMED', opening_balance: null,
  closing_balance: null, closing_balance_at: null, gst_number: null, mobile: null, pincode: null, ...over,
});

describe('TallyLedgersPanel', () => {
  it('renders nothing without ledger positions', () => {
    const { container } = render(<TallyLedgersPanel positions={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows every linked ledger with primary marker, brand source and reconciliation', () => {
    render(
      <TallyLedgersPanel
        positions={[
          pos({}),
          pos({ ledger_id: 'l2', name: 'Advik Home (RR)', brand: 'RR', reconciles: false, tally_difference: '25.00' }),
          pos({ ledger_id: 'l3', name: 'Advik Home (Singer)', brand: null }),
        ]}
        ledgers={[meta({ is_primary: true }), meta({ id: 'l2', brand_source: 'OVERRIDE' })]}
      />,
    );
    expect(screen.getAllByTestId('tally-ledger-row')).toHaveLength(3);
    expect(screen.getByText(/3 ledgers linked to this shop/)).toBeInTheDocument();
    expect(screen.getAllByTestId('primary-ledger')).toHaveLength(1);
    expect(screen.getByText('(set manually)')).toBeInTheDocument();
    expect(screen.getByText('Unbranded')).toBeInTheDocument();
    expect(screen.getByTestId('ledger-difference')).toHaveTextContent('25');
  });
});

const item = (i: number, over: Partial<AccountHistoryItem> = {}): AccountHistoryItem => ({
  date: `2026-11-${String((i % 28) + 1).padStart(2, '0')}`, kind: 'INVOICE', voucher_type: 'Sales', voucher_number: `S/${i}`,
  amount: '1000.00', brand: 'USHA', ledger_id: 'l1', ledger_name: 'Advik Home (USHA)', bill_name: `SGRG/${i}`,
  narration: null, retired: false, retired_reason: null, ...over,
});

describe('AccountHistoryTable', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
  });

  it('lists the history across ledgers, marks retired rows and pages through it', async () => {
    const offsets: string[] = [];
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers/c1/history': route((url) => {
        const off = new URL(url, 'http://x').searchParams.get('offset') ?? '0';
        offsets.push(off);
        const items = off === '0'
          ? [item(1, { kind: 'PAYMENT', ledger_name: 'Advik Home (RR)', brand: 'RR' }), item(2, { retired: true, retired_reason: 'DELETED' })]
          : [item(60)];
        return json({ items, total: 120 });
      }),
    });
    render(<AccountHistoryTable customerId="c1" />);
    expect(await screen.findAllByTestId('history-row')).toHaveLength(2);
    expect(screen.getByText('Receipt')).toBeInTheDocument();
    expect(screen.getByText('Advik Home (RR)')).toBeInTheDocument();
    expect(screen.getByTestId('retired-marker')).toBeInTheDocument();
    expect(screen.getByTestId('history-range')).toHaveTextContent('1–50 of 120');
    await userEvent.click(screen.getByRole('button', { name: 'Older' }));
    await waitFor(() => expect(screen.getByTestId('history-range')).toHaveTextContent('51–100 of 120'));
    expect(offsets).toEqual(['0', '50']);
  });

  it('shows an empty state', async () => {
    mockApi({ ...baseRoutes(ADMIN_USER), '/api/v1/customers/c1/history': { items: [], total: 0 } });
    render(<AccountHistoryTable customerId="c1" />);
    expect(await screen.findByText('No account history yet.')).toBeInTheDocument();
  });
});
