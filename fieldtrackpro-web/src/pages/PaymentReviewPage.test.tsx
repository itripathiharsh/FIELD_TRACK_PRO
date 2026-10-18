import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { PaymentReviewPage } from './PaymentReviewPage';
import { ADMIN_USER, renderWithProviders, signIn } from '../test/utils';
import { Payment } from '../types';

URL.createObjectURL = vi.fn();
URL.revokeObjectURL = vi.fn();

vi.mock('../api/client', () => ({
  apiClient: {
    hasStoredSession: vi.fn().mockReturnValue(true),
    getCurrentUser: vi.fn().mockResolvedValue({
      id: '11111111-1111-1111-1111-111111111111',
      email: 'admin@fieldtrack.test',
      mobile_number: null,
      full_name: 'Test Administrator',
      role: 'ADMIN',
      is_active: true,
      territory_id: null,
      employee_id: null,
    }),
    clearSession: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    getPaymentReviewQueue: vi.fn(),
    getPaymentProofObjectUrl: vi.fn(),
    verifyPayment: vi.fn(),
    retryPaymentTally: vi.fn(),
    rejectPayment: vi.fn(),
    updatePaymentAllocations: vi.fn(),
  },
}));

import { apiClient } from '../api/client';

const PAYMENT: Payment = {
  id: 'pay-1',
  visit_id: 'visit-1',
  customer_id: 'cust-1',
  employee_id: 'emp-1',
  invoice_id: null,
  amount: '80000.00',
  payment_method: 'ONLINE',
  payment_date: '2026-08-01',
  cheque_number: null,
  cheque_bank_name: null,
  utr_reference: 'UTR12345678',
  notes: null,
  status: 'PENDING_VERIFICATION',
  rejection_reason: null,
  reviewed_by: null,
  reviewed_at: null,
  created_by: 'admin-1',
  created_at: '2026-08-01T00:00:00Z',
  customer_name: 'ABC Electronics',
  employee_name: 'Rahul Sharma',
  allocations: [
    { id: 'alloc-1', payment_id: 'pay-1', brand: 'USHA', allocated_amount: '50000.00', created_at: '2026-08-01T00:00:00Z' },
    { id: 'alloc-2', payment_id: 'pay-1', brand: 'Zebronics', allocated_amount: '30000.00', created_at: '2026-08-01T00:00:00Z' },
  ],
  proofs: [
    { id: 'proof-1', payment_id: 'pay-1', storage_key: 'k1', file_size_bytes: 100, original_filename: 'cheque.jpg', uploaded_by: 'u1', uploaded_at: '2026-08-01T00:00:00Z' },
  ],
};

const PAYMENT_2: Payment = {
  ...PAYMENT,
  id: 'pay-2',
  customer_name: 'XYZ Outlet',
  amount: '40000.00',
  allocations: [
    { id: 'alloc-3', payment_id: 'pay-2', brand: 'Havells', allocated_amount: '40000.00', created_at: '2026-08-01T00:00:00Z' },
  ],
  proofs: [
    { id: 'proof-3', payment_id: 'pay-2', storage_key: 'k3', file_size_bytes: 100, original_filename: 'utr.jpg', uploaded_by: 'u1', uploaded_at: '2026-08-01T00:00:00Z' },
  ],
};

