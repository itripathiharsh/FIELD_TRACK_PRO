import { describe, expect, it, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';

import { EmployeeDailyLogsPage } from './EmployeeDailyLogsPage';
import {
  ADMIN_USER,
  baseRoutes,
  mockApi,
  renderWithProviders,
  signIn,
} from '../test/utils';

const MOCK_FIELD_OVERVIEW = {
  date: '2026-08-31',
  active_sessions_count: 1,
  completed_sessions_count: 1,
  total_field_force_count: 2,
  pending_location_proposals_count: 0,
  recent_prospects_count: 0,
  pending_payments_count: 0,
  sessions: [
    {
      employee_id: '33333333-3333-3333-3333-333333333333',
      employee_name: 'Rahul Sharma',
      employee_code: 'EMP-001',
      status: 'STARTED',
      start_time: '2026-08-31T09:00:00Z',
      start_accuracy_meters: 12.5,
      visits_total: 5,
      visits_planned: 4,
      visits_adhoc: 1,
      visits_completed: 3,
      collections_amount: '15000',
    },
    {
      employee_id: '44444444-4444-4444-4444-444444444444',
      employee_name: 'Priya Patel',
      employee_code: 'EMP-002',
      status: 'COMPLETED',
      start_time: '2026-08-31T08:30:00Z',
      start_accuracy_meters: 15.0,
      visits_total: 4,
      visits_planned: 4,
      visits_adhoc: 0,
      visits_completed: 4,
      collections_amount: '25000',
    },
  ],
  upcoming_follow_ups: [],
};

describe('EmployeeDailyLogsPage', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
  });

  it('renders employee daily logs title, summary cards, and data table', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/workday/overview/today': MOCK_FIELD_OVERVIEW,
    });

    renderWithProviders(<EmployeeDailyLogsPage />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: /Employee Daily Logs/i })).toBeInTheDocument();
    });

    // Check Rep Names
    expect(screen.getByText('Rahul Sharma')).toBeInTheDocument();
    expect(screen.getByText('#EMP-001')).toBeInTheDocument();
    expect(screen.getByText('Priya Patel')).toBeInTheDocument();
    expect(screen.getByText('#EMP-002')).toBeInTheDocument();

    // Check KPI counts
    expect(screen.getByText('ACTIVE IN FIELD')).toBeInTheDocument();
    expect(screen.getByText('SHIFT COMPLETED')).toBeInTheDocument();
  });

  it('filters table rows by representative search query', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/workday/overview/today': MOCK_FIELD_OVERVIEW,
    });

    renderWithProviders(<EmployeeDailyLogsPage />);

    await waitFor(() => {
      expect(screen.getByText('Rahul Sharma')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/Search representative name or employee code/i);
    fireEvent.change(searchInput, { target: { value: 'Priya' } });

    expect(screen.queryByText('Rahul Sharma')).not.toBeInTheDocument();
    expect(screen.getByText('Priya Patel')).toBeInTheDocument();
  });

  it('filters table rows by status', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/workday/overview/today': MOCK_FIELD_OVERVIEW,
    });

    renderWithProviders(<EmployeeDailyLogsPage />);

    await waitFor(() => {
      expect(screen.getByText('Rahul Sharma')).toBeInTheDocument();
    });

    const statusSelect = screen.getByRole('combobox');
    fireEvent.change(statusSelect, { target: { value: 'COMPLETED' } });

    expect(screen.queryByText('Rahul Sharma')).not.toBeInTheDocument();
    expect(screen.getByText('Priya Patel')).toBeInTheDocument();
  });
});
