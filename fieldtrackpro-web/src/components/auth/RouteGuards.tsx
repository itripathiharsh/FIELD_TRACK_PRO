import React from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { ACCOUNTANT_BLOCKED_PATHS, canViewAdmin, canViewFinance, isAccountant } from '../../utils/roles';
import { ReconnectingScreen } from './ReconnectingScreen';
import { ChangePasswordRequiredPage } from '../../pages/ChangePasswordRequiredPage';

export const AuthLoadingFallback: React.FC = () => (
  <div className="min-h-screen bg-background flex flex-col items-center justify-center text-on-surface">
    <div className="w-10 h-10 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin" />
    <p className="mt-space-4 font-caption text-caption text-on-surface-variant">
      Initializing FieldTrack Pro Subsystem...
    </p>
  </div>
);

/** Shown (HTTP 403 equivalent) when a signed-in user opens a page their role cannot use. */
export const NotAuthorizedPage: React.FC = () => (
  <div role="alert" className="flex flex-col items-center justify-center text-center py-space-12 gap-space-3">
    <ShieldAlert className="w-12 h-12 text-error" />
    <h1 className="font-headline-md text-headline-md text-primary">Not authorized</h1>
    <p className="font-caption text-caption text-on-surface-variant max-w-md">
      Your account does not have permission to view this page. If you believe this is a mistake,
      contact your administrator.
    </p>
    <Link to="/" className="font-button text-button text-primary underline">
      Back to dashboard
    </Link>
  </div>
);

/** Requires a signed-in user. An expired session redirects to login with a message. */
export const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isAuthenticated, isLoading, sessionExpired, reconnecting } = useAuth();
  // Server unreachable while restoring: keep the session and show Reconnecting (never the login page).
  if (reconnecting && !isAuthenticated) return <ReconnectingScreen />;
  if (isLoading) return <AuthLoadingFallback />;
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={sessionExpired ? { reason: 'session_expired' } : undefined} />;
  }
  // Forced password change: nothing else is reachable until it is done.
  if (user?.must_change_password === true) return <ChangePasswordRequiredPage />;
  return <>{children}</>;
};

/** Admin pages: ADMIN / SUPER_ADMIN, and the ACCOUNTANT (reads; the backend allows only her approved writes). */
export const AdminRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isAuthenticated, isLoading, sessionExpired, reconnecting } = useAuth();
  if (reconnecting && !isAuthenticated) return <ReconnectingScreen />;
  if (isLoading) return <AuthLoadingFallback />;
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={sessionExpired ? { reason: 'session_expired' } : undefined} />;
  }
  if (user?.must_change_password === true) return <ChangePasswordRequiredPage />;
  if (!canViewAdmin(user)) return <NotAuthorizedPage />;
  return <>{children}</>;
};

/** Reports & Collections: ADMIN / SUPER_ADMIN and the read-only ACCOUNTANT. Anyone else sees not-authorized. */
export const FinanceRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, isAuthenticated, isLoading, sessionExpired, reconnecting } = useAuth();
  if (reconnecting && !isAuthenticated) return <ReconnectingScreen />;
  if (isLoading) return <AuthLoadingFallback />;
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={sessionExpired ? { reason: 'session_expired' } : undefined} />;
  }
  if (user?.must_change_password === true) return <ChangePasswordRequiredPage />;
  if (!canViewFinance(user)) return <NotAuthorizedPage />;
  return <>{children}</>;
};

/**
 * Keeps an ACCOUNTANT out of the field-app pages (employee visit planning, form filling): those redirect to
 * the dashboard. Every admin page is open to her. Other roles pass through untouched.
 */
export const AccountantScope: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const fieldPage =
    ACCOUNTANT_BLOCKED_PATHS.some((p) => pathname === p || pathname.startsWith(p + '/')) ||
    /^\/visits\/[^/]+\/forms\//.test(pathname);
  if (isAccountant(user) && fieldPage) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
};
