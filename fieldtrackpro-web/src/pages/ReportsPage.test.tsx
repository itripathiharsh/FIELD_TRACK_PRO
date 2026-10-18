import { describe, expect, it, beforeEach, vi, beforeAll, afterAll } from 'vitest';
import { screen, waitFor, fireEvent, cleanup } from '@testing-library/react';
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
                // eslint-disable-next-line @typescript-eslint/no-this-alias
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
                // eslint-disable-next-line @typescript-eslint/no-this-alias
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


// ---------------------------------------------------------------------------------
// Shared fixtures / helpers for the filter + export tests below
// ---------------------------------------------------------------------------------
const ZONE = { id: 'zone-1', name: 'Zone North', created_at: '2026-01-01T00:00:00Z' };
const AREA = { id: 'area-1', name: 'Area One', territory_id: 'zone-1', territory_name: 'Zone North', created_at: '2026-01-01T00:00:00Z' };
const EMP = {
    id: 'emp-1', user_id: 'u1', full_name: 'Asha Rep', territory_id: 'zone-1', employee_code: 'RF01', created_at: '2026-01-01T00:00:00Z',
    user: { id: 'u1', email: 'a@x.test', mobile_number: null, role: 'EMPLOYEE', is_active: true },
};
const BRAND = { id: 'b1', name: 'USHA', normalized_name: 'usha', is_active: true };
const PERIOD = {
    id: 'p-2026-09', period_year: 2026, period_month: 9, period_name: 'September 2026', status: 'OPEN', snapshot_count: 4,
    total_outlets: 2, total_sales: '1000.00', total_collection: '400.00', total_market_os: '600.00', total_overdue_gt_90: '0.00',
    created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z',
};
const BI_ROW = {
    brand: 'USHA', dimension_name: 'USHA', outlets_count: 2, sales: '1000.00', collection: '400.00', market_outstanding: '600.00',
    bucket_lt_15: '600.00', bucket_15_30: '0', bucket_30_45: '0', bucket_45_60: '0', bucket_60_75: '0', bucket_75_90: '0', bucket_gt_90: '0',
};
const BI = (over: Record<string, unknown> = {}) => ({
    total_outlets: 2, total_sales: '1000.00', total_collection: '400.00', total_market_outstanding: '600.00', total_overdue_gt_90: '0.00',
    brand_summaries: [BI_ROW], zone_summaries: [BI_ROW], area_summaries: [BI_ROW], fos_summaries: [BI_ROW],
    raw_outlet_rows: [{ ...BI_ROW, dms_code: 'D1', outlet_name: 'Outlet One', zone_name: 'Zone North', area_name: 'Area One', fos_name: 'Asha Rep', outlets_count: 1 }],
    data_source: 'SNAPSHOT', data_source_note: null, as_of_date: '2026-09-30', ...over,
});
const OS_ROW = {
    customer_id: 'c1', dms_code: 'D1', outlet_name: 'Outlet One', brand: 'USHA', zone_name: 'Zone North', area_name: 'Area One',
    fos_name: 'Asha Rep', market_outstanding: '600.00', bucket_lt_15: '600.00', bucket_15_30: '0', bucket_30_45: '0', bucket_45_60: '0',
    bucket_60_75: '0', bucket_75_90: '0', bucket_gt_90: '0', highest_overdue_bucket: 'Normal (<15d)', as_of_date: '2026-09-30',
};
const OUTLET_ROW = {
    customer_id: 'c1', dms_code: 'D1', outlet_name: 'Outlet One', zone_name: 'Zone North', area_name: 'Area One', fos_name: 'Asha Rep, Ben Rep',
    geofence_radius_m: 75, location_status: 'MISSING', sales: '1000.00', collection: '400.00', market_outstanding: '600.00', overdue_gt_90: '0',
    as_of_date: '2026-09-30',
};
const STAFF_ROW = {
    employee_id: 'emp-uuid-1', employee_code: 'RF01', employee_name: 'Asha Rep', total_visits: 3, completed_visits: 2, pending_visits: 1,
    missed_visits: 0, flagged_visits: 0, completion_rate: 66.7,
};
const VISIT_ROW = {
    visit_id: 'v1', scheduled_at: '2026-09-30T20:03:00+00:00', employee_name: 'Asha Rep', customer_name: 'Outlet One', dms_code: 'D1',
    zone_name: 'Zone North', area_name: 'Area One', status: 'COMPLETED', check_in_at: '2026-09-30T20:03:00+00:00',
    check_out_at: '2026-09-30T20:20:00+00:00', duration_minutes: 17, is_gps_verified: true,
};
const GEO_ROW = {
    visit_id: 'v1', employee_name: 'Asha Rep', customer_name: 'Outlet One', dms_code: 'D1', attempted_at: '2026-09-30T20:03:00+00:00',
    verification_type: 'CHECK_IN', is_valid: true, distance_m: 12.5, failure_reason: null,
};
const OVERVIEW = {
    totals: { total_outlets: 0, total_invoiced: '0', total_paid: '0', total_outstanding: '0', current_amount: '0', bucket_0_15: '0',
        bucket_16_30: '0', bucket_31_60: '0', bucket_61_90: '0', bucket_90_plus: '0' },
    outlets: [], total_count: 0, skip: 0, limit: 10,
};

