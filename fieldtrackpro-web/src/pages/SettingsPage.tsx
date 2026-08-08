import React, { useState } from 'react';
import { Save, Server, Shield } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { ENV } from '../config/env';

export const SettingsPage: React.FC = () => {
  const [apiUrl, setApiUrl] = useState(ENV.API_BASE_URL || 'http://127.0.0.1:8000');
  const [defaultRadius, setDefaultRadius] = useState('100');
  const [savedNotice, setSavedNotice] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSavedNotice(true);
    setTimeout(() => setSavedNotice(false), 3000);
  };

  return (
    <div className="space-y-space-6 max-w-4xl font-body-md text-on-surface">
      <PageHeader
        title="System Settings & Controls"
        subtitle="Configure global API endpoints, geofence parameters, and audit controls."
      />

      {savedNotice && (
        <div className="p-space-4 bg-primary-container border border-primary-container rounded-lg text-on-primary-container font-headline-sm text-sm font-bold">
          System settings successfully updated.
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-space-6">
        <Card variant="default" className="space-y-space-4">
          <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3">
            <Server className="w-5 h-5 text-primary" />
            <h3 className="font-headline-sm text-base font-bold text-primary">Backend API Connectivity</h3>
          </div>
          <Input
            label="FastAPI Service URL"
            type="text"
            value={apiUrl}
            onChange={(e) => setApiUrl(e.target.value)}
          />
        </Card>

        <Card variant="default" className="space-y-space-4">
          <div className="flex items-center gap-space-2 border-b border-surface-container-highest pb-space-3">
            <Shield className="w-5 h-5 text-primary" />
            <h3 className="font-headline-sm text-base font-bold text-primary">Geo Verification Controls</h3>
          </div>
          <div>
            <Input
              label="Default Geofence Radius (Meters)"
              type="number"
              value={defaultRadius}
              onChange={(e) => setDefaultRadius(e.target.value)}
              className="max-w-xs"
            />
            <p className="font-caption text-xs text-on-surface-variant mt-space-1.5">
              Maximum allowed GPS offset during check-in/out verification.
            </p>
          </div>
        </Card>

        <Button type="submit" variant="secondary" size="md" icon={Save}>
          Save System Parameters
        </Button>
      </form>
    </div>
  );
};
