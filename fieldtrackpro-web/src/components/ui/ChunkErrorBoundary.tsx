import React from 'react';
import { CloudOff } from 'lucide-react';
import { Button } from './Button';
import { isChunkLoadError } from '../../utils/chunkError';

interface Props {
  children: React.ReactNode;
  /** When this value changes (e.g. the pathname) a previous chunk error is cleared. */
  resetKey?: string;
}

interface State {
  error: Error | null;
}

/**
 * Catches failed dynamic imports of lazy routes and offers a reload (a new deploy
 * replaces hashed chunk names, so a stale tab cannot fetch them any more). Any
 * other render error is re-thrown to the enclosing ErrorBoundary unchanged.
 */
export class ChunkErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (!isChunkLoadError(error)) throw error;
    return (
      <div role="alert" className="flex flex-col items-center text-center py-space-12 gap-space-3">
        <CloudOff className="w-10 h-10 text-secondary" aria-hidden="true" />
        <h2 className="font-title-md text-title-md text-primary font-bold">This page could not be loaded</h2>
        <p className="font-caption text-xs text-on-surface-variant max-w-md">
          Your connection may have dropped, or FieldTrack Pro was updated while this tab was open. Reload to get
          the latest version.
        </p>
        <Button variant="primary" size="md" onClick={() => window.location.reload()}>
          Reload
        </Button>
      </div>
    );
  }
}
