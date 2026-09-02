import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Mail,
  Phone,
  MapPin,
  Calendar,
  CalendarCheck,
  Wallet,
  PackagePlus,
  History,
  Plus,
  Layers,
  X,
  Edit2,
  Clock,
  Compass,
  ExternalLink,
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { EmptyState } from '../components/ui/EmptyState';
import { StatusBadge } from '../components/ui/StatusBadge';
import { MetricCard } from '../components/ui/MetricCard';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { Select } from '../components/ui/Select';
import { Input } from '../components/ui/Input';

import { apiClient } from '../api/client';
import { Area, AssignmentType, Employee, EmployeeActivity, EmployeeAreaAssignment, EmployeeWorkdayResponse, Territory, TerritoryAssignmentHistory } from '../types';

const formatCurrency = (value: string): string => `₹${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

/**
 * Employee Detail page — profile, consolidated activity (P2-C), and
 * territory assignment history (P2-D).
 */
export const EmployeeDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [activity, setActivity] = useState<EmployeeActivity | null>(null);
  const [territoryHistory, setTerritoryHistory] = useState<TerritoryAssignmentHistory | null>(null);
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [coverage, setCoverage] = useState<EmployeeAreaAssignment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isReassignOpen, setIsReassignOpen] = useState(false);
  const [reassignType, setReassignType] = useState<AssignmentType>('PERMANENT');
  const [reassignTerritoryId, setReassignTerritoryId] = useState('');
  const [reassignStartDate, setReassignStartDate] = useState(new Date().toISOString().slice(0, 10));
  const [reassignEndDate, setReassignEndDate] = useState('');
  const [reassignError, setReassignError] = useState<string | null>(null);
  const [isReassigning, setIsReassigning] = useState(false);

  // Area Coverage modal state (brand-agnostic many-to-many: independent of,
  // and additive to, the single-Zone Territory Assignment section above).
  const [isCoverageModalOpen, setIsCoverageModalOpen] = useState(false);
  const [coverageAreaId, setCoverageAreaId] = useState('');
  const [coverageError, setCoverageError] = useState<string | null>(null);
  const [isSavingCoverage, setIsSavingCoverage] = useState(false);

  // Edit Profile modal state
  const [isEditProfileOpen, setIsEditProfileOpen] = useState(false);
  const [editFullName, setEditFullName] = useState('');
  const [editEmployeeCode, setEditEmployeeCode] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editMobile, setEditMobile] = useState('');
  const [editWorkingProfile, setEditWorkingProfile] = useState('');
  const [editDob, setEditDob] = useState('');
  const [editAddress, setEditAddress] = useState('');
  const [editFieldErrors, setEditFieldErrors] = useState<Record<string, string>>({});
  const [editProfileError, setEditProfileError] = useState<string | null>(null);
  const [isSavingProfile, setIsSavingProfile] = useState(false);

  // Workday & Daily Field Session state
  const [selectedWorkDate, setSelectedWorkDate] = useState<string>(new Date().toISOString().slice(0, 10));
  const [workdayData, setWorkdayData] = useState<EmployeeWorkdayResponse | null>(null);
  const [isWorkdayLoading, setIsWorkdayLoading] = useState<boolean>(false);

  const loadWorkday = useCallback(async (targetDate: string) => {
    if (!id) return;
    try {
      setIsWorkdayLoading(true);
      const res = await apiClient.getEmployeeWorkday(id, targetDate);
      setWorkdayData(res);
    } catch {
      setWorkdayData(null);
    } finally {
      setIsWorkdayLoading(false);
    }
  }, [id]);

  useEffect(() => {
    loadWorkday(selectedWorkDate);
  }, [loadWorkday, selectedWorkDate]);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      setIsLoading(true);
      const [emp, act, history, terrs, allAreas, areaCoverage] = await Promise.all([
        apiClient.getEmployeeById(id),
        apiClient.getEmployeeActivity(id).catch(() => null),
        apiClient.getTerritoryAssignmentHistory(id).catch(() => null),
        apiClient.getTerritories().catch(() => [] as Territory[]),
        apiClient.getAreas().catch(() => [] as Area[]),
        apiClient.getEmployeeAreaCoverage(id).catch(() => [] as EmployeeAreaAssignment[]),
      ]);
      setEmployee(emp);
      setActivity(act);
      setTerritoryHistory(history);
      setTerritories(terrs);
      setAreas(allAreas);
      setCoverage(areaCoverage);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load employee');
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  const openCoverageModal = () => {
    setCoverageAreaId('');
    setCoverageError(null);
    setIsCoverageModalOpen(true);
  };

  const handleAssignCoverage = async () => {
    if (!id || !coverageAreaId) return;
    setCoverageError(null);
    setIsSavingCoverage(true);
    try {
      await apiClient.assignEmployeeArea(id, coverageAreaId);
      setIsCoverageModalOpen(false);
      await load();
    } catch (err) {
      setCoverageError(err instanceof Error ? err.message : 'Failed to assign area');
    } finally {
      setIsSavingCoverage(false);
    }
  };

  const handleUnassignCoverage = async (areaId: string, name: string) => {
    if (!id || !window.confirm(`Remove this employee's coverage of "${name}"?`)) return;
    try {
      await apiClient.unassignEmployeeArea(id, areaId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove area coverage');
    }
  };

  // Areas not already covered - what the "Assign" modal offers.
  const uncoveredAreas = areas.filter((a) => !coverage.some((c) => c.area_id === a.id));

  useEffect(() => {
    load();
  }, [load]);

  const openEditProfileModal = () => {
    if (!employee) return;
    setEditFullName(employee.full_name);
    setEditEmployeeCode(employee.employee_code || '');
    setEditEmail(employee.user?.email || '');
    setEditMobile(employee.user?.mobile_number || '');
    setEditWorkingProfile(employee.working_profile || '');
    setEditDob(employee.date_of_birth ? String(employee.date_of_birth) : '');
    setEditAddress(employee.address || '');
    setEditFieldErrors({});
    setEditProfileError(null);
    setIsEditProfileOpen(true);
  };

  const handleSaveProfile = async () => {
    if (!id || !employee) return;
    setEditProfileError(null);
    setEditFieldErrors({});
    setIsSavingProfile(true);
    try {
      await apiClient.updateEmployee(id, {
        full_name: editFullName.trim() || undefined,
        employee_code: editEmployeeCode.trim().toUpperCase() || null,
        email: editEmail.trim() || undefined,
        mobile_number: editMobile.trim() || null,
        working_profile: editWorkingProfile.trim() || null,
        date_of_birth: editDob.trim() || null,
        address: editAddress.trim() || null,
      });
      setIsEditProfileOpen(false);
      await load();
    } catch (err: any) {
      if (err?.fieldErrors) {
        setEditFieldErrors(err.fieldErrors);
      }
      setEditProfileError(err instanceof Error ? err.message : 'Failed to update employee profile');
    } finally {
      setIsSavingProfile(false);
    }
  };

  const openReassignModal = () => {
    setReassignType('PERMANENT');
    setReassignTerritoryId(territories[0]?.id || '');
    setReassignStartDate(new Date().toISOString().slice(0, 10));
    setReassignEndDate('');
    setReassignError(null);
    setIsReassignOpen(true);
  };

  const handleCreateReassignment = async () => {
    if (!id || !reassignTerritoryId) return;
    setReassignError(null);
    setIsReassigning(true);
    try {
      await apiClient.createTerritoryAssignment(id, {
        territory_id: reassignTerritoryId,
        assignment_type: reassignType,
        start_date: reassignStartDate,
        end_date: reassignType === 'TEMPORARY' ? reassignEndDate : null,
      });
      setIsReassignOpen(false);
      await load();
    } catch (err) {
      setReassignError(err instanceof Error ? err.message : 'Failed to create reassignment');
    } finally {
      setIsReassigning(false);
    }
  };

  if (isLoading) return (
    <div className="flex items-center justify-center h-64" role="status">
      <div className="w-10 h-10 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin" />
    </div>
  );
  if (error) return <ErrorBanner message={error} onRetry={load} />;
  if (!employee) return <EmptyState title="Employee not found" subtitle="The requested employee could not be found." />;

  return (
    <div className="space-y-space-6">
      <PageHeader
        title={employee.full_name}
        subtitle="Employee profile, activity, and territory assignment."
        actions={
          <button
            onClick={() => navigate('/employees')}
            className="flex items-center gap-2 text-sm text-on-surface-variant hover:text-on-surface"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Employees
          </button>
        }
      />

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Profile</CardTitle>
            <CardSubtitle>Employee information</CardSubtitle>
          </div>
          <Button variant="outline" size="sm" icon={Edit2} onClick={openEditProfileModal}>
            Edit Profile
          </Button>
        </CardHeader>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-space-4 p-space-5">
          <div className="flex items-center gap-space-2">
            <Mail className="w-4 h-4 text-on-surface-variant" />
            <span className="text-sm">{employee.user?.email || employee.user_id || '—'}</span>
          </div>
          <div className="flex items-center gap-space-2">
            <Phone className="w-4 h-4 text-on-surface-variant" />
            <span className="text-sm">{employee.user?.mobile_number || '—'}</span>
          </div>
          <div className="flex items-center gap-space-2">
            <MapPin className="w-4 h-4 text-on-surface-variant" />
            <span className="text-sm">
              Territory: {territoryHistory?.effective_territory_name || activity?.territory_name || 'Unassigned'}
            </span>
          </div>
          <div className="flex items-center gap-space-2">
            <Calendar className="w-4 h-4 text-on-surface-variant" />
            <span className="text-sm">Code: {employee.employee_code || '—'}</span>
          </div>
        </div>
      </Card>

      {/* Daily Workday & Field Session Card */}
      <Card className="space-y-space-4">
        <CardHeader className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Clock className="w-5 h-5 text-primary" />
              <CardTitle>Daily Workday & Field Session</CardTitle>
            </div>
            <CardSubtitle>Start Day, End Day, GPS fixes, and field metrics for selected date.</CardSubtitle>
          </div>
          <div className="flex items-center gap-2">
            <Input
              type="date"
              value={selectedWorkDate}
              onChange={(e) => setSelectedWorkDate(e.target.value)}
              className="w-auto text-sm py-1.5"
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSelectedWorkDate(new Date().toISOString().slice(0, 10))}
            >
              Today
            </Button>
          </div>
        </CardHeader>

        {isWorkdayLoading ? (
          <div className="p-space-6 text-center text-on-surface-variant text-sm">
            Loading workday session...
          </div>
        ) : !workdayData?.session ? (
          <div className="p-space-4 rounded-lg bg-surface-container-low border border-surface-container-highest flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-500">
                <Clock className="w-5 h-5" />
              </div>
              <div>
                <p className="font-semibold text-sm">Workday Not Started</p>
                <p className="text-xs text-on-surface-variant">No work session recorded for {selectedWorkDate}.</p>
              </div>
            </div>
            {workdayData?.summary && (
              <div className="flex items-center gap-6 text-xs text-on-surface-variant">
                <span>Visits: <strong>{workdayData.summary.total_visits}</strong> ({workdayData.summary.planned_visits} planned, {workdayData.summary.adhoc_visits} ad-hoc)</span>
                <span>Collections: <strong>{formatCurrency(workdayData.summary.collections_total_amount)}</strong></span>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-space-4">
            {/* Status Banner */}
            <div className={`p-space-3 rounded-lg border flex items-center justify-between ${
              workdayData.session.status === 'COMPLETED'
                ? 'bg-emerald-50/50 border-emerald-200 text-emerald-900 dark:bg-emerald-950/20 dark:border-emerald-800 dark:text-emerald-300'
                : 'bg-amber-50/50 border-amber-200 text-amber-900 dark:bg-amber-950/20 dark:border-amber-800 dark:text-amber-300'
            }`}>
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${
                  workdayData.session.status === 'COMPLETED' ? 'bg-emerald-500' : 'bg-amber-500 animate-pulse'
                }`} />
                <span className="font-bold text-xs uppercase tracking-wider">
                  Workday {workdayData.session.status}
                </span>
              </div>
              <span className="text-xs font-medium">
                {workdayData.session.start_time && new Date(workdayData.session.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                {workdayData.session.end_time && ` — ${new Date(workdayData.session.end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
              </span>
            </div>

            {/* GPS & Timing Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-space-4">
              {/* Start Day Card */}
              <div className="p-space-4 rounded-lg bg-surface-container-low border border-surface-container-highest space-y-space-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-primary flex items-center gap-1.5">
                    <Compass className="w-3.5 h-3.5" /> Start Day Fix
                  </span>
                  <span className="text-xs font-mono text-on-surface-variant">
                    {workdayData.session.start_time ? new Date(workdayData.session.start_time).toLocaleTimeString() : '—'}
                  </span>
                </div>
                {workdayData.session.start_latitude != null && workdayData.session.start_longitude != null ? (
                  <div className="space-y-1">
                    <p className="text-xs text-on-surface font-mono">
                      {workdayData.session.start_latitude.toFixed(6)}, {workdayData.session.start_longitude.toFixed(6)}
                      {workdayData.session.start_accuracy_meters != null && (
                        <span className="text-on-surface-variant ml-2 font-sans text-[11px]">
                          (±{Math.round(workdayData.session.start_accuracy_meters)}m)
                        </span>
                      )}
                    </p>
                    <a
                      href={`https://www.google.com/maps/search/?api=1&query=${workdayData.session.start_latitude},${workdayData.session.start_longitude}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-primary hover:underline font-medium mt-1"
                    >
                      <ExternalLink className="w-3 h-3" /> View Location on Map
                    </a>
                  </div>
                ) : (
                  <p className="text-xs text-on-surface-variant">No GPS coordinates recorded.</p>
                )}
                {workdayData.session.start_notes && (
                  <p className="text-xs text-on-surface-variant italic pt-1 border-t border-surface-container-highest">
                    &quot;{workdayData.session.start_notes}&quot;
                  </p>
                )}
              </div>

              {/* End Day Card */}
              <div className="p-space-4 rounded-lg bg-surface-container-low border border-surface-container-highest space-y-space-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-primary flex items-center gap-1.5">
                    <Compass className="w-3.5 h-3.5" /> End Day Fix
                  </span>
                  <span className="text-xs font-mono text-on-surface-variant">
                    {workdayData.session.end_time ? new Date(workdayData.session.end_time).toLocaleTimeString() : 'In Progress...'}
                  </span>
                </div>
                {workdayData.session.end_latitude != null && workdayData.session.end_longitude != null ? (
                  <div className="space-y-1">
                    <p className="text-xs text-on-surface font-mono">
                      {workdayData.session.end_latitude.toFixed(6)}, {workdayData.session.end_longitude.toFixed(6)}
                      {workdayData.session.end_accuracy_meters != null && (
                        <span className="text-on-surface-variant ml-2 font-sans text-[11px]">
                          (±{Math.round(workdayData.session.end_accuracy_meters)}m)
                        </span>
                      )}
                    </p>
                    <a
                      href={`https://www.google.com/maps/search/?api=1&query=${workdayData.session.end_latitude},${workdayData.session.end_longitude}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-primary hover:underline font-medium mt-1"
                    >
                      <ExternalLink className="w-3 h-3" /> View Location on Map
                    </a>
                  </div>
                ) : (
                  <p className="text-xs text-on-surface-variant">
                    {workdayData.session.status === 'COMPLETED' ? 'No GPS coordinates recorded.' : 'Awaiting employee End Day submission.'}
                  </p>
                )}
                {workdayData.session.end_notes && (
                  <p className="text-xs text-on-surface-variant italic pt-1 border-t border-surface-container-highest">
                    &quot;{workdayData.session.end_notes}&quot;
                  </p>
                )}
              </div>
            </div>

            {/* Daily Operational Metrics */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-space-3 pt-2">
              <div className="p-space-3 rounded-lg bg-surface-container-low border border-surface-container-highest">
                <span className="text-[11px] uppercase tracking-wider text-on-surface-variant font-semibold">Total Visits</span>
                <p className="text-base font-bold text-on-surface mt-0.5">{workdayData.summary.total_visits}</p>
                <span className="text-[10px] text-on-surface-variant">{workdayData.summary.planned_visits} planned · {workdayData.summary.adhoc_visits} ad-hoc</span>
              </div>
              <div className="p-space-3 rounded-lg bg-surface-container-low border border-surface-container-highest">
                <span className="text-[11px] uppercase tracking-wider text-on-surface-variant font-semibold">Completed Visits</span>
                <p className="text-base font-bold text-emerald-600 mt-0.5">{workdayData.summary.completed_visits}</p>
                <span className="text-[10px] text-on-surface-variant">{workdayData.summary.missed_visits} missed · {workdayData.summary.flagged_visits} flagged</span>
              </div>
              <div className="p-space-3 rounded-lg bg-surface-container-low border border-surface-container-highest">
                <span className="text-[11px] uppercase tracking-wider text-on-surface-variant font-semibold">Total Collection</span>
                <p className="text-base font-bold text-on-surface mt-0.5">{formatCurrency(workdayData.summary.collections_total_amount)}</p>
                <span className="text-[10px] text-on-surface-variant">{workdayData.summary.collections_count} collection(s)</span>
              </div>
              <div className="p-space-3 rounded-lg bg-surface-container-low border border-surface-container-highest">
                <span className="text-[11px] uppercase tracking-wider text-on-surface-variant font-semibold">Verified Collection</span>
                <p className="text-base font-bold text-primary mt-0.5">{formatCurrency(workdayData.summary.collections_verified_amount)}</p>
                <span className="text-[10px] text-emerald-600 font-medium">Verified by Accounts</span>
              </div>
            </div>
          </div>
        )}
      </Card>

      {/* P2-C: Employee Activity */}
      <Card className="space-y-space-4">
        <CardHeader>
          <div>
            <CardTitle>Activity</CardTitle>
            <CardSubtitle>What this employee has actually done - visits, collections, and orders.</CardSubtitle>
          </div>
        </CardHeader>

        {!activity ? (
          <EmptyState title="No activity data" subtitle="Activity could not be loaded for this employee." />
        ) : (
          <div className="space-y-space-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-space-4">
              <MetricCard
                title="Visits"
                value={activity.visits_total}
                icon={CalendarCheck}
                color="primary"
                subtitle={`${activity.visits_planned ?? (activity.visits_total - (activity.visits_adhoc ?? 0))} planned · ${activity.visits_adhoc ?? 0} ad-hoc · ${activity.visits_completed} completed`}
              />
              <MetricCard title="Collections" value={activity.collections_total} icon={Wallet} color="secondary" subtitle={`${activity.collections_verified} verified (${formatCurrency(activity.collections_verified_amount)}) · ${activity.collections_pending} pending`} />
              <MetricCard title="Orders Captured" value={activity.orders_total} icon={PackagePlus} color="slate" />
              <MetricCard title="Rejected Collections" value={activity.collections_rejected} icon={Wallet} color={activity.collections_rejected > 0 ? 'rose' : 'slate'} />
            </div>

            <div>
              <p className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant font-semibold mb-space-2">
                Recent Visits
              </p>
              {activity.visits.length === 0 ? (
                <p className="font-caption text-xs text-on-surface-variant py-space-3 text-center">No visits recorded.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-surface-container-low text-on-surface-variant text-xs uppercase tracking-wider border-b border-surface-container-highest">
                      <tr>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Outlet</th>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Type</th>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Scheduled</th>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Duration</th>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Geo Failures</th>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-container-highest">
                      {activity.visits.slice(0, 20).map((v) => (
                        <tr key={v.id} className="hover:bg-surface-container-low/80">
                          <td className="px-space-3 py-space-2">
                            {v.customer_name}
                            {v.outlet_code && <span className="text-xs text-on-surface-variant font-mono ml-1">({v.outlet_code})</span>}
                          </td>
                          <td className="px-space-3 py-space-2">
                            {v.visit_type === 'AD_HOC' ? (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-900 border border-amber-300">
                                AD-HOC
                              </span>
                            ) : (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-800 border border-slate-300">
                                PLANNED
                              </span>
                            )}
                          </td>
                          <td className="px-space-3 py-space-2 text-on-surface-variant">{new Date(v.scheduled_at).toLocaleString()}</td>
                          <td className="px-space-3 py-space-2 text-on-surface-variant">{v.duration_minutes != null ? `${v.duration_minutes} min` : '—'}</td>
                          <td className={v.geo_failure_count > 0 ? 'px-space-3 py-space-2 text-error font-semibold' : 'px-space-3 py-space-2 text-on-surface-variant'}>
                            {v.geo_failure_count}
                          </td>
                          <td className="px-space-3 py-space-2">
                            <StatusBadge status={v.status} size="sm" />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div>
              <p className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant font-semibold mb-space-2">
                Recent Collections
              </p>
              {activity.collections.length === 0 ? (
                <p className="font-caption text-xs text-on-surface-variant py-space-3 text-center">No collections recorded.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-surface-container-low text-on-surface-variant text-xs uppercase tracking-wider border-b border-surface-container-highest">
                      <tr>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Outlet</th>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Amount</th>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Method</th>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Date</th>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-container-highest">
                      {activity.collections.slice(0, 20).map((c) => (
                        <tr key={c.id} className="hover:bg-surface-container-low/80">
                          <td className="px-space-3 py-space-2">{c.customer_name || '—'}</td>
                          <td className="px-space-3 py-space-2 font-medium">{formatCurrency(c.amount)}</td>
                          <td className="px-space-3 py-space-2 text-on-surface-variant">{c.payment_method}</td>
                          <td className="px-space-3 py-space-2 text-on-surface-variant">{c.payment_date}</td>
                          <td className="px-space-3 py-space-2">
                            <StatusBadge status={c.status} size="sm" />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {activity.orders.length > 0 && (
              <div>
                <p className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant font-semibold mb-space-2">
                  Recent Orders
                </p>
                <div className="space-y-space-1.5">
                  {activity.orders.slice(0, 10).map((o) => (
                    <div key={o.id} className="flex items-center justify-between text-sm py-space-1.5 border-b border-surface-container-highest last:border-0">
                      <span className="text-on-surface truncate max-w-md">{o.note || '(no note)'}</span>
                      <span className="text-on-surface-variant text-xs shrink-0 ml-space-3">{new Date(o.uploaded_at).toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* P2-D: Territory Assignment */}
      <Card className="space-y-space-4">
        <CardHeader>
          <div>
            <CardTitle>Territory Assignment</CardTitle>
            <CardSubtitle>Current effective territory and full reassignment history.</CardSubtitle>
          </div>
          <Button variant="primary" size="sm" icon={Plus} onClick={openReassignModal}>
            New Reassignment
          </Button>
        </CardHeader>

        {!territoryHistory ? (
          <EmptyState title="No territory data" subtitle="Territory assignment history could not be loaded." />
        ) : (
          <>
            <div className="p-space-4 bg-surface-container-low border border-outline-variant rounded-xl flex items-center gap-space-2">
              <MapPin className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold text-primary">
                Currently working: {territoryHistory.effective_territory_name || 'Unassigned'}
              </span>
            </div>

            <div>
              <p className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant font-semibold mb-space-2 flex items-center gap-1.5">
                <History className="w-3.5 h-3.5" /> Assignment History
              </p>
              {territoryHistory.assignments.length === 0 ? (
                <p className="font-caption text-xs text-on-surface-variant py-space-3 text-center">
                  No reassignments recorded yet - this employee is on their original territory.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-surface-container-low text-on-surface-variant text-xs uppercase tracking-wider border-b border-surface-container-highest">
                      <tr>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Territory</th>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Type</th>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Start</th>
                        <th className="px-space-3 py-space-2 font-bold text-primary">End</th>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Created By</th>
                        <th className="px-space-3 py-space-2 font-bold text-primary">Current</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-container-highest">
                      {territoryHistory.assignments.map((a) => (
                        <tr key={a.id} className={a.is_current ? 'bg-primary-container/20' : 'hover:bg-surface-container-low/80'}>
                          <td className="px-space-3 py-space-2 font-medium">{a.territory_name}</td>
                          <td className="px-space-3 py-space-2 text-on-surface-variant">{a.assignment_type}</td>
                          <td className="px-space-3 py-space-2 text-on-surface-variant">{a.start_date}</td>
                          <td className="px-space-3 py-space-2 text-on-surface-variant">{a.end_date || '—'}</td>
                          <td className="px-space-3 py-space-2 text-on-surface-variant">{a.created_by_email || '—'}</td>
                          <td className="px-space-3 py-space-2">{a.is_current && <StatusBadge status="ACTIVE" size="sm" />}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </Card>

      {/* Area Coverage: brand-agnostic many-to-many, independent of the
          single-Zone Territory Assignment above - an employee can cover
          several Areas across several Zones at once. */}
      <Card className="space-y-space-4">
        <CardHeader>
          <div>
            <CardTitle>Area Coverage</CardTitle>
            <CardSubtitle>Every Area this employee covers - can span multiple Zones at once.</CardSubtitle>
          </div>
          <Button variant="outline" size="sm" icon={Plus} onClick={openCoverageModal}>
            Assign Area
          </Button>
        </CardHeader>

        {coverage.length === 0 ? (
          <p className="font-caption text-xs text-on-surface-variant py-space-3 text-center">
            No areas assigned yet.
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-space-3">
            {coverage.map((c) => (
              <div
                key={c.id}
                className="flex items-center justify-between p-space-3 rounded-lg border border-surface-container-highest hover:bg-surface-container-low transition-colors"
              >
                <div className="flex items-center gap-space-2 min-w-0">
                  <Layers className="w-4 h-4 text-secondary shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-primary truncate">{c.area_name}</p>
                    <p className="text-xs text-on-surface-variant truncate">{c.territory_name}</p>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  icon={X}
                  className="text-error hover:bg-error-container/30 shrink-0"
                  onClick={() => handleUnassignCoverage(c.area_id, c.area_name)}
                >
                  Remove
                </Button>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Modal isOpen={isCoverageModalOpen} onClose={() => setIsCoverageModalOpen(false)} title="Assign Area Coverage" size="md">
        <div className="space-y-space-4">
          {coverageError && <ErrorBanner message={coverageError} />}

          {uncoveredAreas.length === 0 ? (
            <p className="text-xs text-on-surface-variant">
              This employee already covers every existing area, or no areas have been created yet.
            </p>
          ) : (
            <Select label="Area" value={coverageAreaId} onChange={(e) => setCoverageAreaId(e.target.value)}>
              <option value="">— Select an area —</option>
              {uncoveredAreas.map((a) => (
                <option key={a.id} value={a.id}>{a.name} ({a.territory_name})</option>
              ))}
            </Select>
          )}

          <Button
            variant="primary"
            className="w-full"
            disabled={!coverageAreaId}
            isLoading={isSavingCoverage}
            onClick={() => void handleAssignCoverage()}
          >
            Assign
          </Button>
        </div>
      </Modal>

      <Modal isOpen={isReassignOpen} onClose={() => setIsReassignOpen(false)} title="New Territory Reassignment" size="md">
        <div className="space-y-space-4">
          {reassignError && <ErrorBanner message={reassignError} />}

          <Select label="Assignment Type" value={reassignType} onChange={(e) => setReassignType(e.target.value as AssignmentType)}>
            <option value="PERMANENT">Permanent</option>
            <option value="TEMPORARY">Temporary</option>
          </Select>

          <Select label="Territory" value={reassignTerritoryId} onChange={(e) => setReassignTerritoryId(e.target.value)}>
            <option value="">— Select a territory —</option>
            {territories.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </Select>

          <Input
            label="Start Date"
            type="date"
            value={reassignStartDate}
            onChange={(e) => setReassignStartDate(e.target.value)}
          />

          {reassignType === 'TEMPORARY' && (
            <Input
              label="End Date"
              type="date"
              value={reassignEndDate}
              onChange={(e) => setReassignEndDate(e.target.value)}
              helperText="Required for a temporary assignment - the employee reverts to their base territory after this date."
            />
          )}

          <Button
            variant="primary"
            className="w-full"
            disabled={!reassignTerritoryId || (reassignType === 'TEMPORARY' && !reassignEndDate)}
            isLoading={isReassigning}
            onClick={() => void handleCreateReassignment()}
          >
            Create Reassignment
          </Button>
        </div>
      </Modal>

      <Modal
        isOpen={isEditProfileOpen}
        onClose={() => !isSavingProfile && setIsEditProfileOpen(false)}
        disableClose={isSavingProfile}
        title="Edit Employee Profile"
        size="md"
      >
        <div className="space-y-space-4">
          {editProfileError && <ErrorBanner message={editProfileError} />}

          {employee && editEmail.trim().toLowerCase() !== (employee.user?.email || '').toLowerCase() && (
            <div className="p-space-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-amber-700 dark:text-amber-300 text-xs">
              <strong>Warning:</strong> Changing email will sign this user out of other sessions.
            </div>
          )}

          <Input
            label="Full Name"
            value={editFullName}
            error={editFieldErrors.full_name}
            onChange={(e) => setEditFullName(e.target.value)}
            required
          />

          <div className="grid grid-cols-2 gap-space-3">
            <Input
              label="Email"
              type="email"
              value={editEmail}
              error={editFieldErrors.email}
              onChange={(e) => setEditEmail(e.target.value)}
            />
            <Input
              label="Mobile Phone"
              type="tel"
              value={editMobile}
              error={editFieldErrors.mobile_number}
              onChange={(e) => setEditMobile(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-space-3">
            <Input
              label="Employee Code"
              value={editEmployeeCode}
              error={editFieldErrors.employee_code}
              onChange={(e) => setEditEmployeeCode(e.target.value)}
              helperText="Uppercase unique code."
            />
          </div>

          <div className="grid grid-cols-2 gap-space-3">
            <Input
              label="Working Profile"
              value={editWorkingProfile}
              onChange={(e) => setEditWorkingProfile(e.target.value)}
              placeholder="e.g. FIELD_REP"
            />
            <Input
              label="Date of Birth"
              type="date"
              value={editDob}
              onChange={(e) => setEditDob(e.target.value)}
            />
          </div>

          <Input
            label="Address"
            value={editAddress}
            onChange={(e) => setEditAddress(e.target.value)}
            placeholder="Residential / office address"
          />

          <div className="pt-space-4 flex justify-end gap-space-3 border-t border-surface-container-highest">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={isSavingProfile}
              onClick={() => setIsEditProfileOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              isLoading={isSavingProfile}
              onClick={() => void handleSaveProfile()}
            >
              Save Changes
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
