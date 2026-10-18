import React, { useEffect, useState } from 'react';
import { Camera, ImageOff } from 'lucide-react';
import { apiClient } from '../../api/client';

interface OutletProofImageProps {
  /** Stream one specific proof. */
  proofId?: string;
  /** Or stream the outlet's approved primary photo. */
  customerId?: string;
  alt: string;
  className?: string;
  emptyLabel?: string;
  onClick?: () => void;
}

/**
 * Outlet photo. The image routes need the Authorization header, which a plain <img src>
 * cannot send, so the bytes are fetched as a blob and shown through an object URL that
 * is revoked on unmount / when the source changes.
 */
export const OutletProofImage: React.FC<OutletProofImageProps> = ({
  proofId,
  customerId,
  alt,
  className = '',
  emptyLabel = 'No outlet photo yet',
  onClick,
}) => {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(Boolean(proofId || customerId));

  useEffect(() => {
    if (!proofId && !customerId) {
      setUrl(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    let created: string | null = null;
    setLoading(true);
    setFailed(false);
    setUrl(null);
    const req = proofId ? apiClient.getOutletProofImageUrl(proofId) : apiClient.getCustomerOutletImageUrl(customerId!);
    req
      .then((u) => {
        if (cancelled) {
          URL.revokeObjectURL(u);
          return;
        }
        created = u;
        setUrl(u);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [proofId, customerId]);

  if (loading) {
    return (
      <div
        role="status"
        aria-label="Loading photo"
        className={`flex items-center justify-center bg-surface-container animate-pulse ${className}`}
      >
        <Camera className="w-6 h-6 text-on-surface-variant" />
      </div>
    );
  }
  if (!url) {
    return (
      <div
        className={`flex flex-col items-center justify-center gap-1 bg-surface-container text-on-surface-variant text-xs text-center p-2 ${className}`}
      >
        <ImageOff className="w-6 h-6" />
        <span>{failed ? 'Photo unavailable' : emptyLabel}</span>
      </div>
    );
  }
  const img = <img src={url} alt={alt} className={`object-cover ${className}`} />;
  return onClick ? (
    <button
      type="button"
      onClick={onClick}
      className="block p-0 border-0 bg-transparent cursor-zoom-in"
      aria-label={`Open photo: ${alt}`}
    >
      {img}
    </button>
  ) : (
    img
  );
};

interface OutletPhotoLightboxProps {
  proofId: string | null;
  title?: string;
  onClose: () => void;
}

/** Large view of one proof photo. */
export const OutletPhotoLightbox: React.FC<OutletPhotoLightboxProps> = ({ proofId, title, onClose }) => {
  useEffect(() => {
    if (!proofId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [proofId, onClose]);

  if (!proofId) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title ? `Photo: ${title}` : 'Outlet photo'}
      className="fixed inset-0 z-[100] bg-black/80 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <button
        type="button"
        onClick={onClose}
        className="absolute top-4 right-4 px-3 py-1.5 rounded bg-white/90 text-sm font-bold cursor-pointer"
      >
        Close
      </button>
      <div onClick={(e) => e.stopPropagation()} className="max-w-5xl max-h-[90vh]">
        <OutletProofImage
          proofId={proofId}
          alt={title || 'Outlet photo'}
          className="max-h-[85vh] max-w-full object-contain rounded-lg"
        />
      </div>
    </div>
  );
};
