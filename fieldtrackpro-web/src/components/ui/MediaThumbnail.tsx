import React, { useEffect, useState } from 'react';
import { Download, FileText, Trash2 } from 'lucide-react';
import { Button } from './Button';
import { apiClient } from '../../api/client';
import { VisitMedia } from '../../types';

interface MediaThumbnailProps {
  media: VisitMedia;
  canDelete?: boolean;
  onDeleted?: () => void;
}

/**
 * Renders one media attachment.
 *
 * FT-015: the media endpoints require an Authorization header. A plain
 * `<img src>` or `<a href>` cannot supply one, so previews rendered broken and
 * downloads returned 403. The bytes are fetched with credentials and exposed
 * as an object URL, which keeps the endpoint protected while letting the
 * browser display and save the file.
 *
 * Also fixes the type test: `media_type` is the enum PHOTO | DOCUMENT, not a
 * MIME string, so the previous `includes('image')` check was never true.
 */
export const MediaThumbnail: React.FC<MediaThumbnailProps> = ({
  media,
  canDelete = false,
  onDeleted,
}) => {
  const isPhoto = media.media_type === 'PHOTO';
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    if (!isPhoto) return;
    let revoked: string | null = null;
    let cancelled = false;

    apiClient
      .getMediaObjectUrl(media.id)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        revoked = url;
        setObjectUrl(url);
      })
      .catch((err: Error) => {
        if (!cancelled) setLoadError(err.message || 'Preview unavailable');
      });

    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [media.id, isPhoto]);

  const handleDownload = async () => {
    try {
      const url = objectUrl ?? (await apiClient.getMediaObjectUrl(media.id));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = media.storage_key.split('/').pop() || 'attachment';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      if (!objectUrl) URL.revokeObjectURL(url);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Download failed');
    }
  };

  /** FT-016: deletion was implemented in the API but unreachable from the UI. */
  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      await apiClient.deleteMedia(media.id);
      onDeleted?.();
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Delete failed');
      setIsDeleting(false);
    }
  };

  const fileName = media.storage_key.split('/').pop() || media.id;
  const sizeKb = (media.file_size_bytes / 1024).toFixed(1);

  return (
    <div className="p-space-3 bg-surface-container-low border border-outline-variant rounded-lg font-body-md text-xs flex items-center gap-space-3">
      <div className="w-14 h-14 shrink-0 rounded-lg overflow-hidden bg-surface-container flex items-center justify-center border border-outline-variant">
        {isPhoto && objectUrl ? (
          <img src={objectUrl} alt={fileName} className="w-full h-full object-cover" />
        ) : isPhoto && !loadError ? (
          <div className="w-5 h-5 border-2 border-outline border-t-transparent rounded-full animate-spin" />
        ) : (
          <FileText className="w-6 h-6 text-outline" />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <p className="font-headline-sm text-primary font-bold truncate">{fileName}</p>
        <p className="font-caption text-on-surface-variant">
          {sizeKb} KB · {media.media_type} · {new Date(media.uploaded_at).toLocaleString()}
        </p>
        {loadError && <p className="text-error font-semibold mt-0.5">{loadError}</p>}
      </div>

      <div className="flex items-center gap-space-2 shrink-0">
        <Button variant="outline" size="sm" icon={Download} onClick={() => void handleDownload()}>
          Download
        </Button>
        {canDelete && (
          <Button
            variant="danger"
            size="sm"
            icon={Trash2}
            isLoading={isDeleting}
            onClick={() => void handleDelete()}
            aria-label={`Delete ${fileName}`}
          >
            Delete
          </Button>
        )}
      </div>
    </div>
  );
};
