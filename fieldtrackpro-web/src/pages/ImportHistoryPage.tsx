import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, Download, CheckCircle2 } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { Modal } from '../components/ui/Modal';
import { StatusBadge } from '../components/ui/StatusBadge';
import { DataTable, Column } from '../components/ui/DataTable';
import { apiClient } from '../api/client';
import { ImportBatchRead, ImportStatus } from '../types';

export const ImportHistoryPage: React.FC = () => {
  const navigate = useNavigate();
  const [batches, setBatches] = useState<ImportBatchRead[]>([]);
  const [statusFilter, setStatusFilter] = useState<ImportStatus | ''>('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<ImportBatchRead | null>(null);
  const [isCommitting, setIsCommitting] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getImportBatches();
      setBatches(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load import history');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = statusFilter ? batches.filter((b) => b.status === statusFilter) : batches;

  const handleDownloadErrors = async (batch: ImportBatchRead) => {
    try {
      const url = await apiClient.getImportErrorsCsvObjectUrl(batch.id);
      const a = document.createElement('a');
      a.href = url;
      a.download = `import_${batch.filename}_errors.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : 'Failed to download error report');
    }
  };

  const handleCommit = async () => {
    if (!selected) return;
    setIsCommitting(true);
    setDetailError(null);
    try {
      const committed = await apiClient.commitImportBatch(selected.id);
      setSelected(committed);
      await load();
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : 'Commit failed');
    } finally {
      setIsCommitting(false);
    }
  };

  const columns: Column<ImportBatchRead>[] = [
    { header: 'File', accessor: (b) => <span className="font-medium">{b.filename}</span> },
    { header: 'Uploaded By', accessor: (b) => b.uploaded_by_email || b.uploaded_by.slice(0, 8) },
    { header: 'Uploaded At', accessor: (b) => new Date(b.uploaded_at).toLocaleString('en-IN') },
    { header: 'Rows', accessor: (b) => b.rows_processed },
    { header: 'Created / Updated', accessor: (b) => `${b.rows_created} / ${b.rows_updated}` },
    { header: 'Errors', accessor: (b) => b.rows_error },
    { header: 'Status', accessor: (b) => <StatusBadge status={b.status} size="sm" /> },
  ];

  return (
    <div className="space-y-space-6">
      <PageHeader
        title="Import History"
        subtitle="Audit trail of every Excel/MIS import: who imported what, when, and the outcome."
        actions={
          <Button variant="primary" icon={UploadCloud} onClick={() => navigate('/imports/new')}>
            New Import
          </Button>
        }
      />

      {error && <ErrorBanner message={error} onRetry={load} />}

      <div className="flex items-center gap-space-3 max-w-xs">
        <Select
          label="Status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as ImportStatus | '')}
        >
          <option value="">All</option>
          <option value="VALIDATED">Validated (pending commit)</option>
          <option value="COMMITTED">Committed</option>
          <option value="FAILED">Failed</option>
          <option value="PENDING">Pending</option>
        </Select>
      </div>

      <DataTable
        columns={columns}
        data={filtered}
        isLoading={isLoading}
        emptyMessage="No imports yet"
        onRowClick={(b) => {
          setSelected(b);
          setDetailError(null);
        }}
      />

      <Modal isOpen={!!selected} onClose={() => setSelected(null)} title="Import Batch Detail" subtitle={selected?.filename} size="lg">
        {selected && (
          <div className="space-y-space-4">
            {detailError && <ErrorBanner message={detailError} />}

            <div className="grid grid-cols-2 gap-space-3 text-sm">
              <div>
                <p className="text-on-surface-variant font-caption text-xs uppercase">Status</p>
                <StatusBadge status={selected.status} size="sm" />
              </div>
              <div>
                <p className="text-on-surface-variant font-caption text-xs uppercase">Sheet</p>
                <p className="font-medium">{selected.sheet_name}</p>
              </div>
              <div>
                <p className="text-on-surface-variant font-caption text-xs uppercase">Uploaded By</p>
                <p className="font-medium">{selected.uploaded_by_email || '—'}</p>
              </div>
              <div>
                <p className="text-on-surface-variant font-caption text-xs uppercase">Uploaded At</p>
                <p className="font-medium">{new Date(selected.uploaded_at).toLocaleString('en-IN')}</p>
              </div>
              <div>
                <p className="text-on-surface-variant font-caption text-xs uppercase">Rows Processed</p>
                <p className="font-medium">{selected.rows_processed}</p>
              </div>
              <div>
                <p className="text-on-surface-variant font-caption text-xs uppercase">Created / Updated / Skipped / Errors</p>
                <p className="font-medium">{selected.rows_created} / {selected.rows_updated} / {selected.rows_skipped} / {selected.rows_error}</p>
              </div>
              {selected.committed_at && (
                <div>
                  <p className="text-on-surface-variant font-caption text-xs uppercase">Committed At</p>
                  <p className="font-medium">{new Date(selected.committed_at).toLocaleString('en-IN')}</p>
                </div>
              )}
              {selected.failure_reason && (
                <div className="col-span-2">
                  <p className="text-error font-caption text-xs uppercase">Failure Reason</p>
                  <p className="font-medium text-error">{selected.failure_reason}</p>
                </div>
              )}
            </div>

            <div className="flex flex-wrap gap-space-3 pt-space-3 border-t border-surface-container-highest">
              {(selected.error_report?.length ?? 0) > 0 && (
                <Button variant="outline" icon={Download} onClick={() => void handleDownloadErrors(selected)}>
                  Download Error Report
                </Button>
              )}
              {selected.status === 'VALIDATED' && (
                <Button variant="primary" icon={CheckCircle2} isLoading={isCommitting} onClick={() => void handleCommit()}>
                  Confirm Import
                </Button>
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
};
