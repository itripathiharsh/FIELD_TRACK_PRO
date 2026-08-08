import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { BarChart3, CheckCircle2, ShieldAlert, TrendingUp } from 'lucide-react';
import { MetricCard } from '../components/ui/MetricCard';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { apiClient } from '../api/client';
import { GeoVerificationLog, Visit } from '../types';

/**
 * Operational summary.
 *
 * FT-029: this page previously displayed invented figures - "96.4% completion
 * rate", "98.8% GPS verification", "4 flagged events", "100% of completed
 * visits attached at least 1 photograph" - none of which came from the system.
 * Presenting fabricated analytics as real reporting is the defect.
 *
 * Every number below is now computed from data the API actually returned, and
 * the page states plainly when there is nothing to report.
 *
 * The dedicated report endpoints specified in 07_api_design.md section 8
 * (/reports/employee-visits, /reports/customer-history, /reports/productivity,
 * /reports/geo-verification, and CSV/PDF export) do not exist in the backend.
 * Building them is new feature work, tracked as FT-067 - see
 * docs/REPAIR_DECISIONS.md RD-004.
 */
export const ReportsPage: React.FC = () => {
  const [visits, setVisits] = useState<Visit[]>([]);
  const [geoLogs, setGeoLogs] = useState<GeoVerificationLog[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setIsLoading(true);
    setError(null);
    apiClient
      .getVisits()
      .then(async (visitList) => {
        setVisits(visitList);
        const logs = await Promise.all(
          visitList.map((v) =>
            apiClient.getVisitGeoLogs(v.id).catch(() => [] as GeoVerificationLog[]),
          ),
        );
        setGeoLogs(logs.flat());
      })
      .catch((err: Error) => {
        setVisits([]);
        setGeoLogs([]);
        setError(err.message || 'Unable to load report data');
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const stats = useMemo(() => {
    const total = visits.length;
    const completed = visits.filter((v) => v.status === 'COMPLETED').length;
    const flagged = visits.filter((v) => v.status === 'FLAGGED').length;
    const missed = visits.filter((v) => v.status === 'MISSED').length;

    const attempts = geoLogs.length;
    const passed = geoLogs.filter((l) => l.is_valid).length;

    return {
      total,
      completed,
      flagged,
      missed,
      attempts,
      passed,
      completionRate: total > 0 ? Math.round((completed / total) * 100) : null,
      verificationRate: attempts > 0 ? Math.round((passed / attempts) * 100) : null,
    };
  }, [visits, geoLogs]);

  const hasData = stats.total > 0;

  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <PageHeader
        title="Reports & Field Analytics"
        subtitle="Operational performance metrics derived from recorded visit activity."
      />

      {error && <ErrorBanner message={error} onRetry={load} onDismiss={() => setError(null)} />}

      {!isLoading && !hasData && !error ? (
        <EmptyState
          icon={BarChart3}
          title="No visits in range"
          subtitle="Reporting figures appear once visits have been scheduled and executed."
        />
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-space-6">
            <MetricCard
              title="Completion Rate"
              value={stats.completionRate === null ? '—' : `${stats.completionRate}%`}
              subtitle={`${stats.completed} of ${stats.total} visit${stats.total === 1 ? '' : 's'} completed`}
              icon={TrendingUp}
              color="emerald"
            />
            <MetricCard
              title="GPS Verification Rate"
              value={stats.verificationRate === null ? '—' : `${stats.verificationRate}%`}
              subtitle={
                stats.attempts === 0
                  ? 'No verification attempts recorded'
                  : `${stats.passed} of ${stats.attempts} attempt${stats.attempts === 1 ? '' : 's'} passed`
              }
              icon={CheckCircle2}
              color="blue"
            />
            <MetricCard
              title="Flagged For Review"
              value={stats.flagged}
              subtitle={
                stats.flagged === 0
                  ? 'Nothing to review'
                  : 'Repeated verification failures need a decision'
              }
              icon={ShieldAlert}
              color={stats.flagged > 0 ? 'amber' : 'slate'}
            />
          </div>

          <Card variant="default">
            <CardHeader>
              <div>
                <CardTitle>Visit Status Breakdown</CardTitle>
                <CardSubtitle>Counts across all visits currently visible to you</CardSubtitle>
              </div>
            </CardHeader>
            <div className="overflow-x-auto">
              <table className="w-full text-left font-body-md text-on-surface">
                <thead className="bg-surface-container-low text-on-surface-variant font-label-md text-xs uppercase tracking-wider border-b border-surface-container-highest">
                  <tr>
                    <th className="px-space-4 py-space-3 font-bold text-primary">Status</th>
                    <th className="px-space-4 py-space-3 font-bold text-primary">Visits</th>
                    <th className="px-space-4 py-space-3 font-bold text-primary">Share</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-highest">
                  {(
                    [
                      ['Completed', stats.completed],
                      ['Flagged', stats.flagged],
                      ['Missed', stats.missed],
                      [
                        'Pending / In progress',
                        stats.total - stats.completed - stats.flagged - stats.missed,
                      ],
                    ] as Array<[string, number]>
                  ).map(([label, count]) => (
                    <tr key={label}>
                      <td className="px-space-4 py-space-3.5 font-headline-sm text-sm text-primary font-semibold">
                        {label}
                      </td>
                      <td className="px-space-4 py-space-3.5 font-body-md text-sm">{count}</td>
                      <td className="px-space-4 py-space-3.5 font-caption text-xs text-on-surface-variant">
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

      <Card variant="flat" className="bg-primary-tint/20 border-primary-fixed-dim">
        <h4 className="font-headline-sm text-sm font-bold text-primary mb-space-2">
          Detailed reporting is not yet available
        </h4>
        <p className="font-caption text-xs text-on-surface-variant leading-relaxed">
          Employee productivity, customer visit history, the geo-verification report and CSV/PDF
          export are defined in the project specification but are not implemented in this build.
          The figures above are calculated live from visit and geo-verification records; no
          placeholder data is shown.
        </p>
      </Card>
    </div>
  );
};
