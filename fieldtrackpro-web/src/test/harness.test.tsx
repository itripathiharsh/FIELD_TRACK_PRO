import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

/**
 * Infrastructure smoke test.
 *
 * Confirms the Vitest + jsdom + React Testing Library harness itself works,
 * so that a failure in any real test can be attributed to the application
 * rather than to the tooling.
 */
describe('test harness', () => {
  it('renders a React component into jsdom', () => {
    render(<h1>FieldTrack Pro</h1>);
    expect(screen.getByRole('heading', { name: 'FieldTrack Pro' })).toBeInTheDocument();
  });

  it('provides a clean localStorage for every test', () => {
    expect(localStorage.getItem('fieldtrack_access_token')).toBeNull();
    localStorage.setItem('fieldtrack_access_token', 'set-by-this-test');
    expect(localStorage.getItem('fieldtrack_access_token')).toBe('set-by-this-test');
  });

  it('does not leak state from the previous test', () => {
    expect(localStorage.getItem('fieldtrack_access_token')).toBeNull();
  });
});
