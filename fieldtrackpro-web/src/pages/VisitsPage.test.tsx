import { describe, expect, it, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { VisitsPage } from './VisitsPage';
import {
  ADMIN_USER,
  CUSTOMER,
  EMPLOYEE,
  EMPLOYEE_USER,
  VISIT,
  baseRoutes,
  json,
  mockApi,
  renderWithProviders,
  route,
  signIn,
} from '../test/utils';

/**
 * VisitsPage behaviour.
 *
 * Covers FT-006 (the employee dropdown was permanently empty because the page
 * called a non-existent endpoint, and it submitted a users.id where an
 * employees.id is required) and FT-044 (an admin-only action was shown to
 * field staff).
 */
describe('VisitsPage - admin', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
  });

  it('populates the employee dropdown from /employees (FT-006)', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [VISIT],
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderWithProviders(<VisitsPage />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /schedule visit/i })).toBeInTheDocument(),
    );

    await userEvent.click(screen.getByRole('button', { name: /schedule visit/i }));

    const employeeSelect = await screen.findByLabelText(/assigned field employee/i);
    const options = within(employeeSelect).getAllByRole('option');
    // Placeholder + the real employee.
    expect(options).toHaveLength(2);
    expect(options[1]).toHaveTextContent('Test Field Rep');
  });

  it('submits the EMPLOYEE id, not the user id (FT-006)', async () => {
    const posted: Array<Record<string, string>> = [];
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
      '/api/v1/visits': route((_url, init) => {
        if (init?.method === 'POST') {
          posted.push(JSON.parse(init.body as string));
          return json(VISIT, 201);
        }
        return json([]);
      }),
    });

    renderWithProviders(<VisitsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /schedule visit/i }));

    await userEvent.selectOptions(await screen.findByLabelText(/select customer/i), CUSTOMER.id);
    await userEvent.selectOptions(screen.getByLabelText(/assigned field employee/i), EMPLOYEE.id);
    await userEvent.click(screen.getByRole('button', { name: /dispatch visit/i }));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0].employee_id).toBe(EMPLOYEE.id);
    // The distinction that caused a foreign-key 500 in the original build.
    expect(posted[0].employee_id).not.toBe(EMPLOYEE_USER.id);
    expect(posted[0].customer_id).toBe(CUSTOMER.id);
  });

  it('warns when no employee profiles exist instead of failing silently', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [],
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [],
    });

    renderWithProviders(<VisitsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /schedule visit/i }));

    expect(
      await screen.findByText(/no employee profiles available/i),
    ).toBeInTheDocument();
  });

  it('does not create a visit until both selections are made', async () => {
    /**
     * Both selects are marked `required`, so the browser blocks submission
     * natively and the JS guard is a second line of defence. The guarantee
     * that matters is the one asserted here: no visit is created from an
     * incomplete form.
     */
    let postCalls = 0;
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
      '/api/v1/visits': route((_url, init) => {
        if (init?.method === 'POST') {
          postCalls += 1;
          return json(VISIT, 201);
        }
        return json([]);
      }),
    });

    renderWithProviders(<VisitsPage />);
    await userEvent.click(await screen.findByRole('button', { name: /schedule visit/i }));

    // Nothing selected.
    await userEvent.click(screen.getByRole('button', { name: /dispatch visit/i }));
    expect(postCalls).toBe(0);

    // Only a customer selected.
    await userEvent.selectOptions(screen.getByLabelText(/select customer/i), CUSTOMER.id);
    await userEvent.click(screen.getByRole('button', { name: /dispatch visit/i }));
    expect(postCalls).toBe(0);

    // Both selected: the request is finally made.
    await userEvent.selectOptions(screen.getByLabelText(/assigned field employee/i), EMPLOYEE.id);
    await userEvent.click(screen.getByRole('button', { name: /dispatch visit/i }));
    await waitFor(() => expect(postCalls).toBe(1));
  });

  it('requests the selected status filter from the API', async () => {
    const requested: string[] = [];
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
      '/api/v1/visits': route((url) => {
        requested.push(url);
        return json([VISIT]);
      }),
    });

    renderWithProviders(<VisitsPage />);
    await waitFor(() => expect(requested.length).toBeGreaterThan(0));

    await userEvent.click(screen.getByRole('button', { name: 'COMPLETED' }));

    await waitFor(() =>
      expect(requested.some((u) => u.includes('status=COMPLETED'))).toBe(true),
    );
  });

  it('shows an error banner when the visit list fails to load', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers': [],
      '/api/v1/employees': [],
      '/api/v1/visits': () => json({ error: { code: 'X', message: 'Upstream failure' } }, 503),
    });

    renderWithProviders(<VisitsPage />);
    await waitFor(() => expect(screen.getByText('Upstream failure')).toBeInTheDocument());
  });
});

describe('VisitsPage - employee (FT-044)', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(EMPLOYEE_USER);
  });

  it('does not offer the admin-only scheduling action', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/visits': [VISIT],
    });

    renderWithProviders(<VisitsPage />);
    await waitFor(() => expect(screen.getByText(/visit dispatch/i)).toBeInTheDocument());

    expect(screen.queryByRole('button', { name: /schedule visit/i })).not.toBeInTheDocument();
  });

  it('does not request the admin-only employee roster', async () => {
    const fetchSpy = mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/visits': [VISIT],
    });

    renderWithProviders(<VisitsPage />);
    await waitFor(() => expect(screen.getByText(/visit dispatch/i)).toBeInTheDocument());

    const calledEmployees = fetchSpy.mock.calls.some(([u]) =>
      String(u).includes('/api/v1/employees'),
    );
    expect(calledEmployees).toBe(false);
  });

  it('still shows the assigned visits', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/visits': [VISIT],
    });

    renderWithProviders(<VisitsPage />);
    await waitFor(() =>
      expect(screen.getByText(new RegExp(VISIT.id.substring(0, 8), 'i'))).toBeInTheDocument(),
    );
  });
});






