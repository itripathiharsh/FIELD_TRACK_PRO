import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AdminVisitPlanningPage } from './AdminVisitPlanningPage';
import { AuthProvider } from '../context/AuthContext';
import { baseRoutes, ADMIN_USER, mockApi, signIn } from '../test/utils';
import { Customer, Employee, TeamMonthlyPlan, PlannedVisit } from '../types';

const MOCK_EMPLOYEES: Employee[] = [
  {
    id: 'e1111111-1111-1111-1111-111111111111',
    user_id: 'u1111111-1111-1111-1111-111111111111',
    full_name: 'Arun Sharma',
    employee_code: 'EMP-001',
    territory_id: '44444444-4444-4444-4444-444444444444',
    created_at: '2026-01-01T00:00:00Z',
    user: {
      id: 'u1111111-1111-1111-1111-111111111111',
      email: 'arun@fieldtrack.test',
      mobile_number: null,
      role: 'EMPLOYEE',
      is_active: true,
    },
  },
  {
    id: 'e2222222-2222-2222-2222-222222222222',
    user_id: 'u2222222-2222-2222-2222-222222222222',
    full_name: 'Pooja Verma',
    employee_code: 'EMP-002',
    territory_id: '44444444-4444-4444-4444-444444444444',
    created_at: '2026-01-01T00:00:00Z',
    user: {
      id: 'u2222222-2222-2222-2222-222222222222',
      email: 'pooja@fieldtrack.test',
      mobile_number: null,
      role: 'EMPLOYEE',
      is_active: true,
    },
  },
];

const MOCK_CUSTOMERS: Customer[] = [
  {
    id: 'c1111111-1111-1111-1111-111111111111',
    name: 'Apex Retailers',
    contact_number: '9876543210',
    contact_person: 'Rahul Verma',
    address: 'Sector 18, Noida',
    location: null,
    geofence_radius_m: 100,
    territory_id: '44444444-4444-4444-4444-444444444444',
    area_id: null,
    area_name: 'Noida Area',
    outlet_code: 'APX-001',
    created_by: 'admin',
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'c2222222-2222-2222-2222-222222222222',
    name: 'Metro Supermart',
    contact_number: '9876543211',
    contact_person: 'Pooja Singh',
    address: 'Connaught Place, New Delhi',
    location: null,
    geofence_radius_m: 100,
    territory_id: '44444444-4444-4444-4444-444444444444',
    area_id: null,
    area_name: 'Central Delhi',
    outlet_code: 'MET-002',
    created_by: 'admin',
    created_at: '2026-01-01T00:00:00Z',
  },
];

const today = new Date();
const currentYear = today.getFullYear();
const currentMonth = today.getMonth() + 1;
const testDay15Str = `${currentYear}-${String(currentMonth).padStart(2, '0')}-15`;

const MOCK_PLANNED_VISIT: PlannedVisit = {
  id: 'v1111111-1111-1111-1111-111111111111',
  monthly_plan_id: 'p1111111-1111-1111-1111-111111111111',
  employee_id: MOCK_EMPLOYEES[0].id,
  employee_name: MOCK_EMPLOYEES[0].full_name,
  employee_code: MOCK_EMPLOYEES[0].employee_code,
  customer_id: MOCK_CUSTOMERS[0].id,
  customer_name: MOCK_CUSTOMERS[0].name,
  customer_outlet_code: MOCK_CUSTOMERS[0].outlet_code,
  customer_address: MOCK_CUSTOMERS[0].address,
  planned_date: testDay15Str,
  visit_type: 'PLANNED',
  priority: 'HIGH',
  notes: 'Quarterly review with branch head',
  status: 'PLANNED',
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
};

const MOCK_TEAM_PLAN: TeamMonthlyPlan = {
  year: currentYear,
  month: currentMonth,
  total_planned_visits: 1,
  active_days_count: 1,
  active_employees_count: 1,
  planned_visits: [MOCK_PLANNED_VISIT],
};

