import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, ShieldAlert, TrendingUp, Users, Download, FileText, Calendar } from 'lucide-react';
import { MetricCard } from '../components/ui/MetricCard';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { Button } from '../components/ui/Button';
import { apiClient } from '../api/client';
import { generatePDFContent as buildPDF } from '../utils/pdf-report';

interface EmployeeReportRow {
    employee_id: string;
    employee_name: string;
    total_visits: number;
    completed_visits: number;
    pending_visits: number;
    missed_visits: number;
    flagged_visits: number;
    completion_rate: number;
}

interface ProductivityDashboard {
    total_employees: number;
    active_employees: number;
    total_visits_today: number;
    completed_visits_today: number;
    pending_visits_today: number;
    missed_visits_today: number;
    flagged_visits_today: number;
    avg_visits_per_employee: number;
}

interface GeoReportRow {
    visit_id: string;
    employee_name: string;
    customer_name: string;
    attempted_at: string;
    verification_type: string;
    is_valid: boolean;
    distance_m: number;
    failure_reason: string | null;
}

interface DateRange {
    startDate: string;
    endDate: string;
}

/**
 * Reports page — displays real report data from backend APIs with date filtering and export.
 */
export const ReportsPage: React.FC = () => {
    const [employeeReport, setEmployeeReport] = useState<EmployeeReportRow[]>([]);
    const [productivity, setProductivity] = useState<ProductivityDashboard | null>(null);
    const [geoReport, setGeoReport] = useState<GeoReportRow[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isExporting, setIsExporting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<'overview' | 'employees' | 'geo'>('overview');
    // P1-13: `dateRange` is the DRAFT filter, bound directly to the date
    // inputs - it changes on every keystroke/date-pick and must never by
    // itself trigger a report reload. `appliedDateRange` is what the last
    // "Apply Filter" (or "Clear") click actually committed, and is the only
    // thing `load` depends on. Previously there was only one date-range
    // state, and `load`'s useCallback depended on it directly, so changing
    // either input alone refetched the report immediately - "Apply Filter"
    // was decorative, not gating anything.
    const [dateRange, setDateRange] = useState<DateRange>({
        startDate: '',
        endDate: '',
    });
    const [appliedDateRange, setAppliedDateRange] = useState<DateRange>({
        startDate: '',
        endDate: '',
    });
    const [dateError, setDateError] = useState<string | null>(null);

    const validateDateRange = useCallback((): boolean => {
        if (dateRange.startDate && dateRange.endDate) {
            const start = new Date(dateRange.startDate);
            const end = new Date(dateRange.endDate);
            if (end < start) {
                setDateError('End date must be after start date');
                return false;
            }
        }
        setDateError(null);
        return true;
    }, [dateRange]);

    const load = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
            const [empData, prodData, geoData] = await Promise.all([
                apiClient.getEmployeeReport(
                    appliedDateRange.startDate || undefined,
                    appliedDateRange.endDate || undefined
                ).catch(() => [] as EmployeeReportRow[]),
                apiClient.getProductivityDashboard().catch(() => null),
                apiClient.getGeoVerificationReport(
                    appliedDateRange.startDate || undefined,
                    appliedDateRange.endDate || undefined
                ).catch(() => [] as GeoReportRow[]),
            ]);
            setEmployeeReport(empData);
            setProductivity(prodData);
            setGeoReport(geoData);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unable to load report data');
        } finally {
            setIsLoading(false);
        }
    }, [appliedDateRange]);

    // Fires on mount, and whenever "Apply Filter"/"Clear" actually commits a
    // new appliedDateRange - never on a raw draft-input change.
    useEffect(() => {
        load();
    }, [load]);

    const handleDateChange = useCallback((field: 'startDate' | 'endDate', value: string) => {
        setDateRange(prev => ({ ...prev, [field]: value }));
    }, []);

    const applyDateFilter = useCallback(() => {
        if (validateDateRange()) {
            setAppliedDateRange(dateRange);
        }
    }, [validateDateRange, dateRange]);

    const clearDateFilter = useCallback(() => {
        const empty = { startDate: '', endDate: '' };
        setDateRange(empty);
        setAppliedDateRange(empty);
        setDateError(null);
    }, []);

    const downloadBlob = useCallback((blob: Blob, filename: string) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        // Chrome race: if the blob URL is revoked before the download task
        // snapshots the filename, Chrome falls back to the blob URL's internal
        // UUID as the file name. Defer the revoke so the download always reads
        // the URL (and its download attribute) first.
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, []);

    const todayStamp = new Date().toISOString().split('T')[0];

    const exportCSV = useCallback((data: Record<string, unknown>[], baseName: string) => {
        if (data.length === 0) return;
        const headers = Object.keys(data[0]);
        const csvContent = [
            headers.join(','),
            ...data.map(row => headers.map(h => {
                const val = row[h];
                if (val === null || val === undefined) return '""';
                const str = String(val).replace(/"/g, '""');
                return `"${str}"`;
            }).join(','))
        ].join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        downloadBlob(blob, `${baseName}-${todayStamp}.csv`);
    }, [downloadBlob, todayStamp]);

    const exportPDF = useCallback(async (data: Record<string, unknown>[], baseName: string, title: string) => {
        if (data.length === 0) return;
        setIsExporting(true);
        try {
            const headers = Object.keys(data[0]);
            const rows = data.map(row => headers.map(h => String(row[h] ?? '')));

            // Exported data reflects whatever is currently on screen, which is
            // driven by the applied filter - the PDF's date-range annotation
            // must match that, not an unapplied draft still sitting in the inputs.
            const pdfContent = generatePDFContent(title, headers, rows, appliedDateRange);
            const blob = new Blob([pdfContent], { type: 'application/pdf' });
            downloadBlob(blob, `${baseName}-${todayStamp}.pdf`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to export PDF');
        } finally {
            setIsExporting(false);
        }
    }, [appliedDateRange, downloadBlob, todayStamp]);

    const generatePDFContent = (title: string, headers: string[], rows: string[][], range: DateRange): Uint8Array => {
        return buildPDF({
            title,
            headers,
            rows,
            dateRange: range,
        });
    };

    const stats = useMemo(() => {
        const total = employeeReport.reduce((sum, r) => sum + r.total_visits, 0);
        const completed = employeeReport.reduce((sum, r) => sum + r.completed_visits, 0);
        const flagged = employeeReport.reduce((sum, r) => sum + r.flagged_visits, 0);
        const missed = employeeReport.reduce((sum, r) => sum + r.missed_visits, 0);
        return { total, completed, flagged, missed };
    }, [employeeReport]);

    return (
        <div className="space-y-space-6 font-body-md text-on-surface">
            <PageHeader
                title="Reports & Field Analytics"
                subtitle="Operational performance metrics derived from recorded visit activity."
            />

            {error && <ErrorBanner message={error} onRetry={load} onDismiss={() => setError(null)} />}

            {/* Date Range Filter */}
            <Card variant="default">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Calendar className="w-5 h-5" />
                        Date Range Filter
                    </CardTitle>
                    <CardSubtitle>Filter report data by date range</CardSubtitle>
                </CardHeader>
                <div className="flex flex-wrap items-end gap-4">
                    <div className="flex flex-col gap-1">
                        <label htmlFor="start-date" className="text-sm font-medium text-on-surface-variant">
                            Start Date
                        </label>
                        <input
                            id="start-date"
                            type="date"
                            value={dateRange.startDate}
                            onChange={(e) => handleDateChange('startDate', e.target.value)}
                            className="px-3 py-2 border border-outline-variant rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                        />
                    </div>
                    <div className="flex flex-col gap-1">
                        <label htmlFor="end-date" className="text-sm font-medium text-on-surface-variant">
                            End Date
                        </label>
                        <input
                            id="end-date"
                            type="date"
                            value={dateRange.endDate}
                            onChange={(e) => handleDateChange('endDate', e.target.value)}
                            className="px-3 py-2 border border-outline-variant rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                        />
                    </div>
                    <div className="flex gap-2">
                        <Button
                            size="sm"
                            variant="secondary"
                            onClick={applyDateFilter}
                            disabled={isLoading}
                        >
                            Apply Filter
                        </Button>
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={clearDateFilter}
                            disabled={isLoading || (!dateRange.startDate && !dateRange.endDate)}
                        >
                            Clear
                        </Button>
                    </div>
                    {dateError && (
                        <p className="text-sm text-red-600 w-full">{dateError}</p>
                    )}
                    {(appliedDateRange.startDate || appliedDateRange.endDate) && !dateError && (
                        <p className="text-sm text-emerald-600 w-full">
                            Active filter: {appliedDateRange.startDate || 'Start'} to {appliedDateRange.endDate || 'End'}
                        </p>
                    )}
                    {!dateError && (dateRange.startDate !== appliedDateRange.startDate || dateRange.endDate !== appliedDateRange.endDate) && (
                        <p className="text-sm text-on-surface-variant w-full">
                            Filter changed - click "Apply Filter" to update the results below.
                        </p>
                    )}
                </div>
            </Card>

            {isLoading ? (
                <div className="flex items-center justify-center h-64">
                    <div className="w-10 h-10 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin" />
                </div>
            ) : (
                <>
                    {/* Tab Navigation */}
                    <div className="flex gap-space-2 border-b border-surface-container-highest">
                        {(['overview', 'employees', 'geo'] as const).map(tab => (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                className={`px-space-4 py-space-2 font-label-md text-sm capitalize ${
                                    activeTab === tab
                                        ? 'text-primary border-b-2 border-primary'
                                        : 'text-on-surface-variant hover:text-on-surface'
                                }`}
                            >
                                {tab === 'geo' ? 'Geo Verification' : tab}
                            </button>
                        ))}
                    </div>

                    {/* Overview Tab */}
                    {activeTab === 'overview' && (
                        <>
                            <div className="grid grid-cols-1 md:grid-cols-4 gap-space-6">
                                <MetricCard
                                    title="Total Employees"
                                    value={productivity?.total_employees ?? 0}
                                    icon={Users}
                                    color="blue"
                                />
                                <MetricCard
                                    title="Visits Today"
                                    value={productivity?.total_visits_today ?? 0}
                                    icon={TrendingUp}
                                    color="emerald"
                                />
                                <MetricCard
                                    title="Completion Rate"
                                    value={stats.total > 0 ? `${Math.round((stats.completed / stats.total) * 100)}%` : '—'}
                                    subtitle={`${stats.completed} of ${stats.total} visits`}
                                    icon={CheckCircle2}
                                    color="emerald"
                                />
                                <MetricCard
                                    title="Flagged"
                                    value={stats.flagged}
                                    subtitle={stats.flagged === 0 ? 'Nothing to review' : 'Needs attention'}
                                    icon={ShieldAlert}
                                    color={stats.flagged > 0 ? 'amber' : 'slate'}
                                />
                            </div>

                            <Card variant="default">
                                <CardHeader>
                                    <CardTitle>Visit Status Breakdown</CardTitle>
                                    <CardSubtitle>Counts across all visits</CardSubtitle>
                                </CardHeader>
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left">
                                        <thead className="bg-surface-container-low text-xs uppercase tracking-wider border-b">
                                            <tr>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Status</th>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Visits</th>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Share</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y">
                                            {([
                                                ['Completed', stats.completed],
                                                ['Flagged', stats.flagged],
                                                ['Missed', stats.missed],
                                                ['Pending / In Progress', stats.total - stats.completed - stats.flagged - stats.missed],
                                            ] as [string, number][]).map(([label, count]) => (
                                                <tr key={label}>
                                                    <td className="px-space-4 py-space-3.5 font-semibold text-sm text-primary">{label}</td>
                                                    <td className="px-space-4 py-space-3.5 text-sm">{count}</td>
                                                    <td className="px-space-4 py-space-3.5 text-xs text-on-surface-variant">
                                                        {stats.total > 0 ? `${Math.round((count / stats.total) * 100)}%` : '—'}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            </Card>
                        </>
                    )}

                    {/* Employees Tab */}
                    {activeTab === 'employees' && (
                        <Card variant="default">
                            <CardHeader className="flex-row items-center justify-between">
                                <div>
                                    <CardTitle>Employee Visit Report</CardTitle>
                                    <CardSubtitle>
                                        Visits per employee
                                        {appliedDateRange.startDate && ` from ${appliedDateRange.startDate}`}
                                        {appliedDateRange.endDate && ` to ${appliedDateRange.endDate}`}
                                    </CardSubtitle>
                                </div>
                                <div className="flex gap-2">
                                    <Button
                                        size="sm"
                                        variant="secondary"
                                        icon={Download}
                                        onClick={() => exportCSV(employeeReport as unknown as Record<string, unknown>[], 'employee-report')}
                                        disabled={employeeReport.length === 0 || isExporting}
                                    >
                                        CSV
                                    </Button>
                                    <Button
                                        size="sm"
                                        variant="secondary"
                                        icon={FileText}
                                        onClick={() => exportPDF(employeeReport as unknown as Record<string, unknown>[], 'employee-report', 'Employee Visit Report')}
                                        disabled={employeeReport.length === 0 || isExporting}
                                        isLoading={isExporting}
                                    >
                                        PDF
                                    </Button>
                                </div>
                            </CardHeader>
                            {employeeReport.length === 0 ? (
                                <EmptyState title="No employee data" subtitle="No visits recorded yet." />
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left">
                                        <thead className="bg-surface-container-low text-xs uppercase tracking-wider border-b">
                                            <tr>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Employee</th>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Total</th>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Completed</th>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Pending</th>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Missed</th>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Flagged</th>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Rate</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y">
                                            {employeeReport.map(row => (
                                                <tr key={row.employee_id}>
                                                    <td className="px-space-4 py-space-3.5 font-semibold text-sm">{row.employee_name}</td>
                                                    <td className="px-space-4 py-space-3.5 text-sm">{row.total_visits}</td>
                                                    <td className="px-space-4 py-space-3.5 text-sm text-emerald-600">{row.completed_visits}</td>
                                                    <td className="px-space-4 py-space-3.5 text-sm">{row.pending_visits}</td>
                                                    <td className="px-space-4 py-space-3.5 text-sm text-red-600">{row.missed_visits}</td>
                                                    <td className="px-space-4 py-space-3.5 text-sm text-amber-600">{row.flagged_visits}</td>
                                                    <td className="px-space-4 py-space-3.5 text-sm font-semibold">{row.completion_rate}%</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </Card>
                    )}

                    {/* Geo Verification Tab */}
                    {activeTab === 'geo' && (
                        <Card variant="default">
                            <CardHeader className="flex-row items-center justify-between">
                                <div>
                                    <CardTitle>Geo-Verification Report</CardTitle>
                                    <CardSubtitle>
                                        Flagged/failed check-ins with reason codes
                                        {appliedDateRange.startDate && ` from ${appliedDateRange.startDate}`}
                                        {appliedDateRange.endDate && ` to ${appliedDateRange.endDate}`}
                                    </CardSubtitle>
                                </div>
                                <div className="flex gap-2">
                                    <Button
                                        size="sm"
                                        variant="secondary"
                                        icon={Download}
                                        onClick={() => exportCSV(geoReport as unknown as Record<string, unknown>[], 'geo-verification-report')}
                                        disabled={geoReport.length === 0 || isExporting}
                                    >
                                        CSV
                                    </Button>
                                    <Button
                                        size="sm"
                                        variant="secondary"
                                        icon={FileText}
                                        onClick={() => exportPDF(geoReport as unknown as Record<string, unknown>[], 'geo-verification-report', 'Geo-Verification Report')}
                                        disabled={geoReport.length === 0 || isExporting}
                                        isLoading={isExporting}
                                    >
                                        PDF
                                    </Button>
                                </div>
                            </CardHeader>
                            {geoReport.length === 0 ? (
                                <EmptyState title="No geo-verification data" subtitle="No verification attempts recorded yet." />
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left">
                                        <thead className="bg-surface-container-low text-xs uppercase tracking-wider border-b">
                                            <tr>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Employee</th>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Customer</th>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Type</th>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Status</th>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Distance</th>
                                                <th className="px-space-4 py-space-3 font-bold text-primary">Reason</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y">
                                            {geoReport.map(row => (
                                                <tr key={row.visit_id}>
                                                    <td className="px-space-4 py-space-3.5 text-sm">{row.employee_name}</td>
                                                    <td className="px-space-4 py-space-3.5 text-sm">{row.customer_name}</td>
                                                    <td className="px-space-4 py-space-3.5 text-sm">{row.verification_type}</td>
                                                    <td className="px-space-4 py-space-3.5 text-sm">
                                                        {row.is_valid ? (
                                                            <span className="text-emerald-600 font-semibold">PASS</span>
                                                        ) : (
                                                            <span className="text-red-600 font-semibold">FAIL</span>
                                                        )}
                                                    </td>
                                                    <td className="px-space-4 py-space-3.5 text-sm">{row.distance_m.toFixed(1)}m</td>
                                                    <td className="px-space-4 py-space-3.5 text-xs text-on-surface-variant">{row.failure_reason || '—'}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </Card>
                    )}
                </>
            )}
        </div>
    );
};
