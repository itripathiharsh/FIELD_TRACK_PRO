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
import { AssignmentType, Employee, EmployeeActivity, Territory, TerritoryAssignmentHistory } from '../types';

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
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isReassignOpen, setIsReassignOpen] = useState(false);
  const [reassignType, setReassignType] = useState<AssignmentType>('PERMANENT');
  const [reassignTerritoryId, setReassignTerritoryId] = useState('');
  const [reassignStartDate, setReassignStartDate] = useState(new Date().toISOString().slice(0, 10));
  const [reassignEndDate, setReassignEndDate] = useState('');
  const [reassignError, setReassignError] = useState<string | null>(null);
  const [isReassigning, setIsReassigning] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      setIsLoading(true);
      const [emp, act, history, terrs] = await Promise.all([
        apiClient.getEmployeeById(id),
        apiClient.getEmployeeActivity(id).catch(() => null),
        apiClient.getTerritoryAssignmentHistory(id).catch(() => null),
        apiClient.getTerritories().catch(() => [] as Territory[]),
      ]);
      setEmployee(emp);
      setActivity(act);
      setTerritoryHistory(history);
      setTerritories(terrs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load employee');
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

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
          <CardTitle>Profile</CardTitle>
          <CardSubtitle>Employee information</CardSubtitle>
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
              <MetricCard title="Visits" value={activity.visits_total} icon={CalendarCheck} color="primary" subtitle={`${activity.visits_completed} completed · ${activity.visits_missed} missed · ${activity.visits_flagged} flagged`} />
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
    </div>
  );
};
