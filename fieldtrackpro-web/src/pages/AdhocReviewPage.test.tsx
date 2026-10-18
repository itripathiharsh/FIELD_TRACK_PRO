import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { AdhocReviewPage } from './AdhocReviewPage';
import { ADMIN_USER, renderWithProviders, signIn } from '../test/utils';
import { Visit } from '../types';

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
    getAdhocReviewVisits: vi.fn(),
  },
}));

import { apiClient } from '../api/client';

const mk = (id: string, over: Partial<Visit>): Visit => ({
  id,
  customer_id: 'c1',
  employee_id: 'e1',
  scheduled_at: '2026-08-01T05:00:00Z',
  status: 'COMPLETED',
  visit_type: 'AD_HOC',
  adhoc_reason: 'Payment Follow-up',
  adhoc_notes: 'Owner asked us to come',
  check_in_at: '2026-08-01T05:30:00Z',
  check_out_at: null,
  synced: true,
  created_by: 'u',
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
  required_form_id: null,
  required_form_name: null,
  required_form_status: null,
  employee_name: 'Rahul Sharma',
  customer_name: 'ABC Electronics',
  customer_outlet_code: 'UPDD001',
  is_adhoc: true,
  review_label: 'AD-HOC',
  ...over,
});

describe('AdhocReviewPage', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
    vi.clearAllMocks();
  });

  it('lists ad-hoc visits with employee, outlet, reason, notes and a warning label', async () => {
    (apiClient.getAdhocReviewVisits as ReturnType<typeof vi.fn>).mockResolvedValue({
      items: [
        mk('v1', {}),
        mk('v2', { customer_name: 'Far Outlet', review_label: 'AD-HOC · OUTSIDE ASSIGNMENT', outside_assignment: true }),
      ],
      total: 2,
    });
    renderWithProviders(<AdhocReviewPage />);
    expect(await screen.findByText('Far Outlet')).toBeInTheDocument();
    expect(screen.getAllByText('Rahul Sharma')).toHaveLength(2);
    expect(screen.getAllByText('Payment Follow-up')).toHaveLength(2);
    const badges = screen.getAllByTestId('visit-review-badge');
    expect(badges[0]).toHaveTextContent(/^AD-HOC$/);
    expect(badges[1]).toHaveTextContent('AD-HOC · OUTSIDE ASSIGNMENT');
    expect(badges[1].className).toMatch(/amber/);
    expect(badges[0].className).not.toMatch(/amber/);
  });

  it('paginates and applies the outside-assignment filter', async () => {
    (apiClient.getAdhocReviewVisits as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [mk('v1', {})], total: 45 });
    renderWithProviders(<AdhocReviewPage />);
    await screen.findByText('ABC Electronics');
    expect(screen.getByText(/Page 1 of 3/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() =>
      expect(apiClient.getAdhocReviewVisits).toHaveBeenLastCalledWith({
        outside_assignment: undefined,
        skip: 20,
        limit: 20,
      }),
    );
    await userEvent.click(screen.getByLabelText(/outside assignment only/i));
    await waitFor(() =>
      expect(apiClient.getAdhocReviewVisits).toHaveBeenLastCalledWith({
        outside_assignment: true,
        skip: 0,
        limit: 20,
      }),
    );
  });

  it('shows empty and error states', async () => {
    (apiClient.getAdhocReviewVisits as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ items: [], total: 0 });
    const { unmount } = renderWithProviders(<AdhocReviewPage />);
    expect(await screen.findByText('No ad-hoc visits to review')).toBeInTheDocument();
    unmount();
    (apiClient.getAdhocReviewVisits as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('kaput'));
    renderWithProviders(<AdhocReviewPage />);
    expect(await screen.findByText(/kaput/)).toBeInTheDocument();
  });
});
