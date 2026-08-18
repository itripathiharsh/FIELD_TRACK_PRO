/**
 * Centralized environment configuration for Admin Web Dashboard.
 * Prevents hardcoded API URLs across components.
 */
const isProd = import.meta.env.PROD;
export const ENV = {
  API_BASE_URL: import.meta.env.VITE_API_BASE_URL || (isProd ? 'https://fieldtrackpro-backend-s7hs.onrender.com/api/v1' : 'http://127.0.0.1:8000/api/v1'),
  APP_ENV: import.meta.env.VITE_APP_ENV || (isProd ? 'production' : 'development'),
};
