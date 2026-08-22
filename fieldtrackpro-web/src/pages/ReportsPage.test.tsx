import { describe, expect, it, beforeEach, vi, beforeAll, afterAll } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ReportsPage } from './ReportsPage';
import {
    ADMIN_USER,
    baseRoutes,
    json,
    mockApi,
    renderWithProviders,
    route,
    signIn,
} from '../test/utils';

// Mock URL.createObjectURL for jsdom environment
beforeAll(() => {
    if (!URL.createObjectURL) {
        URL.createObjectURL = vi.fn().mockReturnValue('blob:mock-url');
    }
    if (!URL.revokeObjectURL) {
        URL.revokeObjectURL = vi.fn();
    }
});

afterAll(() => {
    // Clean up mocks
});

describe('ReportsPage - CSV Export', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(ADMIN_USER);
    });

    it('shows CSV export button for employee report', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': [
                {
                    employee_id: 'emp1',
                    employee_name: 'John Doe',
                    total_visits: 10,
                    completed_visits: 8,
                    pending_visits: 2,
                    missed_visits: 0,
                    flagged_visits: 0,
                    completion_rate: 80.0,
                },
            ],
            '/api/v1/reports/productivity': {
                total_employees: 5,
                active_employees: 3,
                total_visits_today: 15,
                completed_visits_today: 10,
                pending_visits_today: 3,
                missed_visits_today: 1,
                flagged_visits_today: 1,
                avg_visits_per_employee: 3.0,
            },
            '/api/v1/reports/geo-verification': [],
        });

        renderWithProviders(<ReportsPage />);

        // Switch to employees tab
        await userEvent.click(await screen.findByRole('button', { name: 'employees' }));

        // Check CSV button exists
        expect(await screen.findByRole('button', { name: /csv/i })).toBeInTheDocument();
    });

    it('exports CSV with correct data', async () => {
        const employeeData = [
            {
                employee_id: 'emp1',
                employee_name: 'John Doe',
                total_visits: 10,
                completed_visits: 8,
                pending_visits: 2,
                missed_visits: 0,
                flagged_visits: 0,
                completion_rate: 80.0,
            },
        ];

        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': employeeData,
            '/api/v1/reports/productivity': {
                total_employees: 5,
                active_employees: 3,
                total_visits_today: 15,
                completed_visits_today: 10,
                pending_visits_today: 3,
                missed_visits_today: 1,
                flagged_visits_today: 1,
                avg_visits_per_employee: 3.0,
            },
            '/api/v1/reports/geo-verification': [],
        });

        // Mock click to verify download was triggered
        const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

        renderWithProviders(<ReportsPage />);

        // Switch to employees tab
        await userEvent.click(await screen.findByRole('button', { name: 'employees' }));

        // Click CSV export
        const csvButton = await screen.findByRole('button', { name: /csv/i });
        await userEvent.click(csvButton);

        // Verify download was triggered
        await waitFor(() => expect(clickSpy).toHaveBeenCalled());
        clickSpy.mockRestore();
    });

    it('disables CSV export when no data', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': [],
            '/api/v1/reports/productivity': {
                total_employees: 0,
                active_employees: 0,
                total_visits_today: 0,
                completed_visits_today: 0,
                pending_visits_today: 0,
                missed_visits_today: 0,
                flagged_visits_today: 0,
                avg_visits_per_employee: 0,
            },
            '/api/v1/reports/geo-verification': [],
        });

        renderWithProviders(<ReportsPage />);

        // Switch to employees tab
        await userEvent.click(await screen.findByRole('button', { name: 'employees' }));

        // Check CSV button is disabled
        const csvButton = await screen.findByRole('button', { name: /csv/i });
        expect(csvButton).toBeDisabled();
    });

    it('CSV download anchor has a dated, non-UUID filename and csv MIME type', async () => {
        const employeeData = [
            {
                employee_id: 'emp1',
                employee_name: 'John Doe',
                total_visits: 10,
                completed_visits: 8,
                pending_visits: 2,
                missed_visits: 0,
                flagged_visits: 0,
                completion_rate: 80.0,
            },
        ];

        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': employeeData,
            '/api/v1/reports/productivity': {
                total_employees: 5,
                active_employees: 3,
                total_visits_today: 15,
                completed_visits_today: 10,
                pending_visits_today: 3,
                missed_visits_today: 1,
                flagged_visits_today: 1,
                avg_visits_per_employee: 3.0,
            },
            '/api/v1/reports/geo-verification': [],
        });

        const createSpy = vi.spyOn(URL, 'createObjectURL');
        let clickedAnchor: HTMLAnchorElement | null = null;
        const clickSpy = vi
            .spyOn(HTMLAnchorElement.prototype, 'click')
            .mockImplementation(function (this: HTMLAnchorElement) {
                clickedAnchor = this;
            });

        renderWithProviders(<ReportsPage />);
        await userEvent.click(await screen.findByRole('button', { name: 'employees' }));
        await userEvent.click(await screen.findByRole('button', { name: /csv/i }));

        expect(clickSpy).toHaveBeenCalled();
        expect(clickedAnchor).not.toBeNull();
        // Filename must be the dated report name, never a UUID / blob URL segment.
        expect(clickedAnchor!.download).toMatch(/^employee-report-\d{4}-\d{2}-\d{2}\.csv$/);
        expect(clickedAnchor!.download).not.toMatch(/^[0-9a-f]{8}-/);

        const blob = createSpy.mock.calls[0][0] as Blob;
        expect(blob.type.startsWith('text/csv')).toBe(true);

        clickSpy.mockRestore();
        createSpy.mockRestore();
    });

    it('Geo CSV download anchor has a dated, non-UUID filename', async () => {
        const geoData = [
            {
                visit_id: 'v1',
                employee_name: 'Jane Sales Rep',
                customer_name: 'Acme HQ Client',
                attempted_at: '2026-08-12T10:00:00Z',
                verification_type: 'geofence',
                is_valid: false,
                distance_m: 150.5,
                failure_reason: 'Outside geofence radius',
            },
        ];

        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': [],
            '/api/v1/reports/productivity': {
                total_employees: 0,
                active_employees: 0,
                total_visits_today: 0,
                completed_visits_today: 0,
                pending_visits_today: 0,
                missed_visits_today: 0,
                flagged_visits_today: 0,
                avg_visits_per_employee: 0,
            },
            '/api/v1/reports/geo-verification': geoData,
        });

        let clickedAnchor: HTMLAnchorElement | null = null;
        const clickSpy = vi
            .spyOn(HTMLAnchorElement.prototype, 'click')
            .mockImplementation(function (this: HTMLAnchorElement) {
                clickedAnchor = this;
            });

        renderWithProviders(<ReportsPage />);
        await userEvent.click(await screen.findByRole('button', { name: 'visits' }));
        await userEvent.click(await screen.findByRole('button', { name: /geo verification audit/i }));
        await userEvent.click(await screen.findByRole('button', { name: /csv/i }));

        expect(clickSpy).toHaveBeenCalled();
        expect(clickedAnchor!.download).toMatch(/^geo-verification-report-\d{4}-\d{2}-\d{2}\.csv$/);
        expect(clickedAnchor!.download).not.toMatch(/^[0-9a-f]{8}-/);

        clickSpy.mockRestore();
    });
});

