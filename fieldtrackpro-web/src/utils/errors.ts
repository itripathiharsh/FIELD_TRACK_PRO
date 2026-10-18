import { ApiError } from '../api/client';

/** Best human-readable message from an unknown thrown value. */
export function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === 'object' && err !== null) {
    const e = err as {
      response?: { data?: { error?: { message?: unknown } } };
      data?: { error?: { message?: unknown } };
      message?: unknown;
    };
    const nested = e.response?.data?.error?.message ?? e.data?.error?.message ?? e.message;
    if (typeof nested === 'string' && nested) return nested;
  }
  return fallback;
}

/** Per-field validation messages from a 422 ApiError, if any. */
export function fieldErrorsOf(err: unknown): Record<string, string> | undefined {
  return err instanceof ApiError && err.fieldErrors && Object.keys(err.fieldErrors).length > 0
    ? err.fieldErrors
    : undefined;
}
