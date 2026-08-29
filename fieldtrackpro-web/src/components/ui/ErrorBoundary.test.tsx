import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ErrorBoundary } from './ErrorBoundary';

const ProblemChild: React.FC<{ shouldThrow?: boolean }> = ({ shouldThrow }) => {
  if (shouldThrow) {
    throw new Error('Simulated page rendering failure');
  }
  return <div>Normal Content Rendering</div>;
};

describe('ErrorBoundary', () => {
  it('renders children when no error occurs', () => {
    render(
      <ErrorBoundary>
        <ProblemChild shouldThrow={false} />
      </ErrorBoundary>
    );
    expect(screen.getByText('Normal Content Rendering')).toBeInTheDocument();
  });

  it('renders inline fallback boundary without crashing application when inline=true', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <div data-testid="app-shell">
        <nav data-testid="app-nav">Navigation Active</nav>
        <ErrorBoundary inline>
          <ProblemChild shouldThrow={true} />
        </ErrorBoundary>
      </div>
    );

    // Nav is preserved and rendered
    expect(screen.getByTestId('app-nav')).toBeInTheDocument();
    expect(screen.getByText('This section encountered an error')).toBeInTheDocument();
    expect(screen.getByText('Simulated page rendering failure')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /go to dashboard/i })).toBeInTheDocument();

    spy.mockRestore();
  });

  it('renders full-page fallback when inline is omitted', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <ProblemChild shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument();

    spy.mockRestore();
  });
});
