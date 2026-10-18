import React from 'react';
import { ShieldAlert } from 'lucide-react';

export const ConfigErrorScreen: React.FC<{ errors: string[] }> = ({ errors }) => (
  <div role="alert" className="min-h-screen w-full flex flex-col items-center justify-center bg-background text-on-surface p-space-6 text-center gap-space-3">
    <ShieldAlert className="w-12 h-12 text-error" />
    <h1 className="font-headline-md text-headline-md text-primary">Configuration error</h1>
    <p className="font-caption text-caption text-on-surface-variant max-w-lg">
      FieldTrack Pro cannot start because this deployment is misconfigured.
    </p>
    <ul className="font-caption text-caption text-error max-w-lg list-disc text-left">
      {errors.map((e) => (
        <li key={e}>{e}</li>
      ))}
    </ul>
  </div>
);
