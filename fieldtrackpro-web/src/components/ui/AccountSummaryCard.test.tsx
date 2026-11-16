import { describe, expect, it, vi, beforeAll } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AccountSummaryCard } from './AccountSummaryCard';
import { apiClient } from '../../api/client';
import { AccountSummary } from '../../types';

vi.mock('../../api/client', () => ({
  apiClient: {
    getPaymentProofObjectUrl: vi.fn(),
  },
}));

beforeAll(() => {
  if (!URL.createObjectURL) URL.createObjectURL = vi.fn().mockReturnValue('blob:mock-url');
  if (!URL.revokeObjectURL) URL.revokeObjectURL = vi.fn();
});

const BASE_ACCOUNT: AccountSummary = {
  customer_id: 'cust-1',
  customer_name: 'Acme Industrial',
  outlet_code: 'OUT-001',
  total_invoiced: '10000.00',
  total_paid: '4000.00',
  total_outstanding: '6000.00',
  overdue_amount: '0.00',
  max_days_outstanding: 10,
  collection_status: 'NORMAL',
  most_recent_payment: {
    id: 'pay-1', visit_id: 'visit-1', customer_id: 'cust-1', employee_id: 'emp-1', invoice_id: null,
    amount: '4000.00', payment_method: 'CASH', payment_date: '2026-08-01',
    cheque_number: null, cheque_bank_name: null, utr_reference: null, notes: null,
    status: 'VERIFIED', rejection_reason: null, reviewed_by: null, reviewed_at: null,
    created_by: 'user-1', created_at: '2026-08-01T00:00:00Z', proofs: [],
  },
  most_recent_visit_date: '2026-08-05T09:00:00Z',
  most_recent_visit_employee_name: 'Sandeep',
  recent_invoices: [],
  recent_payments: [],
  brand_summary: [],
};

