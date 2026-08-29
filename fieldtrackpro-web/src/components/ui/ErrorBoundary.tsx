import React from 'react';
import { AlertOctagon } from 'lucide-react';
import { Button } from './Button';

interface ErrorBoundaryProps {
  children: React.ReactNode;
  inline?: boolean;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
}

/**
 * Fallback boundary for uncaught render errors.
 * Supports both root-level full-screen fallbacks and layout-level inline fallbacks.
 */
export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, error: null, errorInfo: null };

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an unexpected exception:', error, errorInfo);
    this.setState({ errorInfo });
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.inline) {
        return (
          <div className="bg-surface-container border border-error/20 rounded-radius-lg p-space-6 text-center my-space-6">
            <AlertOctagon className="w-8 h-8 text-error mx-auto mb-space-3" />
            <h2 className="font-title-md text-title-md text-on-surface font-bold mb-space-2">
              This section encountered an error
            </h2>
            <p className="font-caption text-xs text-on-surface-variant max-w-md mx-auto mb-space-4">
              {this.state.error?.message || 'An unexpected rendering error occurred in this view.'}
            </p>
            <div className="flex justify-center gap-space-3">
              <Button variant="secondary" size="sm" onClick={this.handleReset}>
                Try Again
              </Button>
              <Button variant="primary" size="sm" onClick={() => { window.location.href = '/'; }}>
                Go to Dashboard
              </Button>
            </div>
          </div>
        );
      }

      return (
        <div className="min-h-screen bg-background flex flex-col items-center justify-center text-on-surface p-space-6 text-center">
          <AlertOctagon className="w-10 h-10 text-error mb-space-4" />
          <h1 className="font-headline-md text-headline-md text-primary font-bold mb-space-2">
            Something went wrong
          </h1>
          <p className="font-caption text-xs text-on-surface-variant max-w-md mb-space-6">
            FieldTrack Pro hit an unexpected error and couldn&apos;t continue rendering this page.
          </p>
          <Button variant="secondary" size="md" onClick={() => window.location.reload()}>
            Reload
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}

