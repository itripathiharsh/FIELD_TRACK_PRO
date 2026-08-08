import { describe, expect, it, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { CustomersPage } from './CustomersPage';
import {
  ADMIN_USER,
  CUSTOMER,
  TERRITORY,
  baseRoutes,
  json,
  mockApi,
  renderWithProviders,
  route,
  signIn,
} from '../test/utils';

/**
 * CustomersPage behaviour.
 *
 * Covers FT-012 (geofence coordinates must be visible), FT-013 (contact person
 * is separate from the phone number), FT-014 (editing is possible) and the
 * error/empty states that previously hid failures.
 */
describe('CustomersPage', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
  });

  it('renders the real GPS coordinates for each customer (FT-012)', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/territories': [TERRITORY],
    });

    renderWithProviders(<CustomersPage />);

    await waitFor(() => expect(screen.getByText('Acme Industrial')).toBeInTheDocument());
    // The coordinate column must show the actual stored position.
    expect(screen.getByText(/12\.971600, 77\.594600/)).toBeInTheDocument();
    expect(screen.getByText(/Geofence: 75m/)).toBeInTheDocument();
  });

  it('shows the contact person separately from the phone number (FT-013)', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/territories': [TERRITORY],
    });

    renderWithProviders(<CustomersPage />);

    await waitFor(() => expect(screen.getByText(/Contact: Jane Smith/)).toBeInTheDocument());
    expect(screen.getByText('+919876543210')).toBeInTheDocument();
  });

  it('reports a load failure instead of showing an empty table', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers': () =>
        json({ error: { code: 'BOOM', message: 'Database unavailable' } }, 500),
      '/api/v1/territories': [],
    });

    renderWithProviders(<CustomersPage />);

    await waitFor(() => expect(screen.getByText('Database unavailable')).toBeInTheDocument());
  });

  it('offers a genuine empty state when there are no customers', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers': [],
      '/api/v1/territories': [],
    });

    renderWithProviders(<CustomersPage />);

    await waitFor(() =>
      expect(screen.getByText('No customers added yet')).toBeInTheDocument(),
    );
  });

  it('submits the create form with the correct contract', async () => {
    const posted: unknown[] = [];
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/territories': [TERRITORY],
      '/api/v1/customers': route((_url, init) => {
        if (init?.method === 'POST') {
          posted.push(JSON.parse(init.body as string));
          return json(CUSTOMER, 201);
        }
        return json([]);
      }),
    });

    renderWithProviders(<CustomersPage />);
    await waitFor(() => expect(screen.getByText('No customers added yet')).toBeInTheDocument());

    await userEvent.click(screen.getAllByRole('button', { name: /add account/i })[0]);

    await userEvent.type(screen.getByLabelText(/company \/ account name/i), 'New Client Ltd');
    await userEvent.type(screen.getByLabelText(/contact person/i), 'Jonathan Wellington Smythe III');
    await userEvent.type(screen.getByLabelText(/contact number/i), '+919000000001');
    await userEvent.type(screen.getByLabelText(/^address$/i), '9 New Road');
    await userEvent.type(screen.getByLabelText(/latitude/i), '12.9716');
    await userEvent.type(screen.getByLabelText(/longitude/i), '77.5946');

    await userEvent.click(screen.getByRole('button', { name: /save account/i }));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toMatchObject({
      name: 'New Client Ltd',
      // FT-013: a long human name goes to contact_person, never contact_number.
      contact_person: 'Jonathan Wellington Smythe III',
      contact_number: '+919000000001',
      location: { latitude: 12.9716, longitude: 77.5946 },
      geofence_radius_m: 75,
    });
  });

  it('rejects an out-of-range latitude before calling the API', async () => {
    let postCalls = 0;
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/territories': [],
      '/api/v1/customers': route((_url, init) => {
        if (init?.method === 'POST') postCalls += 1;
        return json([], init?.method === 'POST' ? 201 : 200);
      }),
    });

    renderWithProviders(<CustomersPage />);
    await waitFor(() => expect(screen.getByText('No customers added yet')).toBeInTheDocument());

    await userEvent.click(screen.getAllByRole('button', { name: /add account/i })[0]);
    await userEvent.type(screen.getByLabelText(/company \/ account name/i), 'Bad Coords');
    await userEvent.type(screen.getByLabelText(/contact number/i), '+911');
    await userEvent.type(screen.getByLabelText(/^address$/i), 'x');
    await userEvent.type(screen.getByLabelText(/latitude/i), '999');
    await userEvent.type(screen.getByLabelText(/longitude/i), '77');
    await userEvent.click(screen.getByRole('button', { name: /save account/i }));

    await waitFor(() =>
      expect(screen.getByText(/latitude must be a number between -90 and 90/i)).toBeInTheDocument(),
    );
    expect(postCalls).toBe(0);
  });

  it('opens the edit form pre-filled with the existing record (FT-014)', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER],
      '/api/v1/territories': [TERRITORY],
    });

    renderWithProviders(<CustomersPage />);
    await waitFor(() => expect(screen.getByText('Acme Industrial')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: /edit/i }));

    const dialogTitle = await screen.findByText('Edit Customer Account');
    expect(dialogTitle).toBeInTheDocument();
    expect(screen.getByLabelText(/company \/ account name/i)).toHaveValue('Acme Industrial');
    expect(screen.getByLabelText(/contact person/i)).toHaveValue('Jane Smith');
    expect(screen.getByLabelText(/latitude/i)).toHaveValue(12.9716);
  });

  it('sends a PATCH when saving an edit', async () => {
    const patched: unknown[] = [];
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/territories': [TERRITORY],
      [`/api/v1/customers/${CUSTOMER.id}`]: route((_url, init) => {
        if (init?.method === 'PATCH') {
          patched.push(JSON.parse(init.body as string));
          return json({ ...CUSTOMER, name: 'Renamed Client' });
        }
        return json(CUSTOMER);
      }),
      '/api/v1/customers': [CUSTOMER],
    });

    renderWithProviders(<CustomersPage />);
    await waitFor(() => expect(screen.getByText('Acme Industrial')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: /edit/i }));
    const nameField = screen.getByLabelText(/company \/ account name/i);
    await userEvent.clear(nameField);
    await userEvent.type(nameField, 'Renamed Client');
    await userEvent.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => expect(patched).toHaveLength(1));
    expect(patched[0]).toMatchObject({ name: 'Renamed Client' });
  });

  it('surfaces a server rejection in the form rather than closing silently', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/territories': [],
      '/api/v1/customers': route((_url, init) => {
        if (init?.method === 'POST') {
          return json(
            { error: { code: 'VALIDATION', message: 'contact_number is too long' } },
            422,
          );
        }
        return json([]);
      }),
    });

    renderWithProviders(<CustomersPage />);
    await waitFor(() => expect(screen.getByText('No customers added yet')).toBeInTheDocument());

    await userEvent.click(screen.getAllByRole('button', { name: /add account/i })[0]);
    await userEvent.type(screen.getByLabelText(/company \/ account name/i), 'X');
    await userEvent.type(screen.getByLabelText(/contact number/i), '+9100');
    await userEvent.type(screen.getByLabelText(/^address$/i), 'y');
    await userEvent.type(screen.getByLabelText(/latitude/i), '1');
    await userEvent.type(screen.getByLabelText(/longitude/i), '1');
    await userEvent.click(screen.getByRole('button', { name: /save account/i }));

    await waitFor(() =>
      expect(screen.getByText('contact_number is too long')).toBeInTheDocument(),
    );
    // The dialog must stay open so the user can correct the input.
    expect(screen.getByRole('button', { name: /save account/i })).toBeInTheDocument();
  });

  it('filters the table by search query', async () => {
    const second = { ...CUSTOMER, id: 'other-id', name: 'Zebra Logistics' };
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER, second],
      '/api/v1/territories': [TERRITORY],
    });

    renderWithProviders(<CustomersPage />);
    await waitFor(() => expect(screen.getByText('Acme Industrial')).toBeInTheDocument());
    expect(screen.getByText('Zebra Logistics')).toBeInTheDocument();

    await userEvent.type(screen.getByPlaceholderText(/search customers/i), 'Zebra');

    await waitFor(() => expect(screen.queryByText('Acme Industrial')).not.toBeInTheDocument());
    expect(screen.getByText('Zebra Logistics')).toBeInTheDocument();
  });
});




