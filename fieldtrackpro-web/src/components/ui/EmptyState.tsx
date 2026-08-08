import React from 'react';
import { LucideIcon, Inbox } from 'lucide-react';

interface EmptyStateProps {
  title: string;
  subtitle: string;
  icon?: LucideIcon;
  action?: React.ReactNode;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title,
  subtitle,
  icon: Icon = Inbox,
  action,
}) => {
  return (
    <div className="flex flex-col items-center justify-center p-space-10 text-center bg-surface-container-low border border-outline-variant/60 rounded-2xl transition-all duration-200">
      <div className="p-space-4 bg-surface rounded-2xl border border-outline-variant/80 mb-space-4 text-primary shadow-xs">
        <Icon className="w-10 h-10 text-primary stroke-[1.5]" />
      </div>
      <h3 className="font-headline-sm text-base text-primary font-bold">{title}</h3>
      <p className="mt-space-1 font-body-md text-xs text-on-surface-variant max-w-md leading-relaxed">{subtitle}</p>
      {action && <div className="mt-space-5">{action}</div>}
    </div>
  );
};
