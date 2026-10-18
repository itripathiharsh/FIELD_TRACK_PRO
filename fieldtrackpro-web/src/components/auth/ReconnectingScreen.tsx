import React from 'react';
import { WifiOff } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../ui/Button';

/**
 * Shown instead of the login page when the session could not be restored because
 * the server is unreachable (network error / timeout / 5xx / 429). The session is
 * kept; the provider retries automatically and the user can retry by hand.
 */
export const ReconnectingScreen: React.FC = () => {
  const { reconnectAttempt, reconnectChecking, retryReconnect, logout } = useAuth();
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center text-on-surface px-6 text-center">
      <div role="status" aria-live="polite" className="flex flex-col items-center max-w-md">
        <WifiOff className="w-10 h-10 text-secondary mb-space-3" aria-hidden="true" />
        <h1 className="font-headline-md text-headline-md text-primary">Reconnecting…</h1>
        <p className="mt-space-2 font-caption text-caption text-on-surface-variant">
          We cannot reach the FieldTrack Pro server right now. You are still signed in, and we will keep
          trying automatically.
          {reconnectAttempt > 0 && (
            <span className="block mt-1">Attempt {reconnectAttempt} did not succeed.</span>
          )}
        </p>
      </div>
      <div className="mt-space-4 flex items-center gap-space-3">
        <Button type="button" variant="primary" onClick={retryReconnect} isLoading={reconnectChecking}>
          Retry now
        </Button>
        <button
          type="button"
          onClick={() => void logout()}
          className="font-button text-button text-primary underline"
        >
          Sign out
        </button>
      </div>
    </div>
  );
};