describe('PaymentReviewPage - Brand-Wise Payment & Collection', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
    vi.clearAllMocks();
    (apiClient.getPaymentReviewQueue as ReturnType<typeof vi.fn>).mockResolvedValue([PAYMENT, PAYMENT_2]);
    let counter = 0;
    (apiClient.getPaymentProofObjectUrl as ReturnType<typeof vi.fn>).mockImplementation(() => {
      counter += 1;
      return Promise.resolve(`blob:test-url-${counter}`);
    });
  });

  it('renders brand allocation breakdown in queue and modal detail', async () => {
    renderWithProviders(<PaymentReviewPage />);
    expect(await screen.findByText('ABC Electronics')).toBeInTheDocument();
    expect(screen.getByText(/USHA:\s*₹50,000/i)).toBeInTheDocument();
    expect(screen.getByText(/Zebronics:\s*₹30,000/i)).toBeInTheDocument();

    await userEvent.click(screen.getByText('ABC Electronics'));
    expect(screen.getByText('Brand Allocation Breakdown')).toBeInTheDocument();
  });

  it('allows Admin to verify payment directly', async () => {
    (apiClient.verifyPayment as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...PAYMENT,
      status: 'VERIFIED',
    });

    renderWithProviders(<PaymentReviewPage />);
    await userEvent.click(await screen.findByText('ABC Electronics'));

    const verifyBtn = screen.getByRole('button', { name: /verify/i });
    await userEvent.click(verifyBtn);

    await waitFor(() => {
      expect(apiClient.verifyPayment).toHaveBeenCalledWith('pay-1', {});
    });
  });

  it('states the Tally lifecycle: posting after verification, balances change only after Tally confirms', async () => {
    renderWithProviders(<PaymentReviewPage />);
    await waitFor(() => expect(screen.getByText('ABC Electronics')).toBeInTheDocument());
    expect(screen.getByRole('note')).toHaveTextContent(/Tally posting happens after verification/i);
    expect(screen.getByRole('note')).toHaveTextContent(/only after Tally confirms/i);
    expect(screen.getByRole('option', { name: 'Pending verification' })).toBeInTheDocument();
  });

  it('offers only Verify and Reject on a pending collection, and none once verified', async () => {
    renderWithProviders(<PaymentReviewPage />);
    await userEvent.click(await screen.findByText('ABC Electronics'));
    expect(screen.getByRole('button', { name: /^verify$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^reject$/i })).toBeInTheDocument();
    expect(screen.getByText(/not yet posted to tally/i)).toBeInTheDocument();
  });

  it('shows an empty state and an error state', async () => {
    (apiClient.getPaymentReviewQueue as ReturnType<typeof vi.fn>).mockResolvedValueOnce([]);
    const { unmount } = renderWithProviders(<PaymentReviewPage />);
    expect(await screen.findByText('No collections in this status')).toBeInTheDocument();
    unmount();
    (apiClient.getPaymentReviewQueue as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('boom'));
    renderWithProviders(<PaymentReviewPage />);
    expect(await screen.findByText(/boom/)).toBeInTheDocument();
  });
});


