import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { VisitDetailsPage } from './VisitDetailsPage';
import { AuthProvider } from '../context/AuthContext';
import { ADMIN_USER, baseRoutes, CUSTOMER, EMPLOYEE_USER, VISIT, json, mockApi, route, signIn } from '../test/utils';

function renderVisitDetail(id: string) {
    return render(
        <MemoryRouter initialEntries={[`/visits/${id}`]}>
            <AuthProvider>
                <Routes>
                    <Route path="/visits/:id" element={<VisitDetailsPage />} />
                </Routes>
            </AuthProvider>
        </MemoryRouter>,
    );
}

describe('VisitDetailsPage - admin status update', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(ADMIN_USER);
    });

    it('shows admin override buttons for non-terminal visits', async () => {
        const visit = { ...VISIT, status: 'PENDING' as const };

        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/visits': [VISIT],
            [`/api/v1/visits/${VISIT.id}`]: visit,
            [`/api/v1/visits/${VISIT.id}/geo-logs`]: [],
            [`/api/v1/visits/${VISIT.id}/media`]: [],
            [`/api/v1/visits/${VISIT.id}/signatures`]: [],
            [`/api/v1/customers/${CUSTOMER.id}`]: CUSTOMER,
            // Longer/more specific than the customer-detail pattern above, so
            // mockApi's suffix matcher tries this first - without it, a
            // request for account data would incorrectly resolve to the raw
            // Customer mock (P1: /account is a real, separate endpoint).
            [`/api/v1/customers/${CUSTOMER.id}/account`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
        });

        renderVisitDetail(VISIT.id);

        expect(await screen.findByText(/Acme Industrial/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /mark missed/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /approve as completed/i })).toBeInTheDocument();
    });

    it('calls updateVisitStatus when admin clicks Mark Missed', async () => {
        const visit = { ...VISIT, status: 'PENDING' as const };
        const updatedVisit = { ...VISIT, status: 'MISSED' as const };

        let statusCallCount = 0;

        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/visits': [VISIT],
            [`/api/v1/visits/${VISIT.id}`]: route((url) => {
                if (url.includes('/status')) {
                    statusCallCount++;
                    return json(updatedVisit);
                }
                return json(statusCallCount > 0 ? updatedVisit : visit);
            }),
            [`/api/v1/visits/${VISIT.id}/geo-logs`]: [],
            [`/api/v1/visits/${VISIT.id}/media`]: [],
            [`/api/v1/visits/${VISIT.id}/signatures`]: [],
            [`/api/v1/customers/${CUSTOMER.id}`]: CUSTOMER,
            // Longer/more specific than the customer-detail pattern above, so
            // mockApi's suffix matcher tries this first - without it, a
            // request for account data would incorrectly resolve to the raw
            // Customer mock (P1: /account is a real, separate endpoint).
            [`/api/v1/customers/${CUSTOMER.id}/account`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
        });

        renderVisitDetail(VISIT.id);

        expect(await screen.findByText(/Acme Industrial/i)).toBeInTheDocument();

        const markMissedButton = screen.getByRole('button', { name: /mark missed/i });
        markMissedButton.click();

        await waitFor(() => {
            expect(statusCallCount).toBe(1);
        });
    });

    it('does not show admin override for terminal visits', async () => {
        const visit = { ...VISIT, status: 'COMPLETED' as const };

        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/visits': [VISIT],
            [`/api/v1/visits/${VISIT.id}`]: visit,
            [`/api/v1/visits/${VISIT.id}/geo-logs`]: [],
            [`/api/v1/visits/${VISIT.id}/media`]: [],
            [`/api/v1/visits/${VISIT.id}/signatures`]: [],
            [`/api/v1/customers/${CUSTOMER.id}`]: CUSTOMER,
            // Longer/more specific than the customer-detail pattern above, so
            // mockApi's suffix matcher tries this first - without it, a
            // request for account data would incorrectly resolve to the raw
            // Customer mock (P1: /account is a real, separate endpoint).
            [`/api/v1/customers/${CUSTOMER.id}/account`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
        });

        renderVisitDetail(VISIT.id);

        expect(await screen.findByText(/Acme Industrial/i)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /mark missed/i })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /approve as completed/i })).not.toBeInTheDocument();
    });
});

