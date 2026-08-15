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
import { Customer } from '../types';

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

describe('VisitsPage - bulk scheduling', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
  });

  const openBulkModal = async () => {
    // The main "Bulk Schedule" button is in the page header actions
    const buttons = await screen.findAllByRole('button', { name: /bulk schedule/i });
    // Click the first one (the header button, not the modal submit button)
    await userEvent.click(buttons[0]);
    await screen.findByText(/bulk schedule visits/i);
  };

  const submitBulkForm = async () => {
    // The submit button is the last button in the modal form
    const modal = screen.getByRole('dialog');
    const buttons = within(modal).getAllByRole('button');
    // Last button is the submit button
    await userEvent.click(buttons[buttons.length - 1]);
  };

  it('shows the Bulk Schedule button for admin', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [VISIT],
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderWithProviders(<VisitsPage />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /bulk schedule/i })).toBeInTheDocument(),
    );
  });

  it('opens the bulk schedule modal when clicked', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [VISIT],
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderWithProviders(<VisitsPage />);
    await openBulkModal();

    expect(screen.getByText(/bulk schedule visits/i)).toBeInTheDocument();
  });

  it('populates customer selection from /customers', async () => {
    const CUSTOMER_2: Customer = {
      ...CUSTOMER,
      id: '88888888-8888-8888-8888-888888888888',
      name: 'Second Customer',
    };

    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [],
      '/api/v1/customers': [CUSTOMER, CUSTOMER_2],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderWithProviders(<VisitsPage />);
    await openBulkModal();

    // Customer names should appear in the bulk modal checkbox list
    const modal = screen.getByRole('dialog');
    expect(within(modal).getByText('Acme Industrial')).toBeInTheDocument();
    expect(within(modal).getByText('Second Customer')).toBeInTheDocument();
  });

  it('populates employee selection from /employees', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [VISIT],
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderWithProviders(<VisitsPage />);
    await openBulkModal();

    const employeeSelect = screen.getByLabelText(/assign employee/i);
    const options = within(employeeSelect).getAllByRole('option');
    expect(options).toHaveLength(2); // placeholder + employee
    expect(options[1]).toHaveTextContent('Test Field Rep');
  });

  it('submits bulk schedule with correct payload', async () => {
    const posted: Array<Record<string, unknown>> = [];
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
      '/api/v1/visits/bulk': route((_url, init) => {
        if (init?.method === 'POST') {
          posted.push(JSON.parse(init.body as string));
          return json([VISIT], 201);
        }
        return json([]);
      }),
      '/api/v1/visits': [VISIT],
    });

    renderWithProviders(<VisitsPage />);
    await openBulkModal();

    // Select customer checkbox
    const checkboxes = screen.getAllByRole('checkbox');
    await userEvent.click(checkboxes[0]);

    // Select employee
    await userEvent.selectOptions(screen.getByLabelText(/assign employee/i), EMPLOYEE.id);

    // Submit
    await submitBulkForm();

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0].customer_ids).toEqual([CUSTOMER.id]);
    expect(posted[0].employee_id).toBe(EMPLOYEE.id);
    expect(posted[0].scheduled_at).toBeDefined();
  });

  it('shows error when no customers selected', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [VISIT],
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderWithProviders(<VisitsPage />);
    await openBulkModal();

    // Select employee but no customer
    await userEvent.selectOptions(screen.getByLabelText(/assign employee/i), EMPLOYEE.id);

    // Submit
    await submitBulkForm();

    expect(await screen.findByText(/please select at least one customer/i)).toBeInTheDocument();
  });

  it('shows error when no employee selected', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/visits': [VISIT],
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderWithProviders(<VisitsPage />);
    await openBulkModal();

    // Select customer but no employee
    const checkboxes = screen.getAllByRole('checkbox');
    await userEvent.click(checkboxes[0]);

    // Submit
    await submitBulkForm();

    expect(await screen.findByText(/please select at least one customer and an employee/i)).toBeInTheDocument();
  });

  it('refreshes visits list after successful bulk schedule', async () => {
    let visitGetCalls = 0;
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
      '/api/v1/visits/bulk': route((_url, init) => {
        if (init?.method === 'POST') {
          return json([VISIT], 201);
        }
        return json([]);
      }),
      '/api/v1/visits': route(() => {
        visitGetCalls += 1;
        return json([VISIT]);
      }),
    });

    renderWithProviders(<VisitsPage />);

    // Initial load
    await waitFor(() => expect(visitGetCalls).toBeGreaterThan(0));
    const initialCalls = visitGetCalls;

    // Open bulk modal and submit
    await openBulkModal();
    const checkboxes = screen.getAllByRole('checkbox');
    await userEvent.click(checkboxes[0]);
    await userEvent.selectOptions(screen.getByLabelText(/assign employee/i), EMPLOYEE.id);
    await submitBulkForm();

    // Verify list was refreshed
    await waitFor(() => expect(visitGetCalls).toBeGreaterThan(initialCalls));
  });

  it('closes modal after successful bulk schedule', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
      '/api/v1/visits/bulk': route((_url, init) => {
        if (init?.method === 'POST') {
          return json([VISIT], 201);
        }
        return json([]);
      }),
      '/api/v1/visits': [VISIT],
    });

    renderWithProviders(<VisitsPage />);
    await openBulkModal();

    // Select and submit
    const checkboxes = screen.getAllByRole('checkbox');
    await userEvent.click(checkboxes[0]);
    await userEvent.selectOptions(screen.getByLabelText(/assign employee/i), EMPLOYEE.id);
    await submitBulkForm();

    // Modal should close
    await waitFor(() =>
      expect(screen.queryByText(/bulk schedule visits/i)).not.toBeInTheDocument()
    );
  });

  it('shows error banner when bulk schedule API fails', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/employees': [EMPLOYEE],
      '/api/v1/visits/bulk': () => json({ error: { code: 'BULK_ERROR', message: 'Bulk schedule failed' } }, 500),
      '/api/v1/visits': [VISIT],
    });

    renderWithProviders(<VisitsPage />);
    await openBulkModal();

    // Select and submit
    const checkboxes = screen.getAllByRole('checkbox');
    await userEvent.click(checkboxes[0]);
    await userEvent.selectOptions(screen.getByLabelText(/assign employee/i), EMPLOYEE.id);
    await submitBulkForm();

    expect(await screen.findByText(/bulk schedule failed/i)).toBeInTheDocument();
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






