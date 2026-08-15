import React, { useState } from 'react';
import { Download, FileSignature } from 'lucide-react';
import { Button } from './Button';
import { apiClient } from '../../api/client';
import { VisitSignature } from '../../types';

interface SignatureThumbnailProps {
  signature: VisitSignature;
}

/**
 * Renders a digital signature with download capability.
 */
export const SignatureThumbnail: React.FC<SignatureThumbnailProps> = ({ signature }) => {
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownload = async () => {
    try {
      setIsDownloading(true);
      setLoadError(null);
      const { download_url } = await apiClient.getSignatureDownloadUrl(signature.id);
      window.open(download_url, '_blank');
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Download failed');
    } finally {
      setIsDownloading(false);
    }
  };

  const typeLabel = signature.signature_type === 'CUSTOMER' ? 'Customer Acknowledgement' : 'Employee Signature';
  const methodLabel = signature.capture_method === 'PHOTO_UPLOAD' ? 'Uploaded photo' : 'Signed on screen';

  return (
    <div className="p-space-3 bg-surface-container-low border border-outline-variant rounded-lg font-body-md text-xs flex items-center gap-space-3">
      <div className="w-14 h-14 shrink-0 rounded-lg overflow-hidden bg-surface-container flex items-center justify-center border border-outline-variant">
        <FileSignature className="w-6 h-6 text-primary" />
      </div>

      <div className="min-w-0 flex-1">
        <p className="font-headline-sm text-primary font-bold">{typeLabel}</p>
        <p className="font-caption text-on-surface-variant">
          {methodLabel} &middot; {new Date(signature.signed_at).toLocaleString()}
        </p>
        {loadError && <p className="text-error font-semibold mt-0.5">{loadError}</p>}
      </div>

      <div className="flex items-center gap-space-2 shrink-0">
        <Button variant="outline" size="sm" icon={Download} isLoading={isDownloading} onClick={() => void handleDownload()}>
          Download
        </Button>
      </div>
    </div>
  );
};
