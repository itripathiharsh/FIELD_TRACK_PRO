import React from 'react';

export interface PageHeaderProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  breadcrumbs?: { label: string; href?: string }[];
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  subtitle,
  actions,
  breadcrumbs,
}) => {
  return (
    <div className="mb-space-6 flex flex-col md:flex-row md:items-center md:justify-between gap-space-4 pb-space-4 border-b border-surface-container-highest">
      <div>
        {breadcrumbs && breadcrumbs.length > 0 && (
          <div className="flex items-center gap-space-2 text-xs font-label-md text-on-surface-variant uppercase tracking-wider mb-space-1">
            {breadcrumbs.map((b, idx) => (
              <React.Fragment key={idx}>
                {idx > 0 && <span>/</span>}
                <span className={idx === breadcrumbs.length - 1 ? 'text-primary font-bold' : ''}>
                  {b.label}
                </span>
              </React.Fragment>
            ))}
          </div>
        )}
        <h1 className="font-headline-lg text-headline-lg text-primary tracking-tight font-bold leading-tight">
          {title}
        </h1>
        {subtitle && (
          <p className="font-caption text-caption text-on-surface-variant mt-space-1 leading-relaxed">
            {subtitle}
          </p>
        )}
      </div>

      {actions && (
        <div className="flex items-center gap-space-3 shrink-0">
          {actions}
        </div>
      )}
    </div>
  );
};
