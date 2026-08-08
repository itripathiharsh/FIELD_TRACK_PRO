import React from 'react';
import { Download, TrendingUp, ShieldAlert, CheckCircle2 } from 'lucide-react';
import { MetricCard } from '../components/ui/MetricCard';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';

export const ReportsPage: React.FC = () => {
  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <PageHeader
        title="Reports & Field Analytics"
        subtitle="Operational performance metrics, compliance summaries, and export tools."
        actions={
          <Button variant="secondary" size="sm" icon={Download}>
            Export PDF Report
          </Button>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-space-6">
        <MetricCard
          title="Completion Rate"
          value="96.4%"
          subtitle="+2.1% from last month"
          icon={TrendingUp}
          color="emerald"
        />
        <MetricCard
          title="GPS Verification Rate"
          value="98.8%"
          subtitle="Proximity enforcement passing"
          icon={CheckCircle2}
          color="blue"
        />
        <MetricCard
          title="Flagged Location Anomaly"
          value="4 Events"
          subtitle="Investigated and resolved"
          icon={ShieldAlert}
          color="amber"
        />
      </div>

      <Card variant="default">
        <CardHeader>
          <CardTitle>Operational Summary Highlights</CardTitle>
        </CardHeader>
        <div className="space-y-space-3 font-body-md text-sm text-on-surface leading-relaxed">
          <p>• <strong className="text-primary">Visit Density:</strong> Highest field activity concentrated in North Region Metropolitan territory.</p>
          <p>• <strong className="text-primary">Geofence Compliance:</strong> Average check-in distance recorded at 24.2 meters from customer center points (Allowed radius: 100m).</p>
          <p>• <strong className="text-primary">Media Audit:</strong> 100% of completed visits attached at least 1 site inspection photograph.</p>
        </div>
      </Card>
    </div>
  );
};
