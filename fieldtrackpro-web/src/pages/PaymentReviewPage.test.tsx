import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { PaymentReviewPage } from './PaymentReviewPage';
import { ADMIN_USER, renderWithProviders, signIn } from '../test/utils';
import { Payment } from '../types';

URL.createObjectURL = vi.fn();
URL.revokeObjectURL = vi.fn();

// vi.mock's factory is hoisted above imports, so it cannot reference
// ADMIN_USER (imported below) - an equivalent literal is inlined instead.
vi.mock('../api/client', () => ({
  apiClient: {
    // AuthProvider's session-restore effect needs these to resolve cleanly.
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
  },
}));

import { apiClient } from '../api/client';

const PAYMENT: Payment = {
  id: 'pay-1',
  visit_id: 'visit-1',
  customer_id: 'cust-1',
  employee_id: 'emp-1',
  invoice_id: null,
  amount: '500.00',
  payment_method: 'CASH',
  payment_date: '2026-08-01',
  cheque_number: null,
  cheque_bank_name: null,
  utr_reference: null,
  notes: null,
  status: 'PENDING_VERIFICATION',
  rejection_reason: null,
  reviewed_by: null,
  reviewed_at: null,
  created_by: 'admin-1',
  created_at: '2026-08-01T00:00:00Z',
  customer_name: 'ABC Traders',
  employee_name: 'Rahul Sharma',
  proofs: [
    { id: 'proof-1', payment_id: 'pay-1', storage_key: 'k1', file_size_bytes: 100, original_filename: 'cheque.jpg', uploaded_by: 'u1', uploaded_at: '2026-08-01T00:00:00Z' },
    { id: 'proof-2', payment_id: 'pay-1', storage_key: 'k2', file_size_bytes: 100, original_filename: 'cheque2.jpg', uploaded_by: 'u1', uploaded_at: '2026-08-01T00:00:00Z' },
  ],
};

const PAYMENT_2: Payment = { ...PAYMENT, id: 'pay-2', customer_name: 'XYZ Outlet', proofs: [
  { id: 'proof-3', payment_id: 'pay-2', storage_key: 'k3', file_size_bytes: 100, original_filename: 'utr.jpg', uploaded_by: 'u1', uploaded_at: '2026-08-01T00:00:00Z' },
] };

describe('PaymentReviewPage - blob URL lifecycle (P1-11)', () => {
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

  it('fetches a preview object URL for each proof when a payment is opened', async () => {
    renderWithProviders(<PaymentReviewPage />);
    await userEvent.click(await screen.findByText('ABC Traders'));

    await waitFor(() => {
      expect(apiClient.getPaymentProofObjectUrl).toHaveBeenCalledWith('proof-1');
      expect(apiClient.getPaymentProofObjectUrl).toHaveBeenCalledWith('proof-2');
    });
  });

  it('revokes every created object URL when a different payment is opened', async () => {
    renderWithProviders(<PaymentReviewPage />);

    await userEvent.click(await screen.findByText('ABC Traders'));
    await waitFor(() => expect(apiClient.getPaymentProofObjectUrl).toHaveBeenCalledTimes(2));

    // Close the first, open the second.
    await userEvent.click(screen.getByRole('button', { name: 'Close modal' }));
    await userEvent.click(await screen.findByText('XYZ Outlet'));

    await waitFor(() => {
      // The two URLs created for pay-1's proofs must both have been revoked.
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test-url-1');
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test-url-2');
    });
  });

  it('revokes object URLs when the modal is closed without opening another payment', async () => {
    renderWithProviders(<PaymentReviewPage />);
    await userEvent.click(await screen.findByText('ABC Traders'));
    await waitFor(() => expect(apiClient.getPaymentProofObjectUrl).toHaveBeenCalledTimes(2));

    await userEvent.keyboard('{Escape}');

    await waitFor(() => {
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test-url-1');
      expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test-url-2');
    });
  });

  it('does not re-fetch proof URLs on an unrelated re-render of the same open payment', async () => {
    renderWithProviders(<PaymentReviewPage />);
    await userEvent.click(await screen.findByText('ABC Traders'));
    await waitFor(() => expect(apiClient.getPaymentProofObjectUrl).toHaveBeenCalledTimes(2));

    // Typing into the rejection-reason field re-renders the page (state
    // change) without changing which payment is open - the URL-fetching
    // effect is keyed on `selected`, not on every render, so this must not
    // trigger additional fetches.
    await userEvent.type(screen.getByLabelText(/rejection reason/i), 'not legible');

    expect(apiClient.getPaymentProofObjectUrl).toHaveBeenCalledTimes(2);
  });
});
