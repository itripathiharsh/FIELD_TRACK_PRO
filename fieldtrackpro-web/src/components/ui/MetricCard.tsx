import React from 'react';
import { LucideIcon } from 'lucide-react';
import { Card } from './Card';

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  trend?: string;
  color?: 'blue' | 'emerald' | 'amber' | 'rose' | 'slate' | 'primary' | 'secondary';
  onClick?: () => void;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  subtitle,
  icon: Icon,
  trend,
  color = 'primary',
  onClick,
}) => {
  const colorMap = {
    primary: 'bg-primary-container text-on-primary-container',
    secondary: 'bg-secondary-fixed text-on-secondary-fixed',
    blue: 'bg-primary-tint text-primary',
    emerald: 'bg-primary-container text-on-primary-container',
    amber: 'bg-secondary-fixed text-on-secondary-fixed',
    rose: 'bg-error-container text-on-error-container',
    slate: 'bg-surface-container-high text-on-surface',
  };

  return (
    <Card
      variant="hover"
      onClick={onClick}
      className={`h-full flex flex-col justify-between !p-4 min-w-0 ${onClick ? 'cursor-pointer' : ''}`}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="font-label-md text-[11px] sm:text-xs text-on-surface-variant block uppercase tracking-wider font-semibold truncate flex-1 min-w-0">
          {title}
        </span>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 shadow-2xs ${colorMap[color] || colorMap.primary}`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>

      <div className="my-auto py-1 min-w-0">
        <div className="flex items-baseline flex-wrap gap-1.5">
          <span className="font-headline-lg text-lg sm:text-xl lg:text-lg 2xl:text-xl font-bold tracking-tight text-primary break-words leading-tight">
            {value}
          </span>
          {trend && (
            <span className="font-label-md text-[10px] text-secondary-container font-bold bg-secondary-fixed/50 px-1.5 py-0.5 rounded shrink-0">
              {trend}
            </span>
          )}
        </div>
      </div>

      {subtitle ? (
        <p className="font-caption text-[11px] text-on-surface-variant mt-1.5 leading-tight truncate">
          {subtitle}
        </p>
      ) : (
        <div className="h-2" />
      )}
    </Card>
  );
};
