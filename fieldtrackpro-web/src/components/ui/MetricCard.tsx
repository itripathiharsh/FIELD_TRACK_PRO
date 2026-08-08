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
      className={`flex items-start justify-between ${onClick ? 'cursor-pointer' : ''}`}
    >
      <div>
        <span className="font-label-md text-xs text-on-surface-variant block uppercase tracking-wider font-semibold mb-space-1">
          {title}
        </span>
        <div className="flex items-baseline gap-space-2 mt-1">
          <span className="font-headline-lg text-3xl font-bold tracking-tight text-primary">
            {value}
          </span>
          {trend && (
            <span className="font-label-md text-xs text-secondary-container font-bold bg-secondary-fixed/50 px-2 py-0.5 rounded">
              {trend}
            </span>
          )}
        </div>
        {subtitle && (
          <p className="font-caption text-xs text-on-surface-variant mt-space-2 leading-tight">
            {subtitle}
          </p>
        )}
      </div>
      <div className={`w-11 h-11 rounded-xl flex items-center justify-center shrink-0 shadow-xs ${colorMap[color] || colorMap.primary}`}>
        <Icon className="w-5 h-5" />
      </div>
    </Card>
  );
};
