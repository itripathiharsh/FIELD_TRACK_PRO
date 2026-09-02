import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  Search,
  Calendar,
  RefreshCw,
  ChevronRight,
  UserCheck,
  Clock,
  CheckCircle2,
  AlertCircle,
  Wallet,
  ArrowUpDown,
  Download,
  Filter,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { TodayFieldActivityOverview, EmployeeWorkdaySessionItem } from '../types';

const formatCurrency = (value: string | number | undefined | null): string => {
  if (value === undefined || value === null) return '₹0';
  const num = typeof value === 'number' ? value : parseFloat(value) || 0;
  return `₹${num.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
};

export const EmployeeDailyLogsPage: React.FC = () => {
  const navigate = useNavigate();

  const todayStr = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const [selectedDate, setSelectedDate] = useState<string>(todayStr);

  const [overview, setOverview] = useState<TodayFieldActivityOverview | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [sortBy, setSortBy] = useState<'name' | 'visits' | 'collections' | 'status'>('name');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');

  const fetchDailyLogs = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getTodayFieldOverview(
        selectedDate !== todayStr ? selectedDate : undefined
      );
      setOverview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load employee daily logs');
    } finally {
      setIsLoading(false);
    }
  }, [selectedDate, todayStr]);

  useEffect(() => {
    fetchDailyLogs();
  }, [fetchDailyLogs]);

  // Filtered and sorted sessions
  const filteredSessions = useMemo(() => {
    if (!overview?.sessions) return [];

    const list = overview.sessions.filter((s: EmployeeWorkdaySessionItem) => {
      if (statusFilter !== 'ALL' && s.status !== statusFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesName = s.employee_name.toLowerCase().includes(q);
        const matchesCode = (s.employee_code || '').toLowerCase().includes(q);
        if (!matchesName && !matchesCode) return false;
      }
      return true;
    });

    list.sort((a, b) => {
      let comparison = 0;
      if (sortBy === 'name') {
        comparison = a.employee_name.localeCompare(b.employee_name);
      } else if (sortBy === 'visits') {
        comparison = (b.visits_completed || 0) - (a.visits_completed || 0);
      } else if (sortBy === 'collections') {
        const collA = parseFloat(a.collections_amount || '0') || 0;
        const collB = parseFloat(b.collections_amount || '0') || 0;
        comparison = collB - collA;
      } else if (sortBy === 'status') {
        comparison = a.status.localeCompare(b.status);
      }
      return sortOrder === 'asc' ? comparison : -comparison;
    });

    return list;
  }, [overview?.sessions, statusFilter, searchQuery, sortBy, sortOrder]);

  // Aggregate Metrics
  const metrics = useMemo(() => {
    if (!overview?.sessions) {
      return {
        totalReps: 0,
        activeReps: 0,
        completedReps: 0,
        notStartedReps: 0,
        totalVisits: 0,
        completedVisits: 0,
        totalCollections: 0,
      };
    }

    const sessions = overview.sessions;
    const totalReps = sessions.length;
    const activeReps = sessions.filter((s) => s.status === 'STARTED').length;
    const completedReps = sessions.filter((s) => s.status === 'COMPLETED').length;
    const notStartedReps = sessions.filter((s) => s.status === 'NOT_STARTED').length;
    const totalVisits = sessions.reduce((acc, s) => acc + (s.visits_total || 0), 0);
    const completedVisits = sessions.reduce((acc, s) => acc + (s.visits_completed || 0), 0);
    const totalCollections = sessions.reduce(
      (acc, s) => acc + (parseFloat(s.collections_amount || '0') || 0),
      0
    );

    return {
      totalReps,
      activeReps,
      completedReps,
      notStartedReps,
      totalVisits,
      completedVisits,
      totalCollections,
    };
  }, [overview?.sessions]);

  const handleExportCSV = () => {
    if (!filteredSessions.length) return;
    const headers = [
      'Employee Name',
      'Employee Code',
      'Status',
      'Start Time',
      'Accuracy (m)',
      'Total Visits',
      'Planned Visits',
      'Ad-hoc Visits',
      'Completed Visits',
      'Collections Amount (INR)',
    ];

    const rows = filteredSessions.map((s) => [
      `"${s.employee_name.replace(/"/g, '""')}"`,
      `"${s.employee_code || ''}"`,
      s.status,
      s.start_time ? new Date(s.start_time).toLocaleTimeString() : 'N/A',
      s.start_accuracy_meters ? Math.round(s.start_accuracy_meters) : 'N/A',
      s.visits_total,
      s.visits_planned,
      s.visits_adhoc,
      s.visits_completed,
      parseFloat(s.collections_amount || '0') || 0,
    ]);

    const csvContent =
      'data:text/csv;charset=utf-8,' +
      [headers.join(','), ...rows.map((e) => e.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `employee_daily_logs_${selectedDate}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Top Header & Date Navigation */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-surface p-5 rounded-2xl border border-outline-variant/50 shadow-xs">
        <div>
          <div className="flex items-center gap-2 text-primary font-bold text-xs uppercase tracking-wider mb-1">
            <Users className="w-4 h-4" />
            <span>Field Operations</span>
          </div>
          <h1 className="text-xl md:text-2xl font-bold font-headline-md text-primary tracking-tight">
            Employee Daily Logs
          </h1>
          <p className="text-xs text-on-surface-variant mt-0.5">
            Real-time shift tracking, GPS check-ins, planned vs ad-hoc visits, and field collections per representative.
          </p>
        </div>

        {/* Date Controls & Actions */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center bg-surface-container-low border border-outline-variant rounded-xl p-1 shadow-xs">
            <button
              onClick={() => setSelectedDate(todayStr)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                selectedDate === todayStr
                  ? 'bg-primary text-on-primary shadow-xs'
                  : 'text-on-surface hover:bg-surface-container'
              }`}
            >
              Today
            </button>
            <button
              onClick={() => {
                const d = new Date();
                d.setDate(d.getDate() - 1);
                setSelectedDate(d.toISOString().slice(0, 10));
              }}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
                selectedDate !== todayStr &&
                selectedDate === new Date(Date.now() - 86400000).toISOString().slice(0, 10)
                  ? 'bg-primary text-on-primary shadow-xs'
                  : 'text-on-surface hover:bg-surface-container'
              }`}
            >
              Yesterday
            </button>
            <div className="flex items-center pl-2 pr-2 border-l border-outline-variant/60 ml-1">
              <Calendar className="w-3.5 h-3.5 text-on-surface-variant mr-1.5 shrink-0" />
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="text-xs bg-transparent border-0 focus:ring-0 text-on-surface font-semibold cursor-pointer outline-none"
              />
            </div>
          </div>

          <button
            onClick={fetchDailyLogs}
            disabled={isLoading}
            title="Refresh Logs"
            className="p-2.5 bg-surface border border-outline-variant rounded-xl hover:bg-surface-container text-on-surface transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-primary' : ''}`} />
          </button>

          <button
            onClick={handleExportCSV}
            disabled={!filteredSessions.length}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold bg-surface border border-outline-variant text-on-surface rounded-xl hover:bg-surface-container transition-colors disabled:opacity-40"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export CSV</span>
          </button>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="p-4 rounded-xl bg-error-container/20 border border-error/30 text-error flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span className="text-xs font-medium">{error}</span>
          </div>
          <button onClick={fetchDailyLogs} className="text-xs font-bold underline hover:opacity-80">
            Retry
          </button>
        </div>
      )}

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-4 gap-3.5">
        <div className="p-4 rounded-2xl bg-surface border border-outline-variant/50 shadow-xs flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-primary-container/60 text-secondary-container flex items-center justify-center shrink-0">
            <Users className="w-5 h-5" />
          </div>
          <div>
            <span className="text-[11px] font-semibold text-on-surface-variant uppercase tracking-wider block">
              Field Force
            </span>
            <div className="flex items-baseline gap-1.5 mt-0.5">
              <span className="text-xl font-bold text-primary font-headline-sm">{metrics.totalReps}</span>
              <span className="text-[11px] text-on-surface-variant">Reps Total</span>
            </div>
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-surface border border-outline-variant/50 shadow-xs flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 flex items-center justify-center shrink-0">
            <UserCheck className="w-5 h-5" />
          </div>
          <div>
            <span className="text-[11px] font-semibold text-on-surface-variant uppercase tracking-wider block">
              Active / In Field
            </span>
            <div className="flex items-baseline gap-1.5 mt-0.5">
              <span className="text-xl font-bold text-emerald-600 font-headline-sm">{metrics.activeReps}</span>
              <span className="text-[11px] text-on-surface-variant">
                ({metrics.completedReps} completed)
              </span>
            </div>
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-surface border border-outline-variant/50 shadow-xs flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-blue-100 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 flex items-center justify-center shrink-0">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div>
            <span className="text-[11px] font-semibold text-on-surface-variant uppercase tracking-wider block">
              Visits Executed
            </span>
            <div className="flex items-baseline gap-1.5 mt-0.5">
              <span className="text-xl font-bold text-blue-600 font-headline-sm">{metrics.completedVisits}</span>
              <span className="text-[11px] text-on-surface-variant">/ {metrics.totalVisits} visits</span>
            </div>
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-surface border border-outline-variant/50 shadow-xs flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 flex items-center justify-center shrink-0">
            <Wallet className="w-5 h-5" />
          </div>
          <div>
            <span className="text-[11px] font-semibold text-on-surface-variant uppercase tracking-wider block">
              Field Collections
            </span>
            <div className="flex items-baseline gap-1.5 mt-0.5">
              <span className="text-xl font-bold text-primary font-headline-sm">
                {formatCurrency(metrics.totalCollections)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Table Section */}
      <div className="bg-surface rounded-2xl border border-outline-variant/50 shadow-xs overflow-hidden">
        {/* Table Filters Bar */}
        <div className="p-4 border-b border-outline-variant/40 flex flex-wrap items-center justify-between gap-3 bg-surface-container-low/30">
          <div className="flex flex-wrap items-center gap-3 flex-1 min-w-[260px]">
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant" />
              <input
                type="text"
                placeholder="Search representative name or employee code..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full h-9 pl-9 pr-3 text-xs bg-surface border border-outline-variant rounded-xl focus:outline-none focus:border-primary text-on-surface font-medium"
              />
            </div>

            <div className="flex items-center gap-1.5">
              <Filter className="w-3.5 h-3.5 text-on-surface-variant" />
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="h-9 px-3 text-xs bg-surface border border-outline-variant rounded-xl focus:outline-none focus:border-primary text-on-surface font-medium cursor-pointer"
              >
                <option value="ALL">All Statuses</option>
                <option value="STARTED">Active / Started</option>
                <option value="COMPLETED">Shift Completed</option>
                <option value="NOT_STARTED">Not Started</option>
              </select>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs text-on-surface-variant font-medium">
              Showing <strong className="text-on-surface">{filteredSessions.length}</strong> of {metrics.totalReps} representatives
            </span>
          </div>
        </div>

        {/* Data Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-surface-container-low text-on-surface-variant uppercase tracking-wider font-semibold border-b border-outline-variant/30">
              <tr>
                <th
                  onClick={() => {
                    if (sortBy === 'name') setSortOrder((o) => (o === 'asc' ? 'desc' : 'asc'));
                    else {
                      setSortBy('name');
                      setSortOrder('asc');
                    }
                  }}
                  className="px-4 py-3 cursor-pointer hover:text-primary transition-colors select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>Employee</span>
                    <ArrowUpDown className="w-3 h-3 text-on-surface-variant" />
                  </div>
                </th>
                <th
                  onClick={() => {
                    if (sortBy === 'status') setSortOrder((o) => (o === 'asc' ? 'desc' : 'asc'));
                    else {
                      setSortBy('status');
                      setSortOrder('asc');
                    }
                  }}
                  className="px-4 py-3 cursor-pointer hover:text-primary transition-colors select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>Status</span>
                    <ArrowUpDown className="w-3 h-3 text-on-surface-variant" />
                  </div>
                </th>
                <th className="px-4 py-3">Start GPS &amp; Accuracy</th>
                <th
                  onClick={() => {
                    if (sortBy === 'visits') setSortOrder((o) => (o === 'asc' ? 'desc' : 'asc'));
                    else {
                      setSortBy('visits');
                      setSortOrder('desc');
                    }
                  }}
                  className="px-4 py-3 cursor-pointer hover:text-primary transition-colors select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>Visits Breakdown</span>
                    <ArrowUpDown className="w-3 h-3 text-on-surface-variant" />
                  </div>
                </th>
                <th className="px-4 py-3">Completion Rate</th>
                <th
                  onClick={() => {
                    if (sortBy === 'collections') setSortOrder((o) => (o === 'asc' ? 'desc' : 'asc'));
                    else {
                      setSortBy('collections');
                      setSortOrder('desc');
                    }
                  }}
                  className="px-4 py-3 cursor-pointer hover:text-primary transition-colors select-none"
                >
                  <div className="flex items-center gap-1">
                    <span>Collections (₹)</span>
                    <ArrowUpDown className="w-3 h-3 text-on-surface-variant" />
                  </div>
                </th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/20">
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-on-surface-variant">
                    <div className="inline-flex items-center gap-2">
                      <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                      <span>Loading employee daily logs for {selectedDate}...</span>
                    </div>
                  </td>
                </tr>
              ) : filteredSessions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-on-surface-variant">
                    <div className="max-w-xs mx-auto space-y-2">
                      <Clock className="w-8 h-8 text-on-surface-variant/60 mx-auto" />
                      <p className="font-semibold text-sm text-on-surface">No daily log records found</p>
                      <p className="text-xs text-on-surface-variant">
                        No field representative activity recorded for {selectedDate} matching your filters.
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredSessions.map((s) => {
                  const visitPct =
                    s.visits_total > 0 ? Math.round((s.visits_completed / s.visits_total) * 100) : 0;
                  return (
                    <tr key={s.employee_id} className="hover:bg-surface-container-low/50 transition-colors">
                      {/* Rep Info */}
                      <td className="px-4 py-3.5">
                        <div className="flex items-center gap-2.5">
                          <div className="w-7 h-7 rounded-full bg-primary-container text-secondary-container font-bold text-xs flex items-center justify-center shrink-0 uppercase">
                            {s.employee_name.charAt(0)}
                          </div>
                          <div>
                            <span className="font-semibold text-on-surface block text-xs">
                              {s.employee_name}
                            </span>
                            {s.employee_code && (
                              <span className="text-[11px] text-on-surface-variant font-mono">
                                #{s.employee_code}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>

                      {/* Status */}
                      <td className="px-4 py-3.5">
                        <span
                          className={`inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold tracking-wide uppercase ${
                            s.status === 'STARTED'
                              ? 'bg-emerald-100 text-emerald-900 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800'
                              : s.status === 'COMPLETED'
                              ? 'bg-indigo-100 text-indigo-900 dark:bg-indigo-950/60 dark:text-indigo-300 border border-indigo-300 dark:border-indigo-800'
                              : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border border-slate-300 dark:border-slate-700'
                          }`}
                        >
                          {s.status === 'STARTED'
                            ? 'ACTIVE IN FIELD'
                            : s.status === 'COMPLETED'
                            ? 'SHIFT COMPLETED'
                            : 'NOT STARTED'}
                        </span>
                      </td>

                      {/* Start Time & GPS */}
                      <td className="px-4 py-3.5 font-mono text-xs">
                        {s.start_time ? (
                          <div>
                            <span className="font-semibold text-on-surface">
                              {new Date(s.start_time).toLocaleTimeString([], {
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </span>
                            {s.start_accuracy_meters && (
                              <span className="text-[10px] text-on-surface-variant ml-1 font-sans">
                                (±{Math.round(s.start_accuracy_meters)}m)
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-on-surface-variant font-sans text-[11px]">—</span>
                        )}
                      </td>

                      {/* Visits Breakdown */}
                      <td className="px-4 py-3.5">
                        <div>
                          <span className="font-bold text-on-surface text-xs">{s.visits_total}</span>
                          <span className="text-[11px] text-on-surface-variant ml-1">
                            ({s.visits_planned} plan + {s.visits_adhoc} adhoc)
                          </span>
                        </div>
                      </td>

                      {/* Progress Bar */}
                      <td className="px-4 py-3.5">
                        <div className="space-y-1 w-28">
                          <div className="flex items-center justify-between text-[10px]">
                            <span className="font-bold text-emerald-600">{s.visits_completed} done</span>
                            <span className="text-on-surface-variant font-mono">{visitPct}%</span>
                          </div>
                          <div className="w-full h-1.5 bg-surface-container rounded-full overflow-hidden">
                            <div
                              className="h-full bg-emerald-500 rounded-full transition-all duration-300"
                              style={{ width: `${Math.min(visitPct, 100)}%` }}
                            />
                          </div>
                        </div>
                      </td>

                      {/* Collections */}
                      <td className="px-4 py-3.5">
                        <span className="font-bold text-on-surface text-xs">
                          {formatCurrency(s.collections_amount)}
                        </span>
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-3.5 text-right">
                        <button
                          onClick={() => navigate(`/employees/${s.employee_id}`)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold text-primary bg-primary-container/40 hover:bg-primary-container rounded-lg transition-colors cursor-pointer"
                        >
                          <span>Profile</span>
                          <ChevronRight className="w-3 h-3" />
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
