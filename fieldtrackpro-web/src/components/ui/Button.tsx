import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  icon?: React.ElementType;
  iconPosition?: 'left' | 'right';
  isLoading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'secondary',
  size = 'md',
  icon: Icon,
  iconPosition = 'left',
  isLoading = false,
  className = '',
  disabled,
  ...props
}) => {
  const baseStyles =
    'inline-flex items-center justify-center font-button text-button uppercase tracking-wider rounded-lg transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-offset-1 active:scale-[0.98] shrink-0 disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100 cursor-pointer select-none';

  const variantStyles = {
    primary:
      'bg-primary hover:bg-primary-container text-on-primary shadow-xs hover:shadow-md focus:ring-primary',
    secondary:
      'bg-secondary-container hover:bg-secondary-fixed text-primary font-bold shadow-xs hover:shadow-md focus:ring-secondary-container',
    outline:
      'bg-surface border border-outline-variant hover:bg-surface-container-low text-on-surface hover:border-primary-container focus:ring-primary-container',
    ghost:
      'bg-transparent text-on-surface-variant hover:text-on-surface hover:bg-surface-container focus:ring-outline',
    danger:
      'bg-error-container hover:bg-error/20 text-on-error-container border border-error focus:ring-error',
  };

  const sizeStyles = {
    sm: 'h-8 px-space-3 text-xs gap-space-1.5',
    md: 'h-10 px-space-4 text-sm gap-space-2',
    lg: 'h-12 px-space-6 text-base gap-space-2.5',
  };

  return (
    <button
      className={`${baseStyles} ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin shrink-0" />
      ) : Icon && iconPosition === 'left' ? (
        <Icon className={size === 'sm' ? 'w-3.5 h-3.5 shrink-0' : size === 'lg' ? 'w-5 h-5 shrink-0' : 'w-4 h-4 shrink-0'} />
      ) : null}

      <span>{children}</span>

      {!isLoading && Icon && iconPosition === 'right' ? (
        <Icon className={size === 'sm' ? 'w-3.5 h-3.5 shrink-0' : size === 'lg' ? 'w-5 h-5 shrink-0' : 'w-4 h-4 shrink-0'} />
      ) : null}
    </button>
  );
};