describe('AccountSummaryCard', () => {
  it('shows the Tally ledger balance and flags a reconciliation difference', () => {
    const account: AccountSummary = {
      ...BASE_ACCOUNT, balance_source: 'TALLY', balance_as_of: '2026-11-16T10:00:00Z',
      tally_opening_balance: '2000.00', adjustments: '-200.00', tally_closing_balance: '5300.00', tally_difference: '0.00',
    };
    const { rerender } = render(<MemoryRouter><AccountSummaryCard account={account} /></MemoryRouter>);
    expect(screen.getByTestId('tally-balance')).toHaveTextContent('Balance as per Tally');
    expect(screen.getByTestId('tally-balance')).toHaveTextContent('₹5,300.00');
    expect(screen.queryByText(/differs from this Tally ledger/)).not.toBeInTheDocument();
    rerender(<MemoryRouter><AccountSummaryCard account={{ ...account, tally_difference: '120.00' }} /></MemoryRouter>);
    expect(screen.getByText(/differs from this Tally ledger by ₹120.00/)).toBeInTheDocument();
  });

  it('shows a Tally receipt with no stated mode as such, with its narration', () => {
    const pay = { ...BASE_ACCOUNT.most_recent_payment!, id: 'pay-t', payment_method: 'UNSPECIFIED' as const,
      tally_voucher_type: 'BANK RECEIPT', tally_transaction_type: 'Cheque', narration: 'eRTGS/ICIC0007405/OLEAD' };
    render(<MemoryRouter><AccountSummaryCard account={{ ...BASE_ACCOUNT, recent_payments: [pay] }} /></MemoryRouter>);
    expect(screen.getByText('MODE NOT IN TALLY')).toBeInTheDocument();
    expect(screen.getByText('eRTGS/ICIC0007405/OLEAD')).toBeInTheDocument();
    expect(screen.getByText(/BANK RECEIPT \(Cheque\)/)).toBeInTheDocument();
  });

  it('shows the Total Billed tile using total_invoiced', () => {
    render(<MemoryRouter><AccountSummaryCard account={BASE_ACCOUNT} /></MemoryRouter>);
    expect(screen.getByText('Total Billed')).toBeInTheDocument();
    expect(screen.getByText('₹10,000.00')).toBeInTheDocument();
  });

  it('shows Last Payment and Last Visit summary lines', () => {
    render(<MemoryRouter><AccountSummaryCard account={BASE_ACCOUNT} /></MemoryRouter>);
    expect(screen.getByText('Last Payment')).toBeInTheDocument();
    expect(screen.getByText(/₹4,000.00.*2026-08-01/)).toBeInTheDocument();
    expect(screen.getByText('Last Visit')).toBeInTheDocument();
    expect(screen.getByText(/Sandeep/)).toBeInTheDocument();
  });

  it('shows "No visits yet" / "No payments yet" when there is no history', () => {
    const account = { ...BASE_ACCOUNT, most_recent_payment: null, most_recent_visit_date: null, most_recent_visit_employee_name: null };
    render(<MemoryRouter><AccountSummaryCard account={account} /></MemoryRouter>);
    expect(screen.getByText('No payments yet')).toBeInTheDocument();
    expect(screen.getByText('No visits yet')).toBeInTheDocument();
  });

  it('shows a Proof button for a payment with an attached proof, and opens it on click', async () => {
    (apiClient.getPaymentProofObjectUrl as ReturnType<typeof vi.fn>).mockResolvedValueOnce('blob:proof-url');
    const windowOpenSpy = vi.spyOn(window, 'open').mockImplementation(() => null);

    const account: AccountSummary = {
      ...BASE_ACCOUNT,
      recent_payments: [{
        ...BASE_ACCOUNT.most_recent_payment!,
        proofs: [{ id: 'proof-1', payment_id: 'pay-1', storage_key: 'k', file_size_bytes: 100, original_filename: null, uploaded_by: null, uploaded_at: '2026-08-01T00:00:00Z' }],
      }],
    };
    render(<MemoryRouter><AccountSummaryCard account={account} /></MemoryRouter>);

    const proofButton = screen.getByRole('button', { name: /proof/i });
    fireEvent.click(proofButton);

    await waitFor(() => expect(apiClient.getPaymentProofObjectUrl).toHaveBeenCalledWith('proof-1'));
    expect(windowOpenSpy).toHaveBeenCalledWith('blob:proof-url', '_blank', 'noopener,noreferrer');
    windowOpenSpy.mockRestore();
  });

  it('does not show a Proof button for a payment with no attached proof', () => {
    const account: AccountSummary = { ...BASE_ACCOUNT, recent_payments: [BASE_ACCOUNT.most_recent_payment!] };
    render(<MemoryRouter><AccountSummaryCard account={account} /></MemoryRouter>);
    expect(screen.queryByRole('button', { name: /proof/i })).not.toBeInTheDocument();
  });

  it.each([
    [20, 'text-primary'],
    [21, 'text-amber-600'],
    [25, 'text-amber-600'],
    [26, 'text-rose-600'],
  ])('colours Days Due for %i days with %s', (days, cls) => {
    render(<MemoryRouter><AccountSummaryCard account={{ ...BASE_ACCOUNT, max_days_outstanding: days }} /></MemoryRouter>);
    expect(screen.getByTestId('days-due')).toHaveClass(cls);
  });

  it('shows Verified, awaiting Tally next to Paid when > 0, using backend values as-is', () => {
    const account: AccountSummary = {
      ...BASE_ACCOUNT,
      verified_awaiting_tally_amount: '2500.00',
      brand_summary: [{
        brand: 'USHA', total_invoiced: '10000.00', total_paid: '4000.00', verified_awaiting_tally_amount: '2500.00',
        total_outstanding: '6000.00', overdue_amount: '0.00', invoice_count: 1, payment_count: 2,
        latest_invoice_date: null, latest_payment_date: null,
      }],
    };
    render(<MemoryRouter><AccountSummaryCard account={account} /></MemoryRouter>);
    expect(screen.getAllByText('Paid (in Tally)').length).toBeGreaterThan(0);
    const chips = screen.getAllByTestId('awaiting-tally-amount');
    expect(chips.length).toBeGreaterThanOrEqual(1);
    expect(chips[0]).toHaveTextContent('Verified, awaiting Tally: ₹2,500');
    expect(chips[0]).toHaveAttribute('title', 'Verified by admin, will reduce outstanding once posted to Tally');
    // Outstanding is the backend's number, not total_invoiced - total_paid - awaiting.
    expect(screen.getAllByText('₹6,000.00').length).toBeGreaterThan(0);
  });

  it('hides the awaiting-Tally amount when it is zero or absent', () => {
    render(
      <MemoryRouter>
        <AccountSummaryCard account={{ ...BASE_ACCOUNT, verified_awaiting_tally_amount: '0.00' }} />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('awaiting-tally-amount')).not.toBeInTheDocument();
  });

  it('shows the reconciliation equation and ageing table when the backend sends position fields', () => {
    const account: AccountSummary = {
      ...BASE_ACCOUNT,
      total_outstanding: '11000.00',
      opening_balance: '5000.00',
      paid_in_tally: '4000.00',
      reconciles: true,
      ageing: { normal: '11000.00', warning: '0.00', overdue: '0.00', baseline_current: '0.00', baseline_overdue: '0.00' },
      brand_summary: [{
        brand: 'Aquafina', total_invoiced: '10000.00', total_paid: '0.00', total_outstanding: '11000.00',
        overdue_amount: '0.00', invoice_count: 1, payment_count: 0, latest_invoice_date: null, latest_payment_date: null,
        opening_balance: '5000.00', paid_in_tally: '4000.00', reconciles: false,
      }],
    };
    render(<MemoryRouter><AccountSummaryCard account={account} /></MemoryRouter>);
    expect(screen.getByTestId('pos-opening')).toHaveTextContent('₹5,000.00');
    expect(screen.getByTestId('pos-outstanding')).toHaveTextContent('₹11,000.00');
    expect(screen.getByTestId('ageing-total')).toBeInTheDocument();
    expect(screen.getByTestId('brand-opening-Aquafina')).toHaveTextContent('₹5,000');
    expect(screen.getByTestId('reconcile-warning')).toBeInTheDocument();
  });
});
