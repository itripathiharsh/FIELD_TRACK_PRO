import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { apiClient } from '../api/client';
import { User } from '../types';

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (identity: string, pass: string) => Promise<User>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

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
 *   - a stored token that /auth/me rejects is discarded, never "recovered"
 *     into a guessed user;
 *   - no role is ever inferred from the email address.
 */
export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  // Restore a session only if the stored token is genuinely accepted.
  useEffect(() => {
    let cancelled = false;

    const restore = async () => {
      if (!apiClient.hasStoredSession()) {
        if (!cancelled) setIsLoading(false);
        return;
      }
      try {
        const currentUser = await apiClient.getCurrentUser();
        if (!cancelled) setUser(currentUser);
      } catch {
        // The token is absent, expired, revoked or forged. Discard it.
        // No fallback user: an unverifiable token means "not signed in".
        apiClient.clearSession();
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    };

    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (identity: string, pass: string): Promise<User> => {
    setIsLoading(true);
    try {
      await apiClient.login(identity, pass);
      // Identity and role come from the server, never from the submitted email.
      const currentUser = await apiClient.getCurrentUser();
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
  }, []);

  const logout = useCallback(async (): Promise<void> => {
    // FT-009: revoke the refresh token server-side before clearing locally.
    // Local state is cleared even if the network call fails, so the user is
    // never trapped in a session they asked to end.
    try {
      await apiClient.logout();
    } finally {
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
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
