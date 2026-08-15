import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Eye, ListChecks } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { DataTable, Column } from '../components/ui/DataTable';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { StatusBadge } from '../components/ui/StatusBadge';
import { apiClient } from '../api/client';
import { FormSubmission, FormTemplate } from '../types';

export const FormSubmissionsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [form, setForm] = useState<FormTemplate | null>(null);
  const [submissions, setSubmissions] = useState<FormSubmission[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!id) return;
    setIsLoading(true);
    Promise.all([apiClient.getFormTemplate(id), apiClient.getFormSubmissions({ form_id: id })])
      .then(([f, subs]) => { setForm(f); setSubmissions(subs); setError(null); })
      .catch((err: Error) => setError(err.message || 'Unable to load submissions'))
      .finally(() => setIsLoading(false));
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const columns: Column<FormSubmission>[] = [
    {
      header: 'Employee',
      accessor: (s) => <span className="font-headline-sm text-sm text-primary font-bold">{s.employee_name || s.submitted_by.substring(0, 8)}</span>,
    },
    {
      header: 'Outlet / Visit',
      accessor: (s) => (
        <div>
          <p className="font-body-md text-sm text-on-surface">{s.customer_name || `Visit #${s.visit_id.substring(0, 8)}`}</p>
          {s.visit_scheduled_at && (
            <p className="font-caption text-xs text-on-surface-variant">{new Date(s.visit_scheduled_at).toLocaleDateString()}</p>
          )}
        </div>
      ),
    },
    { header: 'Status', accessor: (s) => <StatusBadge status={s.status} size="sm" /> },
    { header: 'Version', accessor: (s) => <span className="font-caption text-xs text-on-surface">v{s.form_version}</span> },
    {
      header: 'Started',
      accessor: (s) => <span className="font-caption text-xs text-on-surface-variant">{new Date(s.started_at).toLocaleString()}</span>,
    },
    {
      header: 'Submitted',
      accessor: (s) => <span className="font-caption text-xs text-on-surface-variant">{s.submitted_at ? new Date(s.submitted_at).toLocaleString() : '—'}</span>,
    },
    {
      header: 'Action',
      accessor: (s) => (
        <Button variant="outline" size="sm" icon={Eye} onClick={(e) => { e.stopPropagation(); navigate(`/forms/${id}/submissions/${s.id}`); }}>
          Review
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-space-6">
      <Button variant="ghost" size="sm" icon={ArrowLeft} onClick={() => navigate(`/forms/${id}/edit`)}>
        Back to Builder
      </Button>
      <PageHeader title={form ? `Submissions — ${form.name}` : 'Submissions'} subtitle="Every employee response recorded against this form." />

      {error && <ErrorBanner message={error} onRetry={load} onDismiss={() => setError(null)} />}

      {!isLoading && !error && submissions.length === 0 ? (
        <EmptyState icon={ListChecks} title="No submissions yet" subtitle="Submissions will appear here once employees fill and submit this form." />
      ) : (
        <DataTable
          columns={columns}
          data={submissions}
          isLoading={isLoading}
          searchPlaceholder="Search by employee..."
          searchFilter={(s, q) => (s.employee_name || '').toLowerCase().includes(q.toLowerCase())}
          onRowClick={(s) => navigate(`/forms/${id}/submissions/${s.id}`)}
        />
      )}
    </div>
  );
};
