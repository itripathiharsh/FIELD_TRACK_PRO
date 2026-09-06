import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { RequirementsPage } from './RequirementsPage';
import { ADMIN_USER, renderWithProviders, signIn } from '../test/utils';
import { CustomerRequirement } from '../types';

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
    getAllRequirements: vi.fn(),
    approveRequirement: vi.fn(),
    partiallyApproveRequirement: vi.fn(),
    rejectRequirement: vi.fn(),
  },
}));

import { apiClient } from '../api/client';

const MOCK_REQUIREMENTS: CustomerRequirement[] = [
  {
    id: 'req-001',
    customer_id: 'cust-1',
    customer_name: 'Shree Radhey Appliances',
    outlet_code: 'UP01RADHEY',
    visit_id: 'visit-101',
    brand: 'Usha',
    requirement_type: 'Bulk Order',
    product_details: '10 x Usha Ceiling Fans High-Speed',
    quantity: 10,
    expected_value: 25000,
    notes: 'Urgent delivery required before weekend',
    status: 'PENDING',
    photo_url: 'http://test/storage/photo1.jpg',
    created_by: 'user-emp-1',
    creator_name: 'Ramesh Field Rep',
    employee_name: 'Ramesh Field Rep',
    created_at: '2026-09-06T10:00:00Z',
    updated_at: '2026-09-06T10:00:00Z',
  },
  {
    id: 'req-002',
    customer_id: 'cust-2',
    customer_name: 'Kanpur Electricals',
    outlet_code: 'UP02KANPUR',
    brand: 'Havells',
    product_details: '5 x Industrial Exhaust Fans',
    quantity: 5,
    expected_value: 40000,
    status: 'PARTIALLY_APPROVED',
    approved_quantity: 2,
    approved_value: 16000,
    admin_notes: 'Partial stock allocation due to shortage',
    decided_by: '11111111-1111-1111-1111-111111111111',
    decider_name: 'Test Administrator',
    decided_at: '2026-09-06T11:00:00Z',
    created_by: 'user-emp-1',
    creator_name: 'Ramesh Field Rep',
    employee_name: 'Ramesh Field Rep',
    created_at: '2026-09-06T09:00:00Z',
    updated_at: '2026-09-06T11:00:00Z',
  },
];

describe('RequirementsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    signIn(ADMIN_USER);
    vi.mocked(apiClient.getAllRequirements).mockResolvedValue(MOCK_REQUIREMENTS);
  });

  it('renders KPI metrics and customer requirements table', async () => {
    renderWithProviders(<RequirementsPage />);

    expect(await screen.findByText('Customer Requirements')).toBeInTheDocument();
    expect(screen.getByText('Shree Radhey Appliances')).toBeInTheDocument();
    expect(screen.getByText('Kanpur Electricals')).toBeInTheDocument();
    expect(screen.getByText('10 x Usha Ceiling Fans High-Speed')).toBeInTheDocument();

    // Verify KPI counters
    expect(screen.getByText('Total Requests')).toBeInTheDocument();
    expect(screen.getAllByText('Pending Review').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Partially Approved').length).toBeGreaterThan(0);
  });

  it('opens review modal and supports partial approval with preserved original request', async () => {
    const user = userEvent.setup();
    vi.mocked(apiClient.partiallyApproveRequirement).mockResolvedValue({
      ...MOCK_REQUIREMENTS[0],
      status: 'PARTIALLY_APPROVED',
      approved_quantity: 4,
      approved_value: 10000,
      admin_notes: 'Approved 4 units for initial dispatch',
      decider_name: 'Test Administrator',
      decided_at: '2026-09-06T12:00:00Z',
    });

    renderWithProviders(<RequirementsPage />);

    // Click "Review & Decide" for the first requirement
    const reviewButtons = await screen.findAllByRole('button', { name: /review & decide/i });
    await user.click(reviewButtons[0]);

    // Modal should be open
    expect(await screen.findByText(/Original Field Request \(Preserved\)/i)).toBeInTheDocument();
    // Preserved fields visible
    expect(screen.getAllByText('10 units').length).toBeGreaterThan(0);
    expect(screen.getAllByText('₹25,000').length).toBeGreaterThan(0);

    // Select Partially Approve tab
    const partialTab = screen.getByRole('button', { name: /^partially approve$/i });
    await user.click(partialTab);

    // Fill approved quantity and value
    const qtyInput = screen.getByPlaceholderText('e.g. 5');
    const valInput = screen.getByPlaceholderText('e.g. 25000');
    await user.clear(qtyInput);
    await user.type(qtyInput, '4');
    await user.clear(valInput);
    await user.type(valInput, '10000');

    // Enter admin notes
    const notesInput = screen.getByPlaceholderText(/Reason for partial allocation/i);
    await user.type(notesInput, 'Approved 4 units for initial dispatch');

    // Submit partial approval
    const confirmBtn = screen.getByRole('button', { name: /confirm partial approval/i });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(apiClient.partiallyApproveRequirement).toHaveBeenCalledWith('req-001', {
        approved_quantity: 4,
        approved_value: 10000,
        admin_notes: 'Approved 4 units for initial dispatch',
      });
    });
  });
});
