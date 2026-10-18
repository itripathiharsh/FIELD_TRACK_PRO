/**
 * Centralized environment configuration for Admin Web Dashboard.
 * Prevents hardcoded API URLs across components.
 *
 * Production builds never fall back to a guessed API origin: a missing
 * VITE_API_BASE_URL is a configuration error (see ConfigErrorScreen). The
 * localhost fallback exists for local development only.
 */
export const DEV_API_FALLBACK = 'http://127.0.0.1:8000/api/v1';

export interface ResolvedEnv {
  API_BASE_URL: string;
  APP_ENV: string;
  MAPLIBRE_TILE_URL: string;
  /** Human-readable problems that make the app unusable. Empty when valid. */
  CONFIG_ERRORS: string[];
}

export function resolveEnv(
  raw: Partial<Record<string, string | undefined>>,
  isProd: boolean,
): ResolvedEnv {
  const configured = (raw.VITE_API_BASE_URL ?? '').trim();
  const errors: string[] = [];
  let apiBase = configured;
  if (!configured) {
    if (isProd) {
      errors.push('VITE_API_BASE_URL is not set. Set it to the backend API URL (e.g. https://api.example.com/api/v1) in the hosting environment and redeploy.');
    } else {
      apiBase = DEV_API_FALLBACK;
    }
  } else if (isProd && !/^https:\/\//i.test(configured)) {
    errors.push('VITE_API_BASE_URL must be an https:// URL in production builds.');
  }
  return {
    API_BASE_URL: apiBase,
    APP_ENV: raw.VITE_APP_ENV || (isProd ? 'production' : 'development'),
    MAPLIBRE_TILE_URL: raw.VITE_MAPLIBRE_TILE_URL || '',
    CONFIG_ERRORS: errors,
  };
}

export const ENV = resolveEnv(import.meta.env, import.meta.env.PROD);

if (ENV.CONFIG_ERRORS.length > 0) {
  // eslint-disable-next-line no-console
  console.error('[FieldTrack Pro] Invalid configuration:', ENV.CONFIG_ERRORS.join(' '));
}
