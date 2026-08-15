import React from 'react';
import { AlertOctagon } from 'lucide-react';
import { Button } from './Button';

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  errorInfo: React.ErrorInfo | null;
}

/**
 * Last-resort fallback for an uncaught render error.
 *
 * Without this, React 18 unmounts the entire tree on an uncaught exception,
 * leaving an empty #root - a blank page with no indication anything went
 * wrong. This renders an on-brand message instead, using only tokens that
 * already exist elsewhere in the app.
 */
export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, error: null, errorInfo: null };

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an unexpected exception:', error, errorInfo);
    this.setState({ errorInfo });
  }

  render() {
    if (this.state.hasError) {
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
