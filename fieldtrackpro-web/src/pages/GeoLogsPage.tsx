import React, { useCallback, useEffect, useState } from 'react';
import { MapPin } from 'lucide-react';
import { DataTable, Column } from '../components/ui/DataTable';
import { StatusBadge } from '../components/ui/StatusBadge';
import { PageHeader } from '../components/ui/PageHeader';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { EmptyState } from '../components/ui/EmptyState';
import { apiClient } from '../api/client';
import { GeoVerificationLog, Visit } from '../types';

/** A geo log paired with the visit it belongs to, for display context. */
interface GeoLogRow extends GeoVerificationLog {
  customer_id?: string;
}

export const GeoLogsPage: React.FC = () => {
  const [logs, setLogs] = useState<GeoLogRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setIsLoading(true);
    setError(null);

    apiClient
      .getVisits()
      .then(async (visits: Visit[]) => {
        const results = await Promise.all(
          visits.map(async (v) => {
            const entries = await apiClient.getVisitGeoLogs(v.id);
            return entries.map((entry) => ({ ...entry, customer_id: v.customer_id }));
          }),
        );
        setLogs(results.flat());
      })
      .catch((err: Error) => {
        // FT-005: the geo-logs endpoint used to return 500, and this page
        // swallowed it and rendered "No records found" - indistinguishable
        // from a genuinely empty audit trail. Failures are now reported.
        setLogs([]);
        setError(err.message || 'Unable to load geo verification logs');
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const columns: Column<GeoLogRow>[] = [
    {
      header: 'Event / Visit ID',
      accessor: (log) => (
        <div>
          <p className="font-headline-sm text-sm text-primary font-bold">
            {log.verification_type.replace('_', '-')}
          </p>
          <p className="font-caption text-xs text-on-surface-variant">
            Visit: {log.visit_id.substring(0, 8)}...
          </p>
        </div>
      ),
    },
    {
      header: 'GPS Coordinates',
      accessor: (log) => (
        <div className="font-caption text-xs text-on-surface font-mono">
          {log.latitude !== null && log.longitude !== null ? (
            <p>
              {log.latitude.toFixed(6)}, {log.longitude.toFixed(6)}
            </p>
          ) : (
            <span className="text-outline">—</span>
          )}
        </div>
      ),
    },
    {
      header: 'Distance to Target',
      accessor: (log) => (
        <span className="font-caption text-xs text-on-surface">
          {Math.round(log.distance_from_customer_m)} meters
        </span>
      ),
    },
    {
      header: 'Attempted At',
      accessor: (log) => (
        <span className="font-caption text-xs text-on-surface-variant">
          {new Date(log.attempted_at).toLocaleString()}
        </span>
      ),
    },
    {
      header: 'Validation Result',
      accessor: (log) => <StatusBadge status={log.is_valid ? 'VALID' : 'INVALID'} size="sm" />,
    },
    {
      header: 'Failure Reason',
      accessor: (log) => (
        <span
          className={`font-caption text-xs ${
            log.failure_reason ? 'text-error font-semibold' : 'text-on-surface-variant'
          }`}
        >
          {log.failure_reason || 'None (Verified Proximity)'}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <PageHeader
        title="Master Geo Verification Audit Logs"
        subtitle="Audit log of all location verification attempts and mock location detection events."
      />

      {error && <ErrorBanner message={error} onRetry={load} onDismiss={() => setError(null)} />}

      {!isLoading && !error && logs.length === 0 ? (
        <EmptyState
          icon={MapPin}
          title="No check-ins recorded yet"
          subtitle="Geo verification attempts appear here as soon as field staff check in or out."
        />
      ) : (
        <DataTable
          columns={columns}
          data={logs}
          isLoading={isLoading}
          searchPlaceholder="Search logs by verification type, visit ID, failure reason..."
          searchFilter={(log, q) =>
            Boolean(
              log.verification_type.toLowerCase().includes(q.toLowerCase()) ||
                log.visit_id.toLowerCase().includes(q.toLowerCase()) ||
                (log.failure_reason && log.failure_reason.toLowerCase().includes(q.toLowerCase())),
            )
          }
        />
      )}
    </div>
  );
};