type Calls = Record<string, string[]>;

/** Mock every endpoint the Reports page touches; every URL requested is recorded per path. */
function setupApi(overrides: Record<string, unknown> = {}, calls: Calls = {}): Calls {
    const rec = (path: string, body: unknown) =>
        route((url) => {
            (calls[path] ??= []).push(url);
            return json(body);
        });
    mockApi({
        ...baseRoutes(ADMIN_USER),
        '/api/v1/territories': [ZONE],
        '/api/v1/areas': [AREA],
        '/api/v1/employees': [EMP],
        '/api/v1/brands': [BRAND],
        '/api/v1/reports/monthly-periods': [PERIOD],
        '/api/v1/reports/business-summary': rec('business-summary', BI()),
        '/api/v1/reports/outstanding': rec('outstanding', [OS_ROW]),
        '/api/v1/reports/outlets': rec('outlets', [OUTLET_ROW]),
        '/api/v1/reports/employees': rec('employees', [STAFF_ROW]),
        '/api/v1/reports/visits-detailed': rec('visits-detailed', [VISIT_ROW]),
        '/api/v1/reports/geo-verification': rec('geo-verification', [GEO_ROW]),
        '/api/v1/collections/overview': rec('collections-overview', OVERVIEW),
        ...overrides,
    });
    return calls;
}

const last = (calls: Calls, key: string) => (calls[key] ?? [])[(calls[key] ?? []).length - 1] ?? '';
const q = (url: string) => new URL(url, 'http://x').searchParams;

async function openTab(name: string) {
    await userEvent.click(await screen.findByRole('button', { name }));
}

/** Wait until the report for `key` has been requested, then return its latest query params. */
async function params(calls: Calls, key: string) {
    await waitFor(() => expect((calls[key] ?? []).length).toBeGreaterThan(0));
    return q(last(calls, key));
}

