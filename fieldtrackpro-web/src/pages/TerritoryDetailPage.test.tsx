import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { TerritoryDetailPage } from './TerritoryDetailPage';
import { AuthProvider } from '../context/AuthContext';
import { ADMIN_USER, baseRoutes, CUSTOMER, EMPLOYEE, TERRITORY, json, mockApi, route, signIn } from '../test/utils';

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

        expect(await screen.findByText('North Region')).toBeInTheDocument();
        expect(screen.getByText(/Field Representatives: 1/)).toBeInTheDocument();
        expect(screen.getByText(/Customer Accounts: 1/)).toBeInTheDocument();
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

        await screen.findByText('North Region');

        expect(screen.getByText('Test Field Rep')).toBeInTheDocument();
        expect(screen.getByText('Acme Industrial')).toBeInTheDocument();
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

        expect(await screen.findByText('North Region')).toBeInTheDocument();
        expect(screen.getByText(/back to territories/i)).toBeInTheDocument();
    });
});
