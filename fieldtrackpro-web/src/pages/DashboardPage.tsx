import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  Building2,
  CalendarCheck,
  ShieldCheck,
  AlertOctagon,
  ArrowUpRight,
  Plus,
  RefreshCw,
} from 'lucide-react';
import { MetricCard } from '../components/ui/MetricCard';
import { StatusBadge } from '../components/ui/StatusBadge';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { useAuth } from '../context/AuthContext';
import { apiClient } from '../api/client';
import { Customer, Employee, Visit } from '../types';

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { user, isLoading: isAuthLoading } = useAuth();
  const isAdmin = user?.role === 'ADMIN';

  const [visits, setVisits] = useState<Visit[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /**
   * FT-028: every metric is derived from data actually returned by the API.
   * The previous implementation used `employees.length || 12` style fallbacks,
   * so the dashboard displayed 12 representatives, 48 customers and 24 visits
   * on a database that contained one of each.
   *
   * FT-019: an employee sees their own day via /visits/me/today; an admin sees
   * the whole operation.
   */
  const fetchData = useCallback(() => {
    // FT-069: wait for authentication to resolve before fetching. On the first
    // render `user` is still null, so `isAdmin` is false and an administrator
    // would briefly be served the employee endpoints - producing an empty
    // dashboard and a needless 403 against the admin-only roster.
    if (isAuthLoading || !user) return;

    setIsLoading(true);
    setError(null);

    const visitsPromise = isAdmin ? apiClient.getVisits() : apiClient.getMyTodayVisits();
    const customersPromise = apiClient.getCustomers().catch(() => [] as Customer[]);
    const employeesPromise = isAdmin
      ? apiClient.getEmployees().catch(() => [] as Employee[])
      : Promise.resolve([] as Employee[]);

    Promise.all([visitsPromise, customersPromise, employeesPromise])
      .then(([vList, cList, eList]) => {
        setVisits(vList);
        setCustomers(cList);
        setEmployees(eList);
      })
      .catch((err: Error) => {
        setVisits([]);
        setError(err.message || 'Unable to load dashboard data');
      })
      .finally(() => setIsLoading(false));
  }, [isAdmin, isAuthLoading, user]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const totalVisits = visits.length;
  const completedVisits = visits.filter((v) => v.status === 'COMPLETED').length;
  const inProgressVisits = visits.filter((v) => v.status === 'IN_PROGRESS').length;
  const flaggedVisits = visits.filter((v) => v.status === 'FLAGGED').length;

  // Undefined until there is data to compute it from - never a flattering default.
  const geoComplianceRate =
    totalVisits > 0 ? Math.round(((totalVisits - flaggedVisits) / totalVisits) * 100) : null;

  return (
    <div className="space-y-space-6">
      <PageHeader
        title={isAdmin ? 'Operational Overview' : 'My Day'}
        subtitle={
          isAdmin
            ? 'Real-time telemetry, field agent status, and geo-verification analytics command center.'
            : "Today's assigned visits and check-in status."
        }
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              icon={RefreshCw}
              onClick={fetchData}
              isLoading={isLoading}
            >
              Sync
            </Button>
            {isAdmin && (
              <Button variant="secondary" size="sm" icon={Plus} onClick={() => navigate('/visits')}>
                New Dispatch
              </Button>
            )}
          </>
        }
      />

      {error && <ErrorBanner message={error} onRetry={fetchData} onDismiss={() => setError(null)} />}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-space-4">
        {isAdmin && (
          <MetricCard
            title="Field Representatives"
            value={employees.length}
            subtitle="Registered employee profiles"
            icon={Users}
            color="primary"
            onClick={() => navigate('/employees')}
          />
        )}
        <MetricCard
          title="Customer Accounts"
          value={customers.length}
          subtitle="Monitored geofence zones"
          icon={Building2}
          color="slate"
          onClick={isAdmin ? () => navigate('/customers') : undefined}
        />
        <MetricCard
          title={isAdmin ? 'Visits' : 'My Visits Today'}
          value={totalVisits}
          subtitle={`${completedVisits} completed, ${inProgressVisits} active`}
          icon={CalendarCheck}
          color="emerald"
          onClick={() => navigate('/visits')}
        />
        <MetricCard
          title="Geo Compliance"
          value={geoComplianceRate === null ? '—' : `${geoComplianceRate}%`}
          subtitle={
            geoComplianceRate === null
              ? 'No visits recorded yet'
              : `${flaggedVisits} location anomal${flaggedVisits === 1 ? 'y' : 'ies'} flagged`
          }
          icon={ShieldCheck}
          color={geoComplianceRate !== null && geoComplianceRate < 85 ? 'amber' : 'emerald'}
          onClick={isAdmin ? () => navigate('/geo-logs') : undefined}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-space-6">
        <Card variant="default" className="lg:col-span-2 flex flex-col justify-between">
          <div>
            <CardHeader>
              <div>
                <CardTitle>{isAdmin ? 'Recent Field Operations' : "Today's Visits"}</CardTitle>
                <CardSubtitle>Live visit status feed and check-in times</CardSubtitle>
              </div>
              <Button
                variant="ghost"
                size="sm"
                icon={ArrowUpRight}
                onClick={() => navigate('/visits')}
              >
                View All
              </Button>
            </CardHeader>

            <div className="overflow-x-auto">
              <table className="w-full text-left font-body-md text-on-surface">
                <thead className="bg-surface-container-low text-on-surface-variant font-label-md text-xs uppercase tracking-wider border-b border-surface-container-highest">
                  <tr>
                    <th className="px-space-4 py-space-3 font-bold text-primary">Customer</th>
                    <th className="px-space-4 py-space-3 font-bold text-primary">Scheduled</th>
                    <th className="px-space-4 py-space-3 font-bold text-primary">Status</th>
                    <th className="px-space-4 py-space-3 font-bold text-primary">Check-In</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-highest">
                  {isLoading ? (
                    Array.from({ length: 4 }).map((_, idx) => (
                      <tr key={idx} className="animate-pulse">
                        <td colSpan={4} className="px-space-4 py-space-3.5">
                          <div className="h-4 bg-surface-container-high rounded w-3/4"></div>
                        </td>
                      </tr>
                    ))
                  ) : visits.length === 0 ? (
                    <tr>
                      <td
                        colSpan={4}
                        className="px-space-4 py-space-8 text-center text-on-surface-variant font-caption"
                      >
                        {isAdmin
                          ? 'No visit activity recorded.'
                          : 'Nothing scheduled for today. Enjoy the breather.'}
                      </td>
                    </tr>
                  ) : (
                    visits.slice(0, 5).map((visit) => (
                      <tr
                        key={visit.id}
                        onClick={() => navigate(`/visits/${visit.id}`)}
                        className="hover:bg-surface-container-low/80 cursor-pointer transition-colors duration-150"
                      >
                        <td className="px-space-4 py-space-3.5 font-headline-sm text-sm text-primary font-semibold">
                          {visit.customer_name ||
                            customers.find((c) => c.id === visit.customer_id)?.name ||
                            `Customer #${visit.customer_id.substring(0, 8)}`}
                        </td>
                        <td className="px-space-4 py-space-3.5 font-caption text-xs text-on-surface-variant">
                          {new Date(visit.scheduled_at).toLocaleString()}
                        </td>
                        <td className="px-space-4 py-space-3.5">
                          <StatusBadge status={visit.status} size="sm" />
                        </td>
                        <td className="px-space-4 py-space-3.5 font-label-md text-xs text-on-surface-variant">
                          {visit.check_in_at ? (
                            new Date(visit.check_in_at).toLocaleTimeString()
                          ) : (
                            <span className="text-outline">—</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </Card>

        <div className="space-y-space-6 flex flex-col justify-between">
          <Card variant="default">
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
            </CardHeader>
            <div className="space-y-space-3">
              <button
                onClick={() => navigate('/visits')}
                className="w-full text-left p-space-3.5 rounded-lg bg-surface-container-low border border-outline-variant hover:border-primary-container transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="font-label-md text-sm text-primary font-bold group-hover:text-secondary-container transition-colors">
                    {isAdmin ? 'Visit Dispatch' : 'My Visits'}
                  </p>
                  <p className="font-caption text-xs text-on-surface-variant">
                    {isAdmin ? "View and assign today's schedule" : 'Open your assigned visits'}
                  </p>
                </div>
                <ArrowUpRight className="w-4 h-4 text-primary group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
              </button>

              {/* FT-045: admin-only destinations are not offered to employees,
                  whose requests those endpoints reject with 403. */}
              {isAdmin && (
                <>
                  <button
                    onClick={() => navigate('/geo-logs')}
                    className="w-full text-left p-space-3.5 rounded-lg bg-surface-container-low border border-outline-variant hover:border-primary-container transition-all flex items-center justify-between group cursor-pointer"
                  >
                    <div>
                      <p className="font-label-md text-sm text-primary font-bold group-hover:text-secondary-container transition-colors">
                        Geo Audit Trail
                      </p>
                      <p className="font-caption text-xs text-on-surface-variant">
                        Inspect GPS coordinate logs
                      </p>
                    </div>
                    <ArrowUpRight className="w-4 h-4 text-primary group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                  </button>

                  <button
                    onClick={() => navigate('/media')}
                    className="w-full text-left p-space-3.5 rounded-lg bg-surface-container-low border border-outline-variant hover:border-primary-container transition-all flex items-center justify-between group cursor-pointer"
                  >
                    <div>
                      <p className="font-label-md text-sm text-primary font-bold group-hover:text-secondary-container transition-colors">
                        Media Attachments
                      </p>
                      <p className="font-caption text-xs text-on-surface-variant">
                        Inspect site photos and files
                      </p>
                    </div>
                    <ArrowUpRight className="w-4 h-4 text-primary group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                  </button>
                </>
              )}
            </div>
          </Card>

          <Card variant="flat" className="bg-primary-tint/20 border-primary-fixed-dim">
            <div className="flex items-center gap-space-2.5 text-primary mb-space-2">
              <AlertOctagon className="w-5 h-5 shrink-0 text-secondary-container" />
              <h4 className="font-headline-sm text-sm font-bold text-primary">
                System Telemetry Guard
              </h4>
            </div>
            <p className="font-caption text-xs text-on-surface-variant leading-relaxed">
              Check-in location is verified against each customer&apos;s own geofence radius. Mock
              location signals are flagged automatically for review.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
};
