import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { CustomerDetailPage } from './CustomerDetailPage';
import { AuthProvider } from '../context/AuthContext';
import { ADMIN_USER, baseRoutes, CUSTOMER, json, mockApi, route, signIn } from '../test/utils';

function renderCustomerDetail(id: string) {
    return render(
        <MemoryRouter initialEntries={[`/customers/${id}`]}>
            <AuthProvider>
                <Routes>
                    <Route path="/customers/:id" element={<CustomerDetailPage />} />
                </Routes>
            </AuthProvider>
        </MemoryRouter>,
    );
}

describe('CustomerDetailPage', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(ADMIN_USER);
    });

    it('loads and displays customer details', async () => {
        const customer = {
            ...CUSTOMER,
            contact_number: '+919876543210',
            contact_person: 'John Contact',
            address: '123 Test Street',
            location: { latitude: 12.9716, longitude: 77.5946 },
            geofence_radius_m: 100,
        };

        mockApi({
            ...baseRoutes(ADMIN_USER),
            // Longer/more specific than the '/api/v1/customers' catch-all
            // below, so mockApi's suffix matcher tries this first - without
            // it, the P1 account fetch would incorrectly match the customer
            // catch-all and receive a raw Customer object instead of a 404.
            [`/api/v1/customers/${CUSTOMER.id}/account`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
            [`/api/v1/customers/${CUSTOMER.id}/orders`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
            '/api/v1/customers': route((url) => {
                if (url.includes(CUSTOMER.id)) {
                    return json(customer);
                }
                return json([]);
            }),
        });

        renderCustomerDetail(CUSTOMER.id);

        expect(await screen.findByText('Acme Industrial')).toBeInTheDocument();
        expect(screen.getByText('+919876543210')).toBeInTheDocument();
        expect(screen.getByText('John Contact')).toBeInTheDocument();
        expect(screen.getByText('123 Test Street')).toBeInTheDocument();
        expect(screen.getByText('100m')).toBeInTheDocument();
    });

    it('shows loading state', () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            // Longer/more specific than the '/api/v1/customers' catch-all
            // below, so mockApi's suffix matcher tries this first - without
            // it, the P1 account fetch would incorrectly match the customer
            // catch-all and receive a raw Customer object instead of a 404.
            [`/api/v1/customers/${CUSTOMER.id}/account`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
            '/api/v1/customers': () => new Promise(() => {}),
        });

        renderCustomerDetail(CUSTOMER.id);

        expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('shows error state when API fails', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            // Longer/more specific than the '/api/v1/customers' catch-all
            // below, so mockApi's suffix matcher tries this first - without
            // it, the P1 account fetch would incorrectly match the customer
            // catch-all and receive a raw Customer object instead of a 404.
            [`/api/v1/customers/${CUSTOMER.id}/account`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
            [`/api/v1/customers/${CUSTOMER.id}/orders`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
            '/api/v1/customers': route((url) => {
                if (url.includes(CUSTOMER.id)) {
                    return json({ error: { code: 'NOT_FOUND', message: 'Customer not found' } }, 404);
                }
                return json([]);
            }),
        });

        renderCustomerDetail(CUSTOMER.id);

        expect(await screen.findByText(/customer not found/i)).toBeInTheDocument();
    });

    it('shows not found state when customer is null', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            // Longer/more specific than the '/api/v1/customers' catch-all
            // below, so mockApi's suffix matcher tries this first - without
            // it, the P1 account fetch would incorrectly match the customer
            // catch-all and receive a raw Customer object instead of a 404.
            [`/api/v1/customers/${CUSTOMER.id}/account`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
            [`/api/v1/customers/${CUSTOMER.id}/orders`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
            '/api/v1/customers': route((url) => {
                if (url.includes(CUSTOMER.id)) {
                    return json(null, 200);
                }
                return json([]);
            }),
        });

        renderCustomerDetail(CUSTOMER.id);

        expect(await screen.findByText(/customer not found/i)).toBeInTheDocument();
    });

    it('has back navigation button', async () => {
        const customer = {
            ...CUSTOMER,
            contact_number: '+919876543210',
            contact_person: 'John Contact',
            address: '123 Test Street',
            location: { latitude: 12.9716, longitude: 77.5946 },
            geofence_radius_m: 100,
        };

        mockApi({
            ...baseRoutes(ADMIN_USER),
            // Longer/more specific than the '/api/v1/customers' catch-all
            // below, so mockApi's suffix matcher tries this first - without
            // it, the P1 account fetch would incorrectly match the customer
            // catch-all and receive a raw Customer object instead of a 404.
            [`/api/v1/customers/${CUSTOMER.id}/account`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
            [`/api/v1/customers/${CUSTOMER.id}/orders`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
            '/api/v1/customers': route((url) => {
                if (url.includes(CUSTOMER.id)) {
                    return json(customer);
                }
                return json([]);
            }),
        });

        renderCustomerDetail(CUSTOMER.id);

        expect(await screen.findByText('Acme Industrial')).toBeInTheDocument();
        expect(screen.getByText(/back to customers/i)).toBeInTheDocument();
    });

    it('loads and displays customer visit history', async () => {
        const customer = {
            ...CUSTOMER,
            contact_number: '+919876543210',
            address: '123 Test Street',
            location: { latitude: 12.9716, longitude: 77.5946 },
            geofence_radius_m: 100,
        };

        const visitHistory = [
            {
                visit_id: 'visit-001',
                scheduled_at: '2026-01-15T10:00:00Z',
                status: 'COMPLETED',
                employee_name: 'Test Employee',
                check_in_at: '2026-01-15T10:05:00Z',
                check_out_at: '2026-01-15T11:00:00Z',
            },
        ];

        mockApi({
            ...baseRoutes(ADMIN_USER),
            // Longer/more specific than the '/api/v1/customers' catch-all
            // below, so mockApi's suffix matcher tries this first - without
            // it, the P1 account fetch would incorrectly match the customer
            // catch-all and receive a raw Customer object instead of a 404.
            [`/api/v1/customers/${CUSTOMER.id}/account`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
            [`/api/v1/customers/${CUSTOMER.id}/orders`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
            '/api/v1/customers': route((url) => {
                if (url.includes(CUSTOMER.id)) {
                    return json(customer);
                }
                return json([]);
            }),
            '/api/v1/reports/customers': route((url) => {
                if (url.includes('/history')) {
                    return json(visitHistory);
                }
                return json([]);
            }),
        });

        renderCustomerDetail(CUSTOMER.id);

        // Verify the Visit History section appears
        expect(await screen.findByText('Visit History')).toBeInTheDocument();
        expect(screen.getByText('Test Employee')).toBeInTheDocument();
        expect(screen.getByText(/1 visit recorded/i)).toBeInTheDocument();
    });
});