describe('ReportsPage - Date Range Filtering', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(ADMIN_USER);
    });

    it('shows date range filter controls', async () => {
        setupApi();
        renderWithProviders(<ReportsPage />);
        expect(await screen.findByLabelText(/start date/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/end date/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /apply filter/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /clear/i })).toBeInTheDocument();
    });

    it('sends the date range to the API (Field Staff) only when the filter is applied', async () => {
        const calls = setupApi();
        renderWithProviders(<ReportsPage />);
        await openTab('employees');
        await params(calls, 'employees');
        const before = calls.employees.length;

        fireEvent.change(await screen.findByLabelText(/start date/i), { target: { value: '2026-01-01' } });
        fireEvent.change(screen.getByLabelText(/end date/i), { target: { value: '2026-12-31' } });
        expect(calls.employees.length).toBe(before); // typing alone never fetches

        await userEvent.click(screen.getByRole('button', { name: /apply filter/i }));
        await waitFor(() => expect(calls.employees.length).toBeGreaterThan(before));
        const p = q(last(calls, 'employees'));
        expect(p.get('start_date')).toBe('2026-01-01');
        expect(p.get('end_date')).toBe('2026-12-31');
    });

    it('validates end date is after start date', async () => {
        setupApi();
        renderWithProviders(<ReportsPage />);
        fireEvent.change(await screen.findByLabelText(/start date/i), { target: { value: '2026-12-31' } });
        fireEvent.change(screen.getByLabelText(/end date/i), { target: { value: '2026-01-01' } });
        await userEvent.click(screen.getByRole('button', { name: /apply filter/i }));
        expect(await screen.findByText(/end date must be after start date/i)).toBeInTheDocument();
    });

    it('clears date filter when clear button is clicked', async () => {
        setupApi();
        renderWithProviders(<ReportsPage />);
        const start = await screen.findByLabelText(/start date/i);
        const end = screen.getByLabelText(/end date/i);
        fireEvent.change(start, { target: { value: '2026-01-01' } });
        fireEvent.change(end, { target: { value: '2026-12-31' } });
        await userEvent.click(screen.getByRole('button', { name: /clear/i }));
        expect(start).toHaveValue('');
        expect(end).toHaveValue('');
    });

    it('banner correctness: no misleading "Active filter" banner; the Applied filters strip lists exactly the params sent', async () => {
        const calls = setupApi();
        renderWithProviders(<ReportsPage />);
        await params(calls, 'business-summary');
        const strip = await screen.findByTestId('applied-filters');
        expect(strip).toHaveTextContent(/none - showing all data/i);

        fireEvent.change(screen.getByLabelText(/start date/i), { target: { value: '2026-09-01' } });
        fireEvent.change(screen.getByLabelText(/end date/i), { target: { value: '2026-09-30' } });
        await userEvent.click(screen.getByRole('button', { name: /apply filter/i }));
        await waitFor(() => expect(screen.getByTestId('applied-filters')).toHaveTextContent('01/09/2026 to 30/09/2026'));
        expect(screen.queryByText(/active filter/i)).not.toBeInTheDocument();
        expect(q(last(calls, 'business-summary')).get('start_date')).toBe('2026-09-01');
    });
});

// --- P1-13: date-input edits must not bypass "Apply Filter" -----------------
describe('ReportsPage - P1-13 draft vs applied filter state', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(ADMIN_USER);
    });

    it('does not refetch report data when a date input changes without clicking Apply Filter', async () => {
        const calls = setupApi();
        renderWithProviders(<ReportsPage />);
        await openTab('employees');
        await params(calls, 'employees');
        const initial = calls.employees.length;

        fireEvent.change(await screen.findByLabelText(/start date/i), { target: { value: '2026-01-01' } });
        fireEvent.change(screen.getByLabelText(/end date/i), { target: { value: '2026-12-31' } });
        await new Promise((resolve) => setTimeout(resolve, 300));
        expect(calls.employees.length).toBe(initial);
    });

    it('an unrelated re-render (switching tabs) while an edit is pending never fetches with the unapplied draft dates', async () => {
        const calls = setupApi();
        renderWithProviders(<ReportsPage />);
        await params(calls, 'business-summary');

        fireEvent.change(await screen.findByLabelText(/start date/i), { target: { value: '2026-06-01' } });
        fireEvent.change(screen.getByLabelText(/end date/i), { target: { value: '2026-06-30' } });

        await openTab('employees');
        await openTab('business_bi');
        await new Promise((resolve) => setTimeout(resolve, 300));

        Object.values(calls).flat().forEach((u) => {
            expect(u).not.toContain('start_date=2026-06-01');
            expect(u).not.toContain('end_date=2026-06-30');
        });
    });

    it('pressing Apply Filter commits the draft and fetches exactly once with the new dates', async () => {
        const calls = setupApi();
        renderWithProviders(<ReportsPage />);
        await openTab('employees');
        await params(calls, 'employees');
        const before = calls.employees.length;

        fireEvent.change(await screen.findByLabelText(/start date/i), { target: { value: '2026-02-01' } });
        fireEvent.change(screen.getByLabelText(/end date/i), { target: { value: '2026-02-28' } });
        expect(calls.employees.length).toBe(before);

        await userEvent.click(screen.getByRole('button', { name: /apply filter/i }));
        await waitFor(() => expect(calls.employees.length).toBe(before + 1));
        expect(last(calls, 'employees')).toContain('start_date=2026-02-01');
        expect(last(calls, 'employees')).toContain('end_date=2026-02-28');
    });
});

