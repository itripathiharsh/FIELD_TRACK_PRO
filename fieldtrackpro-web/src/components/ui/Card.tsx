import React from 'react';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  variant?: 'default' | 'hover' | 'flat';
}

export const Card: React.FC<CardProps> = ({
  children,
  variant = 'default',
  className = '',
  ...props
}) => {
  const variantStyles = {
    default: 'bg-surface border border-surface-container-highest shadow-xs',
    hover: 'bg-surface border border-surface-container-highest shadow-xs hover:shadow-md hover:border-outline-variant transition-all duration-200',
    flat: 'bg-surface-container-low border border-surface-container-highest',
  };

  return (
    <div
      className={`rounded-xl p-space-6 text-on-surface ${variantStyles[variant]} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
};

export const CardHeader: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <div className={`mb-space-4 flex items-center justify-between gap-space-4 ${className}`}>{children}</div>
);

export const CardTitle: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <h3 className={`font-headline-sm text-headline-sm text-primary font-bold ${className}`}>{children}</h3>
);

export const CardSubtitle: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <p className={`font-caption text-caption text-on-surface-variant mt-space-0.5 ${className}`}>{children}</p>
);