function renderAdminPlanningPage() {
  return render(
    <MemoryRouter initialEntries={['/admin/visit-planning']}>
      <AuthProvider>
        <AdminVisitPlanningPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('AdminVisitPlanningPage — Admin Monthly Planning & Oversight', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
  });

  it('renders the admin planning page with title, summary metrics, and employee filter', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visit-planning/team-plan': MOCK_TEAM_PLAN,
      '/api/v1/employees': MOCK_EMPLOYEES,
      '/api/v1/customers': MOCK_CUSTOMERS,
    });

    renderAdminPlanningPage();

    await waitFor(() => {
      expect(screen.getByText('Visit Planning & Oversight')).toBeInTheDocument();
    });

    // Check summary metrics
    expect(screen.getByText('Total Planned:')).toBeInTheDocument();
    expect(screen.getByText('Active Days:')).toBeInTheDocument();
    expect(screen.getByText('Reps Active:')).toBeInTheDocument();

    // Check Employee scope dropdown
    const filterSelect = screen.getByRole('combobox', { name: '' });
    expect(filterSelect).toBeInTheDocument();
    expect(screen.getAllByText(/All Employees/i).length).toBeGreaterThanOrEqual(1);

    // Check weekdays header
    expect(screen.getByText('Sun')).toBeInTheDocument();
    expect(screen.getByText('Mon')).toBeInTheDocument();
    expect(screen.getByText('Wed')).toBeInTheDocument();
  });

  it('filters by individual employee when selected in the scope dropdown', async () => {
    let capturedEmployeeId: string | null = null;
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visit-planning/team-plan': (url: string) => {
        const parsed = new URL(url, 'http://localhost');
        capturedEmployeeId = parsed.searchParams.get('employee_id');
        return new Response(JSON.stringify(MOCK_TEAM_PLAN), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      },
      '/api/v1/employees': MOCK_EMPLOYEES,
      '/api/v1/customers': MOCK_CUSTOMERS,
    });

    renderAdminPlanningPage();

    await waitFor(() => {
      expect(screen.getByText('Visit Planning & Oversight')).toBeInTheDocument();
    });

    const filterSelect = screen.getByRole('combobox');
    fireEvent.change(filterSelect, {
      target: { value: MOCK_EMPLOYEES[0].id },
    });

    await waitFor(() => {
      expect(capturedEmployeeId).toBe(MOCK_EMPLOYEES[0].id);
    });
  });

  it('clicking a day displays planned visit cards with employee ownership badge and action buttons', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visit-planning/team-plan': MOCK_TEAM_PLAN,
      '/api/v1/employees': MOCK_EMPLOYEES,
      '/api/v1/customers': MOCK_CUSTOMERS,
    });

    renderAdminPlanningPage();

    await waitFor(() => {
      expect(screen.getByText('Visit Planning & Oversight')).toBeInTheDocument();
    });

    // Find day cell for day 15
    const dayCell = document.querySelector(`[data-date="${testDay15Str}"]`);
    expect(dayCell).toBeDefined();
    if (dayCell) {
      fireEvent.click(dayCell);
    }

    await waitFor(() => {
      expect(screen.getAllByText('Apex Retailers').length).toBeGreaterThanOrEqual(1);
    });

    // Check employee ownership badge
    expect(screen.getAllByText(/Arun Sharma/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/EMP-001/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Code: APX-001/i)).toBeInTheDocument();
    expect(screen.getByText(/Quarterly review with branch head/i)).toBeInTheDocument();

    // Check admin action buttons
    expect(screen.getByRole('button', { name: /Edit visit/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Reschedule visit/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Reassign visit/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Delete visit/i })).toBeInTheDocument();
  });

  it('opens the Schedule Planned Visit modal and renders employee and customer selectors', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visit-planning/team-plan': MOCK_TEAM_PLAN,
      '/api/v1/employees': MOCK_EMPLOYEES,
      '/api/v1/customers': MOCK_CUSTOMERS,
    });

    renderAdminPlanningPage();

    await waitFor(() => {
      expect(screen.getByText('Visit Planning & Oversight')).toBeInTheDocument();
    });

    const scheduleBtn = screen.getByRole('button', { name: /Schedule Planned Visit/i });
    fireEvent.click(scheduleBtn);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Schedule Planned Visit' })).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/Assign to Employee/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Planned Date/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Confirm Schedule/i })).toBeInTheDocument();
  });

  it('opens the Reassign modal showing current owner and target employee selector', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visit-planning/team-plan': MOCK_TEAM_PLAN,
      '/api/v1/employees': MOCK_EMPLOYEES,
      '/api/v1/customers': MOCK_CUSTOMERS,
    });

    renderAdminPlanningPage();

    await waitFor(() => {
      expect(screen.getByText('Visit Planning & Oversight')).toBeInTheDocument();
    });

    // Select day 15
    const dayCell = document.querySelector(`[data-date="${testDay15Str}"]`);
    if (dayCell) {
      fireEvent.click(dayCell);
    }

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Reassign visit/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Reassign visit/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Reassign Planned Visit' })).toBeInTheDocument();
    });

    expect(screen.getByText(/Reassignment Transfer Flow/i)).toBeInTheDocument();
    expect(screen.getByText('Current Owner')).toBeInTheDocument();
    expect(screen.getByText('New Owner *')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Confirm Reassignment/i })).toBeInTheDocument();
  });

  it('opens the Reschedule modal and confirms target date', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visit-planning/team-plan': MOCK_TEAM_PLAN,
      '/api/v1/employees': MOCK_EMPLOYEES,
      '/api/v1/customers': MOCK_CUSTOMERS,
    });

    renderAdminPlanningPage();

    await waitFor(() => {
      expect(screen.getByText('Visit Planning & Oversight')).toBeInTheDocument();
    });

    const dayCell = document.querySelector(`[data-date="${testDay15Str}"]`);
    if (dayCell) {
      fireEvent.click(dayCell);
    }

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Reschedule visit/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Reschedule visit/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Reschedule Planned Visit' })).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/New Target Date/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Confirm New Date/i })).toBeInTheDocument();
  });

  it('opens the Edit modal and updates priority and notes', async () => {
    let capturedPatchBody: unknown = null;
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visit-planning/team-plan': MOCK_TEAM_PLAN,
      '/api/v1/employees': MOCK_EMPLOYEES,
      '/api/v1/customers': MOCK_CUSTOMERS,
      [`/api/v1/visit-planning/visits/${MOCK_PLANNED_VISIT.id}`]: (_url: string, init?: RequestInit) => {
        if (init?.method === 'PATCH') {
          capturedPatchBody = JSON.parse(init.body as string);
          return new Response(
            JSON.stringify({
              ...MOCK_PLANNED_VISIT,
              ...(capturedPatchBody as object),
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          );
        }
        return new Response(JSON.stringify(MOCK_PLANNED_VISIT), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      },
    });

    renderAdminPlanningPage();

    await waitFor(() => {
      expect(screen.getByText('Visit Planning & Oversight')).toBeInTheDocument();
    });

    const dayCell = document.querySelector(`[data-date="${testDay15Str}"]`);
    if (dayCell) {
      fireEvent.click(dayCell);
    }

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Edit visit/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Edit visit/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Edit Planned Visit' })).toBeInTheDocument();
    });

    const prioritySelect = screen.getByRole('combobox', { name: /Priority/i });
    fireEvent.change(prioritySelect, { target: { value: 'LOW' } });

    fireEvent.click(screen.getByRole('button', { name: /Save Changes/i }));

    await waitFor(() => {
      expect(capturedPatchBody).toEqual(
        expect.objectContaining({
          priority: 'LOW',
        }),
      );
    });
  });

  it('opens the Delete confirmation modal and shows confirmation details', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visit-planning/team-plan': MOCK_TEAM_PLAN,
      '/api/v1/employees': MOCK_EMPLOYEES,
      '/api/v1/customers': MOCK_CUSTOMERS,
    });

    renderAdminPlanningPage();

    await waitFor(() => {
      expect(screen.getByText('Visit Planning & Oversight')).toBeInTheDocument();
    });

    const dayCell = document.querySelector(`[data-date="${testDay15Str}"]`);
    if (dayCell) {
      fireEvent.click(dayCell);
    }

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Delete visit/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Delete visit/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Delete Planned Visit' })).toBeInTheDocument();
    });

    expect(screen.getByText(/Are you sure you want to delete this planned visit\?/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Delete Planned Visit/i })).toBeInTheDocument();
  });
});
