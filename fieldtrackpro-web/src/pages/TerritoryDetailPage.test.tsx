import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { TerritoryDetailPage } from './TerritoryDetailPage';
import { AuthProvider } from '../context/AuthContext';
import { ADMIN_USER, baseRoutes, CUSTOMER, EMPLOYEE, TERRITORY, json, mockApi, route, signIn } from '../test/utils';
import { apiClient } from '../api/client';

function renderTerritoryDetail(id: string) {
    return render(
        <MemoryRouter initialEntries={[`/territories/${id}`]}>
            <AuthProvider>
                <Routes>
                    <Route path="/territories/:id" element={<TerritoryDetailPage />} />
                </Routes>
            </AuthProvider>
        </MemoryRouter>,
    );
}

describe('TerritoryDetailPage', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(ADMIN_USER);
        vi.restoreAllMocks();
    });

    it('loads and displays territory details', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/territories': route((url) => {
                if (url.includes(TERRITORY.id)) {
                    return json(TERRITORY);
                }
                return json([]);
            }),
            '/api/v1/employees': [EMPLOYEE],
            '/api/v1/customers': [CUSTOMER],
        });

        renderTerritoryDetail(TERRITORY.id);

        const headings = await screen.findAllByText('North Region');
        expect(headings.length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText('Field Representatives')).toBeInTheDocument();
        expect(screen.getAllByText('Customer Accounts').length).toBeGreaterThanOrEqual(1);
    });

    it('shows loading state', () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/territories': () => new Promise(() => {}),
            '/api/v1/employees': [],
            '/api/v1/customers': [],
        });

        renderTerritoryDetail(TERRITORY.id);

        expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('shows not found state when territory does not exist', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/territories': route(() => {
                return json({ error: { code: 'NOT_FOUND', message: 'Territory not found' } }, 404);
            }),
            '/api/v1/employees': [],
            '/api/v1/customers': [],
        });

        renderTerritoryDetail('nonexistent-id');

        expect(await screen.findByText(/territory not found/i)).toBeInTheDocument();
    });

    it('shows assigned employees and customers', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/territories': route((url) => {
                if (url.includes(TERRITORY.id)) {
                    return json(TERRITORY);
                }
                return json([]);
            }),
            '/api/v1/employees': [EMPLOYEE],
            '/api/v1/customers': [CUSTOMER],
        });

        renderTerritoryDetail(TERRITORY.id);

        const headings = await screen.findAllByText('North Region');
        expect(headings.length).toBeGreaterThanOrEqual(1);

        expect(screen.getByText('Test Field Rep')).toBeInTheDocument();
        expect(screen.getByText('Acme Industrial')).toBeInTheDocument();
    });

    it('calls updateCustomer with territory_id: null when removing an assigned customer', async () => {
        vi.spyOn(window, 'confirm').mockReturnValue(true);
        const updateSpy = vi.spyOn(apiClient, 'updateCustomer').mockResolvedValue({
            ...CUSTOMER,
            territory_id: null,
        });

        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/territories': route((url) => {
                if (url.includes(TERRITORY.id)) {
                    return json(TERRITORY);
                }
                return json([]);
            }),
            '/api/v1/employees': [EMPLOYEE],
            '/api/v1/customers': [CUSTOMER],
        });

        renderTerritoryDetail(TERRITORY.id);

        expect(await screen.findByText('Acme Industrial')).toBeInTheDocument();

        const removeButton = screen.getByRole('button', { name: /remove/i });
        fireEvent.click(removeButton);

        await waitFor(() => {
            expect(updateSpy).toHaveBeenCalledWith(CUSTOMER.id, { territory_id: null });
        });
    });

    it('has back navigation button', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/territories': route((url) => {
                if (url.includes(TERRITORY.id)) {
                    return json(TERRITORY);
                }
                return json([]);
            }),
            '/api/v1/employees': [],
            '/api/v1/customers': [],
        });

        renderTerritoryDetail(TERRITORY.id);

        const headings = await screen.findAllByText('North Region');
        expect(headings.length).toBeGreaterThanOrEqual(1);
        expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument();
    });
});