describe('ReportsPage - PDF Export', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(ADMIN_USER);
    });

    it('shows PDF export button for employee report', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': [
                {
                    employee_id: 'emp1',
                    employee_name: 'John Doe',
                    total_visits: 10,
                    completed_visits: 8,
                    pending_visits: 2,
                    missed_visits: 0,
                    flagged_visits: 0,
                    completion_rate: 80.0,
                },
            ],
            '/api/v1/reports/productivity': {
                total_employees: 5,
                active_employees: 3,
                total_visits_today: 15,
                completed_visits_today: 10,
                pending_visits_today: 3,
                missed_visits_today: 1,
                flagged_visits_today: 1,
                avg_visits_per_employee: 3.0,
            },
            '/api/v1/reports/geo-verification': [],
        });

        renderWithProviders(<ReportsPage />);

        // Switch to employees tab
        await userEvent.click(await screen.findByRole('button', { name: 'employees' }));

        // Check PDF button exists
        expect(await screen.findByRole('button', { name: /pdf/i })).toBeInTheDocument();
    });

    it('exports PDF with correct data', async () => {
        const employeeData = [
            {
                employee_id: 'emp1',
                employee_name: 'John Doe',
                total_visits: 10,
                completed_visits: 8,
                pending_visits: 2,
                missed_visits: 0,
                flagged_visits: 0,
                completion_rate: 80.0,
            },
        ];

        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': employeeData,
            '/api/v1/reports/productivity': {
                total_employees: 5,
                active_employees: 3,
                total_visits_today: 15,
                completed_visits_today: 10,
                pending_visits_today: 3,
                missed_visits_today: 1,
                flagged_visits_today: 1,
                avg_visits_per_employee: 3.0,
            },
            '/api/v1/reports/geo-verification': [],
        });

        // Mock click to verify download was triggered
        const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

        renderWithProviders(<ReportsPage />);

        // Switch to employees tab
        await userEvent.click(await screen.findByRole('button', { name: 'employees' }));

        // Click PDF export
        const pdfButton = await screen.findByRole('button', { name: /pdf/i });
        await userEvent.click(pdfButton);

        // Verify download was triggered
        await waitFor(() => expect(clickSpy).toHaveBeenCalled());
        clickSpy.mockRestore();
    });

    it('disables PDF export when no data', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': [],
            '/api/v1/reports/productivity': {
                total_employees: 0,
                active_employees: 0,
                total_visits_today: 0,
                completed_visits_today: 0,
                pending_visits_today: 0,
                missed_visits_today: 0,
                flagged_visits_today: 0,
                avg_visits_per_employee: 0,
            },
            '/api/v1/reports/geo-verification': [],
        });

        renderWithProviders(<ReportsPage />);

        // Switch to employees tab
        await userEvent.click(await screen.findByRole('button', { name: 'employees' }));

        // Check PDF button is disabled
        const pdfButton = await screen.findByRole('button', { name: /pdf/i });
        expect(pdfButton).toBeDisabled();
    });

    it('PDF download anchor has a dated, non-UUID filename and application/pdf MIME type', async () => {
        const employeeData = [
            {
                employee_id: 'emp1',
                employee_name: 'John Doe',
                total_visits: 10,
                completed_visits: 8,
                pending_visits: 2,
                missed_visits: 0,
                flagged_visits: 0,
                completion_rate: 80.0,
            },
        ];

        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': employeeData,
            '/api/v1/reports/productivity': {
                total_employees: 5,
                active_employees: 3,
                total_visits_today: 15,
                completed_visits_today: 10,
                pending_visits_today: 3,
                missed_visits_today: 1,
                flagged_visits_today: 1,
                avg_visits_per_employee: 3.0,
            },
            '/api/v1/reports/geo-verification': [],
        });

        const createSpy = vi.spyOn(URL, 'createObjectURL');
        let clickedAnchor: HTMLAnchorElement | null = null;
        const clickSpy = vi
            .spyOn(HTMLAnchorElement.prototype, 'click')
            .mockImplementation(function (this: HTMLAnchorElement) {
                clickedAnchor = this;
            });

        renderWithProviders(<ReportsPage />);
        await userEvent.click(await screen.findByRole('button', { name: 'employees' }));
        await userEvent.click(await screen.findByRole('button', { name: /pdf/i }));

        expect(clickSpy).toHaveBeenCalled();
        expect(clickedAnchor).not.toBeNull();
        expect(clickedAnchor!.download).toMatch(/^employee-report-\d{4}-\d{2}-\d{2}\.pdf$/);
        expect(clickedAnchor!.download).not.toMatch(/^[0-9a-f]{8}-/);

        const blob = createSpy.mock.calls[0][0] as Blob;
        expect(blob.type).toBe('application/pdf');

        clickSpy.mockRestore();
        createSpy.mockRestore();
    });
});

