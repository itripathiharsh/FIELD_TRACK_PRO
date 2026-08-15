import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, FileText, Tag, Eye, Pencil, Send, Archive, Undo2, Copy, ListChecks, ClipboardList, PlayCircle, CheckCircle2 } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { DataTable, Column } from '../components/ui/DataTable';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { Input } from '../components/ui/Input';
import { Modal } from '../components/ui/Modal';
import { PageHeader } from '../components/ui/PageHeader';
import { StatusBadge } from '../components/ui/StatusBadge';
import { useAuth } from '../context/AuthContext';
import { apiClient, RequirementCategory } from '../api/client';
import { Customer, FormStatus, FormSubmission, FormTemplateSummary, Visit } from '../types';

const STATUS_FILTERS: Array<'ALL' | FormStatus> = ['ALL', 'DRAFT', 'PUBLISHED', 'ARCHIVED'];

interface QueueItem {
  visit: Visit;
  submission: FormSubmission | undefined;
  outletName: string;
}

/**
 * Employee-facing forms WORK QUEUE - not a template browser.
 *
 * A form can only ever be filled from within a specific visit's context
 * (FormSubmission.visit_id is NOT NULL), so this page shows exactly the
 * (form, visit) pairs relevant to this employee's own assigned visits,
 * split into what's outstanding vs. already submitted - never a catalog of
 * every template that exists, and never any admin template-management
 * control (those live only in AdminFormsManager below).
 */
const EmployeeFormsBrowser: React.FC = () => {
  const navigate = useNavigate();
  const [items, setItems] = useState<QueueItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [visits, customers] = await Promise.all([
        apiClient.getVisits(),
        apiClient.getCustomers().catch(() => [] as Customer[]),
      ]);
      const outletNameById = new Map(customers.map((c) => [c.id, c.name]));
      const relevant = visits.filter((v) => v.required_form_id);
      const withSubmissions = await Promise.all(
        relevant.map(async (visit) => {
          const subs = await apiClient
            .getFormSubmissions({ visit_id: visit.id, form_id: visit.required_form_id! })
            .catch(() => [] as FormSubmission[]);
          return {
            visit,
            submission: subs[0],
            outletName: outletNameById.get(visit.customer_id) || `Outlet #${visit.customer_id.slice(0, 8)}`,
          };
        }),
      );
      withSubmissions.sort((a, b) => new Date(b.visit.scheduled_at).getTime() - new Date(a.visit.scheduled_at).getTime());
      setItems(withSubmissions);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load forms');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const pending = items.filter((i) => i.submission?.status !== 'SUBMITTED');
  const completed = items.filter((i) => i.submission?.status === 'SUBMITTED');

  const renderRow = (item: QueueItem, completedRow: boolean) => (
    <div
      key={item.visit.id}
      className="p-space-3.5 bg-surface-container-low border border-outline-variant rounded-lg flex items-center justify-between gap-space-3"
    >
      <div className="min-w-0">
        <p className="font-headline-sm text-sm text-primary font-bold truncate">{item.visit.required_form_name}</p>
        <p className="font-caption text-xs text-on-surface-variant">{item.outletName}</p>
        <p className="font-caption text-xs text-on-surface-variant">
          {completedRow
            ? `Submitted: ${item.submission?.submitted_at ? new Date(item.submission.submitted_at).toLocaleString() : '—'}`
            : `Visit: ${new Date(item.visit.scheduled_at).toLocaleDateString()} · Status: ${item.submission ? 'Draft' : 'Not Started'}`}
        </p>
      </div>
      <div className="flex items-center gap-space-2 shrink-0">
        {item.submission && <StatusBadge status={item.submission.status} size="sm" />}
        {completedRow ? (
          <Button variant="outline" size="sm" icon={Eye} onClick={() => navigate(`/visits/${item.visit.id}/forms/${item.visit.required_form_id}`)}>
            View
          </Button>
        ) : (
          <Button variant="secondary" size="sm" icon={PlayCircle} onClick={() => navigate(`/visits/${item.visit.id}/forms/${item.visit.required_form_id}`)}>
            {item.submission ? 'Continue' : 'Open'}
          </Button>
        )}
      </div>
    </div>
  );

  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <PageHeader title="Requirement Forms" subtitle="Forms required for your assigned visits." />

      {error && <ErrorBanner message={error} onRetry={() => void load()} onDismiss={() => setError(null)} />}

      {!isLoading && !error && items.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title="No forms required right now"
          subtitle="When an admin assigns a required form to one of your visits, it will appear here."
        />
      ) : isLoading ? (
        <Card variant="flat" className="animate-pulse h-28">
          <div className="h-4 bg-surface-container-high rounded w-1/2 mb-space-2" />
          <div className="h-3 bg-surface-container-high rounded w-1/3" />
        </Card>
      ) : (
        <>
          <Card variant="default" className="space-y-space-3">
            <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3">
              <ClipboardList className="w-5 h-5 text-primary" />
              <h3 className="font-headline-sm text-base font-bold text-primary">Pending ({pending.length})</h3>
            </div>
            {pending.length === 0 ? (
              <p className="font-caption text-xs text-on-surface-variant py-space-3 text-center">Nothing outstanding.</p>
            ) : (
              <div className="space-y-space-3">{pending.map((i) => renderRow(i, false))}</div>
            )}
          </Card>

          {completed.length > 0 && (
            <Card variant="default" className="space-y-space-3">
              <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3">
                <CheckCircle2 className="w-5 h-5 text-primary" />
                <h3 className="font-headline-sm text-base font-bold text-primary">Completed ({completed.length})</h3>
              </div>
              <div className="space-y-space-3">{completed.map((i) => renderRow(i, true))}</div>
            </Card>
          )}
        </>
      )}
    </div>
  );
};

