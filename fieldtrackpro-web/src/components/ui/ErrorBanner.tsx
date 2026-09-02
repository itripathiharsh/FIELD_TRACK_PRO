import React from 'react';
import { AlertTriangle, RefreshCw, X } from 'lucide-react';
import { Button } from './Button';

interface ErrorBannerProps {
  message: string;
  requestId?: string;
  onRetry?: () => void;
  onDismiss?: () => void;
}

export const ErrorBanner: React.FC<ErrorBannerProps> = ({ message, requestId, onRetry, onDismiss }) => {
  return (
    <div className="flex items-center justify-between gap-space-3 p-space-4 bg-error-container border border-error/40 rounded-xl text-on-error-container font-body-md text-xs shadow-xs animate-in fade-in-0 duration-200">
      <div className="flex items-center gap-space-3">
        <AlertTriangle className="w-5 h-5 text-error shrink-0" />
        <div className="flex flex-col">
          <span className="font-medium leading-relaxed">{message}</span>
          {requestId && (
            <span className="font-mono text-[10px] text-on-error-container/70 mt-0.5">
              Reference ID: {requestId}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-space-2 shrink-0">
        {onRetry && (
          <Button variant="danger" size="sm" icon={RefreshCw} onClick={onRetry}>
            Retry
          </Button>
        )}
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="p-1 text-on-error-container/80 hover:text-on-error-container rounded hover:bg-error/10 transition-colors cursor-pointer"
            aria-label="Dismiss error"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
};
