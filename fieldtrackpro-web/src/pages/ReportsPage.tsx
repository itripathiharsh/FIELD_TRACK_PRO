import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, ShieldAlert, TrendingUp, Users, Download } from 'lucide-react';
import { MetricCard } from '../components/ui/MetricCard';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { Button } from '../components/ui/Button';
import { apiClient } from '../api/client';

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

/**
 * Reports page — displays real report data from backend APIs.
 */
export const ReportsPage: React.FC = () => {
    const [employeeReport, setEmployeeReport] = useState<EmployeeReportRow[]>([]);
    const [productivity, setProductivity] = useState<ProductivityDashboard | null>(null);
    const [geoReport, setGeoReport] = useState<GeoReportRow[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<'overview' | 'employees' | 'geo'>('overview');

    const load = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
            const [empData, prodData, geoData] = await Promise.all([
                apiClient.getEmployeeReport().catch(() => [] as EmployeeReportRow[]),
                apiClient.getProductivityDashboard().catch(() => null),
                apiClient.getGeoVerificationReport().catch(() => [] as GeoReportRow[]),
            ]);
            setEmployeeReport(empData);
            setProductivity(prodData);
            setGeoReport(geoData);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unable to load report data');
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const exportCSV = useCallback((data: Record<string, unknown>[], filename: string) => {
        if (data.length === 0) return;
        const headers = Object.keys(data[0]);
        const csv = [
            headers.join(','),
            ...data.map(row => headers.map(h => `"${row[h] ?? ''}"`).join(','))
        ].join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${filename}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }, []);

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
                                    <CardSubtitle>Visits per employee</CardSubtitle>
                                </div>
                                <Button
                                    size="sm"
                                    variant="secondary"
                                    icon={Download}
                                    onClick={() => exportCSV(employeeReport as unknown as Record<string, unknown>[], 'employee_report')}
                                    disabled={employeeReport.length === 0}
                                >
                                    Export CSV
                                </Button>
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
                                    <CardSubtitle>Flagged/failed check-ins with reason codes</CardSubtitle>
                                </div>
                                <Button
                                    size="sm"
                                    variant="secondary"
                                    icon={Download}
                                    onClick={() => exportCSV(geoReport as unknown as Record<string, unknown>[], 'geo_verification_report')}
                                    disabled={geoReport.length === 0}
                                >
                                    Export CSV
                                </Button>
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
