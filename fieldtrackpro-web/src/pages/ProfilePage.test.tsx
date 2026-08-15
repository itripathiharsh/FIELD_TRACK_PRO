import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { ProfilePage } from './ProfilePage';
import { AuthProvider } from '../context/AuthContext';
import { ADMIN_USER, baseRoutes, EMPLOYEE, EMPLOYEE_USER, json, mockApi, signIn } from '../test/utils';

function renderProfile() {
    return render(
        <MemoryRouter initialEntries={['/profile']}>
            <AuthProvider>
                <ProfilePage />
            </AuthProvider>
        </MemoryRouter>,
    );
}

describe('ProfilePage - employee', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(EMPLOYEE_USER);
    });

    it('fetches and displays employee profile from /employees/me', async () => {
        const spy = mockApi({
            ...baseRoutes(EMPLOYEE_USER),
            '/api/v1/employees/me': EMPLOYEE,
        });

        renderProfile();

        await waitFor(() => {
            expect(screen.getAllByText('Test Field Rep').length).toBeGreaterThanOrEqual(1);
        });

        expect(screen.getByText('EMP-001')).toBeInTheDocument();
        expect(screen.getAllByText('rep@fieldtrack.test').length).toBeGreaterThanOrEqual(1);

        const urls = spy.mock.calls.map(([u]) => String(u));
        expect(urls.some((u) => u.includes('/employees/me'))).toBe(true);
    });

    it('shows error when no employee profile exists', async () => {
        mockApi({
            ...baseRoutes(EMPLOYEE_USER),
            '/api/v1/employees/me': () => json({ error: { code: 'NOT_FOUND', message: 'No employee profile found' } }, 404),
        });

        renderProfile();

        await waitFor(() => {
            expect(screen.getByText(/no employee profile found/i)).toBeInTheDocument();
        });
    });
});

describe('ProfilePage - admin', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(ADMIN_USER);
    });

    it('shows no employee profile for admin without employee record', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/employees/me': () => json({ error: { code: 'NOT_FOUND', message: 'No employee profile found' } }, 404),
        });

        renderProfile();

        await waitFor(() => {
            expect(screen.getByText(/no employee profile found/i)).toBeInTheDocument();
        });
    });
});
