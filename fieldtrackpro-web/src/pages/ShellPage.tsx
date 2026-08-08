import React from 'react';
import { Server, ShieldAlert, CheckCircle2 } from 'lucide-react';
import { ENV } from '../config/env';

interface ShellPageProps {
  apiHealth: { status: string } | null;
  error: string | null;
}

export const ShellPage: React.FC<ShellPageProps> = ({ apiHealth, error }) => {
  return (
    <div className="max-w-4xl mx-auto space-y-space-6 font-body-md text-on-surface">
      <div>
        <h1 className="font-headline-lg text-headline-lg tracking-tight text-primary">
          FieldTrack Pro — Admin Shell
        </h1>
        <p className="mt-space-1 font-caption text-caption text-on-surface-variant">
          Infrastructure Bootstrap & API Connectivity Layer
        </p>
      </div>

      <div className="p-space-6 rounded-xl bg-surface border border-surface-container-highest space-y-space-4 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="font-headline-sm text-headline-sm text-primary flex items-center gap-space-2">
            <Server className="w-4 h-4 text-primary" /> API Health Status
          </h2>
          {apiHealth ? (
            <span className="font-label-md text-label-md px-space-2.5 py-space-1 rounded-full bg-primary-container text-on-primary-container border border-primary-container flex items-center gap-space-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-secondary-container" /> Healthy ({apiHealth.status})
            </span>
          ) : (
            <span className="font-label-md text-label-md px-space-2.5 py-space-1 rounded-full bg-secondary-container text-primary font-bold">
              Connecting...
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-space-3 font-caption text-caption text-on-surface">
          <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
            <span className="text-on-surface-variant block mb-space-0.5">VITE_API_BASE_URL:</span>
            <span className="text-primary font-headline-sm">{ENV.API_BASE_URL}</span>
          </div>
          <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant">
            <span className="text-on-surface-variant block mb-space-0.5">VITE_APP_ENV:</span>
            <span className="text-primary font-headline-sm">{ENV.APP_ENV}</span>
          </div>
        </div>

        {error && (
          <div className="p-space-4 rounded-lg bg-error-container border border-error text-on-error-container text-sm flex items-center gap-space-3">
            <ShieldAlert className="w-5 h-5 text-error shrink-0" />
            <div>
              <p className="font-headline-sm">Backend Unreachable</p>
              <p className="font-caption text-caption mt-space-0.5">{error}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
