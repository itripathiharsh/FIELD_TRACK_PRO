import React, { Suspense, lazy } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ChunkErrorBoundary } from './ChunkErrorBoundary';
import { ErrorBoundary } from './ErrorBoundary';
import { RouteFallback } from './RouteFallback';
import { isChunkLoadError } from '../../utils/chunkError';

describe('isChunkLoadError', () => {
  it('recognises the browsers failed dynamic import messages', () => {
    expect(isChunkLoadError(new TypeError('Failed to fetch dynamically imported module: https://x/assets/a.js'))).toBe(true);
    expect(isChunkLoadError(new TypeError('error loading dynamically imported module'))).toBe(true);
    expect(isChunkLoadError(new TypeError('Importing a module script failed.'))).toBe(true);
    expect(isChunkLoadError(Object.assign(new Error('x'), { name: 'ChunkLoadError' }))).toBe(true);
    expect(isChunkLoadError(new Error('Cannot read properties of undefined'))).toBe(false);
    expect(isChunkLoadError(null)).toBe(false);
  });
});

describe('lazy route loading', () => {
  it('shows the shared loading fallback while a chunk loads, then the page', async () => {
    let resolve!: (m: { default: React.ComponentType }) => void;
    const Page = lazy(() => new Promise<{ default: React.ComponentType }>((r) => (resolve = r)));
    render(
      <ChunkErrorBoundary>
        <Suspense fallback={<RouteFallback />}>
          <Page />
        </Suspense>
      </ChunkErrorBoundary>,
    );
    expect(screen.getByTestId('route-loading')).toBeInTheDocument();
    resolve({ default: () => <div>real page</div> });
    expect(await screen.findByText('real page')).toBeInTheDocument();
  });

  it('a failed chunk shows a reload offer instead of a blank screen', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const Broken = lazy(() => Promise.reject(new TypeError('Failed to fetch dynamically imported module: /assets/Map-abc.js')));
    const reload = vi.fn();
    Object.defineProperty(window, 'location', { configurable: true, value: { ...window.location, reload } });
    render(
      <ErrorBoundary>
        <ChunkErrorBoundary>
          <Suspense fallback={<RouteFallback />}>
            <Broken />
          </Suspense>
        </ChunkErrorBoundary>
      </ErrorBoundary>,
    );
    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /reload/i }));
    expect(reload).toHaveBeenCalled();
  });

  it('other render errors are not swallowed: they reach the outer error boundary', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const Boom = () => {
      throw new Error('ordinary bug');
    };
    render(
      <ErrorBoundary>
        <ChunkErrorBoundary>
          <Boom />
        </ChunkErrorBoundary>
      </ErrorBoundary>,
    );
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    expect(screen.queryByText(/could not be loaded/i)).not.toBeInTheDocument();
  });
});
