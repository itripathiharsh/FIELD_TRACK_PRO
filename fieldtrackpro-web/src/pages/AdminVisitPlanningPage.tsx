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
  Search,
  User,
  Users,
  UserCheck,
  ArrowRight,
  Filter,
  AlertTriangle,
  TrendingUp,
} from 'lucide-react';
import { apiClient, ApiError } from '../api/client';
import {
  Customer,
  DailyAnalytics,
  Employee,
  PlannedVisit,
  Priority,
  TeamMonthlyAnalytics,
  TeamMonthlyPlan,
  VisitType,
} from '../types';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { ErrorBanner } from '../components/ui/ErrorBanner';

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

// Timezone-safe date string formatter: YYYY-MM-DD
function formatDateStr(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

// Timezone-safe display formatter
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

export const AdminVisitPlanningPage: React.FC = () => {
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

  // Employee filter state ("" means All Employees)
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string>('');

  // Team plan data state
  const [teamPlan, setTeamPlan] = useState<TeamMonthlyPlan | null>(null);
  const [analytics, setAnalytics] = useState<TeamMonthlyAnalytics | null>(null);
  const [dailyAnalytics, setDailyAnalytics] = useState<DailyAnalytics | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  // Reference lists: Employees & Customers
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerSearchQuery, setCustomerSearchQuery] = useState<string>('');

  // Modal states
  const [isAddModalOpen, setIsAddModalOpen] = useState<boolean>(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState<boolean>(false);
  const [isRescheduleModalOpen, setIsRescheduleModalOpen] = useState<boolean>(false);
  const [isReassignModalOpen, setIsReassignModalOpen] = useState<boolean>(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState<boolean>(false);
  const [activeVisit, setActiveVisit] = useState<PlannedVisit | null>(null);

  // Create Form states
  const [formEmployeeId, setFormEmployeeId] = useState<string>('');
  const [formCustomerId, setFormCustomerId] = useState<string>('');
  const [formPlannedDate, setFormPlannedDate] = useState<string>(todayStr);
  const [formVisitType, setFormVisitType] = useState<VisitType>('PLANNED');
  const [formPriority, setFormPriority] = useState<Priority>('MEDIUM');
  const [formNotes, setFormNotes] = useState<string>('');
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Reschedule state
  const [rescheduleDate, setRescheduleDate] = useState<string>(todayStr);

  // Reassign state
  const [targetEmployeeId, setTargetEmployeeId] = useState<string>('');

  // 1. Fetch team plan data & analytics
  const loadTeamPlan = useCallback(
    async (year: number, month: number, employeeId?: string) => {
      setIsLoading(true);
      setError(null);
      try {
        const [data, anData] = await Promise.all([
          apiClient.getTeamMonthlyPlan({
            year,
            month,
            employee_id: employeeId ? employeeId : undefined,
          }),
          apiClient
            .getTeamAnalytics({
              year,
              month,
              employee_id: employeeId ? employeeId : undefined,
            })
            .catch(() => null),
        ]);
        setTeamPlan(data);
        setAnalytics(anData);
      } catch (err: unknown) {
        if (err instanceof ApiError) {
          setError(err.message || 'Failed to load team monthly plan');
        } else if (err instanceof Error) {
          setError(err.message);
        } else {
          setError('Failed to load team monthly plan');
        }
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  // Load team plan  // Re-fetch when month, year, or employee filter changes
  useEffect(() => {
    loadTeamPlan(selectedYear, selectedMonth, selectedEmployeeId);
  }, [selectedYear, selectedMonth, selectedEmployeeId, loadTeamPlan]);

  // Fetch daily analytics when employee is filtered and date is selected
  useEffect(() => {
    if (selectedEmployeeId && selectedDateStr) {
      apiClient
        .getDailyAnalytics(selectedEmployeeId, selectedDateStr)
        .then(setDailyAnalytics)
        .catch(() => setDailyAnalytics(null));
    } else {
      setDailyAnalytics(null);
    }
  }, [selectedEmployeeId, selectedDateStr]);

  // 2. Fetch employees and customers for selection dropdowns
  useEffect(() => {
    apiClient
      .getEmployees({ limit: 3000 })
      .then((data) => {
        // Sort employees alphabetically by full name
        const sorted = [...data].sort((a, b) =>
          a.full_name.localeCompare(b.full_name),
        );
        setEmployees(sorted);
      })
      .catch(() => setEmployees([]));

    apiClient
      .getCustomers({ limit: 3000 })
      .then((data) => setCustomers(data))
      .catch(() => setCustomers([]));
  }, []);

  // Filtered customers for create modal search
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

  // Group planned visits by date string (YYYY-MM-DD)
  const visitsByDate = useMemo(() => {
    const map: Record<string, PlannedVisit[]> = {};
    if (!teamPlan || !teamPlan.planned_visits) return map;
    for (const v of teamPlan.planned_visits) {
      if (!map[v.planned_date]) {
        map[v.planned_date] = [];
      }
      map[v.planned_date].push(v);
    }
    return map;
  }, [teamPlan]);

  // Selected date visits
  const selectedDateVisits = useMemo(() => {
    return visitsByDate[selectedDateStr] || [];
  }, [visitsByDate, selectedDateStr]);

  // Calendar math
  const daysInMonth = useMemo(() => {
    return new Date(selectedYear, selectedMonth, 0).getDate();
  }, [selectedYear, selectedMonth]);

  const firstDayWeekday = useMemo(() => {
    return new Date(selectedYear, selectedMonth - 1, 1).getDay();
  }, [selectedYear, selectedMonth]);

  // Days in previous month to display trailing numbers in leading empty cells
  const prevMonthDays = useMemo(() => {
    return new Date(selectedYear, selectedMonth - 1, 0).getDate();
  }, [selectedYear, selectedMonth]);

  // Trailing empty days to complete the calendar week grid
  const trailingEmptyDays = useMemo(() => {
    const totalRendered = firstDayWeekday + daysInMonth;
    const remainder = totalRendered % 7;
    return remainder === 0 ? 0 : 7 - remainder;
  }, [firstDayWeekday, daysInMonth]);

  // Derived Metric: Average Visits per Employee
  const avgVisitsPerEmployee = useMemo(() => {
    const total = analytics ? analytics.team_total_planned : (teamPlan ? teamPlan.total_planned_visits : 0);
    const activeReps = teamPlan ? teamPlan.active_employees_count : 0;
    if (selectedEmployeeId && analytics?.employees?.[0]) {
      const emp = analytics.employees[0];
      if (emp.avg_planned_per_active_day !== null && emp.avg_planned_per_active_day !== undefined) {
        return String(emp.avg_planned_per_active_day);
      }
      return emp.total_planned > 0 ? String(emp.total_planned) : '0.0';
    }
    if (activeReps === 0) return '0.0';
    return (total / activeReps).toFixed(1);
  }, [analytics, teamPlan, selectedEmployeeId]);

  // Navigation handlers
  const handlePrevMonth = () => {
    let nextYear = selectedYear;
    let nextMonth = selectedMonth - 1;
    if (nextMonth < 1) {
      nextMonth = 12;
      nextYear -= 1;
    }
    setSelectedYear(nextYear);
    setSelectedMonth(nextMonth);
    setSelectedDateStr(formatDateStr(nextYear, nextMonth, 1));
  };

  const handleNextMonth = () => {
    let nextYear = selectedYear;
    let nextMonth = selectedMonth + 1;
    if (nextMonth > 12) {
      nextMonth = 1;
      nextYear += 1;
    }
    setSelectedYear(nextYear);
    setSelectedMonth(nextMonth);
    setSelectedDateStr(formatDateStr(nextYear, nextMonth, 1));
  };

  const handleToday = () => {
    setSelectedYear(todayYear);
    setSelectedMonth(todayMonth);
    setSelectedDateStr(todayStr);
  };

  // Helper to show temporary success banner
  const triggerSuccess = (msg: string) => {
    setSuccessBanner(msg);
    setTimeout(() => setSuccessBanner(null), 5000);
  };

  // --- Create Planned Visit (Admin on behalf of employee) ---
  const handleOpenAddModal = (dateStr?: string) => {
    const targetDate = dateStr || selectedDateStr || todayStr;
    setFormPlannedDate(targetDate);
    // If an employee is filtered, default to that employee; otherwise pick first available or blank
    setFormEmployeeId(selectedEmployeeId || (employees.length > 0 ? employees[0].id : ''));
    setFormCustomerId('');
    setFormVisitType('PLANNED');
    setFormPriority('MEDIUM');
    setFormNotes('');
    setFormError(null);
    setCustomerSearchQuery('');
    setIsAddModalOpen(true);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formEmployeeId) {
      setFormError('Please select an employee for this planned visit');
      return;
    }
    if (!formCustomerId) {
      setFormError('Please select a customer / outlet');
      return;
    }
    if (!formPlannedDate) {
      setFormError('Please select a planned date');
      return;
    }

    setIsSubmitting(true);
    setFormError(null);
    try {
      await apiClient.createPlannedVisit({
        employee_id: formEmployeeId,
        customer_id: formCustomerId,
        planned_date: formPlannedDate,
        visit_type: formVisitType,
        priority: formPriority,
        notes: formNotes.trim() ? formNotes.trim() : null,
      });

      setIsAddModalOpen(false);
      setSelectedDateStr(formPlannedDate);
      triggerSuccess('Planned visit successfully created on behalf of employee');

      // If scheduled in another month, switch to that month
      const [pYear, pMonth] = formPlannedDate.split('-').map(Number);
      if (pYear !== selectedYear || pMonth !== selectedMonth) {
        setSelectedYear(pYear);
        setSelectedMonth(pMonth);
      } else {
        await loadTeamPlan(selectedYear, selectedMonth, selectedEmployeeId);
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

  // --- Edit Planned Visit ---
  const handleOpenEditModal = (visit: PlannedVisit) => {
    setActiveVisit(visit);
    setFormVisitType(visit.visit_type);
    setFormPriority(visit.priority);
    setFormNotes(visit.notes || '');
    setFormError(null);
    setIsEditModalOpen(true);
  };

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
      triggerSuccess('Planned visit updated successfully');
      await loadTeamPlan(selectedYear, selectedMonth, selectedEmployeeId);
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

  // --- Reschedule Planned Visit ---
  const handleOpenRescheduleModal = (visit: PlannedVisit) => {
    setActiveVisit(visit);
    setRescheduleDate(visit.planned_date);
    setFormError(null);
    setIsRescheduleModalOpen(true);
  };

  const handleRescheduleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeVisit) return;
    if (!rescheduleDate) {
      setFormError('Please select a target date');
      return;
    }

    setIsSubmitting(true);
    setFormError(null);
    try {
      await apiClient.reschedulePlannedVisit(activeVisit.id, rescheduleDate);
      setIsRescheduleModalOpen(false);
      setSelectedDateStr(rescheduleDate);
      triggerSuccess(
        `Planned visit rescheduled to ${formatDisplayDate(rescheduleDate)}`,
      );

      // Handle cross-month navigation if applicable
      const [rYear, rMonth] = rescheduleDate.split('-').map(Number);
      if (rYear !== selectedYear || rMonth !== selectedMonth) {
        setSelectedYear(rYear);
        setSelectedMonth(rMonth);
      } else {
        await loadTeamPlan(selectedYear, selectedMonth, selectedEmployeeId);
      }
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setFormError(err.message || 'Failed to reschedule planned visit');
      } else if (err instanceof Error) {
        setFormError(err.message);
      } else {
        setFormError('Failed to reschedule planned visit');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // --- Reassign Planned Visit (Admin Reassignment) ---
  const handleOpenReassignModal = (visit: PlannedVisit) => {
    setActiveVisit(visit);
    // Pick the first employee that is not the current visit owner
    const candidate = employees.find((emp) => emp.id !== visit.employee_id);
    setTargetEmployeeId(candidate ? candidate.id : '');
    setFormError(null);
    setIsReassignModalOpen(true);
  };

  const handleReassignSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeVisit) return;
    if (!targetEmployeeId) {
      setFormError('Please select a target employee');
      return;
    }
    if (targetEmployeeId === activeVisit.employee_id) {
      setFormError('Target employee cannot be the current visit owner');
      return;
    }

    setIsSubmitting(true);
    setFormError(null);
    try {
      const updated = await apiClient.reassignPlannedVisit(
        activeVisit.id,
        targetEmployeeId,
      );
      setIsReassignModalOpen(false);
      triggerSuccess(
        `Planned visit reassigned to ${updated.employee_name || 'new employee'}`,
      );
      await loadTeamPlan(selectedYear, selectedMonth, selectedEmployeeId);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setFormError(err.message || 'Failed to reassign planned visit');
      } else if (err instanceof Error) {
        setFormError(err.message);
      } else {
        setFormError('Failed to reassign planned visit');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // --- Delete Planned Visit ---
  const handleOpenDeleteModal = (visit: PlannedVisit) => {
    setActiveVisit(visit);
    setFormError(null);
    setIsDeleteModalOpen(true);
  };

  const handleDeleteSubmit = async () => {
    if (!activeVisit) return;
    setIsSubmitting(true);
    setFormError(null);
    try {
      await apiClient.deletePlannedVisit(activeVisit.id);
      setIsDeleteModalOpen(false);
      triggerSuccess('Planned visit removed successfully');
      await loadTeamPlan(selectedYear, selectedMonth, selectedEmployeeId);
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

  // Active employee object for display
  const currentFilteredEmployee = useMemo(() => {
    return employees.find((emp) => emp.id === selectedEmployeeId) || null;
  }, [employees, selectedEmployeeId]);

  return (
    <div className="p-space-6 space-y-space-6 bg-surface min-h-screen text-on-surface">
      {/* Top Page Header */}
      <PageHeader
        title="Visit Planning & Oversight"
        subtitle="Manage, review, and coordinate monthly planned field visits across sales executives"
        actions={
          <Button
            id="admin-schedule-visit-btn"
            onClick={() => handleOpenAddModal()}
            className="flex items-center gap-space-2 bg-primary-container text-white hover:bg-primary-container/90"
          >
            <Plus className="w-4 h-4" />
            <span>Schedule Planned Visit</span>
          </Button>
        }
      />

      {/* Success Notification Banner */}
      {successBanner && (
        <div
          role="status"
          className="flex items-center gap-space-2 p-space-4 rounded bg-emerald-50 text-emerald-800 border border-emerald-200 text-sm font-body animate-fadeIn"
        >
          <CheckCircle2 className="w-5 h-5 shrink-0 text-emerald-600" />
          <span>{successBanner}</span>
        </div>
      )}

      {/* Error Alert Banner */}
      {error && <ErrorBanner message={error} />}

      {/* 1. Dedicated Control Bar: Month Navigation, Today & Employee Scope Filter */}
      <Card className="p-4 sm:p-5 border border-surface-container-highest shadow-xs bg-surface rounded-2xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          {/* Left: Month Navigator & Today */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center bg-surface-low border border-outline/30 rounded-xl shadow-2xs overflow-hidden p-0.5">
              <Button
                variant="ghost"
                size="sm"
                onClick={handlePrevMonth}
                aria-label="Previous month"
                className="px-2.5 h-9 rounded-lg hover:bg-surface-high transition-colors text-on-surface"
              >
                <ChevronLeft className="w-5 h-5" />
              </Button>
              <div className="px-4 font-heading font-bold text-base min-w-[170px] text-center text-primary tracking-tight">
                {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleNextMonth}
                aria-label="Next month"
                className="px-2.5 h-9 rounded-lg hover:bg-surface-high transition-colors text-on-surface"
              >
                <ChevronRight className="w-5 h-5" />
              </Button>
            </div>

            <Button
              variant="outline"
              size="sm"
              onClick={handleToday}
              className="h-10 px-3.5 flex items-center gap-1.5 border-outline/40 hover:bg-surface-high text-xs font-bold rounded-xl text-primary shadow-2xs"
            >
              <CalendarDays className="w-4 h-4 text-primary" />
              <span>Today</span>
            </Button>
          </div>

          {/* Right: Employee Scope Filter */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2.5 bg-surface-low px-3 py-1.5 rounded-xl border border-outline/25 shadow-2xs">
              <Filter className="w-3.5 h-3.5 text-primary shrink-0" />
              <span className="text-xs font-bold text-on-surface-variant uppercase tracking-wider shrink-0">
                Employee Scope:
              </span>
              <select
                id="admin-employee-filter"
                value={selectedEmployeeId}
                onChange={(e) => setSelectedEmployeeId(e.target.value)}
                className="px-3 py-1.5 rounded-lg border border-outline/40 bg-surface text-xs font-semibold text-on-surface focus:outline-hidden focus:ring-2 focus:ring-primary min-w-[220px] max-w-[340px] truncate shadow-2xs"
              >
                <option value="">All Employees ({employees.length})</option>
                {employees.map((emp) => (
                  <option key={emp.id} value={emp.id}>
                    {emp.full_name} {emp.employee_code ? `(${emp.employee_code})` : ''}
                  </option>
                ))}
              </select>
            </div>

            {selectedEmployeeId && analytics?.employees?.[0]?.behind_schedule && (
              <span className="px-2.5 py-1 rounded-lg bg-amber-100 text-amber-900 border border-amber-300 font-bold text-xs flex items-center gap-1.5 shadow-2xs">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-700" />
                Behind Schedule
              </span>
            )}
          </div>
        </div>

        {/* Scope Indicator Line */}
        <div className="mt-3 pt-3 border-t border-surface-container-highest flex flex-wrap items-center justify-between gap-3 text-xs text-on-surface-variant">
          <div className="flex items-center gap-2">
            <Users className="w-4 h-4 text-primary" />
            <span>
              Scope:{' '}
              <strong className="text-on-surface font-semibold">
                {currentFilteredEmployee
                  ? `${currentFilteredEmployee.full_name} (${currentFilteredEmployee.employee_code || 'Rep'})`
                  : 'All Employees'}
              </strong>
            </span>
          </div>

          <span className="text-xs text-on-surface-variant font-caption italic">
            Click any day on the calendar to inspect or schedule planned visits
          </span>
        </div>
      </Card>

      {/* 2. Executive KPI Cards Row (Distinct Box / Row) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {/* Card 1: Total Planned Visits */}
        <Card className="p-4 border border-surface-container-highest bg-surface rounded-2xl shadow-xs flex flex-col justify-between hover:shadow-sm transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-on-surface-variant uppercase tracking-wider">Total Planned:</span>
            <div className="w-8 h-8 rounded-xl bg-primary/10 flex items-center justify-center text-primary">
              <CalendarDays className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2">
            <div className="text-2xl font-heading font-extrabold text-primary">
              {analytics ? analytics.team_total_planned : (teamPlan ? teamPlan.total_planned_visits : 0)}
            </div>
            <p className="text-xs text-on-surface-variant mt-1">
              Active Days: <strong className="text-on-surface font-semibold">{teamPlan ? teamPlan.active_days_count : 0}</strong>
            </p>
          </div>
        </Card>

        {/* Card 2: Completed Visits */}
        <Card className="p-4 border border-emerald-200/70 dark:border-emerald-800/40 bg-emerald-50/30 dark:bg-emerald-950/20 rounded-2xl shadow-xs flex flex-col justify-between hover:shadow-sm transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-emerald-800 dark:text-emerald-300 uppercase tracking-wider">Completed:</span>
            <div className="w-8 h-8 rounded-xl bg-emerald-100 dark:bg-emerald-900/40 flex items-center justify-center text-emerald-700">
              <CheckCircle2 className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2">
            <div className="text-2xl font-heading font-extrabold text-emerald-700 dark:text-emerald-400">
              {analytics ? analytics.team_completed : 0}
            </div>
            <p className="text-xs text-emerald-700 dark:text-emerald-300 mt-1">
              Completion: <strong className="font-bold">{analytics && analytics.team_completion_rate !== null ? `${analytics.team_completion_rate}%` : '—'}</strong>
            </p>
          </div>
        </Card>

        {/* Card 3: Missed Visits */}
        <Card className="p-4 border border-rose-200/70 dark:border-rose-800/40 bg-rose-50/30 dark:bg-rose-950/20 rounded-2xl shadow-xs flex flex-col justify-between hover:shadow-sm transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-rose-800 dark:text-rose-300 uppercase tracking-wider">Missed:</span>
            <div className="w-8 h-8 rounded-xl bg-rose-100 dark:bg-rose-900/40 flex items-center justify-center text-rose-700">
              <AlertTriangle className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2">
            <div className="text-2xl font-heading font-extrabold text-rose-700 dark:text-rose-400">
              {analytics ? analytics.team_missed : 0}
            </div>
            <p className="text-xs text-rose-700 dark:text-rose-300 mt-1">
              Extra: <strong className="font-bold">{analytics ? analytics.team_extra : 0}</strong> unplanned
            </p>
          </div>
        </Card>

        {/* Card 4: Reps Active */}
        <Card className="p-4 border border-surface-container-highest bg-surface rounded-2xl shadow-xs flex flex-col justify-between hover:shadow-sm transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-on-surface-variant uppercase tracking-wider">Reps Active:</span>
            <div className="w-8 h-8 rounded-xl bg-indigo-50 dark:bg-indigo-950/40 flex items-center justify-center text-indigo-600">
              <Users className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2">
            <div className="text-2xl font-heading font-extrabold text-primary">
              {teamPlan ? teamPlan.active_employees_count : 0}
            </div>
            <p className="text-xs text-on-surface-variant mt-1">
              Roster: <strong className="text-on-surface font-semibold">{employees.length} reps</strong>
            </p>
          </div>
        </Card>

        {/* Card 5: Avg Visits / Employee (Requested by user) */}
        <Card className="p-4 border border-amber-200/70 dark:border-amber-800/40 bg-amber-50/30 dark:bg-amber-950/20 rounded-2xl shadow-xs flex flex-col justify-between hover:shadow-sm transition-shadow">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-amber-900 dark:text-amber-300 uppercase tracking-wider">Avg Visits / Employee:</span>
            <div className="w-8 h-8 rounded-xl bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center text-amber-800">
              <TrendingUp className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2">
            <div className="text-2xl font-heading font-extrabold text-amber-800 dark:text-amber-400">
              {avgVisitsPerEmployee}
            </div>
            <p className="text-xs text-amber-800 dark:text-amber-300 mt-1 font-medium">
              {selectedEmployeeId ? 'Avg / active day' : 'Visits per active rep'}
            </p>
          </div>
        </Card>
      </div>

      {/* 3. Main Grid: Redesigned Calendar (Left/Center) + Day Inspection Panel (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Calendar View: 7 or 8 columns on large screens */}
        <div className="lg:col-span-7 xl:col-span-8">
          <Card className="border border-surface-container-highest shadow-sm bg-surface rounded-2xl overflow-hidden p-0">
            {/* Calendar Card Subheader with Status Legend */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between px-5 py-3.5 bg-surface-low border-b border-surface-container-highest gap-2">
              <div className="flex items-center gap-2">
                <CalendarDays className="w-4 h-4 text-primary" />
                <h3 className="font-heading font-bold text-sm text-primary">
                  Schedule Overview &bull; {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
                </h3>
                <span className="text-xs font-mono font-bold text-on-surface-variant bg-surface px-2 py-0.5 rounded-full border border-outline/25 ml-1">
                  {teamPlan?.total_planned_visits || 0} visits
                </span>
              </div>

              {/* Status Indicator Legend */}
              <div className="flex items-center gap-3 text-xs font-caption text-on-surface-variant">
                <div className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-primary" />
                  <span>Planned</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-emerald-500" />
                  <span>Completed</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-rose-500" />
                  <span>Missed</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-amber-400" />
                  <span>Today</span>
                </div>
              </div>
            </div>

            {/* Weekday Header */}
            <div className="grid grid-cols-7 border-b border-surface-container-highest bg-surface-low/90 text-center font-heading font-bold text-xs py-2.5 text-on-surface-variant uppercase tracking-wider">
              {WEEKDAY_NAMES.map((name, idx) => (
                <div key={name} className={idx === 0 || idx === 6 ? 'text-secondary font-extrabold' : ''}>
                  {name}
                </div>
              ))}
            </div>

            {/* Month Days Grid */}
            {isLoading ? (
              <div className="p-16 flex flex-col items-center justify-center text-on-surface-variant gap-3">
                <div className="w-9 h-9 border-3 border-primary/20 border-t-primary rounded-full animate-spin" />
                <span className="text-sm font-caption font-medium">Loading team monthly plan...</span>
              </div>
            ) : (
              <div className="grid grid-cols-7 gap-px bg-surface-container-highest/50">
                {/* Leading days from previous month: muted numbering, clearly non-interactive */}
                {Array.from({ length: firstDayWeekday }).map((_, idx) => {
                  const prevDayNum = prevMonthDays - firstDayWeekday + idx + 1;
                  return (
                    <div
                      key={`prev-${idx}`}
                      className="min-h-[120px] bg-surface-low/30 p-2.5 select-none flex flex-col justify-between opacity-50 cursor-default"
                    >
                      <span className="w-7 h-7 flex items-center justify-center rounded-full text-xs font-heading font-medium text-on-surface-variant/50">
                        {prevDayNum}
                      </span>
                      <div className="h-6" />
                    </div>
                  );
                })}

                {/* Day Cells for Current Month: Uniform clean background for all days */}
                {Array.from({ length: daysInMonth }).map((_, idx) => {
                  const dayNum = idx + 1;
                  const dayDateStr = formatDateStr(selectedYear, selectedMonth, dayNum);
                  const isSelected = selectedDateStr === dayDateStr;
                  const isToday = todayStr === dayDateStr;
                  const dayVisits = visitsByDate[dayDateStr] || [];
                  const visitCount = dayVisits.length;

                  return (
                    <div
                      key={dayDateStr}
                      data-date={dayDateStr}
                      onClick={() => setSelectedDateStr(dayDateStr)}
                      className={`min-h-[120px] p-2.5 cursor-pointer transition-all duration-150 flex flex-col justify-between relative group ${
                        isSelected
                          ? 'bg-primary/5 ring-2 ring-primary ring-inset z-10 shadow-xs'
                          : isToday
                          ? 'bg-amber-500/5 ring-2 ring-amber-400/80'
                          : 'bg-surface hover:bg-primary/[0.03]'
                      }`}
                    >
                      {/* Day Header: Day Number, Today Badge & Quick Action Button */}
                      <div className="flex items-center justify-between">
                        <span
                          className={`w-7 h-7 flex items-center justify-center rounded-full text-xs font-heading font-bold transition-transform ${
                            isSelected
                              ? 'bg-primary text-white shadow-xs scale-105'
                              : isToday
                              ? 'bg-amber-400 text-slate-950 font-black shadow-xs ring-2 ring-amber-300/60'
                              : 'text-on-surface group-hover:bg-surface-high'
                          }`}
                        >
                          {dayNum}
                        </span>

                        <div className="flex items-center gap-1">
                          {isToday && (
                            <span className="text-[10px] font-caption font-extrabold text-amber-800 dark:text-amber-200 bg-amber-100 dark:bg-amber-950/80 px-1.5 py-0.5 rounded uppercase tracking-wider border border-amber-300 dark:border-amber-800 shadow-2xs">
                              Today
                            </span>
                          )}
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleOpenAddModal(dayDateStr);
                            }}
                            title="Schedule visit for this day"
                            aria-label={`Schedule visit for day ${dayNum}`}
                            className="opacity-0 group-hover:opacity-100 transition-opacity w-5 h-5 flex items-center justify-center rounded hover:bg-primary/10 text-primary"
                          >
                            <Plus className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>

                      {/* Day Content: Rich Visit Preview */}
                      <div className="mt-2 flex flex-col gap-1.5">
                        {visitCount > 0 ? (
                          <div className="space-y-1">
                            <span
                              className={`inline-flex items-center justify-between w-full px-2 py-1 rounded-lg text-xs font-heading font-bold shadow-2xs transition-colors ${
                                isSelected
                                  ? 'bg-primary text-white shadow-xs'
                                  : 'bg-primary/10 text-primary border border-primary/20 hover:bg-primary/15'
                              }`}
                            >
                              <span>{visitCount} Planned</span>
                              {dayVisits.length > 3 && (
                                <span className="text-[10px] font-mono opacity-80">+{dayVisits.length - 3}</span>
                              )}
                            </span>

                            {/* Customer Outlet Name Preview */}
                            {dayVisits[0]?.customer_name && (
                              <div
                                className="hidden sm:flex items-center gap-1 text-[11px] text-on-surface-variant font-medium px-1 truncate"
                                title={dayVisits[0].customer_name}
                              >
                                <Building2 className="w-3 h-3 text-secondary shrink-0" />
                                <span className="truncate">{dayVisits[0].customer_name}</span>
                              </div>
                            )}

                            {/* Status Density Dots */}
                            <div className="flex items-center gap-1 px-1">
                              {dayVisits.slice(0, 4).map((v, i) => (
                                <span
                                  key={v.id || i}
                                  title={`${v.employee_name || 'Rep'}: ${v.customer_name || 'Outlet'} (${v.status})`}
                                  className={`w-1.5 h-1.5 rounded-full shadow-2xs ${
                                    v.status === 'COMPLETED'
                                      ? 'bg-emerald-500'
                                      : v.status === 'MISSED'
                                      ? 'bg-rose-500'
                                      : 'bg-primary'
                                  }`}
                                />
                              ))}
                            </div>
                          </div>
                        ) : (
                          <div className="h-6" />
                        )}
                      </div>
                    </div>
                  );
                })}

                {/* Trailing days into next month: muted numbering to complete grid row */}
                {Array.from({ length: trailingEmptyDays }).map((_, idx) => {
                  const nextDayNum = idx + 1;
                  return (
                    <div
                      key={`next-${idx}`}
                      className="min-h-[120px] bg-surface-low/30 p-2.5 select-none flex flex-col justify-between opacity-50 cursor-default"
                    >
                      <span className="w-7 h-7 flex items-center justify-center rounded-full text-xs font-heading font-medium text-on-surface-variant/50">
                        {nextDayNum}
                      </span>
                      <div className="h-6" />
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        </div>

        {/* Day Details Inspection Panel: 5 or 4 columns on large screens */}
        <div className="lg:col-span-5 xl:col-span-4">
          <Card className="border border-surface-container-highest shadow-sm bg-surface rounded-2xl flex flex-col h-full p-0 overflow-hidden">
            {/* Header: Full Display Date without truncation */}
            <CardHeader className="border-b border-surface-container-highest px-5 py-4 bg-surface-low !flex-col !items-stretch !justify-start gap-3 w-full mb-0">
              <div className="flex items-start justify-between gap-3 w-full">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <CalendarDays className="w-5 h-5 text-secondary shrink-0" />
                    <h3
                      className="text-base sm:text-lg font-heading font-bold text-primary leading-snug break-words"
                      title={formatDisplayDate(selectedDateStr)}
                    >
                      {formatDisplayDate(selectedDateStr)}
                    </h3>
                  </div>
                  <p className="text-xs text-on-surface-variant mt-1 font-semibold">
                    {selectedDateVisits.length}{' '}
                    {selectedDateVisits.length === 1 ? 'Planned Visit' : 'Planned Visits'}
                  </p>
                </div>

                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleOpenAddModal(selectedDateStr)}
                  className="shrink-0 flex items-center gap-1.5 border border-primary/50 text-primary hover:bg-primary/5 hover:border-primary text-xs font-bold px-3.5 py-1.5 whitespace-nowrap shadow-2xs rounded-xl transition-all"
                >
                  <Plus className="w-4 h-4 text-primary" />
                  <span>Add Visit</span>
                </Button>
              </div>

              {/* Daily Planned vs Actual Analytics Strip */}
              {dailyAnalytics && (
                <div className="pt-2.5 border-t border-surface-container-highest flex flex-wrap items-center gap-2 text-xs w-full">
                  <span className="px-2 py-0.5 rounded-md bg-surface border border-outline/30 font-medium text-primary">
                    Planned: <strong>{dailyAnalytics.planned}</strong>
                  </span>
                  <span className="px-2 py-0.5 rounded-md bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/30 font-medium text-emerald-800 dark:text-emerald-300">
                    Completed: <strong>{dailyAnalytics.completed}</strong>
                  </span>
                  <span className="px-2 py-0.5 rounded-md bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800/30 font-medium text-rose-800 dark:text-rose-300">
                    Missed: <strong>{dailyAnalytics.missed}</strong>
                  </span>
                  <span className="px-2 py-0.5 rounded-md bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/30 font-medium text-amber-800 dark:text-amber-300">
                    Extra: <strong>{dailyAnalytics.extra_unplanned}</strong>
                  </span>
                </div>
              )}
            </CardHeader>

            {/* List of Planned Visits for this Day */}
            <div className="p-4 sm:p-5 space-y-3.5 flex-1 overflow-y-auto max-h-[640px]">
              {selectedDateVisits.length === 0 ? (
                <div className="py-12 px-6 flex flex-col items-center justify-center text-center rounded-2xl bg-surface-low/50 border border-dashed border-outline/30 my-3">
                  <div className="w-12 h-12 rounded-2xl bg-primary/10 flex items-center justify-center mb-3">
                    <CalendarDays className="w-6 h-6 text-primary" />
                  </div>
                  <h4 className="font-heading font-bold text-sm text-on-surface">No Planned Visits</h4>
                  <p className="text-xs text-on-surface-variant mt-1 max-w-xs">
                    No field visits scheduled for {formatDisplayDate(selectedDateStr)}.
                  </p>
                  <Button
                    size="sm"
                    onClick={() => handleOpenAddModal(selectedDateStr)}
                    className="mt-4 flex items-center gap-1.5 px-4 py-2 font-semibold shadow-xs bg-primary text-white hover:bg-primary/90 rounded-xl"
                  >
                    <Plus className="w-4 h-4" />
                    <span>Schedule Visit for this Day</span>
                  </Button>
                </div>
              ) : (
                selectedDateVisits.map((visit) => (
                  <div
                    key={visit.id}
                    data-testid={`visit-card-${visit.id}`}
                    className={`p-4 rounded-xl border transition-all duration-150 space-y-3 shadow-2xs hover:shadow-xs bg-surface ${
                      visit.status === 'MISSED'
                        ? 'border-l-4 border-l-rose-500 border-surface-container-highest bg-rose-50/20 dark:bg-rose-950/10'
                        : visit.status === 'CANCELLED'
                        ? 'border-l-4 border-l-slate-400 border-surface-container-highest bg-surface-low/60 opacity-60'
                        : visit.status === 'COMPLETED'
                        ? 'border-l-4 border-l-emerald-500 border-surface-container-highest bg-emerald-50/20 dark:bg-emerald-950/10'
                        : 'border-l-4 border-l-primary border-surface-container-highest bg-surface hover:bg-surface-low/50'
                    }`}
                  >
                    {/* Employee Assignment Tag & Status Badges */}
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-primary/10 text-primary text-xs font-heading font-bold">
                        <User className="w-3.5 h-3.5 text-primary" />
                        <span>
                          {visit.employee_name || 'Assigned Rep'}{' '}
                          {visit.employee_code ? `(${visit.employee_code})` : ''}
                        </span>
                      </div>

                      <div className="flex items-center gap-1.5">
                        {/* Status Badge */}
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded-md font-bold uppercase tracking-wide border ${
                            visit.status === 'MISSED'
                              ? 'bg-rose-100 text-rose-800 border-rose-300 dark:bg-rose-950 dark:text-rose-300'
                              : visit.status === 'CANCELLED'
                              ? 'bg-slate-200 text-slate-700 border-slate-300 dark:bg-slate-800 dark:text-slate-400 line-through'
                              : visit.status === 'COMPLETED'
                              ? 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-950 dark:text-emerald-300'
                              : 'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-950 dark:text-blue-300'
                          }`}
                        >
                          {visit.status}
                        </span>

                        {/* Priority Badge */}
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded-md font-bold uppercase tracking-wide ${
                            visit.priority === 'HIGH'
                              ? 'bg-rose-100 text-rose-800'
                              : visit.priority === 'MEDIUM'
                              ? 'bg-amber-100 text-amber-900'
                              : 'bg-slate-100 text-slate-700'
                          }`}
                        >
                          {visit.priority}
                        </span>

                        {/* Visit Type Badge: Only display when AD_HOC to avoid duplicate "PLANNED" badge */}
                        {visit.visit_type === 'AD_HOC' && (
                          <span className="text-[10px] px-2 py-0.5 rounded-md bg-purple-100 text-purple-800 dark:bg-purple-950 dark:text-purple-300 font-bold uppercase tracking-wide border border-purple-200 dark:border-purple-800">
                            Ad-Hoc
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Customer Info */}
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <Building2 className="w-4 h-4 text-secondary shrink-0" />
                        <h4 className="font-heading font-bold text-sm text-on-surface line-clamp-1">
                          {visit.customer_name || 'Unnamed Outlet'}
                        </h4>
                      </div>

                      <div className="flex items-center gap-2 flex-wrap">
                        {visit.customer_outlet_code && (
                          <span className="px-1.5 py-0.5 rounded bg-surface-low border border-outline/30 text-[11px] font-mono font-medium text-on-surface-variant">
                            Code: {visit.customer_outlet_code}
                          </span>
                        )}
                        {visit.customer_address && (
                          <div className="flex items-center gap-1 text-xs text-on-surface-variant">
                            <MapPin className="w-3 h-3 text-on-surface-variant shrink-0" />
                            <span className="line-clamp-1">{visit.customer_address}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Notes if any */}
                    {visit.notes && (
                      <div className="text-xs italic bg-surface-low/80 p-2.5 rounded-lg border border-outline/20 text-on-surface-variant">
                        &ldquo;{visit.notes}&rdquo;
                      </div>
                    )}

                    {/* Admin Action Toolbar (hidden for cancelled visits) */}
                    {visit.status !== 'CANCELLED' && (
                      <div className="pt-2 border-t border-surface-container-highest flex items-center justify-end gap-1.5">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleOpenEditModal(visit)}
                          title="Edit visit"
                          aria-label="Edit visit"
                          className="h-7 px-2.5 text-xs flex items-center gap-1 text-on-surface hover:bg-surface-high rounded-lg font-medium"
                        >
                          <Edit3 className="w-3.5 h-3.5 text-primary" />
                          <span>Edit</span>
                        </Button>

                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleOpenRescheduleModal(visit)}
                          title="Reschedule visit"
                          aria-label="Reschedule visit"
                          className="h-7 px-2.5 text-xs flex items-center gap-1 text-on-surface hover:bg-surface-high rounded-lg font-medium"
                        >
                          <CalendarClock className="w-3.5 h-3.5 text-secondary" />
                          <span>Reschedule</span>
                        </Button>

                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleOpenReassignModal(visit)}
                          title="Reassign to another employee"
                          aria-label="Reassign visit"
                          className="h-7 px-2.5 text-xs flex items-center gap-1 text-on-surface hover:bg-surface-high rounded-lg font-medium"
                        >
                          <UserCheck className="w-3.5 h-3.5 text-amber-700" />
                          <span>Reassign</span>
                        </Button>

                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleOpenDeleteModal(visit)}
                          title="Delete visit"
                          aria-label="Delete visit"
                          className="h-7 px-2.5 text-xs flex items-center gap-1 text-rose-700 hover:bg-rose-50 dark:hover:bg-rose-950/50 rounded-lg font-medium"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          <span>Delete</span>
                        </Button>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </Card>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* MODAL 1: Create Planned Visit on behalf of Employee                       */}
      {/* ========================================================================= */}
      <Modal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title="Schedule Planned Visit"
      >
        <form onSubmit={handleCreateSubmit} className="space-y-space-4">
          {formError && <ErrorBanner message={formError} />}

          {/* 1. Employee Selection */}
          <div>
            <label
              htmlFor="form-employee-select"
              className="block text-xs font-semibold text-on-surface mb-1 font-heading"
            >
              Assign to Employee *
            </label>
            <select
              id="form-employee-select"
              value={formEmployeeId}
              onChange={(e) => setFormEmployeeId(e.target.value)}
              className="w-full px-space-3 py-space-2 rounded border border-outline/60 bg-surface text-sm font-medium focus:ring-2 focus:ring-primary"
              required
            >
              <option value="">-- Select Employee --</option>
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.full_name} {emp.employee_code ? `(${emp.employee_code})` : ''}
                </option>
              ))}
            </select>
          </div>

          {/* 2. Customer / Outlet Selection */}
          <div>
            <label
              htmlFor="customer-search-input"
              className="block text-xs font-semibold text-on-surface mb-1 font-heading"
            >
              Customer / Outlet *
            </label>
            <div className="relative mb-space-2">
              <Search className="w-4 h-4 text-on-surface-variant absolute left-3 top-2.5" />
              <input
                id="customer-search-input"
                type="text"
                placeholder="Search by outlet name, code, address..."
                value={customerSearchQuery}
                onChange={(e) => setCustomerSearchQuery(e.target.value)}
                className="w-full pl-9 pr-space-3 py-1.5 text-xs rounded border border-outline/50 bg-surface focus:outline-hidden focus:ring-2 focus:ring-primary"
              />
            </div>
            <select
              id="form-customer-select"
              value={formCustomerId}
              onChange={(e) => setFormCustomerId(e.target.value)}
              className="w-full px-space-3 py-space-2 rounded border border-outline/60 bg-surface text-sm font-medium focus:ring-2 focus:ring-primary max-h-40"
              required
            >
              <option value="">
                {customerSearchQuery.trim()
                  ? filteredCustomers.length > 0
                    ? `-- Select Outlet (${filteredCustomers.length} of ${customers.length} matching) --`
                    : `-- No Outlets Matching "${customerSearchQuery}" --`
                  : `-- Select Outlet (${customers.length} available) --`}
              </option>
              {filteredCustomers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} {c.outlet_code ? `[${c.outlet_code}]` : ''} - {c.address || 'No Address'}
                </option>
              ))}
            </select>
          </div>

          {/* 3. Planned Date */}
          <div>
            <label
              htmlFor="form-planned-date"
              className="block text-xs font-semibold text-on-surface mb-1 font-heading"
            >
              Planned Date *
            </label>
            <input
              id="form-planned-date"
              type="date"
              value={formPlannedDate}
              onChange={(e) => setFormPlannedDate(e.target.value)}
              className="w-full px-space-3 py-space-2 rounded border border-outline/60 bg-surface text-sm font-medium focus:ring-2 focus:ring-primary"
              required
            />
          </div>

          {/* 4. Priority & Visit Type */}
          <div className="grid grid-cols-2 gap-space-3">
            <div>
              <label
                htmlFor="form-priority-select"
                className="block text-xs font-semibold text-on-surface mb-1 font-heading"
              >
                Priority
              </label>
              <select
                id="form-priority-select"
                value={formPriority}
                onChange={(e) => setFormPriority(e.target.value as Priority)}
                className="w-full px-space-3 py-space-2 rounded border border-outline/60 bg-surface text-sm font-medium focus:ring-2 focus:ring-primary"
              >
                <option value="LOW">Low</option>
                <option value="MEDIUM">Medium</option>
                <option value="HIGH">High</option>
              </select>
            </div>

            <div>
              <label
                htmlFor="form-visit-type-select"
                className="block text-xs font-semibold text-on-surface mb-1 font-heading"
              >
                Visit Type
              </label>
              <select
                id="form-visit-type-select"
                value={formVisitType}
                onChange={(e) => setFormVisitType(e.target.value as VisitType)}
                className="w-full px-space-3 py-space-2 rounded border border-outline/60 bg-surface text-sm font-medium focus:ring-2 focus:ring-primary"
              >
                <option value="PLANNED">Planned</option>
                <option value="AD_HOC">Ad-Hoc</option>
              </select>
            </div>
          </div>

          {/* 5. Planning Notes */}
          <div>
            <label
              htmlFor="form-notes-input"
              className="block text-xs font-semibold text-on-surface mb-1 font-heading"
            >
              Notes / Objectives
            </label>
            <textarea
              id="form-notes-input"
              value={formNotes}
              onChange={(e) => setFormNotes(e.target.value)}
              placeholder="e.g., Monthly stock review, payment collection follow-up"
              rows={2}
              className="w-full px-space-3 py-space-2 rounded border border-outline/60 bg-surface text-sm font-body focus:ring-2 focus:ring-primary"
            />
          </div>

          {/* Modal Actions */}
          <div className="pt-space-2 border-t border-surface-container-highest flex items-center justify-end gap-space-2">
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
              disabled={isSubmitting}
              className="bg-primary-container text-white hover:bg-primary-container/90"
            >
              {isSubmitting ? 'Scheduling...' : 'Confirm Schedule'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* ========================================================================= */}
      {/* MODAL 2: Edit Planned Visit                                               */}
      {/* ========================================================================= */}
      <Modal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        title="Edit Planned Visit"
      >
        <form onSubmit={handleEditSubmit} className="space-y-space-4">
          {formError && <ErrorBanner message={formError} />}

          {activeVisit && (
            <div className="p-space-3 bg-surface-low rounded border border-surface-container-highest text-xs space-y-1">
              <div>
                <span className="text-on-surface-variant">Outlet:</span>{' '}
                <strong className="text-primary">{activeVisit.customer_name}</strong>
              </div>
              <div>
                <span className="text-on-surface-variant">Assigned Rep:</span>{' '}
                <strong>
                  {activeVisit.employee_name}{' '}
                  {activeVisit.employee_code ? `(${activeVisit.employee_code})` : ''}
                </strong>
              </div>
              <div>
                <span className="text-on-surface-variant">Date:</span>{' '}
                <strong>{formatDisplayDate(activeVisit.planned_date)}</strong>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-space-3">
            <div>
              <label
                htmlFor="edit-priority-select"
                className="block text-xs font-semibold text-on-surface mb-1 font-heading"
              >
                Priority
              </label>
              <select
                id="edit-priority-select"
                value={formPriority}
                onChange={(e) => setFormPriority(e.target.value as Priority)}
                className="w-full px-space-3 py-space-2 rounded border border-outline/60 bg-surface text-sm font-medium focus:ring-2 focus:ring-primary"
              >
                <option value="LOW">Low</option>
                <option value="MEDIUM">Medium</option>
                <option value="HIGH">High</option>
              </select>
            </div>

            <div>
              <label
                htmlFor="edit-visit-type-select"
                className="block text-xs font-semibold text-on-surface mb-1 font-heading"
              >
                Visit Type
              </label>
              <select
                id="edit-visit-type-select"
                value={formVisitType}
                onChange={(e) => setFormVisitType(e.target.value as VisitType)}
                className="w-full px-space-3 py-space-2 rounded border border-outline/60 bg-surface text-sm font-medium focus:ring-2 focus:ring-primary"
              >
                <option value="PLANNED">Planned</option>
                <option value="AD_HOC">Ad-Hoc</option>
              </select>
            </div>
          </div>

          <div>
            <label
              htmlFor="edit-notes-input"
              className="block text-xs font-semibold text-on-surface mb-1 font-heading"
            >
              Notes
            </label>
            <textarea
              id="edit-notes-input"
              value={formNotes}
              onChange={(e) => setFormNotes(e.target.value)}
              rows={3}
              className="w-full px-space-3 py-space-2 rounded border border-outline/60 bg-surface text-sm font-body focus:ring-2 focus:ring-primary"
            />
          </div>

          <div className="pt-space-2 border-t border-surface-container-highest flex items-center justify-end gap-space-2">
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
              disabled={isSubmitting}
              className="bg-primary-container text-white hover:bg-primary-container/90"
            >
              {isSubmitting ? 'Saving...' : 'Save Changes'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* ========================================================================= */}
      {/* MODAL 3: Reschedule Planned Visit                                         */}
      {/* ========================================================================= */}
      <Modal
        isOpen={isRescheduleModalOpen}
        onClose={() => setIsRescheduleModalOpen(false)}
        title="Reschedule Planned Visit"
      >
        <form onSubmit={handleRescheduleSubmit} className="space-y-space-4">
          {formError && <ErrorBanner message={formError} />}

          {activeVisit && (
            <div className="p-space-3 bg-surface-low rounded border border-surface-container-highest text-xs space-y-1">
              <div>
                <span className="text-on-surface-variant">Outlet:</span>{' '}
                <strong className="text-primary">{activeVisit.customer_name}</strong>
              </div>
              <div>
                <span className="text-on-surface-variant">Assigned Rep:</span>{' '}
                <strong>
                  {activeVisit.employee_name}{' '}
                  {activeVisit.employee_code ? `(${activeVisit.employee_code})` : ''}
                </strong>
              </div>
              <div>
                <span className="text-on-surface-variant">Current Date:</span>{' '}
                <span className="text-rose-700 font-semibold line-through">
                  {formatDisplayDate(activeVisit.planned_date)}
                </span>
              </div>
            </div>
          )}

          <div>
            <label
              htmlFor="reschedule-date-input"
              className="block text-xs font-semibold text-on-surface mb-1 font-heading"
            >
              New Target Date *
            </label>
            <input
              id="reschedule-date-input"
              type="date"
              value={rescheduleDate}
              onChange={(e) => setRescheduleDate(e.target.value)}
              className="w-full px-space-3 py-space-2 rounded border border-outline/60 bg-surface text-sm font-medium focus:ring-2 focus:ring-primary"
              required
            />
          </div>

          <div className="text-xs text-on-surface-variant italic bg-surface-low p-space-2 rounded border border-outline/20">
            Rescheduling across months will automatically migrate this visit into the target
            month&apos;s plan for this employee.
          </div>

          <div className="pt-space-2 border-t border-surface-container-highest flex items-center justify-end gap-space-2">
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
              disabled={isSubmitting}
              className="bg-primary-container text-white hover:bg-primary-container/90"
            >
              {isSubmitting ? 'Rescheduling...' : 'Confirm New Date'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* ========================================================================= */}
      {/* MODAL 4: Reassign Planned Visit (Current Employee -> New Employee)         */}
      {/* ========================================================================= */}
      <Modal
        isOpen={isReassignModalOpen}
        onClose={() => setIsReassignModalOpen(false)}
        title="Reassign Planned Visit"
      >
        <form onSubmit={handleReassignSubmit} className="space-y-space-4">
          {formError && <ErrorBanner message={formError} />}

          {activeVisit && (
            <div className="p-space-3 bg-surface-low rounded border border-surface-container-highest text-xs space-y-1">
              <div>
                <span className="text-on-surface-variant">Customer / Outlet:</span>{' '}
                <strong className="text-primary">{activeVisit.customer_name}</strong>
              </div>
              <div>
                <span className="text-on-surface-variant">Date:</span>{' '}
                <strong>{formatDisplayDate(activeVisit.planned_date)}</strong>
              </div>
            </div>
          )}

          {/* Visual Reassignment Flow Card */}
          <div className="p-space-4 bg-surface-low rounded border border-surface-container-highest">
            <div className="text-xs font-semibold text-on-surface-variant uppercase tracking-wide mb-space-3 text-center">
              Reassignment Transfer Flow
            </div>
            <div className="flex flex-col sm:flex-row items-center justify-between gap-space-3">
              {/* Current Employee */}
              <div className="w-full sm:w-1/2 p-space-3 bg-surface rounded border border-outline/30 text-center space-y-1">
                <span className="text-[10px] uppercase font-bold text-rose-700 bg-rose-50 px-2 py-0.5 rounded">
                  Current Owner
                </span>
                <p className="font-heading font-bold text-sm text-on-surface mt-1">
                  {activeVisit?.employee_name || 'Unassigned'}
                </p>
                <p className="text-xs text-on-surface-variant">
                  {activeVisit?.employee_code || ''}
                </p>
              </div>

              {/* Transfer Arrow */}
              <div className="p-space-2 rounded-full bg-surface-high text-primary shrink-0">
                <ArrowRight className="w-5 h-5 rotate-90 sm:rotate-0" />
              </div>

              {/* Target Employee Selector */}
              <div className="w-full sm:w-1/2 p-space-3 bg-surface rounded border border-primary/40 text-center space-y-1">
                <span className="text-[10px] uppercase font-bold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded">
                  New Owner *
                </span>
                <div className="mt-1">
                  <select
                    id="reassign-target-employee-select"
                    value={targetEmployeeId}
                    onChange={(e) => setTargetEmployeeId(e.target.value)}
                    className="w-full px-space-2 py-space-1.5 rounded border border-outline/50 bg-surface text-xs font-medium focus:ring-2 focus:ring-primary"
                    required
                  >
                    <option value="">-- Select Target --</option>
                    {employees
                      .filter((emp) => emp.id !== activeVisit?.employee_id)
                      .map((emp) => (
                        <option key={emp.id} value={emp.id}>
                          {emp.full_name} {emp.employee_code ? `(${emp.employee_code})` : ''}
                        </option>
                      ))}
                  </select>
                </div>
              </div>
            </div>
          </div>

          {/* Confirmation Notice */}
          <div className="p-space-3 bg-amber/10 border border-amber/30 rounded text-xs text-secondary flex items-start gap-space-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-secondary" />
            <span>
              This action will remove the planned visit from the current employee&apos;s schedule
              and transfer it to the selected employee&apos;s monthly visit plan.
            </span>
          </div>

          <div className="pt-space-2 border-t border-surface-container-highest flex items-center justify-end gap-space-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsReassignModalOpen(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isSubmitting}
              className="bg-primary-container text-white hover:bg-primary-container/90"
            >
              {isSubmitting ? 'Reassigning...' : 'Confirm Reassignment'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* ========================================================================= */}
      {/* MODAL 5: Delete / Cancel Planned Visit Confirmation                       */}
      {/* ========================================================================= */}
      <Modal
        isOpen={isDeleteModalOpen}
        onClose={() => setIsDeleteModalOpen(false)}
        title="Delete Planned Visit"
      >
        <div className="space-y-space-4">
          {formError && <ErrorBanner message={formError} />}

          {activeVisit && (
            <div className="p-space-4 bg-rose-50 border border-rose-200 rounded text-sm text-rose-900 space-y-1.5">
              <p className="font-semibold">
                Are you sure you want to delete this planned visit?
              </p>
              <div className="text-xs text-rose-800">
                <p>Outlet: <strong>{activeVisit.customer_name}</strong></p>
                <p>Employee: <strong>{activeVisit.employee_name}</strong></p>
                <p>Date: <strong>{formatDisplayDate(activeVisit.planned_date)}</strong></p>
              </div>
            </div>
          )}

          <div className="pt-space-2 border-t border-surface-container-highest flex items-center justify-end gap-space-2">
            <Button
              variant="outline"
              onClick={() => setIsDeleteModalOpen(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={handleDeleteSubmit}
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Deleting...' : 'Delete Planned Visit'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
