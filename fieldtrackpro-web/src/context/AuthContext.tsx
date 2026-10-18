import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { ApiError, apiClient } from '../api/client';
import { User } from '../types';
import { sanitizeUser } from '../utils/roles';

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** True when a signed-in session ended because the token could not be refreshed. */
  sessionExpired: boolean;
  /**
   * True while the session could not be restored because the server was unreachable
   * (network error, timeout, 5xx, 429). The session is NOT lost: the app retries
   * automatically and the user can retry by hand. Never redirects to login.
   */
  reconnecting: boolean;
  /** Number of restore attempts made so far while reconnecting. */
  reconnectAttempt: number;
  /** True while a (manual or automatic) retry is in flight. */
  reconnectChecking: boolean;
  /** Retry restoring the session right now. */
  retryReconnect: () => void;
  /** True when the server requires the user to set a new password before anything else. */
  mustChangePassword: boolean;
  login: (identity: string, pass: string) => Promise<User>;
  logout: () => Promise<void>;
  /**
   * Change the signed-in user's password. The backend revokes EVERY refresh token on
   * success (this device included), so the session is re-established with the new
   * password. Resolves 'reauthenticated' (still signed in, must_change_password cleared)
   * or 'signed_out' (re-login failed; the user must sign in again). Rejects with the
   * server's error when the change itself fails (e.g. wrong current password).
   */
  changePassword: (current: string, next: string) => Promise<'reauthenticated' | 'signed_out'>;
  /** Re-read GET /auth/me (e.g. after a password change) and update the user. */
  refreshUser: () => Promise<User>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

/** Automatic retry delays after the first failed restore (3 tries over ~10 s), then a slow poll. */
const RECONNECT_DELAYS_MS = [2000, 3000, 5000];
const RECONNECT_SLOW_POLL_MS = 10000;

/** True when the failure is "the server could not be reached / is struggling", not "you are not signed in". */
function isTransientFailure(err: unknown): boolean {
  return err instanceof ApiError && err.retryable;
}

/**
 * Authentication state.
 *
 * FT-001 (CRITICAL): this provider previously caught every authentication
 * failure and fabricated an ADMIN session backed by a literal
 * 'demo_access_token'. Any credential - including deliberately invalid ones -
 * produced a full administrator interface.
 *
 * The rules now enforced here:
 *   - the backend is the sole authority on identity and role;
 *   - a failed login throws, and leaves no session and no stored token;
 *   - a stored token that /auth/me DEFINITIVELY rejects (401/403) is discarded,
 *     never "recovered" into a guessed user;
 *   - a network error / timeout / 5xx / 429 is NOT a rejection: the session hint
 *     is kept, a "Reconnecting" state is shown and the restore is retried;
 *   - no role is ever inferred from the email address.
 */
