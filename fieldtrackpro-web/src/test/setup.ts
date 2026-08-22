import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import { apiClient } from '../api/client';

/**
 * Global test setup.
 *
 * Every test starts from a genuinely clean session: no leftover tokens, no
 * leftover fetch stubs. This matters for the authentication tests, where a
 * stale token would mask a regression of FT-001.
 */

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  apiClient.clearSession();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  apiClient.clearSession();
  vi.restoreAllMocks();
});

// jsdom does not implement matchMedia; some responsive helpers expect it.
if (!window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}
