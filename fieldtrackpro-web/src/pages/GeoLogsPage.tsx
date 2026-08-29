import React, { useCallback, useEffect, useState } from 'react';
import { MapPin } from 'lucide-react';
import { DataTable, Column } from '../components/ui/DataTable';
import { StatusBadge } from '../components/ui/StatusBadge';
import { PageHeader } from '../components/ui/PageHeader';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { EmptyState } from '../components/ui/EmptyState';
import { apiClient } from '../api/client';
import { GeoVerificationLog } from '../types';

interface GeoLogRow extends GeoVerificationLog {
  customer_id?: string;
  customer_name?: string;
  employee_id?: string;
  employee_name?: string;
}

export const GeoLogsPage: React.FC = () => {
  const [logs, setLogs] = useState<GeoLogRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [page, setPage] = useState(1);
  const pageSize = 25;
  const [totalCount, setTotalCount] = useState(0);

  const load = useCallback((targetPage = page) => {
    setIsLoading(true);
    setError(null);

    apiClient
      .getGeoLogsPaginated({
        skip: (targetPage - 1) * pageSize,
        limit: pageSize,
      })
      .then(({ items, total }) => {
        setLogs(items as GeoLogRow[]);
        setTotalCount(total);
      })
      .catch((err: Error) => {
        setLogs([]);
        setTotalCount(0);
        setError(err.message || 'Unable to load geo verification logs');
      })
      .finally(() => setIsLoading(false));
  }, [page, pageSize]);

  useEffect(() => {
    load(page);
  }, [page, load]);

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
      header: 'Customer / Outlet',
      accessor: (log) => (
        <span className="font-caption text-xs text-on-surface font-medium">
          {log.customer_name || (log.customer_id ? `ID: ${log.customer_id.substring(0, 8)}...` : '—')}
        </span>
      ),
    },
    {
      header: 'GPS Coordinates',
      accessor: (log) => (
        <div className="font-caption text-xs text-on-surface font-mono">
          {log.latitude !== null && log.latitude !== undefined && log.longitude !== null && log.longitude !== undefined ? (
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
      header: 'Distance (Meters)',
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
        subtitle="Audit log of all location verification attempts and mock location detection events with server-side pagination."
      />

      {error && <ErrorBanner message={error} onRetry={() => load(page)} onDismiss={() => setError(null)} />}

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
          serverSide={true}
          totalCount={totalCount}
          page={page}
          pageSize={pageSize}
          onPageChange={(p) => setPage(p)}
          searchPlaceholder="Search logs..."
        />
      )}
    </div>
  );
};