describe('ReportsPage - Date Range Filtering', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(ADMIN_USER);
    });

    it('shows date range filter controls', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': [],
            '/api/v1/reports/productivity': {
                total_employees: 0,
                active_employees: 0,
                total_visits_today: 0,
                completed_visits_today: 0,
                pending_visits_today: 0,
                missed_visits_today: 0,
                flagged_visits_today: 0,
                avg_visits_per_employee: 0,
            },
            '/api/v1/reports/geo-verification': [],
        });

        renderWithProviders(<ReportsPage />);

        // Check date inputs exist
        expect(await screen.findByLabelText(/start date/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/end date/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /apply filter/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /clear/i })).toBeInTheDocument();
    });

    it('sends date range to API when filter is applied', async () => {
        const requestedUrls: string[] = [];
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': route((url) => {
                requestedUrls.push(url);
                return json([]);
            }),
            '/api/v1/reports/productivity': {
                total_employees: 0,
                active_employees: 0,
                total_visits_today: 0,
                completed_visits_today: 0,
                pending_visits_today: 0,
                missed_visits_today: 0,
                flagged_visits_today: 0,
                avg_visits_per_employee: 0,
            },
            '/api/v1/reports/geo-verification': route((url) => {
                requestedUrls.push(url);
                return json([]);
            }),
        });

        renderWithProviders(<ReportsPage />);

        // Wait for initial load
        await waitFor(() => expect(requestedUrls.length).toBeGreaterThan(0));

        // Set date range using fireEvent for date inputs
        const startDateInput = await screen.findByLabelText(/start date/i);
        const endDateInput = screen.getByLabelText(/end date/i);

        fireEvent.change(startDateInput, { target: { value: '2026-01-01' } });
        fireEvent.change(endDateInput, { target: { value: '2026-12-31' } });

        // Wait for state to update
        await waitFor(() => {
            expect(startDateInput).toHaveValue('2026-01-01');
            expect(endDateInput).toHaveValue('2026-12-31');
        });

        // Clear the requested URLs from initial load
        const initialCount = requestedUrls.length;

        // Apply filter
        await userEvent.click(screen.getByRole('button', { name: /apply filter/i }));

        // Verify API was called with date range
        await waitFor(() => {
            expect(requestedUrls.length).toBeGreaterThan(initialCount);
            // Find the last call to /reports/employees
            const employeeCalls = requestedUrls.filter(u => u.includes('/reports/employees'));
            const lastCall = employeeCalls[employeeCalls.length - 1];
            expect(lastCall).toContain('start_date=2026-01-01');
            expect(lastCall).toContain('end_date=2026-12-31');
        });
    });

    it('validates end date is after start date', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': [],
            '/api/v1/reports/productivity': {
                total_employees: 0,
                active_employees: 0,
                total_visits_today: 0,
                completed_visits_today: 0,
                pending_visits_today: 0,
                missed_visits_today: 0,
                flagged_visits_today: 0,
                avg_visits_per_employee: 0,
            },
            '/api/v1/reports/geo-verification': [],
        });

        renderWithProviders(<ReportsPage />);

        // Set invalid date range (end before start)
        const startDateInput = await screen.findByLabelText(/start date/i);
        const endDateInput = screen.getByLabelText(/end date/i);

        fireEvent.change(startDateInput, { target: { value: '2026-12-31' } });
        fireEvent.change(endDateInput, { target: { value: '2026-01-01' } });

        // Apply filter
        await userEvent.click(screen.getByRole('button', { name: /apply filter/i }));

        // Verify error message
        expect(await screen.findByText(/end date must be after start date/i)).toBeInTheDocument();
    });

    it('clears date filter when clear button is clicked', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': [],
            '/api/v1/reports/productivity': {
                total_employees: 0,
                active_employees: 0,
                total_visits_today: 0,
                completed_visits_today: 0,
                pending_visits_today: 0,
                missed_visits_today: 0,
                flagged_visits_today: 0,
                avg_visits_per_employee: 0,
            },
            '/api/v1/reports/geo-verification': [],
        });

        renderWithProviders(<ReportsPage />);

        // Set date range
        const startDateInput = await screen.findByLabelText(/start date/i);
        const endDateInput = screen.getByLabelText(/end date/i);

        fireEvent.change(startDateInput, { target: { value: '2026-01-01' } });
        fireEvent.change(endDateInput, { target: { value: '2026-12-31' } });

        // Clear filter
        await userEvent.click(screen.getByRole('button', { name: /clear/i }));

        // Verify inputs are cleared
        expect(startDateInput).toHaveValue('');
        expect(endDateInput).toHaveValue('');
    });

    it('shows active filter indicator when dates are set', async () => {
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': [],
            '/api/v1/reports/productivity': {
                total_employees: 0,
                active_employees: 0,
                total_visits_today: 0,
                completed_visits_today: 0,
                pending_visits_today: 0,
                missed_visits_today: 0,
                flagged_visits_today: 0,
                avg_visits_per_employee: 0,
            },
            '/api/v1/reports/geo-verification': [],
        });

        renderWithProviders(<ReportsPage />);

        // Set date range
        const startDateInput = await screen.findByLabelText(/start date/i);
        const endDateInput = screen.getByLabelText(/end date/i);

        fireEvent.change(startDateInput, { target: { value: '2026-01-01' } });
        fireEvent.change(endDateInput, { target: { value: '2026-12-31' } });

        // Apply filter
        await userEvent.click(screen.getByRole('button', { name: /apply filter/i }));

        // Verify active filter indicator
        expect(await screen.findByText(/active filter/i)).toBeInTheDocument();
    });
});

