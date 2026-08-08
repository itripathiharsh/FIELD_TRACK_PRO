import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, Plus, Calendar } from 'lucide-react';
import { DataTable, Column } from '../components/ui/DataTable';
import { StatusBadge } from '../components/ui/StatusBadge';
import { Modal } from '../components/ui/Modal';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { apiClient } from '../api/client';
import { Visit, VisitStatus, Customer, User } from '../types';

export const VisitsPage: React.FC = () => {
  const navigate = useNavigate();
  const [visits, setVisits] = useState<Visit[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [employees, setEmployees] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedFilter, setSelectedFilter] = useState<string>('ALL');

  // Modal & Form state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedCustomerId, setSelectedCustomerId] = useState('');
  const [selectedEmployeeId, setSelectedEmployeeId] = useState('');
  const [scheduledAt, setScheduledAt] = useState(new Date(Date.now() + 86400000).toISOString().slice(0, 16));
  const [formError, setFormError] = useState<string | null>(null);

  const fetchVisits = (status?: VisitStatus) => {
    setIsLoading(true);
    apiClient.getVisits(status)
      .then((data) => setVisits(data))
      .catch(() => setVisits([]))
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    fetchVisits(selectedFilter === 'ALL' ? undefined : (selectedFilter as VisitStatus));
  }, [selectedFilter]);

  useEffect(() => {
    apiClient.getCustomers().then(setCustomers).catch(() => []);
    apiClient.getUsers().then(setEmployees).catch(() => []);
  }, []);

  const handleCreateVisit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    if (!selectedCustomerId || !selectedEmployeeId) {
      setFormError('Please select both a customer and an employee.');
      return;
    }
    try {
      await apiClient.createVisit({
        customer_id: selectedCustomerId,
        employee_id: selectedEmployeeId,
        scheduled_at: new Date(scheduledAt).toISOString(),
      });
      setIsModalOpen(false);
      fetchVisits(selectedFilter === 'ALL' ? undefined : (selectedFilter as VisitStatus));
    } catch (err: any) {
      setFormError(err.message || 'Failed to schedule visit');
    }
  };

  const columns: Column<Visit>[] = [
    {
      header: 'Visit ID / Customer',
      accessor: (visit) => (
        <div>
          <p className="font-headline-sm text-sm text-primary font-bold">
            {visit.customer_name || `Customer #${visit.customer_id.substring(0, 8)}`}
          </p>
          <p className="font-caption text-xs text-on-surface-variant font-mono">ID: {visit.id.substring(0, 8)}...</p>
        </div>
      ),
    },
    {
      header: 'Purpose / Status',
      accessor: (visit) => (
        <div className="space-y-1">
          <p className="font-body-md text-xs text-on-surface">{visit.purpose || 'Site Inspection'}</p>
          <StatusBadge status={visit.status} size="sm" />
        </div>
      ),
    },
    {
      header: 'Scheduled Time',
      accessor: (visit) => (
        <div className="font-caption text-xs text-on-surface-variant flex items-center gap-1.5 font-medium">
          <Calendar className="w-3.5 h-3.5 text-outline shrink-0" />
          <span>
            {visit.scheduled_start_time
              ? new Date(visit.scheduled_start_time).toLocaleString()
              : (visit as any).scheduled_at
              ? new Date((visit as any).scheduled_at).toLocaleString()
              : 'N/A'}
          </span>
        </div>
      ),
    },
    {
      header: 'Geo Failures',
      accessor: (visit) => (
        <span className={`font-label-md text-xs ${visit.verification_failure_count > 0 ? 'text-secondary font-bold bg-secondary-fixed/40 px-2 py-0.5 rounded inline-block' : 'text-on-surface-variant font-medium'}`}>
          {visit.verification_failure_count || 0} attempt(s)
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

  const filterOptions = ['ALL', 'PENDING', 'IN_PROGRESS', 'COMPLETED', 'FLAGGED', 'MISSED'];

  return (
    <div className="space-y-space-6">
      <PageHeader
        title="Visit Dispatch & Execution"
        subtitle="Field visit scheduling, execution tracking, and geo-verification status."
        actions={
          <Button variant="secondary" size="sm" icon={Plus} onClick={() => setIsModalOpen(true)}>
            Schedule Visit
          </Button>
        }
      />

      {/* Filter Tabs */}
      <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3 overflow-x-auto select-none">
        {filterOptions.map((filter) => {
          const isSelected = selectedFilter === filter;
          return (
            <button
              key={filter}
              type="button"
              onClick={() => setSelectedFilter(filter)}
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

      <DataTable
        columns={columns}
        data={visits}
        isLoading={isLoading}
        searchPlaceholder="Search visits by customer, purpose, ID..."
        searchFilter={(v, q) =>
          (v.customer_name ? v.customer_name.toLowerCase().includes(q.toLowerCase()) : false) ||
          (v.purpose ? v.purpose.toLowerCase().includes(q.toLowerCase()) : false) ||
          v.id.toLowerCase().includes(q.toLowerCase())
        }
        onRowClick={(visit) => navigate(`/visits/${visit.id}`)}
      />

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
          <div className="flex flex-col gap-space-1.5">
            <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold">
              Select Customer
            </label>
            <select
              required
              value={selectedCustomerId}
              onChange={(e) => setSelectedCustomerId(e.target.value)}
              className="w-full h-10 bg-surface border border-outline-variant rounded-lg px-space-3 text-on-surface font-body-md text-sm focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all cursor-pointer"
            >
              <option value="">-- Choose Customer --</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>{c.name} ({c.address})</option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-space-1.5">
            <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold">
              Assigned Field Employee
            </label>
            <select
              required
              value={selectedEmployeeId}
              onChange={(e) => setSelectedEmployeeId(e.target.value)}
              className="w-full h-10 bg-surface border border-outline-variant rounded-lg px-space-3 text-on-surface font-body-md text-sm focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all cursor-pointer"
            >
              <option value="">-- Choose Employee --</option>
              {employees.map((e) => (
                <option key={e.id} value={e.id}>{e.email} ({e.role})</option>
              ))}
            </select>
          </div>
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
            <Button type="submit" variant="secondary" size="sm">
              Dispatch Visit
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
