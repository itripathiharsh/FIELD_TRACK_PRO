import React from 'react';

interface VisitReviewBadgeProps {
  /** `review_label` from the API (admin-only; null/absent for employees, so nothing renders). */
  label: string | null | undefined;
  size?: 'sm' | 'md';
}

/** 'AD-HOC' renders neutral; any label mentioning OUTSIDE ASSIGNMENT renders as a warning. */
export const VisitReviewBadge: React.FC<VisitReviewBadgeProps> = ({ label, size = 'sm' }) => {
  if (!label) return null;
  const outside = label.toUpperCase().includes('OUTSIDE');
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs';
  const tone = outside
    ? 'bg-amber-100 text-amber-900 border-amber-400'
    : 'bg-surface-container text-on-surface-variant border-outline-variant';
  return (
    <span
      data-testid="visit-review-badge"
      className={`inline-flex items-center rounded-full font-bold border whitespace-nowrap ${sizeClasses} ${tone}`}
    >
      {label}
    </span>
  );
};