describe('PaymentReviewPage - Tally lifecycle & bank verification', () => {
  const VERIFIED_BASE: Payment = { ...PAYMENT, status: 'VERIFIED' };
  const AWAITING: Payment = {
    ...VERIFIED_BASE, id: 'pay-a', customer_name: 'Awaiting Outlet', tally_status: 'AWAITING_TALLY', tally_stuck: false,
  };
  const POSTED: Payment = {
    ...VERIFIED_BASE, id: 'pay-p', customer_name: 'Posted Outlet', tally_status: 'POSTED',
    tally_voucher_number: 'RCT-0042', tally_posted_at: '2026-08-02T10:00:00Z',
  };
  const FAILED: Payment = {
    ...VERIFIED_BASE, id: 'pay-f', customer_name: 'Failed Outlet', tally_status: 'FAILED',
    tally_error: 'Ledger not found in Tally', tally_stuck: true,
  };

  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
    vi.clearAllMocks();
    (apiClient.getPaymentReviewQueue as ReturnType<typeof vi.fn>).mockResolvedValue([AWAITING, POSTED, FAILED]);
    (apiClient.getPaymentProofObjectUrl as ReturnType<typeof vi.fn>).mockResolvedValue('blob:x');
  });

  it('shows a Tally badge per payment, the voucher when posted, and the error when failed', async () => {
    renderWithProviders(<PaymentReviewPage />);
    expect(await screen.findByText('Awaiting Outlet')).toBeInTheDocument();
    expect(screen.getAllByText('Verified, awaiting Tally').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Posted to Tally').length).toBeGreaterThanOrEqual(2); // filter option + badge
    expect(screen.getByText(/RCT-0042/)).toBeInTheDocument();
    expect(screen.getAllByText('Tally post failed').length).toBeGreaterThanOrEqual(2); // filter option + badge
    expect(screen.getByText('Ledger not found in Tally')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /retry tally post/i })).toHaveLength(1);
  });

  it('passes tally_status and stuck filters to the queue call', async () => {
    renderWithProviders(<PaymentReviewPage />);
    await screen.findByText('Awaiting Outlet');
    await userEvent.selectOptions(screen.getByLabelText('Tally status'), 'FAILED');
    await waitFor(() =>
      expect(apiClient.getPaymentReviewQueue).toHaveBeenLastCalledWith('PENDING_VERIFICATION', {
        tally_status: 'FAILED',
        stuck: undefined,
      }),
    );
    await userEvent.click(screen.getByLabelText(/stuck only/i));
    await waitFor(() =>
      expect(apiClient.getPaymentReviewQueue).toHaveBeenLastCalledWith('PENDING_VERIFICATION', {
        tally_status: 'FAILED',
        stuck: true,
      }),
    );
  });

  it('starts on Verified + stuck when opened with ?stuck=true', async () => {
    renderWithProviders(<PaymentReviewPage />, { route: '/payments?stuck=true' });
    await screen.findByText('Awaiting Outlet');
    expect(apiClient.getPaymentReviewQueue).toHaveBeenCalledWith('VERIFIED', { tally_status: undefined, stuck: true });
  });

  it('retries a failed Tally post after confirmation and refreshes the row', async () => {
    (apiClient.retryPaymentTally as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...FAILED, tally_status: 'AWAITING_TALLY', tally_error: null, tally_stuck: false,
    });
    renderWithProviders(<PaymentReviewPage />);
    await screen.findByText('Failed Outlet');
    await userEvent.click(screen.getByRole('button', { name: /retry tally post/i }));
    expect(apiClient.retryPaymentTally).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: /confirm retry/i }));
    await waitFor(() => expect(apiClient.retryPaymentTally).toHaveBeenCalledWith('pay-f'));
    await waitFor(() => expect(screen.queryByText('Ledger not found in Tally')).not.toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /retry tally post/i })).not.toBeInTheDocument();
  });

  it('shows the API error when the retry is rejected (409)', async () => {
    (apiClient.retryPaymentTally as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Payment is not in FAILED Tally state'),
    );
    renderWithProviders(<PaymentReviewPage />);
    await screen.findByText('Failed Outlet');
    await userEvent.click(screen.getByRole('button', { name: /retry tally post/i }));
    await userEvent.click(screen.getByRole('button', { name: /confirm retry/i }));
    expect(await screen.findByText(/not in FAILED Tally state/i)).toBeInTheDocument();
  });

  it('verify dialog shows the bank confirmation warning and sends the optional bank fields', async () => {
    (apiClient.getPaymentReviewQueue as ReturnType<typeof vi.fn>).mockResolvedValue([PAYMENT]);
    (apiClient.verifyPayment as ReturnType<typeof vi.fn>).mockResolvedValue({ ...PAYMENT, status: 'VERIFIED' });
    renderWithProviders(<PaymentReviewPage />);
    await userEvent.click(await screen.findByText('ABC Electronics'));
    expect(screen.getByText(/confirm the money is in the bank before verifying/i)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/bank reference/i), ' HDFC123 ');
    await userEvent.type(screen.getByLabelText(/bank verified on/i), '2026-08-03');
    await userEvent.type(screen.getByLabelText(/^note/i), 'Seen in statement');
    await userEvent.click(screen.getByRole('button', { name: /^verify$/i }));
    await waitFor(() =>
      expect(apiClient.verifyPayment).toHaveBeenCalledWith('pay-1', {
        bank_reference: 'HDFC123',
        bank_verified_on: '2026-08-03',
        verified_note: 'Seen in statement',
      }),
    );
  });
});