describe('VisitDetailsPage - employee', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(EMPLOYEE_USER);
    });

    it('does not show admin override buttons for employees', async () => {
        const visit = { ...VISIT, status: 'PENDING' as const };

        mockApi({
            ...baseRoutes(EMPLOYEE_USER),
            '/api/v1/visits': [VISIT],
            [`/api/v1/visits/${VISIT.id}`]: visit,
            [`/api/v1/visits/${VISIT.id}/geo-logs`]: [],
            [`/api/v1/visits/${VISIT.id}/media`]: [],
            [`/api/v1/visits/${VISIT.id}/signatures`]: [],
            [`/api/v1/customers/${CUSTOMER.id}`]: CUSTOMER,
            // Longer/more specific than the customer-detail pattern above, so
            // mockApi's suffix matcher tries this first - without it, a
            // request for account data would incorrectly resolve to the raw
            // Customer mock (P1: /account is a real, separate endpoint).
            [`/api/v1/customers/${CUSTOMER.id}/account`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
        });

        renderVisitDetail(VISIT.id);

        expect(await screen.findByText(/Acme Industrial/i)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /mark missed/i })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /approve as completed/i })).not.toBeInTheDocument();
    });
});

describe('VisitDetailsPage - check-in coordinate fields cannot be hand-typed', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(EMPLOYEE_USER);
    });

    function mockGeolocation(lat: number, lng: number, accuracy: number) {
        const getCurrentPosition = vi.fn((success: PositionCallback) => {
            success({
                coords: { latitude: lat, longitude: lng, accuracy, altitude: null, altitudeAccuracy: null, heading: null, speed: null },
                timestamp: Date.now(),
            } as GeolocationPosition);
        });
        Object.defineProperty(global.navigator, 'geolocation', {
            value: { getCurrentPosition },
            configurable: true,
        });
        return getCurrentPosition;
    }

    function mockVisitRoutes(checkInHandler?: (body: Record<string, unknown>) => Response) {
        const visit = { ...VISIT, status: 'PENDING' as const };
        mockApi({
            ...baseRoutes(EMPLOYEE_USER),
            '/api/v1/visits': [VISIT],
            [`/api/v1/visits/${VISIT.id}`]: visit,
            [`/api/v1/visits/${VISIT.id}/geo-logs`]: [],
            [`/api/v1/visits/${VISIT.id}/media`]: [],
            [`/api/v1/visits/${VISIT.id}/signatures`]: [],
            [`/api/v1/customers/${CUSTOMER.id}`]: CUSTOMER,
            [`/api/v1/customers/${CUSTOMER.id}/account`]: () => json({ error: { code: 'NOT_MOCKED', message: 'not mocked' } }, 404),
            [`/api/v1/visits/${VISIT.id}/check-in`]: checkInHandler
                ? route((_url, init) => checkInHandler(JSON.parse((init?.body as string) ?? '{}')))
                : () => json({ ...visit, status: 'IN_PROGRESS' }),
        });
    }

    it('renders the latitude/longitude/accuracy fields as read-only', async () => {
        mockVisitRoutes();
        renderVisitDetail(VISIT.id);

        await screen.findByText(/Acme Industrial/i);

        expect(screen.getByLabelText('LATITUDE')).toHaveAttribute('readonly');
        expect(screen.getByLabelText('LONGITUDE')).toHaveAttribute('readonly');
        expect(screen.getByLabelText('ACCURACY (M)')).toHaveAttribute('readonly');
    });

    it('disables Perform Check-In until a real GPS capture has happened', async () => {
        mockGeolocation(12.9716, 77.5946, 15);
        mockVisitRoutes();
        renderVisitDetail(VISIT.id);

        await screen.findByText(/Acme Industrial/i);

        const checkInButton = screen.getByRole('button', { name: /perform check-in/i });
        expect(checkInButton).toBeDisabled();

        await userEvent.click(screen.getByRole('button', { name: /use my current location/i }));

        await waitFor(() => expect(checkInButton).not.toBeDisabled());
        expect(screen.getByLabelText('LATITUDE')).toHaveValue(12.9716);
    });

    it('sends captured_at (from the GPS read, not the click time) in the check-in payload', async () => {
        mockGeolocation(12.9716, 77.5946, 15);
        let capturedBody: Record<string, unknown> | null = null;
        mockVisitRoutes((body) => {
            capturedBody = body;
            return json({ ...VISIT, status: 'IN_PROGRESS' });
        });
        renderVisitDetail(VISIT.id);

        await screen.findByText(/Acme Industrial/i);
        await userEvent.click(screen.getByRole('button', { name: /use my current location/i }));
        await waitFor(() => expect(screen.getByRole('button', { name: /perform check-in/i })).not.toBeDisabled());

        await userEvent.click(screen.getByRole('button', { name: /perform check-in/i }));

        await waitFor(() => expect(capturedBody).not.toBeNull());
        expect(capturedBody!.captured_at).toEqual(expect.any(String));
        expect(new Date(capturedBody!.captured_at as string).getTime()).not.toBeNaN();
        expect(capturedBody!.latitude).toBe(12.9716);
    });
});
