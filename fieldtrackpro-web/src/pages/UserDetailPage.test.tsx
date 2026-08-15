import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { UserDetailPage } from './UserDetailPage';
import { AuthProvider } from '../context/AuthContext';
import { ADMIN_USER, baseRoutes, EMPLOYEE_USER, json, mockApi, route, signIn } from '../test/utils';

function renderUserDetail(id: string) {
    return render(
        <MemoryRouter initialEntries={[`/users/${id}`]}>
            <AuthProvider>
                <Routes>
                    <Route path="/users/:id" element={<UserDetailPage />} />
                </Routes>
            </AuthProvider>
        </MemoryRouter>,
    );
}

describe('UserDetailPage', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(ADMIN_USER);
    });

    it('loads and displays user details', async () => {
        const user = {
            ...EMPLOYEE_USER,
            is_active: true,
        };

        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/users': route((url) => {
                if (url.includes(EMPLOYEE_USER.id)) {
                    return json(user);
                }
                return json({ error: { code: 'NOT_FOUND', message: 'User not found' } }, 404);
            }),
        });

        renderUserDetail(EMPLOYEE_USER.id);

        expect(await screen.findByText('Test Field Rep')).toBeInTheDocument();
        expect(screen.getByText('rep@fieldtrack.test')).toBeInTheDocument();
        expect(screen.getByText(/EMPLOYEE/)).toBeInTheDocument();
    });

    it('shows loading state', () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/users': () => new Promise(() => {}),
        });

        renderUserDetail(EMPLOYEE_USER.id);

        expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('shows not found state when user does not exist', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/users': route(() => {
                return json({ error: { code: 'NOT_FOUND', message: 'User not found' } }, 404);
            }),
        });

        renderUserDetail('nonexistent-id');

        expect(await screen.findByText(/user not found/i)).toBeInTheDocument();
    });

    it('deactivates user and updates status', async () => {
        const activeUser = {
            ...EMPLOYEE_USER,
            is_active: true,
        };
        const inactiveUser = {
            ...EMPLOYEE_USER,
            is_active: false,
        };

        let currentUser = activeUser;

        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/users': route((url) => {
                if (url.includes(EMPLOYEE_USER.id)) {
                    if (url.includes('deactivate')) {
                        currentUser = inactiveUser;
                        return json(inactiveUser);
                    }
                    return json(currentUser);
                }
                return json({ error: { code: 'NOT_FOUND', message: 'User not found' } }, 404);
            }),
        });

        renderUserDetail(EMPLOYEE_USER.id);

        expect(await screen.findByText('Test Field Rep')).toBeInTheDocument();

        const deactivateButton = screen.getByRole('button', { name: /deactivate/i });
        deactivateButton.click();

        await waitFor(() => {
            expect(screen.getByText('INACTIVE')).toBeInTheDocument();
        });
    });

    it('activates user and updates status', async () => {
        const inactiveUser = {
            ...EMPLOYEE_USER,
            is_active: false,
        };
        const activeUser = {
            ...EMPLOYEE_USER,
            is_active: true,
        };

        let currentUser = inactiveUser;

        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/users': route((url) => {
                if (url.includes(EMPLOYEE_USER.id)) {
                    if (url.includes('activate')) {
                        currentUser = activeUser;
                        return json(activeUser);
                    }
                    return json(currentUser);
                }
                return json({ error: { code: 'NOT_FOUND', message: 'User not found' } }, 404);
            }),
        });

        renderUserDetail(EMPLOYEE_USER.id);

        expect(await screen.findByText('Test Field Rep')).toBeInTheDocument();

        const activateButton = screen.getByRole('button', { name: /activate/i });
        activateButton.click();

        await waitFor(() => {
            expect(screen.getByText('ACTIVE')).toBeInTheDocument();
        });
    });

    it('has back navigation button', async () => {
        const user = {
            ...EMPLOYEE_USER,
            is_active: true,
        };

        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/users': route((url) => {
                if (url.includes(EMPLOYEE_USER.id)) {
                    return json(user);
                }
                return json({ error: { code: 'NOT_FOUND', message: 'User not found' } }, 404);
            }),
        });

        renderUserDetail(EMPLOYEE_USER.id);

        expect(await screen.findByText('Test Field Rep')).toBeInTheDocument();
        expect(screen.getByText(/back to employees/i)).toBeInTheDocument();
    });
});
