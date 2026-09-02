import React from 'react';
import { Banknote, Smartphone, Landmark, Receipt } from 'lucide-react';
import { PaymentMethod } from '../../types';

export interface PaymentMethodBadgeProps {
  method: PaymentMethod | string | null | undefined;
  size?: 'sm' | 'md';
  showIcon?: boolean;
  chequeNumber?: string | null;
  className?: string;
}

export const PaymentMethodBadge: React.FC<PaymentMethodBadgeProps> = ({
  method,
  size = 'sm',
  showIcon = true,
  chequeNumber,
  className = '',
}) => {
  const normalized = (method || 'UNKNOWN').toUpperCase().trim();

  let styles = 'bg-surface-container text-on-surface-variant border-outline-variant';
  let iconColor = 'text-on-surface-variant';
  let dotColor = 'bg-outline';
  let Icon = Receipt;
  let label = normalized.replace(/_/g, ' ');

  if (normalized === 'CASH') {
    styles = 'bg-emerald-50 text-emerald-800 border-emerald-300 dark:bg-emerald-950/50 dark:text-emerald-200 dark:border-emerald-700/70 shadow-sm';
    iconColor = 'text-emerald-600 dark:text-emerald-400';
    dotColor = 'bg-emerald-500';
    Icon = Banknote;
    label = 'CASH';
  } else if (normalized === 'ONLINE') {
    styles = 'bg-blue-50 text-blue-800 border-blue-300 dark:bg-blue-950/50 dark:text-blue-200 dark:border-blue-700/70 shadow-sm';
    iconColor = 'text-blue-600 dark:text-blue-400';
    dotColor = 'bg-blue-500';
    Icon = Smartphone;
    label = 'ONLINE';
  } else if (normalized === 'CHEQUE' || normalized === 'CHECK') {
    // Cheque payments are distinct & focused with royal purple styling
    styles = 'bg-purple-50 text-purple-800 border-purple-300 dark:bg-purple-950/50 dark:text-purple-200 dark:border-purple-700/70 shadow-sm';
    iconColor = 'text-purple-600 dark:text-purple-400';
    dotColor = 'bg-purple-500';
    Icon = Landmark;
    label = 'CHEQUE';
  }

  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs';
  const iconSizeClass = size === 'sm' ? 'w-3.5 h-3.5' : 'w-4 h-4';

  return (
    <div className={`inline-flex flex-col items-start gap-0.5 ${className}`}>
      <span
        className={`inline-flex items-center gap-1.5 rounded-full font-label-md uppercase tracking-wider font-semibold border transition-colors ${sizeClasses} ${styles}`}
      >
        {showIcon ? (
          <Icon className={`${iconSizeClass} shrink-0 ${iconColor}`} />
        ) : (
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />
        )}
        <span>{label}</span>
      </span>
      {chequeNumber && (
        <span className="text-[10px] font-mono text-purple-700 dark:text-purple-300 font-medium pl-1">
          #{chequeNumber}
        </span>
      )}
    </div>
  );
};
