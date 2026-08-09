import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, Plus, Calendar, CalendarCheck } from 'lucide-react';
import { DataTable, Column } from '../components/ui/DataTable';
import { StatusBadge } from '../components/ui/StatusBadge';
import { Modal } from '../components/ui/Modal';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { useAuth } from '../context/AuthContext';
import { apiClient } from '../api/client';
import { Customer, Employee, Visit, VisitStatus } from '../types';

const FILTERS: Array<'ALL' | VisitStatus> = [
  'ALL',
  'PENDING',
  'IN_PROGRESS',
  'COMPLETED',
  'FLAGGED',
  'MISSED',
];

export const VisitsPage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  const [visits, setVisits] = useState<Visit[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFilter, setSelectedFilter] = useState<'ALL' | VisitStatus>('ALL');

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedCustomerId, setSelectedCustomerId] = useState('');
  const [selectedEmployeeId, setSelectedEmployeeId] = useState('');
  const [scheduledAt, setScheduledAt] = useState(
    new Date(Date.now() + 86400000).toISOString().slice(0, 16),
  );
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const fetchVisits = useCallback((status?: VisitStatus) => {
    setIsLoading(true);
    apiClient
      .getVisits(status)
      .then((data) => {
        setVisits(data);
        setError(null);
      })
      .catch((err: Error) => {
        setVisits([]);
        setError(err.message || 'Unable to load visits');
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    fetchVisits(selectedFilter === 'ALL' ? undefined : selectedFilter);
  }, [selectedFilter, fetchVisits]);

  // Reference data for the scheduling form. Admin-only: the employee roster
  // endpoint is admin-scoped, so employees must not request it.
  useEffect(() => {
    if (!isAdmin) return;
    apiClient.getCustomers().then(setCustomers).catch(() => setCustomers([]));
    // FT-006: the roster comes from /employees and yields employees.id, which
    // is what visits.employee_id references. The previous getUsers() call hit
    // a non-existent endpoint (405), leaving this dropdown permanently empty.
    apiClient.getEmployees().then(setEmployees).catch(() => setEmployees([]));
  }, [isAdmin]);

  const customerNameById = useMemo(() => {
    const map = new Map<string, string>();
    customers.forEach((c) => map.set(c.id, c.name));
    return map;
  }, [customers]);

  const handleCreateVisit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (!selectedCustomerId || !selectedEmployeeId) {
      setFormError('Please select both a customer and an employee.');
      return;
    }
    setIsSaving(true);
    try {
      await apiClient.createVisit({
        customer_id: selectedCustomerId,
        employee_id: selectedEmployeeId,
        scheduled_at: new Date(scheduledAt).toISOString(),
      });
      setIsModalOpen(false);
      setSelectedCustomerId('');
      setSelectedEmployeeId('');
      fetchVisits(selectedFilter === 'ALL' ? undefined : selectedFilter);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to schedule visit');
    } finally {
      setIsSaving(false);
    }
  };

  const columns: Column<Visit>[] = [
    {
      header: 'Visit ID / Customer',
      accessor: (visit) => (
        <div>
          <p className="font-headline-sm text-sm text-primary font-bold">
            {visit.customer_name ||
              customerNameById.get(visit.customer_id) ||
              `Customer #${visit.customer_id.substring(0, 8)}`}
          </p>
          <p className="font-caption text-xs text-on-surface-variant font-mono">
            ID: {visit.id.substring(0, 8)}...
          </p>
        </div>
      ),
    },
    {
      header: 'Status',
      accessor: (visit) => <StatusBadge status={visit.status} size="sm" />,
    },
    {
      header: 'Scheduled Time',
      accessor: (visit) => (
        <div className="font-caption text-xs text-on-surface-variant flex items-center gap-1.5 font-medium">
          <Calendar className="w-3.5 h-3.5 text-outline shrink-0" />
          <span>{new Date(visit.scheduled_at).toLocaleString()}</span>
        </div>
      ),
    },
    {
      header: 'Check-In',
      accessor: (visit) => (
        <span className="font-caption text-xs text-on-surface-variant">
          {visit.check_in_at ? new Date(visit.check_in_at).toLocaleString() : '—'}
        </span>
      ),
    },
    {
      header: 'Action',
      accessor: (visit) => (
        <Button
          variant="outline"
          size="sm"
          icon={Eye}
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/visits/${visit.id}`);
          }}
        >
          View
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-space-6">
      <PageHeader
        title="Visit Dispatch & Execution"
        subtitle="Field visit scheduling, execution tracking, and geo-verification status."
        actions={
          /* FT-044: scheduling is an admin capability; the control is not shown
             to field staff, whose requests the API rejects with 403. */
          isAdmin ? (
            <Button variant="secondary" size="sm" icon={Plus} onClick={() => setIsModalOpen(true)}>
              Schedule Visit
            </Button>
          ) : undefined
        }
      />

      {error && (
        <ErrorBanner
          message={error}
          onRetry={() => fetchVisits(selectedFilter === 'ALL' ? undefined : selectedFilter)}
          onDismiss={() => setError(null)}
        />
      )}

      <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3 overflow-x-auto select-none">
        {FILTERS.map((filter) => {
          const isSelected = selectedFilter === filter;
          return (
            <button
              key={filter}
              type="button"
              onClick={() => setSelectedFilter(filter)}
              aria-pressed={isSelected}
              className={`px-space-3.5 py-space-1.5 rounded-lg font-label-md text-xs uppercase tracking-wider transition-all cursor-pointer font-bold ${
                isSelected
                  ? 'bg-primary text-on-primary shadow-xs active:scale-95'
                  : 'bg-surface border border-outline-variant text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface active:scale-95'
              }`}
            >
              {filter.replace('_', ' ')}
            </button>
          );
        })}
      </div>

      {!isLoading && !error && visits.length === 0 ? (
        <EmptyState
          icon={CalendarCheck}
          title={selectedFilter === 'ALL' ? 'No visits scheduled' : `No ${selectedFilter.replace('_', ' ').toLowerCase()} visits`}
          subtitle={
            isAdmin
              ? 'Schedule a visit to dispatch a field representative to a customer site.'
              : 'Visits assigned to you will appear here.'
          }
          action={
            isAdmin ? (
              <Button variant="secondary" size="sm" icon={Plus} onClick={() => setIsModalOpen(true)}>
                Schedule Visit
              </Button>
            ) : undefined
          }
        />
      ) : (
        <DataTable
          columns={columns}
          data={visits}
          isLoading={isLoading}
          searchPlaceholder="Search visits by customer or ID..."
          searchFilter={(v, q) => {
            const needle = q.toLowerCase();
            const name = v.customer_name || customerNameById.get(v.customer_id) || '';
            return name.toLowerCase().includes(needle) || v.id.toLowerCase().includes(needle);
          }}
          onRowClick={(visit) => navigate(`/visits/${visit.id}`)}
        />
      )}

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Schedule New Field Visit"
        subtitle="Assign field agent dispatch details and client site parameters."
      >
        {formError && (
          <div className="mb-space-4 font-body-md text-xs text-on-error-container bg-error-container p-space-3 rounded-xl border border-error">
            {formError}
          </div>
        )}
        <form onSubmit={handleCreateVisit} className="space-y-space-4">
          <Select
            id="visit-customer"
            label="Select Customer"
            required
            value={selectedCustomerId}
            onChange={(e) => setSelectedCustomerId(e.target.value)}
            error={customers.length === 0 ? 'No customers available. Add a customer account first.' : undefined}
          >
            <option value="">-- Choose Customer --</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.address})
              </option>
            ))}
          </Select>

          <Select
            id="visit-employee"
            label="Assigned Field Employee"
            required
            value={selectedEmployeeId}
            onChange={(e) => setSelectedEmployeeId(e.target.value)}
            error={employees.length === 0 ? 'No employee profiles available. Register a field representative first.' : undefined}
          >
            <option value="">-- Choose Employee --</option>
            {employees.map((emp) => (
              <option key={emp.id} value={emp.id}>
                {emp.full_name}
                {emp.employee_code ? ` (${emp.employee_code})` : ''}
              </option>
            ))}
          </Select>

          <Input
            label="Scheduled Date & Time"
            type="datetime-local"
            required
            value={scheduledAt}
            onChange={(e) => setScheduledAt(e.target.value)}
          />

          <div className="pt-space-4 flex justify-end gap-space-3 border-t border-surface-container-highest mt-space-6">
            <Button type="button" variant="ghost" size="sm" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="secondary" size="sm" isLoading={isSaving}>
              Dispatch Visit
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
