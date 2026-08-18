import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Eye,
  Plus,
  Calendar,
  CalendarCheck,
  Users,
  Search,
  Filter,
  X,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  MapPin,
  UserCheck,
  Clock,
  RotateCcw,
} from 'lucide-react';
import { StatusBadge } from '../components/ui/StatusBadge';
import { Modal } from '../components/ui/Modal';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { Card } from '../components/ui/Card';
import { useAuth } from '../context/AuthContext';
import { apiClient } from '../api/client';
import {
  Area,
  Customer,
  Employee,
  FormTemplateSummary,
  Territory,
  Visit,
  VisitStatus,
} from '../types';

const STATUS_OPTIONS: Array<{ label: string; value: 'ALL' | VisitStatus }> = [
  { label: 'ALL', value: 'ALL' },
  { label: 'PENDING', value: 'PENDING' },
  { label: 'IN PROGRESS', value: 'IN_PROGRESS' },
  { label: 'COMPLETED', value: 'COMPLETED' },
  { label: 'FLAGGED', value: 'FLAGGED' },
  { label: 'MISSED', value: 'MISSED' },
];

const PAGE_SIZE_OPTIONS = [20, 50, 100];

export const VisitsPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  // Read URL query state
  const urlStatus = (searchParams.get('status') as VisitStatus | 'ALL') || 'ALL';
  const urlSearch = searchParams.get('search') || '';
  const urlEmployeeId = searchParams.get('employee_id') || '';
  const urlTerritoryId = searchParams.get('territory_id') || '';
  const urlAreaId = searchParams.get('area_id') || '';
  const urlFromDate = searchParams.get('from_date') || '';
  const urlToDate = searchParams.get('to_date') || '';
  const urlSortOrder = (searchParams.get('sort_order') as 'asc' | 'desc') || 'desc';
  const urlPage = parseInt(searchParams.get('page') || '1', 10);
  const urlPageSize = parseInt(searchParams.get('page_size') || '20', 10);

  // Local state initialized from URL
  const [visits, setVisits] = useState<Visit[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Reference data for scheduling and filter dropdowns
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [publishedForms, setPublishedForms] = useState<FormTemplateSummary[]>([]);

  // Search input draft state
  const [searchInput, setSearchInput] = useState(urlSearch);
  const [isAdvancedFiltersOpen, setIsAdvancedFiltersOpen] = useState(
    Boolean(urlEmployeeId || urlTerritoryId || urlAreaId || urlFromDate || urlToDate),
  );

  // Scheduling Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedCustomerId, setSelectedCustomerId] = useState('');
  const [selectedEmployeeId, setSelectedEmployeeId] = useState('');
  const [selectedFormId, setSelectedFormId] = useState('');
  const [scheduledAt, setScheduledAt] = useState(
    new Date(Date.now() + 86400000).toISOString().slice(0, 16),
  );
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Bulk scheduling modal state
  const [isBulkModalOpen, setIsBulkModalOpen] = useState(false);
  const [bulkSelectedCustomers, setBulkSelectedCustomers] = useState<string[]>([]);
  const [bulkEmployeeId, setBulkEmployeeId] = useState('');
  const [bulkRequiredFormId, setBulkRequiredFormId] = useState('');
  const [bulkScheduledAt, setBulkScheduledAt] = useState(
    new Date(Date.now() + 86400000).toISOString().slice(0, 16),
  );
  const [bulkFormError, setBulkFormError] = useState<string | null>(null);
  const [bulkIsSaving, setBulkIsSaving] = useState(false);

  // Update URL helper
  const updateUrlParams = useCallback(
    (updates: Record<string, string | number | undefined | null>, resetPage = true) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        Object.entries(updates).forEach(([key, val]) => {
          if (val === undefined || val === null || val === '' || (key === 'status' && val === 'ALL')) {
            next.delete(key);
          } else {
            next.set(key, String(val));
          }
        });
        if (resetPage) {
          next.set('page', '1');
        }
        return next;
      });
    },
    [setSearchParams],
  );

  // Fetch reference dropdown options (Admin only)
  useEffect(() => {
    if (!isAdmin) return;
    apiClient.getCustomers().then(setCustomers).catch(() => setCustomers([]));
    apiClient.getEmployees().then(setEmployees).catch(() => setEmployees([]));
    apiClient.getTerritories().then(setTerritories).catch(() => setTerritories([]));
    apiClient.getAreas().then(setAreas).catch(() => setAreas([]));
    apiClient
      .getFormTemplates({ status: 'PUBLISHED' })
      .then(setPublishedForms)
      .catch(() => setPublishedForms([]));
  }, [isAdmin]);

  // Cascading area options
  const areaOptions = useMemo(() => {
    if (!urlTerritoryId) return areas;
    return areas.filter((a) => a.territory_id === urlTerritoryId);
  }, [areas, urlTerritoryId]);

  // Fetch paginated visits from real backend API
  const loadVisits = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const skip = (urlPage - 1) * urlPageSize;
      const resp = await apiClient.getVisitsPaginated({
        status: urlStatus === 'ALL' ? undefined : urlStatus,
        search: urlSearch.trim() || undefined,
        employee_id: urlEmployeeId || undefined,
        territory_id: urlTerritoryId || undefined,
        area_id: urlAreaId || undefined,
        from_date: urlFromDate ? `${urlFromDate}T00:00:00Z` : undefined,
        to_date: urlToDate ? `${urlToDate}T23:59:59Z` : undefined,
        sort_order: urlSortOrder,
        skip,
        limit: urlPageSize,
      });
      setVisits(resp.items);
      setTotalCount(resp.total);
    } catch (err) {
      setVisits([]);
      setTotalCount(0);
      setError(err instanceof Error ? err.message : 'Unable to load visits');
    } finally {
      setIsLoading(false);
    }
  }, [
    urlStatus,
    urlSearch,
    urlEmployeeId,
    urlTerritoryId,
    urlAreaId,
    urlFromDate,
    urlToDate,
    urlSortOrder,
    urlPage,
    urlPageSize,
  ]);

  useEffect(() => {
    loadVisits();
  }, [loadVisits]);

  // Sync search input when URL search changes
  useEffect(() => {
    setSearchInput(urlSearch);
  }, [urlSearch]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateUrlParams({ search: searchInput.trim() }, true);
  };

  const handleClearAllFilters = () => {
    setSearchInput('');
    setSearchParams(new URLSearchParams({ page: '1', page_size: String(urlPageSize) }));
  };

  const totalPages = Math.max(1, Math.ceil(totalCount / urlPageSize));

  // Active filters for chips
  const activeFilters = useMemo(() => {
    const list: Array<{ id: string; label: string; onRemove: () => void }> = [];
    if (urlStatus !== 'ALL') {
      list.push({
        id: 'status',
        label: `Status: ${urlStatus.replace('_', ' ')}`,
        onRemove: () => updateUrlParams({ status: 'ALL' }),
      });
    }
    if (urlSearch) {
      list.push({
        id: 'search',
        label: `Search: "${urlSearch}"`,
        onRemove: () => updateUrlParams({ search: '' }),
      });
    }
    if (urlEmployeeId) {
      const emp = employees.find((e) => e.id === urlEmployeeId);
      list.push({
        id: 'employee',
        label: `Employee: ${emp?.full_name || 'Selected'}`,
        onRemove: () => updateUrlParams({ employee_id: '' }),
      });
    }
    if (urlTerritoryId) {
      const terr = territories.find((t) => t.id === urlTerritoryId);
      list.push({
        id: 'territory',
        label: `Zone: ${terr?.name || 'Selected'}`,
        onRemove: () => updateUrlParams({ territory_id: '', area_id: '' }),
      });
    }
    if (urlAreaId) {
      const area = areas.find((a) => a.id === urlAreaId);
      list.push({
        id: 'area',
        label: `Area: ${area?.name || 'Selected'}`,
        onRemove: () => updateUrlParams({ area_id: '' }),
      });
    }
    if (urlFromDate || urlToDate) {
      const range = `${urlFromDate || 'Any'} → ${urlToDate || 'Any'}`;
      list.push({
        id: 'date',
        label: `Date: ${range}`,
        onRemove: () => updateUrlParams({ from_date: '', to_date: '' }),
      });
    }
    if (urlSortOrder === 'asc') {
      list.push({
        id: 'sort',
        label: 'Sort: Oldest First',
        onRemove: () => updateUrlParams({ sort_order: 'desc' }, false),
      });
    }
    return list;
  }, [
    urlStatus,
    urlSearch,
    urlEmployeeId,
    urlTerritoryId,
    urlAreaId,
    urlFromDate,
    urlToDate,
    urlSortOrder,
    employees,
    territories,
    areas,
    updateUrlParams,
  ]);

  // Handle single visit creation
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
        required_form_id: selectedFormId || null,
      });
      setIsModalOpen(false);
      setSelectedCustomerId('');
      setSelectedEmployeeId('');
      setSelectedFormId('');
      loadVisits();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to schedule visit');
    } finally {
      setIsSaving(false);
    }
  };

  // Handle bulk visit scheduling
  const handleBulkSchedule = async (e: React.FormEvent) => {
    e.preventDefault();
    setBulkFormError(null);
    if (bulkSelectedCustomers.length === 0 || !bulkEmployeeId) {
      setBulkFormError('Please select at least one customer and an employee.');
      return;
    }
    setBulkIsSaving(true);
    try {
      await apiClient.bulkCreateVisits({
        customer_ids: bulkSelectedCustomers,
        employee_id: bulkEmployeeId,
        scheduled_at: new Date(bulkScheduledAt).toISOString(),
        required_form_id: bulkRequiredFormId || null,
      });
      setIsBulkModalOpen(false);
      setBulkSelectedCustomers([]);
      setBulkEmployeeId('');
      setBulkRequiredFormId('');
      loadVisits();
    } catch (err) {
      setBulkFormError(err instanceof Error ? err.message : 'Failed to bulk schedule visits');
    } finally {
      setBulkIsSaving(false);
    }
  };

  const startRecord = (urlPage - 1) * urlPageSize + 1;
  const endRecord = Math.min(urlPage * urlPageSize, totalCount);

  return (
    <div className="space-y-space-5">
      {/* Page Header */}
      <PageHeader
        title="Visit Dispatch & Execution"
        subtitle="Field visit scheduling, execution tracking, geo-verification, and compliance."
        actions={
          isAdmin ? (
            <div className="flex gap-space-2">
              <Button
                variant="outline"
                size="sm"
                icon={Users}
                onClick={() => setIsBulkModalOpen(true)}
              >
                Bulk Schedule
              </Button>
              <Button
                variant="secondary"
                size="sm"
                icon={Plus}
                onClick={() => setIsModalOpen(true)}
              >
                Schedule Visit
              </Button>
            </div>
          ) : undefined
        }
      />

      {error && <ErrorBanner message={error} onRetry={loadVisits} onDismiss={() => setError(null)} />}

      {/* Main Filter & Search Control Panel */}
      <Card variant="flat" className="space-y-space-4">
        {/* Row 1: Search + Status Filter Pills + Advanced Filter Toggle */}
        <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-space-3">
          {/* Working Search Field */}
          <form onSubmit={handleSearchSubmit} className="relative flex-1 max-w-lg">
            <Search className="w-4 h-4 text-on-surface-variant absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search visits, outlets, employees, or IDs..."
              className="w-full h-10 bg-surface border border-outline-variant rounded-lg pl-9 pr-8 text-on-surface font-body-md text-sm focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all"
            />
            {searchInput && (
              <button
                type="button"
                onClick={() => {
                  setSearchInput('');
                  updateUrlParams({ search: '' });
                }}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-on-surface p-0.5"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </form>

          {/* Quick Status Pills */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 lg:pb-0 select-none">
            {STATUS_OPTIONS.map((opt) => {
              const isSelected = urlStatus === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => updateUrlParams({ status: opt.value })}
                  aria-pressed={isSelected}
                  className={`px-3 py-1.5 rounded-lg font-label-md text-xs uppercase tracking-wider transition-all cursor-pointer font-bold whitespace-nowrap ${
                    isSelected
                      ? 'bg-primary text-on-primary shadow-xs active:scale-95'
                      : 'bg-surface border border-outline-variant text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface active:scale-95'
                  }`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>

          {/* Advanced Filter Popover Toggle */}
          <Button
            variant={isAdvancedFiltersOpen ? 'secondary' : 'outline'}
            size="sm"
            icon={Filter}
            onClick={() => setIsAdvancedFiltersOpen(!isAdvancedFiltersOpen)}
          >
            Filters {activeFilters.length > 0 ? `(${activeFilters.length})` : ''}
          </Button>
        </div>

        {/* Collapsible Advanced Filters Drawer */}
        {isAdvancedFiltersOpen && (
          <div className="pt-space-3 border-t border-surface-container-highest grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-space-3">
            {/* Employee Filter */}
            <Select
              label="Assigned Employee"
              value={urlEmployeeId}
              onChange={(e) => updateUrlParams({ employee_id: e.target.value })}
            >
              <option value="">All Employees</option>
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.full_name} {emp.employee_code ? `(${emp.employee_code})` : ''}
                </option>
              ))}
            </Select>

            {/* Zone / Territory Filter */}
            <Select
              label="Zone / Territory"
              value={urlTerritoryId}
              onChange={(e) => updateUrlParams({ territory_id: e.target.value, area_id: '' })}
            >
              <option value="">All Zones</option>
              {territories.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>

            {/* Area Filter */}
            <Select
              label="Area"
              value={urlAreaId}
              onChange={(e) => updateUrlParams({ area_id: e.target.value })}
            >
              <option value="">All Areas</option>
              {areaOptions.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} {!urlTerritoryId ? `(${a.territory_name || 'Zone'})` : ''}
                </option>
              ))}
            </Select>

            {/* Date Range: From */}
            <div className="flex flex-col gap-space-1.5">
              <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold">
                Scheduled From
              </label>
              <input
                type="date"
                value={urlFromDate}
                onChange={(e) => updateUrlParams({ from_date: e.target.value })}
                className="w-full h-10 bg-surface border border-outline-variant rounded-lg px-3 text-on-surface font-body-md text-sm focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all"
              />
            </div>

            {/* Date Range: To */}
            <div className="flex flex-col gap-space-1.5">
              <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold">
                Scheduled To
              </label>
              <input
                type="date"
                value={urlToDate}
                onChange={(e) => updateUrlParams({ to_date: e.target.value })}
                className="w-full h-10 bg-surface border border-outline-variant rounded-lg px-3 text-on-surface font-body-md text-sm focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all"
              />
            </div>
          </div>
        )}

        {/* Active Filter Chips & Clear All */}
        {activeFilters.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 pt-space-2 border-t border-surface-container-highest">
            <span className="font-label-md text-xs text-on-surface-variant font-semibold uppercase tracking-wider">
              Active Filters:
            </span>
            {activeFilters.map((f) => (
              <span
                key={f.id}
                className="inline-flex items-center gap-1.5 bg-surface-container px-2.5 py-1 rounded-full border border-outline-variant text-xs text-on-surface font-medium"
              >
                {f.label}
                <button
                  type="button"
                  onClick={f.onRemove}
                  className="text-on-surface-variant hover:text-error transition-colors cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </span>
            ))}
            <button
              type="button"
              onClick={handleClearAllFilters}
              className="text-xs text-primary hover:underline font-bold ml-2 cursor-pointer inline-flex items-center gap-1"
            >
              <RotateCcw className="w-3 h-3" /> Clear All
            </button>
          </div>
        )}
      </Card>

      {/* Visits Table Card */}
      <div className="bg-surface rounded-xl border border-surface-container-highest shadow-xs overflow-hidden flex flex-col">
        {/* Table Top Status / Sort Info Header */}
        <div className="p-space-4 border-b border-surface-container-highest flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-space-3 bg-surface-container-lowest">
          <div className="flex items-center gap-2">
            <span className="font-headline-sm text-sm font-bold text-on-surface">
              {totalCount > 0
                ? `Showing ${startRecord}–${endRecord} of ${totalCount} visits`
                : 'No visits found'}
            </span>
            {isLoading && (
              <span className="inline-flex items-center text-xs text-primary animate-pulse font-medium">
                Loading...
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            {/* Sort Toggle */}
            <div className="flex items-center gap-1.5 text-xs text-on-surface-variant">
              <span className="font-semibold">Sort:</span>
              <button
                type="button"
                onClick={() =>
                  updateUrlParams(
                    { sort_order: urlSortOrder === 'desc' ? 'asc' : 'desc' },
                    false,
                  )
                }
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-outline-variant bg-surface hover:bg-surface-container text-on-surface font-semibold cursor-pointer"
              >
                <ArrowUpDown className="w-3.5 h-3.5 text-primary" />
                {urlSortOrder === 'desc' ? 'Most Recent First ↓' : 'Oldest First ↑'}
              </button>
            </div>

            {/* Page Size Picker */}
            <div className="flex items-center gap-1.5 text-xs text-on-surface-variant">
              <span className="font-semibold">Per Page:</span>
              <select
                value={urlPageSize}
                onChange={(e) => updateUrlParams({ page_size: e.target.value }, true)}
                className="h-7 px-2 bg-surface border border-outline-variant rounded-md text-xs font-semibold text-on-surface"
              >
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Table Body */}
        {isLoading && visits.length === 0 ? (
          <div className="p-space-8 space-y-4">
            {[1, 2, 3, 4, 5].map((idx) => (
              <div
                key={idx}
                className="h-12 bg-surface-container-low rounded-lg animate-pulse"
              />
            ))}
          </div>
        ) : visits.length === 0 ? (
          <div className="p-space-8">
            <EmptyState
              icon={CalendarCheck}
              title={urlStatus === 'ALL' && !urlSearch ? 'No visits scheduled' : 'No visits match your filters'}
              subtitle={
                urlStatus !== 'ALL' || urlSearch || urlEmployeeId || urlTerritoryId || urlFromDate
                  ? 'Try changing or clearing your search and filter criteria.'
                  : 'Schedule a visit to dispatch a field representative to a customer site.'
              }
              action={
                urlStatus !== 'ALL' || urlSearch || urlEmployeeId || urlTerritoryId || urlAreaId || urlFromDate || urlToDate ? (
                  <Button variant="secondary" size="sm" icon={RotateCcw} onClick={handleClearAllFilters}>
                    Clear All Filters
                  </Button>
                ) : undefined
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-surface-container-highest bg-surface-container-low/50">
                  <th className="px-space-4 py-space-3 font-label-md text-xs text-on-surface uppercase tracking-wider font-bold">
                    Customer / Visit
                  </th>
                  <th className="px-space-4 py-space-3 font-label-md text-xs text-on-surface uppercase tracking-wider font-bold">
                    Assignee
                  </th>
                  <th className="px-space-4 py-space-3 font-label-md text-xs text-on-surface uppercase tracking-wider font-bold">
                    Location
                  </th>
                  <th className="px-space-4 py-space-3 font-label-md text-xs text-on-surface uppercase tracking-wider font-bold">
                    Status
                  </th>
                  <th className="px-space-4 py-space-3 font-label-md text-xs text-on-surface uppercase tracking-wider font-bold">
                    Scheduled Time
                  </th>
                  <th className="px-space-4 py-space-3 font-label-md text-xs text-on-surface uppercase tracking-wider font-bold">
                    Check-In
                  </th>
                  <th className="px-space-4 py-space-3 font-label-md text-xs text-on-surface uppercase tracking-wider font-bold text-right">
                    Action
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-container-highest">
                {visits.map((visit) => {
                  const areaContext = [visit.territory_name, visit.area_name]
                    .filter(Boolean)
                    .join(' / ');
                  return (
                    <tr
                      key={visit.id}
                      onClick={() => navigate(`/visits/${visit.id}`)}
                      className="hover:bg-surface-container-low/70 transition-colors cursor-pointer"
                    >
                      {/* Customer / Visit */}
                      <td className="px-space-4 py-space-3.5">
                        <p className="font-headline-sm text-sm text-primary font-bold hover:underline">
                          {visit.customer_name || `Customer #${visit.customer_id.substring(0, 8)}`}
                        </p>
                        <p className="font-caption text-xs text-on-surface-variant font-mono">
                          ID: {visit.id.substring(0, 8)}...
                        </p>
                      </td>

                      {/* Assignee */}
                      <td className="px-space-4 py-space-3.5">
                        <div className="flex items-center gap-1.5">
                          <UserCheck className="w-3.5 h-3.5 text-on-surface-variant shrink-0" />
                          <span className="font-body-md text-sm text-on-surface font-medium">
                            {visit.employee_name || '—'}
                          </span>
                        </div>
                      </td>

                      {/* Location */}
                      <td className="px-space-4 py-space-3.5">
                        <div className="flex items-center gap-1.5 text-xs text-on-surface">
                          <MapPin className="w-3.5 h-3.5 text-outline shrink-0" />
                          <span>{areaContext || '—'}</span>
                        </div>
                      </td>

                      {/* Status */}
                      <td className="px-space-4 py-space-3.5">
                        <StatusBadge status={visit.status} size="sm" />
                      </td>

                      {/* Scheduled Time */}
                      <td className="px-space-4 py-space-3.5">
                        <div className="font-caption text-xs text-on-surface-variant flex items-center gap-1.5 font-medium">
                          <Calendar className="w-3.5 h-3.5 text-outline shrink-0" />
                          <span>{new Date(visit.scheduled_at).toLocaleString()}</span>
                        </div>
                      </td>

                      {/* Check-In */}
                      <td className="px-space-4 py-space-3.5">
                        <div className="font-caption text-xs text-on-surface-variant flex items-center gap-1.5">
                          <Clock className="w-3.5 h-3.5 text-outline shrink-0" />
                          <span>
                            {visit.check_in_at
                              ? new Date(visit.check_in_at).toLocaleString()
                              : '—'}
                          </span>
                        </div>
                      </td>

                      {/* Action */}
                      <td className="px-space-4 py-space-3.5 text-right">
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
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Server-Side Pagination Bar */}
        {totalCount > 0 && (
          <div className="p-space-4 border-t border-surface-container-highest flex flex-col sm:flex-row items-center justify-between gap-space-3 bg-surface">
            <span className="font-caption text-xs text-on-surface-variant">
              Page <span className="font-bold text-on-surface">{urlPage}</span> of{' '}
              <span className="font-bold text-on-surface">{totalPages}</span> ({totalCount} total visits)
            </span>

            {/* Pagination Controls */}
            <div className="flex items-center gap-1 select-none">
              <Button
                variant="outline"
                size="sm"
                icon={ChevronLeft}
                disabled={urlPage <= 1 || isLoading}
                onClick={() => updateUrlParams({ page: urlPage - 1 }, false)}
              >
                Previous
              </Button>

              {/* Numbered Page Buttons */}
              <div className="hidden sm:flex items-center gap-1 mx-1">
                {Array.from({ length: totalPages }, (_, i) => i + 1)
                  .filter((p) => p === 1 || p === totalPages || Math.abs(p - urlPage) <= 2)
                  .map((p, idx, arr) => {
                    const prevP = arr[idx - 1];
                    const hasGap = prevP && p - prevP > 1;
                    return (
                      <React.Fragment key={p}>
                        {hasGap && <span className="px-1 text-xs text-on-surface-variant">...</span>}
                        <button
                          type="button"
                          onClick={() => updateUrlParams({ page: p }, false)}
                          className={`w-8 h-8 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                            urlPage === p
                              ? 'bg-primary text-on-primary shadow-xs'
                              : 'border border-outline-variant bg-surface text-on-surface hover:bg-surface-container'
                          }`}
                        >
                          {p}
                        </button>
                      </React.Fragment>
                    );
                  })}
              </div>

              <Button
                variant="outline"
                size="sm"
                disabled={urlPage >= totalPages || isLoading}
                onClick={() => updateUrlParams({ page: urlPage + 1 }, false)}
              >
                Next <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Single Visit Scheduling Modal */}
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
                {emp.full_name} {emp.employee_code ? `(${emp.employee_code})` : ''}
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

          <Select
            id="visit-required-form"
            label="Required Form"
            value={selectedFormId}
            onChange={(e) => setSelectedFormId(e.target.value)}
            helperText="The form the employee must fill during this visit - leave unset if none is required."
          >
            <option value="">No form required</option>
            {publishedForms.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </Select>

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

      {/* Bulk Scheduling Modal */}
      <Modal
        isOpen={isBulkModalOpen}
        onClose={() => setIsBulkModalOpen(false)}
        title="Bulk Schedule Visits"
        subtitle="Schedule visits for multiple customers with the same employee."
      >
        <form onSubmit={handleBulkSchedule} className="space-y-space-4">
          {bulkFormError && <ErrorBanner message={bulkFormError} onDismiss={() => setBulkFormError(null)} />}

          <div>
            <label className="block font-label-md text-sm text-on-surface-variant mb-space-2">
              Select Customers
            </label>
            <div className="max-h-48 overflow-y-auto border border-outline-variant rounded-lg p-space-2 space-y-space-1">
              {customers.map((customer) => (
                <label
                  key={customer.id}
                  className="flex items-center gap-space-2 cursor-pointer p-space-1 rounded hover:bg-surface-container-low"
                >
                  <input
                    type="checkbox"
                    checked={bulkSelectedCustomers.includes(customer.id)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setBulkSelectedCustomers([...bulkSelectedCustomers, customer.id]);
                      } else {
                        setBulkSelectedCustomers(bulkSelectedCustomers.filter((id) => id !== customer.id));
                      }
                    }}
                    className="rounded border-outline-variant"
                  />
                  <span className="font-body-md text-sm">{customer.name}</span>
                </label>
              ))}
              {customers.length === 0 && (
                <p className="font-body-md text-sm text-on-surface-variant p-space-2">No customers available.</p>
              )}
            </div>
          </div>

          <Select
            id="bulk-employee"
            label="Assign Employee"
            value={bulkEmployeeId}
            onChange={(e) => setBulkEmployeeId(e.target.value)}
          >
            <option value="">-- Select Employee --</option>
            {employees.map((emp) => (
              <option key={emp.id} value={emp.id}>
                {emp.full_name}
              </option>
            ))}
          </Select>

          <Input
            label="Scheduled Date & Time"
            type="datetime-local"
            value={bulkScheduledAt}
            onChange={(e) => setBulkScheduledAt(e.target.value)}
          />

          <Select
            id="bulk-required-form"
            label="Required Form"
            value={bulkRequiredFormId}
            onChange={(e) => setBulkRequiredFormId(e.target.value)}
            helperText="Applied to every visit created in this batch - leave unset if none is required."
          >
            <option value="">No form required</option>
            {publishedForms.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </Select>

          <div className="pt-space-4 flex justify-end gap-space-3 border-t border-surface-container-highest mt-space-6">
            <Button type="button" variant="ghost" size="sm" onClick={() => setIsBulkModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="secondary" size="sm" isLoading={bulkIsSaving}>
              Bulk Schedule
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
