import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { EmployeeDetailPage } from './EmployeeDetailPage';
import { AuthProvider } from '../context/AuthContext';
import { ADMIN_USER, baseRoutes, EMPLOYEE, json, mockApi, route, signIn } from '../test/utils';

function renderEmployeeDetail(id: string) {
    return render(
        <MemoryRouter initialEntries={[`/employees/${id}`]}>
            <AuthProvider>
                <Routes>
                    <Route path="/employees/:id" element={<EmployeeDetailPage />} />
                </Routes>
            </AuthProvider>
        </MemoryRouter>,
    );
}

describe('EmployeeDetailPage', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(ADMIN_USER);
    });

    it('loads and displays employee details', async () => {
        const employee = {
            id: EMPLOYEE.id,
            user_id: EMPLOYEE.user_id,
            full_name: 'Test Field Rep',
            territory_id: EMPLOYEE.territory_id,
            employee_code: 'EMP-001',
            created_at: '2026-01-01T00:00:00Z',
            user: {
                id: EMPLOYEE.user_id,
                email: 'rep@fieldtrack.test',
                mobile_number: '+919876543210',
                role: 'EMPLOYEE',
            },
        };

        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/employees': route((url) => {
                // Prefix-matched: /employees/{id}/activity and
                // /territory-assignments both contain the plain employee-detail
                // path, so they must be discriminated BEFORE the plain-detail
                // check below or they'd wrongly resolve with the employee body.
                if (url.includes('/activity')) return json(null, 404);
                if (url.includes('/territory-assignments')) return json(null, 404);
                if (url.includes(EMPLOYEE.id)) {
                    return json(employee);
                }
                return json([]);
            }),
        });

        renderEmployeeDetail(EMPLOYEE.id);

        expect(await screen.findByText('Test Field Rep')).toBeInTheDocument();
        expect(screen.getByText('rep@fieldtrack.test')).toBeInTheDocument();
        expect(screen.getByText('+919876543210')).toBeInTheDocument();
        expect(screen.getByText(/EMP-001/)).toBeInTheDocument();
    });

    it('shows loading state', () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/employees': () => new Promise(() => {}),
        });

        renderEmployeeDetail(EMPLOYEE.id);

        expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('shows error state when API fails', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/employees': route((url) => {
                if (url.includes(EMPLOYEE.id)) {
                    return json({ error: { code: 'NOT_FOUND', message: 'Employee not found' } }, 404);
                }
                return json([]);
            }),
        });

        renderEmployeeDetail(EMPLOYEE.id);

        expect(await screen.findByText(/employee not found/i)).toBeInTheDocument();
    });

    it('shows not found state when employee is null', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/employees': route((url) => {
                if (url.includes(EMPLOYEE.id)) {
                    return json(null, 200);
                }
                return json([]);
            }),
        });

        renderEmployeeDetail(EMPLOYEE.id);

        expect(await screen.findByText(/employee not found/i)).toBeInTheDocument();
    });

    it('has back navigation button', async () => {
        const employee = {
            id: EMPLOYEE.id,
            user_id: EMPLOYEE.user_id,
            full_name: 'Test Field Rep',
            territory_id: EMPLOYEE.territory_id,
            employee_code: 'EMP-001',
            created_at: '2026-01-01T00:00:00Z',
            user: {
                id: EMPLOYEE.user_id,
                email: 'rep@fieldtrack.test',
                mobile_number: '+919876543210',
                role: 'EMPLOYEE',
            },
        };

        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/employees': route((url) => {
                if (url.includes('/activity')) return json(null, 404);
                if (url.includes('/territory-assignments')) return json(null, 404);
                if (url.includes(EMPLOYEE.id)) {
                    return json(employee);
                }
                return json([]);
            }),
        });

        renderEmployeeDetail(EMPLOYEE.id);

        expect(await screen.findByText('Test Field Rep')).toBeInTheDocument();
        expect(screen.getByText(/back to employees/i)).toBeInTheDocument();
    });
});
