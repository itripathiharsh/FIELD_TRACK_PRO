import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { MonthlyVisitPlanningPage } from './MonthlyVisitPlanningPage';
import { AuthProvider } from '../context/AuthContext';
import { baseRoutes, EMPLOYEE_USER, mockApi, signIn } from '../test/utils';
import { MonthlyVisitPlan, Customer } from '../types';

const MOCK_CUSTOMERS: Customer[] = [
  {
    id: 'c1111111-1111-1111-1111-111111111111',
    name: 'Reliance Digital Store',
    contact_number: '9876543210',
    contact_person: 'Rahul Verma',
    address: 'Sector 18, Noida',
    location: null,
    geofence_radius_m: 100,
    territory_id: '44444444-4444-4444-4444-444444444444',
    area_id: null,
    area_name: 'Noida Area',
    outlet_code: 'REL-001',
    created_by: 'admin',
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'c2222222-2222-2222-2222-222222222222',
    name: 'Croma Megastore',
    contact_number: '9876543211',
    contact_person: 'Pooja Singh',
    address: 'Connaught Place, New Delhi',
    location: null,
    geofence_radius_m: 100,
    territory_id: '44444444-4444-4444-4444-444444444444',
    area_id: null,
    area_name: 'Central Delhi',
    outlet_code: 'CRO-002',
    created_by: 'admin',
    created_at: '2026-01-01T00:00:00Z',
  },
];

const today = new Date();
const currentYear = today.getFullYear();
const currentMonth = today.getMonth() + 1;
const testDay15Str = `${currentYear}-${String(currentMonth).padStart(2, '0')}-15`;

const MOCK_PLAN: MonthlyVisitPlan = {
  id: 'p1111111-1111-1111-1111-111111111111',
  employee_id: '33333333-3333-3333-3333-333333333333',
  year: currentYear,
  month: currentMonth,
  status: 'ACTIVE',
  notes: 'September targets',
  created_by: EMPLOYEE_USER.id,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
  employee_name: 'Test Field Rep',
  employee_code: 'EMP-001',
  planned_visits: [
    {
      id: 'v1111111-1111-1111-1111-111111111111',
      monthly_plan_id: 'p1111111-1111-1111-1111-111111111111',
      employee_id: '33333333-3333-3333-3333-333333333333',
      customer_id: MOCK_CUSTOMERS[0].id,
      planned_date: testDay15Str,
      visit_type: 'PLANNED',
      priority: 'HIGH',
      notes: 'Quarterly order booking discussion',
      status: 'PLANNED',
      created_at: '2026-09-01T00:00:00Z',
      updated_at: '2026-09-01T00:00:00Z',
      customer_name: 'Reliance Digital Store',
      customer_outlet_code: 'REL-001',
      customer_address: 'Sector 18, Noida',
    },
  ],
  total_planned_visits: 1,
  active_days_count: 1,
};

function renderPlanningPage() {
  return render(
    <MemoryRouter initialEntries={['/visit-planning']}>
      <AuthProvider>
        <MonthlyVisitPlanningPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('MonthlyVisitPlanningPage — Employee Monthly Planning', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(EMPLOYEE_USER);
  });

  it('loads monthly plan and renders summary KPIs and calendar grid', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/visit-planning/my-plan': MOCK_PLAN,
      '/api/v1/customers': MOCK_CUSTOMERS,
    });

    renderPlanningPage();

    await waitFor(() => {
      expect(screen.getByText(/Monthly Visit Planning/i)).toBeInTheDocument();
    });

    // Check KPI metrics
    expect(screen.getByText('Total Planned:')).toBeInTheDocument();
    expect(screen.getByText('Working Days:')).toBeInTheDocument();
    expect(screen.getByText('Plan Status:')).toBeInTheDocument();

    // Check calendar header & weekdays
    expect(screen.getByText('Schedule Overview')).toBeInTheDocument();
    expect(screen.getByText('Mon')).toBeInTheDocument();
    expect(screen.getByText('Wed')).toBeInTheDocument();
    expect(screen.getByText('Fri')).toBeInTheDocument();
  });

  it('clicking a day with planned visits displays the visit cards with customer details and actions', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/visit-planning/my-plan': MOCK_PLAN,
      '/api/v1/customers': MOCK_CUSTOMERS,
    });

    renderPlanningPage();

    await waitFor(() => {
      expect(screen.getByText(/Schedule Overview/i)).toBeInTheDocument();
    });

    // Find day button for 15
    const dayButtons = screen.getAllByRole('button');
    const day15Btn = dayButtons.find((b) => b.textContent?.includes('15'));
    expect(day15Btn).toBeDefined();

    if (day15Btn) {
      fireEvent.click(day15Btn);
    }

    await waitFor(() => {
      expect(screen.getAllByText('Reliance Digital Store').length).toBeGreaterThanOrEqual(1);
    });

    expect(screen.getByText(/Sector 18, Noida/i)).toBeInTheDocument();
    expect(screen.getByText('Quarterly order booking discussion')).toBeInTheDocument();
    expect(screen.getAllByText(/HIGH/i).length).toBeGreaterThanOrEqual(1);
  });

  it('displays a friendly informational state on zero-visit days without errors', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/visit-planning/my-plan': MOCK_PLAN,
      '/api/v1/customers': MOCK_CUSTOMERS,
    });

    renderPlanningPage();

    await waitFor(() => {
      expect(screen.getByText(/Schedule Overview/i)).toBeInTheDocument();
    });

    // Find day button for 28 (which has 0 visits in mock)
    const dayButtons = screen.getAllByRole('button');
    const day28Btn = dayButtons.find((b) => b.textContent?.includes('28'));
    expect(day28Btn).toBeDefined();

    if (day28Btn) {
      fireEvent.click(day28Btn);
    }

    await waitFor(() => {
      expect(screen.getByText(/No visits planned for this date/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Zero planned visits is completely valid/i)).toBeInTheDocument();
  });

  it('opens the Schedule Planned Visit modal when Plan Visit is clicked', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/visit-planning/my-plan': MOCK_PLAN,
      '/api/v1/customers': MOCK_CUSTOMERS,
    });

    renderPlanningPage();

    await waitFor(() => {
      expect(screen.getByText(/Schedule Overview/i)).toBeInTheDocument();
    });

    // Click "Plan Visit" header button
    const planVisitButtons = screen.getAllByRole('button', { name: /plan visit/i });
    expect(planVisitButtons.length).toBeGreaterThanOrEqual(1);
    fireEvent.click(planVisitButtons[0]);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Schedule Planned Visit/i })).toBeInTheDocument();
    });

    expect(screen.getByText(/Select Customer \/ Outlet/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Planned Date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Visit Type/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Priority/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Add to Plan/i })).toBeInTheDocument();
  });
});
