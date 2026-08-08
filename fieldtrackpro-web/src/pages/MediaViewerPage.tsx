import React, { useCallback, useEffect, useState } from 'react';
import { Image as ImageIcon } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { MediaThumbnail } from '../components/ui/MediaThumbnail';
import { apiClient } from '../api/client';
import { VisitMedia } from '../types';

export const MediaViewerPage: React.FC = () => {
  const [mediaItems, setMediaItems] = useState<VisitMedia[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  const load = useCallback(() => {
    setIsLoading(true);
    setError(null);
    apiClient
      .getVisits()
      .then(async (visits) => {
        const results = await Promise.all(
          visits.map((v) => apiClient.getVisitMedia(v.id).catch(() => [] as VisitMedia[])),
        );
        setMediaItems(results.flat());
      })
      .catch((err: Error) => {
        setMediaItems([]);
        setError(err.message || 'Unable to load media attachments');
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = query
    ? mediaItems.filter(
        (m) =>
          m.storage_key.toLowerCase().includes(query.toLowerCase()) ||
          m.media_type.toLowerCase().includes(query.toLowerCase()),
      )
    : mediaItems;

  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <PageHeader
        title="Media Vault & Attachments"
        subtitle="Central repository for uploaded field inspection photos, signatures, and PDFs."
      />

      {error && <ErrorBanner message={error} onRetry={load} onDismiss={() => setError(null)} />}

      <Card variant="default" className="space-y-space-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-4">
          <div className="max-w-md w-full">
            <Input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onClear={() => setQuery('')}
              placeholder="Search media by file name or type..."
            />
          </div>
          <span className="font-label-md text-xs text-on-surface-variant uppercase tracking-wider shrink-0 font-medium">
            Total: <strong className="text-primary font-bold">{filtered.length}</strong> files
          </span>
        </div>

        {isLoading ? (
          <div className="space-y-space-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-20 bg-surface-container-high rounded-lg animate-pulse"
              />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={ImageIcon}
            title={query ? 'No media matches this search' : 'No media uploaded yet'}
            subtitle={
              query
                ? 'Try a different file name or type.'
                : 'Photos and documents attached to visits will appear here.'
            }
          />
        ) : (
          /* FT-015: previews are fetched with the Authorization header via
             MediaThumbnail. The old lightbox pointed an <img src> straight at
             the protected download endpoint, which always returned 403. */
          <div className="space-y-space-3">
            {filtered.map((media) => (
              <MediaThumbnail key={media.id} media={media} onDeleted={load} canDelete />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
};
