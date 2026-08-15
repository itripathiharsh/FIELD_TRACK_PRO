import React from 'react';

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(({
  label,
  error,
  helperText,
  className = '',
  id,
  disabled,
  rows = 3,
  ...props
}, ref) => {
  const textareaId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

  return (
    <div className="w-full flex flex-col gap-space-1.5">
      {label && (
        <label htmlFor={textareaId} className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold">
          {label}
        </label>
      )}
      <textarea
        id={textareaId}
        ref={ref}
        disabled={disabled}
        rows={rows}
        className={`w-full bg-surface border rounded-lg px-space-3 py-space-2 text-on-surface font-body-md text-sm placeholder:text-outline focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all resize-vertical ${
          error ? 'border-error focus:border-error focus:ring-error/20' : 'border-outline-variant'
        } ${disabled ? 'opacity-60 bg-surface-container-low cursor-not-allowed' : ''} ${className}`}
        {...props}
      />
      {error && <p className="font-caption text-xs text-error font-medium">{error}</p>}
      {helperText && !error && <p className="font-caption text-xs text-on-surface-variant">{helperText}</p>}
    </div>
  );
});

Textarea.displayName = 'Textarea';
