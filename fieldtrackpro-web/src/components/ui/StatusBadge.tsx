import React from 'react';
import { VisitStatus } from '../../types';

interface StatusBadgeProps {
  status: VisitStatus | string;
  size?: 'sm' | 'md';
  showDot?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  size = 'md',
  showDot = true,
}) => {
  const normalized = status ? status.toUpperCase() : 'UNKNOWN';

  let styles = 'bg-surface-container text-on-surface-variant border-outline-variant';
  let dotColor = 'bg-on-surface-variant';

  if (normalized === 'COMPLETED' || normalized === 'VALID' || normalized === 'ACTIVE' || normalized === 'ADMIN') {
    styles = 'bg-primary-container text-on-primary-container border-primary-container';
    dotColor = 'bg-secondary-container';
  } else if (normalized === 'IN_PROGRESS' || normalized === 'PENDING') {
    styles = 'bg-primary-tint text-primary border-primary-fixed-dim';
    dotColor = 'bg-primary animate-pulse';
  } else if (normalized === 'FLAGGED' || normalized === 'ON_LEAVE' || normalized === 'MANAGER') {
    styles = 'bg-secondary-fixed text-on-secondary-fixed border-secondary-fixed-dim';
    dotColor = 'bg-secondary-container';
  } else if (normalized === 'MISSED' || normalized === 'DISABLED' || normalized === 'INACTIVE') {
    styles = 'bg-surface-container text-on-surface-variant border-outline-variant';
    dotColor = 'bg-outline';
  } else if (normalized === 'INVALID' || normalized === 'ERROR') {
    styles = 'bg-error-container text-on-error-container border-error';
    dotColor = 'bg-error';
  }

  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-3 py-1 text-[12px]';

  return (
    <span className={`inline-flex items-center gap-space-1.5 rounded-full font-label-md uppercase tracking-wider font-semibold border ${sizeClasses} ${styles}`}>
      {showDot && <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />}
      <span>{normalized.replace(/_/g, ' ')}</span>
    </span>
  );
};