// --- P1-13: date-input edits must not bypass "Apply Filter" -----------------
describe('ReportsPage - P1-13 draft vs applied filter state', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(ADMIN_USER);
    });

    const productivity = {
        total_employees: 0,
        active_employees: 0,
        total_visits_today: 0,
        completed_visits_today: 0,
        pending_visits_today: 0,
        missed_visits_today: 0,
        flagged_visits_today: 0,
        avg_visits_per_employee: 0,
    };

    it('does not refetch report data when a date input changes without clicking Apply Filter', async () => {
        const requestedUrls: string[] = [];
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': route((url) => {
                requestedUrls.push(url);
                return json([]);
            }),
            '/api/v1/reports/productivity': productivity,
            '/api/v1/reports/geo-verification': route((url) => {
                requestedUrls.push(url);
                return json([]);
            }),
        });

        renderWithProviders(<ReportsPage />);
        await waitFor(() => expect(requestedUrls.length).toBeGreaterThan(0));
        const initialCount = requestedUrls.length;

        const startDateInput = await screen.findByLabelText(/start date/i);
        const endDateInput = screen.getByLabelText(/end date/i);

        fireEvent.change(startDateInput, { target: { value: '2026-01-01' } });
        fireEvent.change(endDateInput, { target: { value: '2026-12-31' } });

        // Give an (incorrect) auto-refetch a chance to fire before asserting
        // it didn't - the previous implementation fired this on every change.
        await new Promise((resolve) => setTimeout(resolve, 300));

        expect(requestedUrls.length).toBe(initialCount);
    });

    it('an unrelated re-render (switching tabs) while an edit is pending never fetches with the unapplied draft dates', async () => {
        const requestedUrls: string[] = [];
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': route((url) => {
                requestedUrls.push(url);
                return json([]);
            }),
            '/api/v1/reports/productivity': productivity,
            '/api/v1/reports/geo-verification': route((url) => {
                requestedUrls.push(url);
                return json([]);
            }),
        });

        renderWithProviders(<ReportsPage />);
        await waitFor(() => expect(requestedUrls.length).toBeGreaterThan(0));

        // Edit the draft only - never press Apply.
        fireEvent.change(await screen.findByLabelText(/start date/i), { target: { value: '2026-06-01' } });
        fireEvent.change(screen.getByLabelText(/end date/i), { target: { value: '2026-06-30' } });

        // Trigger unrelated re-renders (tab switching).
        await userEvent.click(screen.getByRole('button', { name: 'employees' }));
        await userEvent.click(screen.getByRole('button', { name: 'business_bi' }));
        await new Promise((resolve) => setTimeout(resolve, 300));

        const employeeCalls = requestedUrls.filter((u) => u.includes('/reports/employees'));
        employeeCalls.forEach((u) => {
            expect(u).not.toContain('start_date=2026-06-01');
            expect(u).not.toContain('end_date=2026-06-30');
        });
    });

    it('pressing Apply Filter commits the draft and fetches exactly once with the new dates', async () => {
        const employeeCalls: string[] = [];
        mockApi({
            ...baseRoutes(ADMIN_USER),
            '/api/v1/reports/employees': route((url) => {
                employeeCalls.push(url);
                return json([]);
            }),
            '/api/v1/reports/productivity': productivity,
            '/api/v1/reports/geo-verification': [],
        });

        renderWithProviders(<ReportsPage />);
        await waitFor(() => expect(employeeCalls.length).toBeGreaterThan(0));
        const countBeforeApply = employeeCalls.length;

        fireEvent.change(await screen.findByLabelText(/start date/i), { target: { value: '2026-02-01' } });
        fireEvent.change(screen.getByLabelText(/end date/i), { target: { value: '2026-02-28' } });
        // No fetch yet - editing the draft alone must not trigger one.
        expect(employeeCalls.length).toBe(countBeforeApply);

        await userEvent.click(screen.getByRole('button', { name: /apply filter/i }));

        await waitFor(() => expect(employeeCalls.length).toBe(countBeforeApply + 1));
        expect(employeeCalls[employeeCalls.length - 1]).toContain('start_date=2026-02-01');
        expect(employeeCalls[employeeCalls.length - 1]).toContain('end_date=2026-02-28');
    });
});
