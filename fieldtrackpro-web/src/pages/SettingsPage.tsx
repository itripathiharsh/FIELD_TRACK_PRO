import React, { useEffect, useState } from 'react';
import { Server, Shield, CheckCircle2, XCircle } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { ENV } from '../config/env';
import { apiClient } from '../api/client';

/**
 * System settings.
 *
 * FT-029: this page previously showed editable "FastAPI Service URL" and
 * "Default Geofence Radius" fields with a Save button that only set a local
 * flag and displayed "System settings successfully updated." Nothing was ever
 * persisted, and the geofence value shown (100 m) did not match the real
 * backend default (75 m). A "saved" confirmation for a discarded change is a
 * misleading-state defect.
 *
 * There is no settings API in the specification, so the page now reports the
 * actual, read-only runtime configuration and verifies connectivity. The
 * geofence radius is a per-customer value and is edited on the customer record,
 * which is where it genuinely lives.
 */
export const SettingsPage: React.FC = () => {
  const [health, setHealth] = useState<'checking' | 'online' | 'offline'>('checking');
  const [healthDetail, setHealthDetail] = useState<string>('');

  useEffect(() => {
    apiClient
      .getHealth()
      .then((data) => {
        setHealth('online');
        setHealthDetail(data.service ? `${data.status} — ${data.service}` : data.status);
      })
      .catch((err: Error) => {
        setHealth('offline');
        setHealthDetail(err.message);
      });
  }, []);

  return (
    <div className="space-y-space-6 max-w-4xl font-body-md text-on-surface">
      <PageHeader
        title="System Settings & Controls"
        subtitle="Runtime configuration and backend connectivity."
      />

      <Card variant="default" className="space-y-space-4">
        <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3">
          <Server className="w-5 h-5 text-primary" />
          <h3 className="font-headline-sm text-base font-bold text-primary">
            Backend API Connectivity
          </h3>
        </div>

        <dl className="grid grid-cols-1 md:grid-cols-2 gap-space-4 font-caption text-xs">
          <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
            <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
              API Base URL
            </dt>
            <dd className="text-primary font-mono break-all">{ENV.API_BASE_URL}</dd>
          </div>
          <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
            <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
              Environment
            </dt>
            <dd className="text-primary font-mono">{ENV.APP_ENV}</dd>
          </div>
          <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant md:col-span-2">
            <dt className="text-on-surface-variant block mb-space-1 uppercase font-semibold">
              Health
            </dt>
            <dd className="flex items-center gap-space-2">
              {health === 'checking' && (
                <span className="text-on-surface-variant">Checking…</span>
              )}
              {health === 'online' && (
                <>
                  <CheckCircle2 className="w-4 h-4 text-secondary shrink-0" />
                  <span className="text-on-surface font-medium">{healthDetail}</span>
                </>
              )}
              {health === 'offline' && (
                <>
                  <XCircle className="w-4 h-4 text-error shrink-0" />
                  <span className="text-error font-medium">{healthDetail || 'Unreachable'}</span>
                </>
              )}
            </dd>
          </div>
        </dl>

        <p className="font-caption text-xs text-on-surface-variant">
          These values come from the deployed configuration and are read-only. Changing them
          requires updating the environment and restarting the service.
        </p>
      </Card>

      <Card variant="default" className="space-y-space-4">
        <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3">
          <Shield className="w-5 h-5 text-primary" />
          <h3 className="font-headline-sm text-base font-bold text-primary">
            Geo Verification Policy
          </h3>
        </div>
        <div className="space-y-space-3 font-body-md text-sm">
          <p>
            Check-in and check-out locations are verified server-side against each customer&apos;s
            own geofence, measured by PostGIS from the stored site coordinates.
          </p>
          <ul className="font-caption text-xs text-on-surface-variant list-disc pl-space-4 space-y-1">
            <li>Geofence radius is configured per customer, on the customer record.</li>
            <li>New customers default to a 75 metre radius.</li>
            <li>GPS readings less accurate than 100 metres are rejected.</li>
            <li>Mock location signals are rejected and recorded for review.</li>
            <li>
              Every attempt, successful or not, is written to an insert-only audit log that the
              application cannot modify or delete.
            </li>
          </ul>
        </div>
      </Card>
    </div>
  );
};
