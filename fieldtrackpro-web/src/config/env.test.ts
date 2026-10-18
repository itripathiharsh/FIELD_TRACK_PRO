import { describe, expect, it } from 'vitest';
import { DEV_API_FALLBACK, resolveEnv } from './env';

describe('resolveEnv', () => {
  it('production without VITE_API_BASE_URL is a configuration error with no fallback URL', () => {
    const env = resolveEnv({}, true);
    expect(env.API_BASE_URL).toBe('');
    expect(env.CONFIG_ERRORS.join(' ')).toMatch(/VITE_API_BASE_URL is not set/);
    expect(JSON.stringify(env)).not.toMatch(/onrender\.com|127\.0\.0\.1|localhost/);
  });

  it('production rejects a non-https API URL', () => {
    const env = resolveEnv({ VITE_API_BASE_URL: 'http://api.example.com/api/v1' }, true);
    expect(env.CONFIG_ERRORS.join(' ')).toMatch(/https/);
  });

  it('production accepts a configured https URL', () => {
    const env = resolveEnv({ VITE_API_BASE_URL: 'https://api.example.com/api/v1' }, true);
    expect(env.CONFIG_ERRORS).toEqual([]);
    expect(env.API_BASE_URL).toBe('https://api.example.com/api/v1');
    expect(env.APP_ENV).toBe('production');
  });

  it('development falls back to localhost without error', () => {
    const env = resolveEnv({}, false);
    expect(env.API_BASE_URL).toBe(DEV_API_FALLBACK);
    expect(env.CONFIG_ERRORS).toEqual([]);
  });
});
