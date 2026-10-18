import React from 'react';

/** The one loading indicator for lazily loaded routes (inside the app shell). */
export const RouteFallback: React.FC = () => (
  <div
    role="status"
    aria-live="polite"
    data-testid="route-loading"
    className="flex flex-col items-center justify-center py-space-12 text-on-surface-variant"
  >
    <div className="w-8 h-8 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin" />
    <p className="mt-space-3 font-caption text-caption">Loading…</p>
  </div>
);
