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
  it('shows the Total Billed tile using total_invoiced', () => {
    render(<MemoryRouter><AccountSummaryCard account={BASE_ACCOUNT} /></MemoryRouter>);
    expect(screen.getByText('Total Billed')).toBeInTheDocument();
    expect(screen.getByText('₹10,000')).toBeInTheDocument();
  });

  it('shows Last Payment and Last Visit summary lines', () => {
    render(<MemoryRouter><AccountSummaryCard account={BASE_ACCOUNT} /></MemoryRouter>);
    expect(screen.getByText('Last Payment')).toBeInTheDocument();
    expect(screen.getByText(/₹4,000.*2026-08-01/)).toBeInTheDocument();
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
    expect(windowOpenSpy).toHaveBeenCalledWith('blob:proof-url', '_blank');
    windowOpenSpy.mockRestore();
  });

  it('does not show a Proof button for a payment with no attached proof', () => {
    const account: AccountSummary = { ...BASE_ACCOUNT, recent_payments: [BASE_ACCOUNT.most_recent_payment!] };
    render(<MemoryRouter><AccountSummaryCard account={account} /></MemoryRouter>);
    expect(screen.queryByRole('button', { name: /proof/i })).not.toBeInTheDocument();
  });
});
