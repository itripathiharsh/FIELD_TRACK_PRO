/**
 * Centralized environment configuration for Admin Web Dashboard.
 * Prevents hardcoded API URLs across components.
 */
export const ENV = {
  API_BASE_URL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
  APP_ENV: import.meta.env.VITE_APP_ENV || 'development',
};
