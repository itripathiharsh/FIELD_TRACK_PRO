import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Plus,
  Edit3,
  CalendarClock,
  Trash2,
  Building2,
  MapPin,
  AlertCircle,
  CheckCircle2,
  Info,
  Search,
  X,
  FileText,
  TrendingUp,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Zap,
} from 'lucide-react';
import { apiClient, ApiError } from '../api/client';
import {
  Customer,
  EmployeeMonthlyAnalytics,
  MonthlyVisitPlan,
  PlannedVisit,
  Priority,
  VisitType,
} from '../types';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { Select } from '../components/ui/Select';
import { Textarea } from '../components/ui/Textarea';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { StatusBadge } from '../components/ui/StatusBadge';

const MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

const WEEKDAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// Helper to format date to YYYY-MM-DD
function formatDateStr(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

// Helper to parse YYYY-MM-DD into a human-readable display string
function formatDisplayDate(dateStr: string): string {
  try {
    const [y, m, d] = dateStr.split('-').map(Number);
    const dateObj = new Date(y, m - 1, d);
    return dateObj.toLocaleDateString('en-IN', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

export const MonthlyVisitPlanningPage: React.FC = () => {
  const today = useMemo(() => new Date(), []);
  const todayYear = today.getFullYear();
  const todayMonth = today.getMonth() + 1;
  const todayDay = today.getDate();
  const todayStr = useMemo(
    () => formatDateStr(todayYear, todayMonth, todayDay),
    [todayYear, todayMonth, todayDay],
  );

  // Month navigation state
  const [selectedYear, setSelectedYear] = useState<number>(todayYear);
  const [selectedMonth, setSelectedMonth] = useState<number>(todayMonth);
  const [selectedDateStr, setSelectedDateStr] = useState<string>(todayStr);

  // Plan data state
  const [plan, setPlan] = useState<MonthlyVisitPlan | null>(null);
  const [analytics, setAnalytics] = useState<EmployeeMonthlyAnalytics | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Reference customers state for selection dropdown
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [isCustomersLoading, setIsCustomersLoading] = useState<boolean>(false);
  const [customerSearchQuery, setCustomerSearchQuery] = useState<string>('');

  // Modal states
  const [isAddModalOpen, setIsAddModalOpen] = useState<boolean>(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState<boolean>(false);
  const [isRescheduleModalOpen, setIsRescheduleModalOpen] = useState<boolean>(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState<boolean>(false);
  const [activeVisit, setActiveVisit] = useState<PlannedVisit | null>(null);

  // Form states for Add/Edit/Reschedule
  const [formCustomerId, setFormCustomerId] = useState<string>('');
  const [formPlannedDate, setFormPlannedDate] = useState<string>(todayStr);
  const [formVisitType, setFormVisitType] = useState<VisitType>('PLANNED');
  const [formPriority, setFormPriority] = useState<Priority>('MEDIUM');
  const [formNotes, setFormNotes] = useState<string>('');
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Reschedule form state
  const [rescheduleDate, setRescheduleDate] = useState<string>(todayStr);

  // 1. Fetch Monthly Plan & Analytics from API
  const loadMonthlyPlan = useCallback(async (year: number, month: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const [data, anData] = await Promise.all([
        apiClient.getMyMonthlyPlan({ year, month }),
        apiClient.getMyMonthAnalytics({ year, month }).catch(() => null),
      ]);
      setPlan(data);
      setAnalytics(anData);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(err.message || 'Failed to load monthly visit plan');
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to load monthly visit plan');
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMonthlyPlan(selectedYear, selectedMonth);
  }, [loadMonthlyPlan, selectedYear, selectedMonth]);

  // 2. Fetch customers for appointment scheduling
  useEffect(() => {
    setIsCustomersLoading(true);
    apiClient
      .getCustomers({ limit: 3000 })
      .then((data) => setCustomers(data))
      .catch(() => setCustomers([]))
      .finally(() => setIsCustomersLoading(false));
  }, []);

  // Filtered customers for dropdown search
  const filteredCustomers = useMemo(() => {
    if (!customerSearchQuery.trim()) return customers;
    const q = customerSearchQuery.toLowerCase();
    return customers.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        (c.outlet_code && c.outlet_code.toLowerCase().includes(q)) ||
        (c.address && c.address.toLowerCase().includes(q)),
    );
  }, [customers, customerSearchQuery]);

  // Group planned visits by date string
  const visitsByDate = useMemo(() => {
    const map: Record<string, PlannedVisit[]> = {};
    if (!plan || !plan.planned_visits) return map;
    for (const v of plan.planned_visits) {
      if (!map[v.planned_date]) {
        map[v.planned_date] = [];
      }
      map[v.planned_date].push(v);
    }
    return map;
  }, [plan]);

  // Calendar calculations
  const daysInMonth = useMemo(() => {
    return new Date(selectedYear, selectedMonth, 0).getDate();
  }, [selectedYear, selectedMonth]);

  const firstDayWeekday = useMemo(() => {
    return new Date(selectedYear, selectedMonth - 1, 1).getDay();
  }, [selectedYear, selectedMonth]);

  // Navigation handlers
  const handlePrevMonth = () => {
    if (selectedMonth === 1) {
      setSelectedYear((y) => y - 1);
      setSelectedMonth(12);
      setSelectedDateStr(formatDateStr(selectedYear - 1, 12, 1));
    } else {
      setSelectedMonth((m) => m - 1);
      setSelectedDateStr(formatDateStr(selectedYear, selectedMonth - 1, 1));
    }
  };

  const handleNextMonth = () => {
    if (selectedMonth === 12) {
      setSelectedYear((y) => y + 1);
      setSelectedMonth(1);
      setSelectedDateStr(formatDateStr(selectedYear + 1, 1, 1));
    } else {
      setSelectedMonth((m) => m + 1);
      setSelectedDateStr(formatDateStr(selectedYear, selectedMonth + 1, 1));
    }
  };

  const handleToday = () => {
    setSelectedYear(todayYear);
    setSelectedMonth(todayMonth);
    setSelectedDateStr(todayStr);
  };

  // Open Add Visit Modal
  const handleOpenAddModal = (dateStr?: string) => {
    const targetDate = dateStr && dateStr >= todayStr ? dateStr : todayStr;
    setFormPlannedDate(targetDate);
    setFormCustomerId('');
    setFormVisitType('PLANNED');
    setFormPriority('MEDIUM');
    setFormNotes('');
    setFormError(null);
    setCustomerSearchQuery('');
    setIsAddModalOpen(true);
  };

  // Submit Add Visit
  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formCustomerId) {
      setFormError('Please select a customer / outlet');
      return;
    }
    if (!formPlannedDate) {
      setFormError('Please select a planned date');
      return;
    }
    if (formPlannedDate < todayStr) {
      setFormError('Cannot plan visits for past dates');
      return;
    }

    setIsSubmitting(true);
    setFormError(null);
    try {
      await apiClient.createPlannedVisit({
        customer_id: formCustomerId,
        planned_date: formPlannedDate,
        visit_type: formVisitType,
        priority: formPriority,
        notes: formNotes.trim() ? formNotes.trim() : null,
      });

      setIsAddModalOpen(false);
      setSelectedDateStr(formPlannedDate);

      // If planned for another month, navigate to that month
      const [pYear, pMonth] = formPlannedDate.split('-').map(Number);
      if (pYear !== selectedYear || pMonth !== selectedMonth) {
        setSelectedYear(pYear);
        setSelectedMonth(pMonth);
      } else {
        await loadMonthlyPlan(selectedYear, selectedMonth);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setFormError(err.message || 'Failed to create planned visit');
      } else if (err instanceof Error) {
        setFormError(err.message);
      } else {
        setFormError('Failed to create planned visit');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Open Edit Visit Modal
  const handleOpenEditModal = (visit: PlannedVisit) => {
    setActiveVisit(visit);
    setFormVisitType(visit.visit_type);
    setFormPriority(visit.priority);
    setFormNotes(visit.notes || '');
    setFormError(null);
    setIsEditModalOpen(true);
  };

  // Submit Edit Visit
  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeVisit) return;

    setIsSubmitting(true);
    setFormError(null);
    try {
      await apiClient.updatePlannedVisit(activeVisit.id, {
        visit_type: formVisitType,
        priority: formPriority,
        notes: formNotes.trim() ? formNotes.trim() : null,
      });

      setIsEditModalOpen(false);
      setActiveVisit(null);
      await loadMonthlyPlan(selectedYear, selectedMonth);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setFormError(err.message || 'Failed to update planned visit');
      } else if (err instanceof Error) {
        setFormError(err.message);
      } else {
        setFormError('Failed to update planned visit');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Open Reschedule Modal
  const handleOpenRescheduleModal = (visit: PlannedVisit) => {
    setActiveVisit(visit);
    setRescheduleDate(visit.planned_date >= todayStr ? visit.planned_date : todayStr);
    setFormError(null);
    setIsRescheduleModalOpen(true);
  };

  // Submit Reschedule
  const handleRescheduleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeVisit) return;
    if (!rescheduleDate) {
      setFormError('Please select a new date');
      return;
    }
    if (rescheduleDate < todayStr) {
      setFormError('Cannot reschedule visits to past dates');
      return;
    }

    setIsSubmitting(true);
    setFormError(null);
    try {
      await apiClient.reschedulePlannedVisit(activeVisit.id, rescheduleDate);

      setIsRescheduleModalOpen(false);
      setActiveVisit(null);
      setSelectedDateStr(rescheduleDate);

      // Check if cross-month reschedule
      const [newY, newM] = rescheduleDate.split('-').map(Number);
      if (newY !== selectedYear || newM !== selectedMonth) {
        setSelectedYear(newY);
        setSelectedMonth(newM);
      } else {
        await loadMonthlyPlan(selectedYear, selectedMonth);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setFormError(err.message || 'Failed to reschedule visit');
      } else if (err instanceof Error) {
        setFormError(err.message);
      } else {
        setFormError('Failed to reschedule visit');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Open Delete Modal
  const handleOpenDeleteModal = (visit: PlannedVisit) => {
    setActiveVisit(visit);
    setFormError(null);
    setIsDeleteModalOpen(true);
  };

  // Submit Delete
  const handleDeleteSubmit = async () => {
    if (!activeVisit) return;
    setIsSubmitting(true);
    setFormError(null);
    try {
      await apiClient.deletePlannedVisit(activeVisit.id);
      setIsDeleteModalOpen(false);
      setActiveVisit(null);
      await loadMonthlyPlan(selectedYear, selectedMonth);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setFormError(err.message || 'Failed to delete planned visit');
      } else if (err instanceof Error) {
        setFormError(err.message);
      } else {
        setFormError('Failed to delete planned visit');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Visits scheduled for currently selected day
  const selectedDayVisits = useMemo(() => {
    return visitsByDate[selectedDateStr] || [];
  }, [visitsByDate, selectedDateStr]);

  const isSelectedDateInPast = selectedDateStr < todayStr;

  return (
    <div className="space-y-space-5">
      {/* Page Header */}
      <PageHeader
        title="Monthly Visit Planning"
        subtitle="Organize your upcoming customer coverage, schedule multiple visits per day, and adjust your itinerary anytime."
        actions={
          <div className="flex items-center gap-space-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleToday}
            >
              Today
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon={Plus}
              onClick={() => handleOpenAddModal(selectedDateStr)}
            >
              Plan Visit
            </Button>
          </div>
        }
      />

      {error && (
        <ErrorBanner
          message={error}
          onRetry={() => loadMonthlyPlan(selectedYear, selectedMonth)}
          onDismiss={() => setError(null)}
        />
      )}

      {/* Month Navigation & Summary Card */}
      <Card variant="flat" className="p-space-4 sm:p-space-5 bg-surface border border-surface-container-highest">
        <div className="flex flex-col md:flex-row items-center justify-between gap-space-4">
          {/* Navigation Controls */}
          <div className="flex items-center gap-space-2">
            <Button
              variant="outline"
              size="sm"
              icon={ChevronLeft}
              onClick={handlePrevMonth}
              aria-label="Previous month"
            />
            <div className="min-w-[200px] text-center">
              <h2 className="font-headline-md text-headline-md text-primary font-bold tracking-tight">
                {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
              </h2>
            </div>
            <Button
              variant="outline"
              size="sm"
              icon={ChevronRight}
              onClick={handleNextMonth}
              aria-label="Next month"
            />
          </div>

          {/* Monthly KPI Summary Badges */}
          <div className="flex flex-wrap items-center justify-center md:justify-end gap-space-3 w-full md:w-auto">
            <div className="px-space-3 py-space-1.5 rounded-xl bg-surface-container-low border border-surface-container-highest flex items-center gap-space-2">
              <CalendarDays className="w-4 h-4 text-primary" />
              <span className="font-caption text-xs text-on-surface-variant">
                Total Planned:
              </span>
              <span className="font-label-md text-sm text-primary font-bold">
                {analytics ? analytics.total_planned : (plan ? plan.total_planned_visits : 0)}
              </span>
            </div>

            <div className="px-space-3 py-space-1.5 rounded-xl bg-surface-container-low border border-surface-container-highest flex items-center gap-space-2">
              <CheckCircle2 className="w-4 h-4 text-secondary-container" />
              <span className="font-caption text-xs text-on-surface-variant">
                Working Days:
              </span>
              <span className="font-label-md text-sm text-secondary font-bold">
                {plan ? plan.active_days_count : 0}
              </span>
            </div>

            <div className="px-space-3 py-space-1.5 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center gap-space-2 text-emerald-800">
              <CheckCircle className="w-4 h-4 text-emerald-600" />
              <span className="font-caption text-xs">
                Completed:
              </span>
              <span className="font-label-md text-sm font-bold">
                {analytics ? analytics.completed : 0}
              </span>
            </div>

            <div className="px-space-3 py-space-1.5 rounded-xl bg-rose-50 border border-rose-200 flex items-center gap-space-2 text-rose-800">
              <XCircle className="w-4 h-4 text-rose-600" />
              <span className="font-caption text-xs">
                Missed:
              </span>
              <span className="font-label-md text-sm font-bold">
                {analytics ? analytics.missed : 0}
              </span>
            </div>

            <div className="px-space-3 py-space-1.5 rounded-xl bg-amber-50 border border-amber-200 flex items-center gap-space-2 text-amber-900">
              <Zap className="w-4 h-4 text-amber-600" />
              <span className="font-caption text-xs">
                Extra:
              </span>
              <span className="font-label-md text-sm font-bold">
                {analytics ? analytics.extra_unplanned : 0}
              </span>
            </div>

            <div className="px-space-3 py-space-1.5 rounded-xl bg-surface-container-low border border-surface-container-highest flex items-center gap-space-2">
              <TrendingUp className="w-4 h-4 text-primary" />
              <span className="font-caption text-xs text-on-surface-variant">
                Completion:
              </span>
              <span className="font-label-md text-sm text-primary font-bold">
                {analytics && analytics.completion_rate !== null ? `${analytics.completion_rate}%` : '—'}
              </span>
            </div>

            <div className="px-space-3 py-space-1.5 rounded-xl bg-surface-container-low border border-surface-container-highest flex items-center gap-space-2">
              <span className="font-caption text-xs text-on-surface-variant">
                Plan Status:
              </span>
              <StatusBadge status={plan?.status || 'ACTIVE'} size="sm" />
            </div>
          </div>
        </div>

        {/* Secondary Analytics Strip: Averages & Schedule Status */}
        {analytics && (
          <div className="mt-space-3 pt-space-3 border-t border-surface-container-highest flex flex-wrap items-center justify-between gap-space-2 text-xs text-on-surface-variant">
            <div className="flex flex-wrap items-center gap-space-4">
              <span>
                Active Planned Days: <strong className="text-on-surface">{analytics.active_planned_days}</strong>
              </span>
              <span className="text-outline/40">|</span>
              <span>
                Avg Planned / Active Day: <strong className="text-on-surface">{analytics.avg_planned_per_active_day ?? '—'}</strong>
              </span>
              <span className="text-outline/40">|</span>
              <span>
                Avg Completed / Execution Day: <strong className="text-on-surface">{analytics.avg_completed_per_execution_day ?? '—'}</strong>
              </span>
            </div>

            {analytics.behind_schedule ? (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-amber-100 text-amber-900 font-semibold text-xs border border-amber-300 animate-pulse">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-700" />
                <span>Behind Schedule</span>
              </div>
            ) : analytics.total_planned > 0 && analytics.completed >= analytics.total_planned ? (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-emerald-100 text-emerald-900 font-semibold text-xs border border-emerald-300">
                <CheckCircle className="w-3.5 h-3.5 text-emerald-700" />
                <span>Target Achieved</span>
              </div>
            ) : null}
          </div>
        )}
      </Card>

      {/* Informational Warning if Missed Visits Exist in Current Month */}
      {analytics && analytics.missed > 0 && (
        <div className="p-3.5 px-4 rounded-2xl bg-rose-50/80 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900/50 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs text-rose-900 dark:text-rose-200 shadow-2xs animate-in fade-in duration-200">
          <div className="flex items-center gap-2.5 min-w-0">
            <AlertTriangle className="w-4 h-4 text-rose-600 dark:text-rose-400 shrink-0" />
            <span>
              <strong>Planning Warning:</strong> You have {analytics.missed} missed planned visit{analytics.missed > 1 ? 's' : ''} this month. Review and reschedule them to maintain target customer coverage.
            </span>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              const missedVisit = plan?.planned_visits.find((v) => v.status === 'MISSED');
              if (missedVisit) {
                setSelectedDateStr(missedVisit.planned_date);
              }
            }}
            className="shrink-0 text-xs border-rose-300 text-rose-800 hover:bg-rose-100 dark:border-rose-800 dark:text-rose-200"
          >
            Review Missed
          </Button>
        </div>
      )}

      {/* Main Content Layout: Calendar Grid + Day Details Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-5">
        {/* Left Column (Desktop 7 cols / Mobile full): Monthly Calendar Grid */}
        <div className="lg:col-span-7 xl:col-span-8">
          <Card className="p-space-4 sm:p-space-5 overflow-hidden">
            <div className="flex items-center justify-between pb-space-4 border-b border-surface-container-highest mb-space-3">
              <div className="flex items-center gap-space-2">
                <CalendarDays className="w-5 h-5 text-primary" />
                <h3 className="font-headline-sm text-headline-sm text-primary font-bold">
                  Schedule Overview
                </h3>
              </div>
              <span className="font-caption text-xs text-on-surface-variant">
                Click any day to view or add visits
              </span>
            </div>

            {/* Weekday Header */}
            <div className="grid grid-cols-7 gap-1 sm:gap-2 mb-space-2 text-center">
              {WEEKDAY_NAMES.map((name, idx) => (
                <div
                  key={name}
                  className={`py-1 font-label-md text-xs uppercase tracking-wider font-bold ${
                    idx === 0 || idx === 6 ? 'text-on-surface-variant/70' : 'text-primary'
                  }`}
                >
                  {name}
                </div>
              ))}
            </div>

            {/* Month Day Cells */}
            {isLoading ? (
              <div className="grid grid-cols-7 gap-1 sm:gap-2 py-space-8 text-center">
                {Array.from({ length: 35 }).map((_, i) => (
                  <div
                    key={i}
                    className="h-20 sm:h-24 rounded-xl bg-surface-container-low/60 animate-pulse border border-surface-container-highest"
                  />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-7 gap-1 sm:gap-2">
                {/* Empty cells for leading days of previous month */}
                {Array.from({ length: firstDayWeekday }).map((_, i) => (
                  <div
                    key={`empty-${i}`}
                    className="h-20 sm:h-24 rounded-xl bg-surface-container-low/20 border border-transparent"
                  />
                ))}

                {/* Day cells for current month */}
                {Array.from({ length: daysInMonth }).map((_, idx) => {
                  const dayNum = idx + 1;
                  const dateStr = formatDateStr(selectedYear, selectedMonth, dayNum);
                  const dayVisits = visitsByDate[dateStr] || [];
                  const visitCount = dayVisits.length;
                  const isToday = dateStr === todayStr;
                  const isSelected = dateStr === selectedDateStr;
                  const isPast = dateStr < todayStr;

                  return (
                    <button
                      key={dateStr}
                      type="button"
                      onClick={() => setSelectedDateStr(dateStr)}
                      className={`h-20 sm:h-24 p-1.5 sm:p-2 rounded-xl text-left flex flex-col justify-between transition-all cursor-pointer border ${
                        isSelected
                          ? 'border-primary ring-2 ring-primary/20 bg-primary-tint/30 shadow-xs'
                          : isToday
                          ? 'border-secondary-container/80 bg-surface shadow-xs'
                          : 'border-surface-container-highest bg-surface hover:bg-surface-container-low hover:border-outline-variant'
                      } ${isPast ? 'opacity-75' : ''}`}
                    >
                      <div className="flex items-center justify-between w-full">
                        <span
                          className={`w-6 h-6 rounded-full flex items-center justify-center font-label-md text-xs font-bold ${
                            isToday
                              ? 'bg-secondary-container text-primary font-black shadow-xs'
                              : isSelected
                              ? 'bg-primary text-on-primary font-bold'
                              : 'text-on-surface'
                          }`}
                        >
                          {dayNum}
                        </span>

                        {visitCount > 0 && (
                          <span className="px-1.5 py-0.5 rounded-md font-label-md text-[10px] font-bold bg-primary-container text-on-primary-container">
                            {visitCount}
                          </span>
                        )}
                      </div>

                      {/* Mini Preview Chips */}
                      <div className="w-full space-y-0.5 overflow-hidden">
                        {visitCount === 0 ? (
                          <span className="hidden sm:block font-caption text-[10px] text-on-surface-variant/50 truncate">
                            No visits
                          </span>
                        ) : (
                          <>
                            {dayVisits.slice(0, 2).map((v) => (
                              <div
                                key={v.id}
                                className={`px-1 py-0.5 rounded text-[10px] truncate font-body-md leading-tight ${
                                  v.priority === 'HIGH'
                                    ? 'bg-amber-100 text-amber-900 border border-amber-300'
                                    : v.priority === 'LOW'
                                    ? 'bg-slate-100 text-slate-800'
                                    : 'bg-blue-50 text-blue-900'
                                }`}
                                title={`${v.customer_name || 'Outlet'} (${v.priority})`}
                              >
                                {v.customer_name || 'Outlet'}
                              </div>
                            ))}
                            {visitCount > 2 && (
                              <span className="font-caption text-[9px] text-primary font-bold">
                                +{visitCount - 2} more
                              </span>
                            )}
                          </>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </Card>
        </div>

        {/* Right Column (Desktop 5 cols / Mobile full): Day Details Inspector */}
        <div className="lg:col-span-5 xl:col-span-4 space-y-space-4">
          <Card className="p-space-5">
            <CardHeader className="border-b border-surface-container-highest pb-space-3 mb-space-4 flex items-center justify-between gap-space-4 w-full">
              <div className="min-w-0 flex-1 pr-space-2">
                <span className="font-caption text-xs text-on-surface-variant uppercase tracking-wider block font-semibold">
                  Selected Day
                </span>
                <CardTitle className="text-base sm:text-lg truncate">
                  {formatDisplayDate(selectedDateStr)}
                </CardTitle>
              </div>

              {!isSelectedDateInPast && (
                <Button
                  variant="secondary"
                  size="sm"
                  icon={Plus}
                  className="shrink-0 whitespace-nowrap shadow-2xs"
                  onClick={() => handleOpenAddModal(selectedDateStr)}
                >
                  Add Visit
                </Button>
              )}
            </CardHeader>

            {/* List of Visits for the selected day */}
            {selectedDayVisits.length > 0 ? (
              <div className="space-y-space-3">
                <div className="flex items-center justify-between font-caption text-xs text-on-surface-variant pb-space-1">
                  <span>{selectedDayVisits.length} Planned Visit{selectedDayVisits.length > 1 ? 's' : ''}</span>
                  {isSelectedDateInPast && (
                    <span className="text-on-surface-variant italic">(Past date - read only)</span>
                  )}
                </div>

                {selectedDayVisits.map((v) => (
                  <div
                    key={v.id}
                    className={`p-space-3.5 rounded-xl border transition-all space-y-space-2.5 ${
                      v.status === 'MISSED'
                        ? 'border-rose-300 bg-rose-50/25 dark:border-rose-800/40'
                        : v.status === 'CANCELLED'
                        ? 'border-surface-container bg-surface-container-low/30 opacity-60'
                        : 'border-surface-container-highest bg-surface-container-low/40 hover:bg-surface-container-low'
                    }`}
                  >
                    {/* Header: Name + Priority + Status */}
                    <div className="flex items-start justify-between gap-space-2">
                      <div className="min-w-0">
                        <div className="flex items-center gap-space-1.5">
                          <Building2 className="w-4 h-4 text-primary shrink-0" />
                          <h4 className="font-headline-sm text-sm text-primary font-bold truncate">
                            {v.customer_name || 'Customer Outlet'}
                          </h4>
                        </div>
                        {v.customer_outlet_code && (
                          <span className="font-caption text-[11px] text-on-surface-variant ml-5 block">
                            Code: {v.customer_outlet_code}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-1 shrink-0">
                        {/* Status Badge (Phase 2E) */}
                        <span
                          className={`px-2 py-0.5 rounded-full font-label-md text-[10px] font-bold uppercase tracking-wider border ${
                            v.status === 'MISSED'
                              ? 'bg-rose-100 text-rose-800 border-rose-300 dark:bg-rose-950 dark:text-rose-300'
                              : v.status === 'CANCELLED'
                              ? 'bg-slate-200 text-slate-700 border-slate-300 dark:bg-slate-800 dark:text-slate-400 line-through'
                              : v.status === 'COMPLETED'
                              ? 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-950 dark:text-emerald-300'
                              : 'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-950 dark:text-blue-300'
                          }`}
                        >
                          {v.status}
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded-full font-label-md text-[10px] font-bold uppercase tracking-wider ${
                            v.priority === 'HIGH'
                              ? 'bg-amber-100 text-amber-900 border border-amber-300'
                              : v.priority === 'LOW'
                              ? 'bg-slate-100 text-slate-700 border border-slate-300'
                              : 'bg-blue-100 text-blue-900 border border-blue-300'
                          }`}
                        >
                          {v.priority}
                        </span>
                        <span className="px-2 py-0.5 rounded-full font-label-md text-[10px] font-semibold bg-surface-container text-on-surface-variant border border-outline-variant uppercase">
                          {v.visit_type === 'AD_HOC' ? 'Ad-Hoc' : 'Planned'}
                        </span>
                      </div>
                    </div>

                    {/* Address & Territory */}
                    {v.customer_address && (
                      <div className="flex items-start gap-space-1.5 text-xs text-on-surface-variant font-body-md pl-0.5">
                        <MapPin className="w-3.5 h-3.5 text-on-surface-variant/70 shrink-0 mt-0.5" />
                        <span className="truncate">{v.customer_address}</span>
                      </div>
                    )}

                    {/* Notes if present */}
                    {v.notes && (
                      <div className="px-space-2.5 py-space-1.5 rounded-lg bg-surface border border-surface-container-highest text-xs text-on-surface font-body-md flex items-start gap-space-1.5">
                        <FileText className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" />
                        <span className="italic">{v.notes}</span>
                      </div>
                    )}

                    {/* Actions: Edit, Reschedule, Delete (only for today or future dates, not cancelled) */}
                    {!isSelectedDateInPast && v.status !== 'CANCELLED' && (
                      <div className="flex items-center justify-end gap-space-1.5 pt-space-2 border-t border-surface-container-highest/60">
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={Edit3}
                          onClick={() => handleOpenEditModal(v)}
                        >
                          Edit
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={CalendarClock}
                          onClick={() => handleOpenRescheduleModal(v)}
                        >
                          Reschedule
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={Trash2}
                          className="text-error hover:bg-error-container/30 hover:text-error"
                          onClick={() => handleOpenDeleteModal(v)}
                        >
                          Cancel
                        </Button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              /* Informational Zero-Visits State */
              <div className="py-space-8 text-center space-y-space-3 px-space-2">
                <div className="w-12 h-12 rounded-2xl bg-surface-container-low border border-surface-container-highest flex items-center justify-center mx-auto text-primary">
                  <CalendarDays className="w-6 h-6" />
                </div>
                <div className="space-y-space-1">
                  <h4 className="font-headline-sm text-sm text-primary font-bold">
                    {selectedDateStr === todayStr ? 'No visits planned for today.' : 'No visits planned for this date'}
                  </h4>
                  <p className="font-caption text-xs text-on-surface-variant max-w-xs mx-auto leading-relaxed">
                    Zero planned visits is completely valid. You can leave {selectedDateStr === todayStr ? 'today' : 'this day'} open for desk work or add customer visits whenever convenient.
                  </p>
                </div>

                {!isSelectedDateInPast && (
                  <Button
                    variant="outline"
                    size="sm"
                    icon={Plus}
                    onClick={() => handleOpenAddModal(selectedDateStr)}
                  >
                    Plan a Visit for this Day
                  </Button>
                )}
              </div>
            )}
          </Card>

          {/* Monthly Planning Tips Card */}
          <Card variant="flat" className="p-space-4 bg-primary-tint/20 border border-primary-fixed-dim space-y-space-2">
            <div className="flex items-center gap-space-2 text-primary font-bold text-xs uppercase font-label-md">
              <Info className="w-4 h-4" />
              Flexible Planning
            </div>
            <p className="font-caption text-xs text-on-surface-variant leading-relaxed">
              You can adjust your plan at any time during the month. Multiple visits can be scheduled on the same day, and future dates can be rescheduled with a single click.
            </p>
          </Card>
        </div>
      </div>

      {/* ================= MODALS ================= */}

      {/* 1. Add Planned Visit Modal */}
      <Modal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title="Schedule Planned Visit"
        subtitle="Select a customer and target date to add to your monthly itinerary."
      >
        {formError && (
          <div className="mb-space-4 font-body-md text-xs text-on-error-container bg-error-container p-space-3 rounded-xl border border-error">
            {formError}
          </div>
        )}

        <form onSubmit={handleCreateSubmit} className="space-y-space-4">
          {/* Customer Selection with Search */}
          <div className="space-y-space-1.5">
            <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold">
              Select Customer / Outlet <span className="text-error">*</span>
            </label>

            {/* Search Filter for Customers */}
            <div className="relative mb-space-1.5">
              <Search className="w-4 h-4 text-on-surface-variant absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                value={customerSearchQuery}
                onChange={(e) => setCustomerSearchQuery(e.target.value)}
                placeholder="Search by customer name, code, or address..."
                className="w-full h-9 bg-surface border border-outline-variant rounded-lg pl-9 pr-8 text-on-surface font-body-md text-xs focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20"
              />
              {customerSearchQuery && (
                <button
                  type="button"
                  onClick={() => setCustomerSearchQuery('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-on-surface-variant hover:text-on-surface"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <Select
              id="plan-customer"
              required
              value={formCustomerId}
              onChange={(e) => setFormCustomerId(e.target.value)}
              disabled={isCustomersLoading}
            >
              <option value="">
                {customerSearchQuery.trim()
                  ? filteredCustomers.length > 0
                    ? `-- Choose an outlet (${filteredCustomers.length} of ${customers.length} matching) --`
                    : `-- No outlets matching "${customerSearchQuery}" --`
                  : `-- Choose an outlet (${customers.length} available) --`}
              </option>
              {filteredCustomers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} {c.outlet_code ? `[${c.outlet_code}]` : ''} - {c.address}
                </option>
              ))}
            </Select>
          </div>

          {/* Planned Date */}
          <div className="w-full flex flex-col gap-space-1.5">
            <label
              htmlFor="plan-date"
              className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold"
            >
              Planned Date <span className="text-error">*</span>
            </label>
            <input
              id="plan-date"
              type="date"
              required
              min={todayStr}
              value={formPlannedDate}
              onChange={(e) => setFormPlannedDate(e.target.value)}
              className="w-full h-10 bg-surface border border-outline-variant rounded-lg px-space-3 text-on-surface font-body-md text-sm focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20"
            />
          </div>

          {/* Visit Type and Priority Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-3">
            <Select
              id="plan-visit-type"
              label="Visit Type"
              value={formVisitType}
              onChange={(e) => setFormVisitType(e.target.value as VisitType)}
            >
              <option value="PLANNED">Planned Beat</option>
              <option value="AD_HOC">Ad-Hoc Follow-up</option>
            </Select>

            <Select
              id="plan-priority"
              label="Priority"
              value={formPriority}
              onChange={(e) => setFormPriority(e.target.value as Priority)}
            >
              <option value="LOW">Low</option>
              <option value="MEDIUM">Medium</option>
              <option value="HIGH">High Priority</option>
            </Select>
          </div>

          {/* Notes */}
          <Textarea
            id="plan-notes"
            label="Visit Notes & Objectives (Optional)"
            placeholder="e.g. Stock verification, order booking, collection follow-up..."
            value={formNotes}
            onChange={(e) => setFormNotes(e.target.value)}
            rows={3}
          />

          {/* Submit Actions */}
          <div className="flex items-center justify-end gap-space-2 pt-space-3 border-t border-surface-container-highest">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsAddModalOpen(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="secondary"
              isLoading={isSubmitting}
            >
              Add to Plan
            </Button>
          </div>
        </form>
      </Modal>

      {/* 2. Edit Planned Visit Modal */}
      <Modal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        title="Edit Planned Visit"
        subtitle={`Update details for ${activeVisit?.customer_name || 'Customer'}`}
      >
        {formError && (
          <div className="mb-space-4 font-body-md text-xs text-on-error-container bg-error-container p-space-3 rounded-xl border border-error">
            {formError}
          </div>
        )}

        <form onSubmit={handleEditSubmit} className="space-y-space-4">
          <div className="p-space-3 rounded-xl bg-surface-container-low border border-surface-container-highest space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-caption text-xs text-on-surface-variant">Customer:</span>
              <span className="font-label-md text-xs text-primary font-bold">{activeVisit?.customer_name}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-caption text-xs text-on-surface-variant">Date:</span>
              <span className="font-label-md text-xs text-on-surface font-semibold">
                {activeVisit ? formatDisplayDate(activeVisit.planned_date) : ''}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-3">
            <Select
              id="edit-visit-type"
              label="Visit Type"
              value={formVisitType}
              onChange={(e) => setFormVisitType(e.target.value as VisitType)}
            >
              <option value="PLANNED">Planned Beat</option>
              <option value="AD_HOC">Ad-Hoc Follow-up</option>
            </Select>

            <Select
              id="edit-priority"
              label="Priority"
              value={formPriority}
              onChange={(e) => setFormPriority(e.target.value as Priority)}
            >
              <option value="LOW">Low</option>
              <option value="MEDIUM">Medium</option>
              <option value="HIGH">High Priority</option>
            </Select>
          </div>

          <Textarea
            id="edit-notes"
            label="Visit Notes & Objectives"
            value={formNotes}
            onChange={(e) => setFormNotes(e.target.value)}
            rows={3}
          />

          <div className="flex items-center justify-end gap-space-2 pt-space-3 border-t border-surface-container-highest">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsEditModalOpen(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="secondary"
              isLoading={isSubmitting}
            >
              Save Changes
            </Button>
          </div>
        </form>
      </Modal>

      {/* 3. Reschedule Planned Visit Modal */}
      <Modal
        isOpen={isRescheduleModalOpen}
        onClose={() => setIsRescheduleModalOpen(false)}
        title="Reschedule Planned Visit"
        subtitle={`Select a new target date for ${activeVisit?.customer_name || 'Customer'}`}
      >
        {formError && (
          <div className="mb-space-4 font-body-md text-xs text-on-error-container bg-error-container p-space-3 rounded-xl border border-error">
            {formError}
          </div>
        )}

        <form onSubmit={handleRescheduleSubmit} className="space-y-space-4">
          <div className="p-space-3 rounded-xl bg-surface-container-low border border-surface-container-highest space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-caption text-xs text-on-surface-variant">Customer:</span>
              <span className="font-label-md text-xs text-primary font-bold">{activeVisit?.customer_name}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-caption text-xs text-on-surface-variant">Current Date:</span>
              <span className="font-label-md text-xs text-on-surface font-semibold">
                {activeVisit ? formatDisplayDate(activeVisit.planned_date) : ''}
              </span>
            </div>
          </div>

          <div className="w-full flex flex-col gap-space-1.5">
            <label
              htmlFor="reschedule-date"
              className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold"
            >
              New Planned Date <span className="text-error">*</span>
            </label>
            <input
              id="reschedule-date"
              type="date"
              required
              min={todayStr}
              value={rescheduleDate}
              onChange={(e) => setRescheduleDate(e.target.value)}
              className="w-full h-10 bg-surface border border-outline-variant rounded-lg px-space-3 text-on-surface font-body-md text-sm focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20"
            />
            <p className="font-caption text-xs text-on-surface-variant">
              Moving to another month is fully supported. The visit will automatically transfer to that month's plan.
            </p>
          </div>

          <div className="flex items-center justify-end gap-space-2 pt-space-3 border-t border-surface-container-highest">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsRescheduleModalOpen(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="secondary"
              isLoading={isSubmitting}
            >
              Confirm Reschedule
            </Button>
          </div>
        </form>
      </Modal>

      {/* 4. Delete / Cancel Confirmation Modal */}
      <Modal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        title="Cancel Planned Visit"
        subtitle="Are you sure you want to remove this visit from your monthly plan?"
      >
        {formError && (
          <div className="mb-space-4 font-body-md text-xs text-on-error-container bg-error-container p-space-3 rounded-xl border border-error">
            {formError}
          </div>
        )}

        <div className="space-y-space-4">
          <div className="p-space-3.5 rounded-xl bg-error-container/20 border border-error/30 space-y-2">
            <div className="flex items-center gap-space-2 text-error font-bold text-xs uppercase font-label-md">
              <AlertCircle className="w-4 h-4" />
              Visit Cancellation
            </div>
            <p className="font-body-md text-xs text-on-surface leading-relaxed">
              This will remove the planned visit to{' '}
              <strong className="text-primary">{activeVisit?.customer_name}</strong> on{' '}
              <strong>{activeVisit ? formatDisplayDate(activeVisit.planned_date) : ''}</strong> from your schedule.
            </p>
          </div>

          <div className="flex items-center justify-end gap-space-2 pt-space-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsDeleteModalOpen(false)}
              disabled={isSubmitting}
            >
              Keep Visit
            </Button>
            <Button
              type="button"
              variant="danger"
              isLoading={isSubmitting}
              onClick={handleDeleteSubmit}
            >
              Yes, Remove Visit
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