// =================================================================================
// Filter-to-params wiring: every tab sends exactly the filters that apply to it
// =================================================================================
describe('ReportsPage - filters reach the API (no silent no-ops)', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(ADMIN_USER);
    });

    async function pickCommon() {
        await userEvent.selectOptions(await screen.findByLabelText('Brand'), 'USHA');
        await userEvent.selectOptions(screen.getByLabelText('Zone (Territory)'), 'zone-1');
        await userEvent.selectOptions(screen.getByLabelText('Area'), 'area-1');
        await userEvent.selectOptions(screen.getByLabelText('FOS / Field Officer'), 'emp-1');
    }

    it('Financial & BI: month/brand/zone/area/employee are sent; search and ageing are disabled', async () => {
        const calls = setupApi();
        renderWithProviders(<ReportsPage />);
        await params(calls, 'business-summary');
        await userEvent.selectOptions(await screen.findByLabelText('Month Period'), '2026-09');
        await pickCommon();
        await waitFor(() => {
            const p = q(last(calls, 'business-summary'));
            expect(p.get('month')).toBe('2026-09');
            expect(p.get('brand')).toBe('USHA');
            expect(p.get('zone_id')).toBe('zone-1');
            expect(p.get('area_id')).toBe('area-1');
            expect(p.get('employee_id')).toBe('emp-1');
        });
        expect(screen.getByLabelText('Search')).toBeDisabled();
        expect(screen.getByLabelText('Ageing Bucket')).toBeDisabled();
        expect(screen.getByLabelText('Ageing Bucket').parentElement).toHaveAttribute('title', expect.stringMatching(/not used by this tab/i));
        const strip = screen.getByTestId('applied-filters');
        expect(strip).toHaveTextContent('Month: September 2026');
        expect(strip).toHaveTextContent('Zone: Zone North');
        expect(strip).toHaveTextContent('Employee: Asha Rep (RF01)');
    });

    it('a date range is sent to Financial & BI, Outstanding and Outlets, and disables the month control', async () => {
        const calls = setupApi();
        renderWithProviders(<ReportsPage />);
        await params(calls, 'business-summary');
        await userEvent.selectOptions(await screen.findByLabelText('Month Period'), '2026-09');
        fireEvent.change(screen.getByLabelText(/start date/i), { target: { value: '2026-08-01' } });
        fireEvent.change(screen.getByLabelText(/end date/i), { target: { value: '2026-08-31' } });
        await userEvent.click(screen.getByRole('button', { name: /apply filter/i }));
        await waitFor(() => expect(q(last(calls, 'business-summary')).get('start_date')).toBe('2026-08-01'));
        const bi = q(last(calls, 'business-summary'));
        expect(bi.get('end_date')).toBe('2026-08-31');
        expect(bi.has('month')).toBe(false); // the range wins; the month is not sent
        expect(screen.getByLabelText('Month Period')).toBeDisabled();
        expect(screen.getByText(/month ignored/i)).toBeInTheDocument();

        await openTab('outstanding');
        const os = await params(calls, 'outstanding');
        expect(os.get('start_date')).toBe('2026-08-01');
        expect(os.get('end_date')).toBe('2026-08-31');
        expect(os.has('month')).toBe(false);

        await openTab('outlets');
        const outlets = await params(calls, 'outlets');
        expect(outlets.get('start_date')).toBe('2026-08-01');
        expect(outlets.get('end_date')).toBe('2026-08-31');
    });

    it('Outstanding: ageing bucket, search, month and entity filters are sent; the as-of date is shown', async () => {
        const calls = setupApi();
        renderWithProviders(<ReportsPage />);
        await openTab('outstanding');
        await params(calls, 'outstanding');
        await userEvent.selectOptions(await screen.findByLabelText('Ageing Bucket'), '75-90');
        await userEvent.selectOptions(screen.getByLabelText('Month Period'), '2026-09');
        await pickCommon();
        await userEvent.type(screen.getByLabelText('Search'), 'one');
        await waitFor(() => {
            const p = q(last(calls, 'outstanding'));
            expect(p.get('ageing_bucket')).toBe('75-90');
            expect(p.get('month')).toBe('2026-09');
            expect(p.get('query')).toBe('one');
            expect(p.get('brand')).toBe('USHA');
            expect(p.get('employee_id')).toBe('emp-1');
        });
        expect(await screen.findByText('30/09/2026')).toBeInTheDocument(); // "As of" column
    });

    it('Outlets: location status + search are sent; Ageing is disabled', async () => {
        const calls = setupApi();
        renderWithProviders(<ReportsPage />);
        await openTab('outlets');
        await params(calls, 'outlets');
        await userEvent.selectOptions(await screen.findByLabelText('Location Status'), 'MISSING');
        await userEvent.type(screen.getByLabelText('Search'), 'one');
        await waitFor(() => {
            const p = q(last(calls, 'outlets'));
            expect(p.get('location_status')).toBe('MISSING');
            expect(p.get('query')).toBe('one');
        });
        expect(screen.getByLabelText('Ageing Bucket')).toBeDisabled();
        expect(screen.getByLabelText('Month Period')).not.toBeDisabled();
        // one row per outlet, the FOS list shown as one string
        expect(screen.getByText('Asha Rep, Ben Rep')).toBeInTheDocument();
    });

    it('Field Staff: search / employee / zone / area / dates are sent; brand, month and ageing are disabled; shows the employee code, not a UUID', async () => {
        const calls = setupApi();
        renderWithProviders(<ReportsPage />);
        await openTab('employees');
        await params(calls, 'employees');
        await userEvent.selectOptions(await screen.findByLabelText('Zone (Territory)'), 'zone-1');
        await userEvent.selectOptions(screen.getByLabelText('Area'), 'area-1');
        await userEvent.selectOptions(screen.getByLabelText('FOS / Field Officer'), 'emp-1');
        await userEvent.type(screen.getByLabelText('Search'), 'asha');
        await waitFor(() => {
            const p = q(last(calls, 'employees'));
            expect(p.get('zone_id')).toBe('zone-1');
            expect(p.get('area_id')).toBe('area-1');
            expect(p.get('employee_id')).toBe('emp-1');
            expect(p.get('query')).toBe('asha');
            expect(p.has('brand')).toBe(false);
        });
        expect(screen.getByLabelText('Brand')).toBeDisabled();
        expect(screen.getByLabelText('Month Period')).toBeDisabled();
        expect(screen.getByLabelText('Ageing Bucket')).toBeDisabled();
        expect(await screen.findByText('RF01')).toBeInTheDocument();
        expect(screen.queryByText('emp-uuid-1')).not.toBeInTheDocument();
    });

    it('Visits: status + search + entity filters are sent and times are rendered in IST (a 20:03 UTC visit is 01/10/2026 01:33)', async () => {
        const calls = setupApi();
        renderWithProviders(<ReportsPage />);
        await openTab('visits');
        await params(calls, 'visits-detailed');
        await userEvent.selectOptions(await screen.findByLabelText('Visit Status'), 'COMPLETED');
        await userEvent.type(screen.getByLabelText('Search'), 'outlet');
        await userEvent.selectOptions(screen.getByLabelText('FOS / Field Officer'), 'emp-1');
        await waitFor(() => {
            const p = q(last(calls, 'visits-detailed'));
            expect(p.get('status')).toBe('COMPLETED');
            expect(p.get('query')).toBe('outlet');
            expect(p.get('employee_id')).toBe('emp-1');
        });
        expect(screen.getByLabelText('Brand')).toBeDisabled();
        expect(await screen.findByText('01/10/2026')).toBeInTheDocument();
        expect(screen.getAllByText('01:33').length).toBeGreaterThan(0);
        expect(screen.queryByText('30/09/2026')).not.toBeInTheDocument();
    });

    it('Geo audit sub-view uses the same filters (status excluded) and IST date-times', async () => {
        const calls = setupApi();
        renderWithProviders(<ReportsPage />);
        await openTab('visits');
        await userEvent.click(await screen.findByRole('button', { name: /geo verification audit/i }));
        await params(calls, 'geo-verification');
        expect(screen.queryByLabelText('Visit Status')).not.toBeInTheDocument();
        await userEvent.selectOptions(screen.getByLabelText('Zone (Territory)'), 'zone-1');
        await userEvent.type(screen.getByLabelText('Search'), 'outlet');
        await waitFor(() => {
            const p = q(last(calls, 'geo-verification'));
            expect(p.get('zone_id')).toBe('zone-1');
            expect(p.get('query')).toBe('outlet');
        });
        expect(await screen.findByText('01/10/2026 01:33')).toBeInTheDocument();
    });

    it('Monthly Snapshots: no filters apply (all controls hidden) and the page says why', async () => {
        const calls = setupApi();
        renderWithProviders(<ReportsPage />);
        await openTab('monthly');
        expect(await screen.findByText(/filters do not apply to monthly snapshots/i)).toBeInTheDocument();
        expect(screen.queryByLabelText('Brand')).not.toBeInTheDocument();
        expect(calls['business-summary'] ?? []).toHaveLength(1); // only the first (default) tab loaded data
    });

    it('Collections Workbench uses the SAME global filters (dates, zone, area, employee, status, search) - no second filter bar', async () => {
        const calls = setupApi();
        renderWithProviders(<ReportsPage />);
        await openTab('collections');
        await params(calls, 'collections-overview');
        expect(screen.queryByPlaceholderText('Search outlets...')).not.toBeInTheDocument(); // the page's own filter card is not rendered
        await userEvent.selectOptions(await screen.findByLabelText('Zone (Territory)'), 'zone-1');
        await userEvent.selectOptions(screen.getByLabelText('Collection Status'), 'OVERDUE');
        await userEvent.type(screen.getByLabelText('Search'), 'one');
        fireEvent.change(screen.getByLabelText(/start date/i), { target: { value: '2026-09-01' } });
        fireEvent.change(screen.getByLabelText(/end date/i), { target: { value: '2026-09-30' } });
        await userEvent.click(screen.getByRole('button', { name: /apply filter/i }));
        await waitFor(() => {
            const p = q(last(calls, 'collections-overview'));
            expect(p.get('territory_id')).toBe('zone-1');
            expect(p.get('collection_status')).toBe('OVERDUE');
            expect(p.get('search')).toBe('one');
            expect(p.get('start_date')).toBe('2026-09-01');
            expect(p.get('end_date')).toBe('2026-09-30');
        });
        expect(screen.getByLabelText('Brand')).toBeDisabled();
        expect(screen.getByLabelText('Month Period')).toBeDisabled();
    });

    it('Financial & BI shows an explicit note when the period fell back to live invoices (and none for snapshots)', async () => {
        const calls = setupApi();
        renderWithProviders(<ReportsPage />);
        await params(calls, 'business-summary');
        expect(await screen.findByTestId('bi-as-of')).toHaveTextContent('as of 30/09/2026');
        expect(screen.queryByTestId('bi-live-note')).not.toBeInTheDocument();
        // second render with the LIVE_INVOICES source
        cleanup();
        setupApi({
            '/api/v1/reports/business-summary': BI({ data_source: 'LIVE_INVOICES', data_source_note: 'No snapshot exists for the selected period', as_of_date: null }),
        });
        renderWithProviders(<ReportsPage />);
        expect(await screen.findByTestId('bi-live-note')).toHaveTextContent(/live invoices, not a snapshot/i);
        expect(screen.getByTestId('bi-live-note')).toHaveTextContent('No snapshot exists for the selected period');
        expect(screen.queryByTestId('bi-as-of')).not.toBeInTheDocument();
    });
});

