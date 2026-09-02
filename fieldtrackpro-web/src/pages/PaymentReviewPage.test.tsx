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
      expect(apiClient.verifyPayment).toHaveBeenCalledWith('pay-1');
    });
  });
});