export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [sessionExpired, setSessionExpired] = useState<boolean>(false);
  const [reconnecting, setReconnecting] = useState<boolean>(false);
  const [reconnectAttempt, setReconnectAttempt] = useState<number>(0);
  const [reconnectChecking, setReconnectChecking] = useState<boolean>(false);

  /** Bumped to cancel an in-flight restore loop (login / logout / unmount). */
  const generationRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef<() => void>(() => {});

  const stopRestoreLoop = useCallback(() => {
    generationRef.current += 1;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    setReconnecting(false);
    setReconnectChecking(false);
  }, []);

  // 401 + failed refresh mid-session: drop the user so route guards redirect to login.
  useEffect(
    () =>
      apiClient.onSessionExpired?.(() => {
        setUser(null);
        setSessionExpired(true);
      }),
    [],
  );

  // Logout performed in another tab: leave this one signed out too.
  useEffect(() => {
    const stopSync = apiClient.startTabSync?.();
    const off = apiClient.onRemoteLogout?.(() => {
      stopRestoreLoop();
      setUser(null);
      setSessionExpired(false);
      setIsLoading(false);
    });
    return () => {
      off?.();
      stopSync?.();
    };
  }, [stopRestoreLoop]);

  // The server says a password change is pending: the route guard shows the change screen.
  useEffect(
    () =>
      apiClient.onPasswordChangeRequired?.(() => {
        setUser((u) => (u && !u.must_change_password ? { ...u, must_change_password: true } : u));
      }),
    [],
  );

  // Restore a session only if the stored token is genuinely accepted.
  useEffect(() => {
    const generation = ++generationRef.current;
    let attempts = 0;
    const alive = () => generationRef.current === generation;

    const restoreOnce = async (): Promise<'done' | 'transient'> => {
      try {
        let restored: boolean;
        if (typeof apiClient.restoreSession === 'function') {
          const outcome = await apiClient.restoreSession();
          // Server unreachable: keep the session (hint + memory) and let the caller retry.
          if (outcome === 'transient') return 'transient';
          restored = outcome === 'restored';
        } else if (typeof apiClient.tryRestoreSession === 'function') {
          restored = await apiClient.tryRestoreSession();
        } else {
          restored = Boolean(apiClient.hasStoredSession?.());
        }
        if (restored) {
          const currentUser = await apiClient.getCurrentUser();
          if (alive()) setUser(sanitizeUser(currentUser));
        } else if (alive()) {
          setUser(null);
        }
        return 'done';
      } catch (err) {
        if (isTransientFailure(err)) return 'transient';
        // Definitive: the token is absent, expired, revoked or forged. Discard it.
        // No fallback user: an unverifiable token means "not signed in".
        apiClient.clearSession?.();
        if (alive()) setUser(null);
        return 'done';
      }
    };

    const step = async (): Promise<void> => {
      if (!alive()) return;
      setReconnectChecking(true);
      const result = await restoreOnce();
      if (!alive()) return;
      attempts += 1;
      setReconnectChecking(false);
      if (result === 'done') {
        setReconnecting(false);
        setIsLoading(false);
        return;
      }
      setReconnectAttempt(attempts);
      setReconnecting(true);
      setIsLoading(false);
      const delay = attempts <= RECONNECT_DELAYS_MS.length ? RECONNECT_DELAYS_MS[attempts - 1] : RECONNECT_SLOW_POLL_MS;
      timerRef.current = setTimeout(() => void step(), delay);
    };

    attemptRef.current = () => {
      if (!alive()) return;
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
      void step();
    };

    void step();
    return () => {
      generationRef.current += 1;
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
    };
  }, []);

  const retryReconnect = useCallback(() => attemptRef.current(), []);

  const login = useCallback(
    async (identity: string, pass: string): Promise<User> => {
      stopRestoreLoop();
      setIsLoading(true);
      try {
        await apiClient.login(identity, pass);
        // Identity and role come from the server, never from the submitted email.
        const currentUser = sanitizeUser(await apiClient.getCurrentUser());
        setSessionExpired(false);
        setUser(currentUser);
        return currentUser;
      } catch (err) {
        // Authentication failed. Leave no partial session behind and let the
        // caller render the real reason.
        apiClient.clearSession();
        setUser(null);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [stopRestoreLoop],
  );

  const logout = useCallback(async (): Promise<void> => {
    // FT-009: revoke the refresh token server-side before clearing locally.
    // Local state is cleared even if the network call fails, so the user is
    // never trapped in a session they asked to end.
    stopRestoreLoop();
    try {
      await apiClient.logout();
    } finally {
      setUser(null);
      setSessionExpired(false);
      setIsLoading(false);
    }
  }, [stopRestoreLoop]);

  const refreshUser = useCallback(async (): Promise<User> => {
    const fresh = sanitizeUser(await apiClient.getCurrentUser());
    setUser(fresh);
    return fresh;
  }, []);

  const changePassword = useCallback(
    async (current: string, next: string): Promise<'reauthenticated' | 'signed_out'> => {
      const identity = user?.email || user?.mobile_number || '';
      const keptSession = await apiClient.changePassword(current, next);
      try {
        if (keptSession) {
          // The server returned a fresh token pair: stay signed in, just re-read /auth/me.
          await refreshUser();
          return 'reauthenticated';
        }
        if (!identity) throw new Error('no identity to sign back in with');
        await login(identity, next);
        return 'reauthenticated';
      } catch {
        await logout();
        return 'signed_out';
      }
    },
    [user, login, logout, refreshUser],
  );

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        sessionExpired,
        reconnecting,
        reconnectAttempt,
        reconnectChecking,
        retryReconnect,
        mustChangePassword: user?.must_change_password === true,
        login,
        logout,
        changePassword,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