// =================================================================================
// Exports: Excel + PDF on every tab, same params as the table, filename from the server
// =================================================================================
describe('ReportsPage - server-side Excel / PDF exports', () => {
    beforeEach(() => {
        localStorage.clear();
        signIn(ADMIN_USER);
    });

    const fileResponse = (name: string, type: string) =>
        new Response(new Blob(['x'], { type }), {
            status: 200,
            headers: { 'Content-Type': type, 'Content-Disposition': `attachment; filename="${name}"` },
        });

    function captureDownloads() {
        const downloads: { name: string; type: string }[] = [];
        const create = vi.spyOn(URL, 'createObjectURL').mockImplementation((b) => {
            downloads.push({ name: '', type: (b as Blob).type });
            return 'blob:x';
        });
        const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
            downloads[downloads.length - 1].name = this.download;
        });
        return { downloads, restore: () => { create.mockRestore(); click.mockRestore(); } };
    }

    const EXPORT_TABS: Array<{ tab: string; path: string; key: string; listKey: string; sub?: string }> = [
        { tab: 'business_bi', path: '/api/v1/reports/business-summary/export', key: 'bi-export', listKey: 'business-summary' },
        { tab: 'outstanding', path: '/api/v1/reports/outstanding/export', key: 'os-export', listKey: 'outstanding' },
        { tab: 'outlets', path: '/api/v1/reports/outlets/export', key: 'outlets-export', listKey: 'outlets' },
        { tab: 'employees', path: '/api/v1/reports/employees/export', key: 'staff-export', listKey: 'employees' },
        { tab: 'visits', path: '/api/v1/reports/visits-detailed/export', key: 'visits-export', listKey: 'visits-detailed' },
        { tab: 'visits', sub: 'geo', path: '/api/v1/reports/geo-verification/export', key: 'geo-export', listKey: 'geo-verification' },
        { tab: 'monthly', path: '/api/v1/reports/monthly-periods/export', key: 'monthly-export', listKey: '' },
    ];

    it.each(EXPORT_TABS)('$tab $sub: Excel and PDF buttons call $path with the same params as the table', async ({ tab, sub, path, key, listKey }) => {
        const calls: Calls = {};
        setupApi({
            [path]: route((url) => {
                (calls[key] ??= []).push(url);
                return fileResponse(url.includes('format=pdf') ? 'Report_20261011_1432_filtered.pdf' : 'Report_20261011_1432_filtered.xlsx',
                    url.includes('format=pdf') ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
            }),
        }, calls);
        const cap = captureDownloads();
        renderWithProviders(<ReportsPage />);
        await openTab(tab);
        if (sub === 'geo') await userEvent.click(await screen.findByRole('button', { name: /geo verification audit/i }));
        if (listKey) await params(calls, listKey);
        // apply a few filters so "same params" is meaningful (those that this tab supports)
        if (tab !== 'monthly') {
            await userEvent.selectOptions(await screen.findByLabelText('FOS / Field Officer'), 'emp-1');
            await waitFor(() => expect(q(last(calls, listKey)).get('employee_id')).toBe('emp-1'));
        }
        const excel = await screen.findByRole('button', { name: /export excel/i });
        await waitFor(() => expect(excel).toBeEnabled());
        await userEvent.click(excel);
        await waitFor(() => expect(calls[key]?.length).toBe(1));
        const xl = q(calls[key][0]);
        expect(xl.get('format')).toBe('xlsx');
        await waitFor(() => expect(cap.downloads.length).toBe(1));
        expect(cap.downloads[0].name).toBe('Report_20261011_1432_filtered.xlsx'); // name from Content-Disposition

        await userEvent.click(screen.getByRole('button', { name: /export pdf/i }));
        await waitFor(() => expect(calls[key]?.length).toBe(2));
        const pdf = q(calls[key][1]);
        expect(pdf.get('format')).toBe('pdf');
        // identical filter params on both exports and on the table request
        const strip = (p: URLSearchParams) => [...p.entries()].filter(([k]) => k !== 'format' && k !== 'view').sort().join('|');
        expect(strip(pdf)).toBe(strip(xl));
        if (listKey) expect(strip(q(last(calls, listKey)))).toBe(strip(xl));
        await waitFor(() => expect(cap.downloads.length).toBe(2));
        expect(cap.downloads[1].name).toBe('Report_20261011_1432_filtered.pdf');
        expect(cap.downloads[1].type).toBe('application/pdf');
        cap.restore();
    });

    it('Financial & BI PDF carries the selected summary view; Excel does not', async () => {
        const calls: Calls = {};
        setupApi({
            '/api/v1/reports/business-summary/export': route((url) => {
                (calls.bi ??= []).push(url);
                return fileResponse('Financial_BI.pdf', 'application/pdf');
            }),
        }, calls);
        const cap = captureDownloads();
        renderWithProviders(<ReportsPage />);
        await params(calls, 'business-summary');
        await userEvent.click(await screen.findByRole('button', { name: /zone summary/i }));
        await userEvent.click(screen.getByRole('button', { name: /export pdf/i }));
        await waitFor(() => expect(calls.bi?.length).toBe(1));
        expect(q(calls.bi[0]).get('view')).toBe('zone');
        await userEvent.click(screen.getByRole('button', { name: /export excel/i }));
        await waitFor(() => expect(calls.bi?.length).toBe(2));
        expect(q(calls.bi[1]).has('view')).toBe(false);
        cap.restore();
    });

    it('exports always use the filtered request: dates, brand and search reach the export URL', async () => {
        const calls: Calls = {};
        setupApi({
            '/api/v1/reports/outstanding/export': route((url) => {
                (calls.x ??= []).push(url);
                return fileResponse('Outstanding.xlsx', 'application/octet-stream');
            }),
        }, calls);
        const cap = captureDownloads();
        renderWithProviders(<ReportsPage />);
        await openTab('outstanding');
        await params(calls, 'outstanding');
        await userEvent.selectOptions(await screen.findByLabelText('Brand'), 'USHA');
        await userEvent.selectOptions(screen.getByLabelText('Ageing Bucket'), '>90');
        await userEvent.type(screen.getByLabelText('Search'), 'one');
        fireEvent.change(screen.getByLabelText(/start date/i), { target: { value: '2026-08-01' } });
        fireEvent.change(screen.getByLabelText(/end date/i), { target: { value: '2026-09-30' } });
        await userEvent.click(screen.getByRole('button', { name: /apply filter/i }));
        await waitFor(() => expect(q(last(calls, 'outstanding')).get('start_date')).toBe('2026-08-01'));
        await waitFor(() => expect(q(last(calls, 'outstanding')).get('query')).toBe('one'));
        await userEvent.click(screen.getByRole('button', { name: /export excel/i }));
        await waitFor(() => expect(calls.x?.length).toBe(1));
        const p = q(calls.x[0]);
        expect(Object.fromEntries(p.entries())).toEqual({
            brand: 'USHA', ageing_bucket: '>90', query: 'one', start_date: '2026-08-01', end_date: '2026-09-30', format: 'xlsx',
        });
        cap.restore();
    });

    it('export buttons are disabled with an explanatory tooltip when there are no rows', async () => {
        setupApi({ '/api/v1/reports/outstanding': [] });
        renderWithProviders(<ReportsPage />);
        await openTab('outstanding');
        const excel = await screen.findByRole('button', { name: /export excel/i });
        await waitFor(() => expect(excel).toBeDisabled());
        expect(screen.getByRole('button', { name: /export pdf/i })).toBeDisabled();
        expect(excel).toHaveAttribute('title', expect.stringMatching(/no rows match/i));
    });

    it('shows an error banner when the export request fails (no silent failure) and no file is saved', async () => {
        setupApi({
            '/api/v1/reports/outstanding/export': () => new Response(JSON.stringify({ error: { code: 'X', message: 'export exploded' } }), { status: 500 }),
        });
        const cap = captureDownloads();
        renderWithProviders(<ReportsPage />);
        await openTab('outstanding');
        const excel = await screen.findByRole('button', { name: /export excel/i });
        await waitFor(() => expect(excel).toBeEnabled());
        await userEvent.click(excel);
        expect(await screen.findByText(/export exploded/i)).toBeInTheDocument();
        expect(cap.downloads).toHaveLength(0);
        cap.restore();
    });
});