const AdminFormsManager: React.FC = () => {
  const navigate = useNavigate();
  const [forms, setForms] = useState<FormTemplateSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [categories, setCategories] = useState<RequirementCategory[]>([]);
  const [showCategoryModal, setShowCategoryModal] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState('');
  const [isSubmittingCategory, setIsSubmittingCategory] = useState(false);
  // Defaults to PUBLISHED - the reusable templates admins actually attach to
  // visits day to day. Drafts-in-progress and retired archives are one click
  // away, not mixed into the default view where they used to clutter it.
  const [statusFilter, setStatusFilter] = useState<'ALL' | FormStatus>('PUBLISHED');

  const loadForms = useCallback(() => {
    setIsLoading(true);
    apiClient.getFormTemplates(statusFilter === 'ALL' ? undefined : { status: statusFilter })
      .then((data) => { setForms(data); setError(null); })
      .catch((err: Error) => setError(err.message || 'Failed to load forms'))
      .finally(() => setIsLoading(false));
  }, [statusFilter]);

  useEffect(() => {
    loadForms();
    apiClient.getRequirementCategories().then(setCategories).catch(() => setCategories([]));
  }, [loadForms]);

  const handleCreateCategory = async () => {
    if (!newCategoryName.trim()) return;
    setIsSubmittingCategory(true);
    try {
      await apiClient.createRequirementCategory(newCategoryName.trim());
      const updated = await apiClient.getRequirementCategories();
      setCategories(updated);
      setNewCategoryName('');
      setShowCategoryModal(false);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to create category');
    } finally {
      setIsSubmittingCategory(false);
    }
  };

  const runAction = async (formId: string, action: () => Promise<unknown>) => {
    setBusyId(formId);
    setActionError(null);
    try {
      await action();
      loadForms();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Action failed');
    } finally {
      setBusyId(null);
    }
  };

  const columns: Column<FormTemplateSummary>[] = [
    {
      header: 'Form',
      accessor: (f) => (
        <div>
          <p className="font-headline-sm text-sm text-primary font-bold">{f.name}</p>
          <p className="font-caption text-xs text-on-surface-variant">
            {f.category_name || 'Uncategorized'} &middot; {f.question_count} question{f.question_count === 1 ? '' : 's'} &middot; Used by {f.visit_count} visit{f.visit_count === 1 ? '' : 's'} &middot; {f.submission_count} submission{f.submission_count === 1 ? '' : 's'}
          </p>
        </div>
      ),
    },
    { header: 'Status', accessor: (f) => <StatusBadge status={f.status} size="sm" /> },
    { header: 'Version', accessor: (f) => <span className="font-caption text-xs text-on-surface">v{f.version}</span> },
    {
      header: 'Created By',
      accessor: (f) => <span className="font-caption text-xs text-on-surface-variant font-mono">{f.created_by.substring(0, 8)}...</span>,
    },
    { header: 'Updated', accessor: (f) => <span className="font-caption text-xs text-on-surface-variant">{new Date(f.updated_at).toLocaleDateString()}</span> },
    {
      header: 'Published',
      accessor: (f) => (
        <span className="font-caption text-xs text-on-surface-variant">
          {f.published_at ? new Date(f.published_at).toLocaleDateString() : '—'}
        </span>
      ),
    },
    {
      header: 'Actions',
      accessor: (f) => (
        <div className="flex items-center gap-space-1.5 flex-wrap">
          <Button variant="outline" size="sm" icon={Eye} onClick={(e) => { e.stopPropagation(); navigate(`/forms/${f.id}/preview`); }}>
            Preview
          </Button>
          {f.status !== 'ARCHIVED' && (
            <Button variant="outline" size="sm" icon={Pencil} onClick={(e) => { e.stopPropagation(); navigate(`/forms/${f.id}/edit`); }}>
              Edit
            </Button>
          )}
          {f.status === 'DRAFT' && (
            <Button variant="ghost" size="sm" icon={Send} isLoading={busyId === f.id} onClick={(e) => { e.stopPropagation(); runAction(f.id, () => apiClient.publishFormTemplate(f.id)); }}>
              Publish
            </Button>
          )}
          {f.status === 'PUBLISHED' && (
            <>
              <Button variant="ghost" size="sm" icon={Undo2} isLoading={busyId === f.id} onClick={(e) => { e.stopPropagation(); runAction(f.id, () => apiClient.unpublishFormTemplate(f.id)); }}>
                Unpublish
              </Button>
              <Button variant="ghost" size="sm" icon={Archive} isLoading={busyId === f.id} onClick={(e) => { e.stopPropagation(); runAction(f.id, () => apiClient.archiveFormTemplate(f.id)); }}>
                Archive
              </Button>
            </>
          )}
          <Button variant="ghost" size="sm" icon={Copy} isLoading={busyId === f.id} onClick={(e) => { e.stopPropagation(); runAction(f.id, () => apiClient.duplicateFormTemplate(f.id)); }}>
            Duplicate
          </Button>
          <Button variant="ghost" size="sm" icon={ListChecks} onClick={(e) => { e.stopPropagation(); navigate(`/forms/${f.id}/submissions`); }}>
            Submissions
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <PageHeader
        title="Requirement Forms"
        subtitle="Reusable templates for Visits - build once, attach to any visit, review submissions in context."
        actions={
          <>
            <Button variant="outline" size="sm" icon={Tag} onClick={() => setShowCategoryModal(true)}>
              Categories
            </Button>
            <Button variant="secondary" size="sm" icon={Plus} onClick={() => navigate('/forms/new')}>
              New Form
            </Button>
          </>
        }
      />

      {error && <ErrorBanner message={error} onRetry={loadForms} onDismiss={() => setError(null)} />}
      {actionError && <ErrorBanner message={actionError} onDismiss={() => setActionError(null)} />}

      <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3 overflow-x-auto select-none">
        {STATUS_FILTERS.map((filter) => {
          const isSelected = statusFilter === filter;
          return (
            <button
              key={filter}
              type="button"
              onClick={() => setStatusFilter(filter)}
              aria-pressed={isSelected}
              className={`px-space-3.5 py-space-1.5 rounded-lg font-label-md text-xs uppercase tracking-wider transition-all cursor-pointer font-bold ${
                isSelected
                  ? 'bg-primary text-on-primary shadow-xs active:scale-95'
                  : 'bg-surface border border-outline-variant text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface active:scale-95'
              }`}
            >
              {filter}
            </button>
          );
        })}
      </div>

      {!isLoading && !error && forms.length === 0 ? (
        <EmptyState
          icon={FileText}
          title={statusFilter === 'ALL' ? 'No forms created yet' : `No ${statusFilter.toLowerCase()} forms`}
          subtitle={
            statusFilter === 'ALL'
              ? 'Build your first flexible requirement form — inspection checklists, requirement capture, and more.'
              : 'Switch to "ALL" to see forms in other statuses, or create a new one.'
          }
          action={
            <Button variant="secondary" size="sm" icon={Plus} onClick={() => navigate('/forms/new')}>
              New Form
            </Button>
          }
        />
      ) : (
        <DataTable
          columns={columns}
          data={forms}
          isLoading={isLoading}
          searchPlaceholder="Search forms by name..."
          searchFilter={(f, q) => f.name.toLowerCase().includes(q.toLowerCase())}
          onRowClick={(f) => navigate(`/forms/${f.id}/edit`)}
        />
      )}

      <Modal isOpen={showCategoryModal} onClose={() => setShowCategoryModal(false)} title="Requirement Categories" subtitle="Used to group forms in the builder.">
        <div className="space-y-space-4">
          <div className="grid grid-cols-2 gap-space-3">
            {categories.map((cat) => (
              <Card key={cat.id} variant="flat" className="flex items-center gap-space-2">
                <Tag className="w-4 h-4 text-primary shrink-0" />
                <span className="font-body-md text-sm text-on-surface">{cat.name}</span>
              </Card>
            ))}
          </div>
          <div className="pt-space-4 border-t border-surface-container-highest flex gap-space-2">
            <Input value={newCategoryName} onChange={(e) => setNewCategoryName(e.target.value)} placeholder="e.g., Safety" />
            <Button variant="secondary" size="md" isLoading={isSubmittingCategory} disabled={!newCategoryName.trim()} onClick={handleCreateCategory}>
              Add
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

/** Role split lives here, not in routing: same /forms concept, role-appropriate UI. */
export const FormsPage: React.FC = () => {
  const { user } = useAuth();
  return user?.role === 'EMPLOYEE' ? <EmployeeFormsBrowser /> : <AdminFormsManager />;
};
