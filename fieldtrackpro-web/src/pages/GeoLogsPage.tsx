import React, { useEffect, useState } from 'react';
import { DataTable, Column } from '../components/ui/DataTable';
import { StatusBadge } from '../components/ui/StatusBadge';
import { PageHeader } from '../components/ui/PageHeader';
import { apiClient } from '../api/client';
import { GeoVerificationLog } from '../types';

export const GeoLogsPage: React.FC = () => {
  const [logs, setLogs] = useState<GeoVerificationLog[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Fetch visits then aggregate geo logs
    apiClient.getVisits()
      .then((visits) => {
        const promises = visits.map((v) => apiClient.getVisitGeoLogs(v.id).catch(() => []));
        return Promise.all(promises);
      })
      .then((results) => {
        const flattened = results.flat();
        setLogs(flattened);
      })
      .catch(() => setLogs([]))
      .finally(() => setIsLoading(false));
  }, []);

  const columns: Column<GeoVerificationLog>[] = [
    {
      header: 'Event / Visit ID',
      accessor: (log) => (
        <div>
          <p className="font-headline-sm text-sm text-primary font-bold">{log.verification_type}</p>
          <p className="font-caption text-xs text-on-surface-variant">Visit: {log.visit_id.substring(0, 8)}...</p>
        </div>
      ),
    },
    {
      header: 'GPS Coordinates',
      accessor: (log) => (
        <div className="font-caption text-xs text-on-surface font-mono">
          <p>{log.latitude}, {log.longitude}</p>
        </div>
      ),
    },
    {
      header: 'Distance to Target',
      accessor: (log) => (
        <span className="font-caption text-xs text-on-surface">
          {log.distance_from_target_m !== null ? `${Math.round(log.distance_from_target_m)} meters` : 'N/A'}
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
        <span className={`font-caption text-xs ${log.failure_reason ? 'text-error font-semibold' : 'text-on-surface-variant'}`}>
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

      <DataTable
        columns={columns}
        data={logs}
        isLoading={isLoading}
        searchPlaceholder="Search logs by verification type, visit ID, failure reason..."
        searchFilter={(log, q) =>
          Boolean(
            log.verification_type.toLowerCase().includes(q.toLowerCase()) ||
            log.visit_id.toLowerCase().includes(q.toLowerCase()) ||
            (log.failure_reason && log.failure_reason.toLowerCase().includes(q.toLowerCase()))
          )
        }
      />
    </div>
  );
};
