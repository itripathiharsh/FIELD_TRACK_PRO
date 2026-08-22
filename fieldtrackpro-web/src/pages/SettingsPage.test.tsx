import { describe, expect, it, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, signIn, ADMIN_USER, mockApi, baseRoutes, json } from '../test/utils';
import { SettingsPage } from './SettingsPage';

describe('SettingsPage Enterprise Admin Redesign', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/health': json({ status: 'UP', service: 'fieldtrackpro-backend' }),
      '/api/v1/employees': json([
        { id: '1', employee_code: '11015', full_name: 'Neeraj Rajput', working_profile: 'Sales Manager' },
        { id: '2', employee_code: '11001', full_name: 'Sahil Verma', working_profile: 'FOS' },
        { id: '3', employee_code: '11012', full_name: 'Pankaj Dixit', working_profile: 'Accountant' },
      ]),
      '/api/v1/territories': json([{ id: 't1', name: 'Lucknow' }]),
      '/api/v1/areas': json([{ id: 'a1', name: 'Aminabad' }]),
      '/api/v1/customers': json([{ id: 'c1', name: 'Outlet 1' }]),
    });
  });

  it('renders all business settings tabs', async () => {
    renderWithProviders(<SettingsPage />);

    expect(screen.getByRole('heading', { name: /Admin Settings & Enterprise Controls/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Organization/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Users & Roles/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Field Operations/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Data & Ingestion/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Integrations & ERP/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Notifications/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /System Diagnostics/i })).toBeInTheDocument();
  });

  it('switches tabs smoothly and displays organization details', async () => {
    renderWithProviders(<SettingsPage />);

    expect(screen.getByText(/SGRG Services Private Limited/i)).toBeInTheDocument();
    expect(screen.getByText(/Kanpur Central, Uttar Pradesh/i)).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /Users & Roles/i }));

    await waitFor(() => {
      expect(screen.getByText(/Users & Role-Based Access Controls/i)).toBeInTheDocument();
    });
  });

  it('navigates to System Diagnostics tab and displays health status', async () => {
    renderWithProviders(<SettingsPage />);

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /System Diagnostics/i }));

    await waitFor(() => {
      expect(screen.getByText(/System Diagnostics & Telemetry Health/i)).toBeInTheDocument();
      expect(screen.getByText(/API Base URL/i)).toBeInTheDocument();
    });
  });
});
