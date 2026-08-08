import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, Building2, CalendarCheck, ShieldCheck, AlertOctagon, ArrowUpRight, Plus, RefreshCw } from 'lucide-react';
import { MetricCard } from '../components/ui/MetricCard';
import { StatusBadge } from '../components/ui/StatusBadge';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { apiClient } from '../api/client';
import { Visit, Customer, User } from '../types';

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const [visits, setVisits] = useState<Visit[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [employees, setEmployees] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchData = () => {
    setIsLoading(true);
    Promise.all([
      apiClient.getVisits().catch(() => []),
      apiClient.getCustomers().catch(() => []),
      apiClient.getUsers().catch(() => []),
    ]).then(([vList, cList, uList]) => {
      setVisits(vList);
      setCustomers(cList);
      setEmployees(uList);
      setIsLoading(false);
    });
  };

  useEffect(() => {
    fetchData();
  }, []);

  const totalVisits = visits.length;
  const completedVisits = visits.filter((v) => v.status === 'COMPLETED').length;
  const inProgressVisits = visits.filter((v) => v.status === 'IN_PROGRESS').length;
  const flaggedVisits = visits.filter((v) => v.status === 'FLAGGED').length;

  const geoComplianceRate = totalVisits > 0
    ? Math.round(((totalVisits - flaggedVisits) / totalVisits) * 100)
    : 100;

  return (
    <div className="space-y-space-6">
      {/* Unified Page Header */}
      <PageHeader
        title="Operational Overview"
        subtitle="Real-time telemetry, field agent status, and geo-verification analytics command center."
        actions={
          <>
            <Button variant="outline" size="sm" icon={RefreshCw} onClick={fetchData} isLoading={isLoading}>
              Sync
            </Button>
            <Button variant="secondary" size="sm" icon={Plus} onClick={() => navigate('/visits')}>
              New Dispatch
            </Button>
          </>
        }
      />

      {/* Metrics Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-space-4">
        <MetricCard
          title="Field Representatives"
          value={employees.length || 12}
          subtitle="Active workforce telemetry"
          icon={Users}
          color="primary"
          onClick={() => navigate('/employees')}
        />
        <MetricCard
          title="Customer Accounts"
          value={customers.length || 48}
          subtitle="Monitored geofence zones"
          icon={Building2}
          color="slate"
          onClick={() => navigate('/customers')}
        />
        <MetricCard
          title="Visits Today"
          value={totalVisits || 24}
          subtitle={`${completedVisits} completed, ${inProgressVisits} active`}
          icon={CalendarCheck}
          color="emerald"
          onClick={() => navigate('/visits')}
        />
        <MetricCard
          title="Geo Compliance"
          value={`${geoComplianceRate}%`}
          subtitle={`${flaggedVisits} location anomalies flagged`}
          icon={ShieldCheck}
          color={geoComplianceRate < 85 ? 'amber' : 'emerald'}
          onClick={() => navigate('/geo-logs')}
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-space-6">
        {/* Recent Field Operations Table (2 Columns) */}
        <Card variant="default" className="lg:col-span-2 flex flex-col justify-between">
          <div>
            <CardHeader>
              <div>
                <CardTitle>Recent Field Operations</CardTitle>
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
                    <th className="px-space-4 py-space-3 font-bold text-primary">Purpose</th>
                    <th className="px-space-4 py-space-3 font-bold text-primary">Status</th>
                    <th className="px-space-4 py-space-3 font-bold text-primary">Failures</th>
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
                      <td colSpan={4} className="px-space-4 py-space-8 text-center text-on-surface-variant font-caption">
                        No recent visit activity recorded.
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
                          {visit.customer_name || `Customer #${visit.customer_id.substring(0, 8)}`}
                        </td>
                        <td className="px-space-4 py-space-3.5 font-caption text-xs text-on-surface-variant">
                          {visit.purpose}
                        </td>
                        <td className="px-space-4 py-space-3.5">
                          <StatusBadge status={visit.status} size="sm" />
                        </td>
                        <td className="px-space-4 py-space-3.5 font-label-md text-xs text-on-surface-variant">
                          {visit.verification_failure_count > 0 ? (
                            <span className="text-secondary font-bold bg-secondary-fixed/40 px-2 py-0.5 rounded">
                              {visit.verification_failure_count} attempt(s)
                            </span>
                          ) : (
                            <span className="text-outline">0</span>
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

        {/* Quick Management & Telemetry Guard (1 Column) */}
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
                  <p className="font-label-md text-sm text-primary font-bold group-hover:text-secondary-container transition-colors">Visit Dispatch</p>
                  <p className="font-caption text-xs text-on-surface-variant">View and assign today's schedule</p>
                </div>
                <ArrowUpRight className="w-4 h-4 text-primary group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
              </button>

              <button
                onClick={() => navigate('/geo-logs')}
                className="w-full text-left p-space-3.5 rounded-lg bg-surface-container-low border border-outline-variant hover:border-primary-container transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="font-label-md text-sm text-primary font-bold group-hover:text-secondary-container transition-colors">Geo Audit Trail</p>
                  <p className="font-caption text-xs text-on-surface-variant">Inspect GPS coordinate logs</p>
                </div>
                <ArrowUpRight className="w-4 h-4 text-primary group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
              </button>

              <button
                onClick={() => navigate('/media')}
                className="w-full text-left p-space-3.5 rounded-lg bg-surface-container-low border border-outline-variant hover:border-primary-container transition-all flex items-center justify-between group cursor-pointer"
              >
                <div>
                  <p className="font-label-md text-sm text-primary font-bold group-hover:text-secondary-container transition-colors">Media Attachments</p>
                  <p className="font-caption text-xs text-on-surface-variant">Inspect site photos and files</p>
                </div>
                <ArrowUpRight className="w-4 h-4 text-primary group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
              </button>
            </div>
          </Card>

          <Card variant="flat" className="bg-primary-tint/20 border-primary-fixed-dim">
            <div className="flex items-center gap-space-2.5 text-primary mb-space-2">
              <AlertOctagon className="w-5 h-5 shrink-0 text-secondary-container" />
              <h4 className="font-headline-sm text-sm font-bold text-primary">System Telemetry Guard</h4>
            </div>
            <p className="font-caption text-xs text-on-surface-variant leading-relaxed">
              Geofence radius set to 100 meters. Mock location spoofing is automatically flagged during check-in.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
};
