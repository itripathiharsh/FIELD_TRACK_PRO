import React from 'react';
import { VisitStatus } from '../../types';

interface StatusBadgeProps {
  status: VisitStatus | string;
  size?: 'sm' | 'md';
  showDot?: boolean;
  /** Overrides the displayed text (the status still drives the colour). */
  label?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  size = 'md',
  showDot = true,
  label,
}) => {
  const normalized = status ? status.toUpperCase() : 'UNKNOWN';

  let styles = 'bg-surface-container text-on-surface-variant border-outline-variant';
  let dotColor = 'bg-on-surface-variant';

  if (normalized === 'COMPLETED' || normalized === 'VALID' || normalized === 'ACTIVE' || normalized === 'ADMIN' || normalized === 'PUBLISHED' || normalized === 'APPROVED' || normalized === 'SUBMITTED' || normalized === 'VERIFIED' || normalized === 'PAID' || normalized === 'NORMAL' || normalized === 'COMMITTED' || normalized === 'POSTED' || normalized === 'VALIDATED') {
    styles = 'bg-primary-container text-on-primary-container border-primary-container';
    dotColor = 'bg-secondary-container';
  } else if (normalized === 'IN_PROGRESS' || normalized === 'PENDING' || normalized === 'IN_REVIEW' || normalized === 'PENDING_VERIFICATION') {
    styles = 'bg-primary-tint text-primary border-primary-fixed-dim';
    dotColor = 'bg-primary animate-pulse';
  } else if (normalized === 'FLAGGED' || normalized === 'ON_LEAVE' || normalized === 'DRAFT' || normalized === 'PARTIALLY_PAID' || normalized === 'PARTIALLY_APPROVED' || normalized === 'AWAITING_TALLY') {
    styles = 'bg-secondary-fixed text-on-secondary-fixed border-secondary-fixed-dim';
    dotColor = 'bg-secondary-container';
  } else if (normalized === 'WARNING') {
    styles = 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800';
    dotColor = 'bg-amber-500';
  } else if (normalized === 'MISSED' || normalized === 'DISABLED' || normalized === 'INACTIVE' || normalized === 'ARCHIVED' || normalized === 'UNPAID' || normalized === 'NOT_APPLICABLE') {
    styles = 'bg-surface-container text-on-surface-variant border-outline-variant';
    dotColor = 'bg-outline';
  } else if (normalized === 'INVALID' || normalized === 'ERROR' || normalized === 'REJECTED' || normalized === 'OVERDUE' || normalized === 'FAILED') {
    styles = 'bg-error-container text-on-error-container border-error';
    dotColor = 'bg-error';
  }

  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-3 py-1 text-[12px]';

  return (
    <span className={`inline-flex items-center gap-space-1.5 rounded-full font-label-md uppercase tracking-wider font-semibold border ${sizeClasses} ${styles}`}>
      {showDot && <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />}
      <span>{label ?? normalized.replace(/_/g, ' ')}</span>
    </span>
  );
};
