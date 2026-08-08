import React, { useEffect, useState } from 'react';
import { Image as ImageIcon, FileText, Download, ExternalLink } from 'lucide-react';
import { DataTable, Column } from '../components/ui/DataTable';
import { PageHeader } from '../components/ui/PageHeader';
import { Modal } from '../components/ui/Modal';
import { Button } from '../components/ui/Button';
import { apiClient } from '../api/client';
import { VisitMedia } from '../types';
import { ENV } from '../config/env';

export const MediaViewerPage: React.FC = () => {
  const [mediaItems, setMediaItems] = useState<VisitMedia[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedMedia, setSelectedMedia] = useState<VisitMedia | null>(null);

  useEffect(() => {
    apiClient.getVisits()
      .then((visits) => {
        const promises = visits.map((v) => apiClient.getVisitMedia(v.id).catch(() => []));
        return Promise.all(promises);
      })
      .then((results) => {
        const flattened = results.flat();
        setMediaItems(flattened);
      })
      .catch(() => setMediaItems([]))
      .finally(() => setIsLoading(false));
  }, []);

  const columns: Column<VisitMedia>[] = [
    {
      header: 'File Name / Key',
      accessor: (item) => (
        <div className="flex items-center gap-space-3">
          <div className="p-2 bg-primary-container text-on-primary-container rounded-lg shrink-0">
            {item.media_type.includes('image') ? <ImageIcon className="w-4 h-4 text-secondary-container" /> : <FileText className="w-4 h-4 text-primary" />}
          </div>
          <div>
            <p className="font-headline-sm text-sm text-primary font-bold">{item.storage_key.split('/').pop() || item.id}</p>
            <p className="font-caption text-xs text-on-surface-variant font-mono">Visit: {item.visit_id.substring(0, 8)}...</p>
          </div>
        </div>
      ),
    },
    {
      header: 'MIME Type',
      accessor: (item) => <span className="font-caption text-xs text-on-surface bg-surface-container-high px-2 py-0.5 rounded font-mono">{item.media_type}</span>,
    },
    {
      header: 'Size',
      accessor: (item) => <span className="font-caption text-xs text-on-surface-variant font-medium">{(item.file_size_bytes / 1024).toFixed(1)} KB</span>,
    },
    {
      header: 'Uploaded At',
      accessor: (item) => (
        <span className="font-caption text-xs text-on-surface-variant">
          {new Date(item.uploaded_at).toLocaleString()}
        </span>
      ),
    },
    {
      header: 'Action',
      accessor: (item) => (
        <Button
          variant="outline"
          size="sm"
          icon={ExternalLink}
          onClick={(e) => {
            e.stopPropagation();
            setSelectedMedia(item);
          }}
        >
          Preview
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <PageHeader
        title="Media Vault & Attachments"
        subtitle="Central repository for uploaded field inspection photos, signatures, and PDFs."
      />

      <DataTable
        columns={columns}
        data={mediaItems}
        isLoading={isLoading}
        searchPlaceholder="Search media by key, type, visit ID..."
        searchFilter={(item, q) =>
          item.storage_key.toLowerCase().includes(q.toLowerCase()) ||
          item.media_type.toLowerCase().includes(q.toLowerCase())
        }
        onRowClick={(item) => setSelectedMedia(item)}
      />

      {/* Lightbox Preview Modal */}
      {selectedMedia && (
        <Modal
          isOpen={Boolean(selectedMedia)}
          onClose={() => setSelectedMedia(null)}
          title={selectedMedia.storage_key.split('/').pop() || 'Media Preview'}
          subtitle={`Uploaded on ${new Date(selectedMedia.uploaded_at).toLocaleString()}`}
          size="lg"
        >
          <div className="space-y-space-4">
            <div className="bg-surface-container-low border border-outline-variant rounded-xl p-space-6 flex items-center justify-center min-h-[240px]">
              {selectedMedia.media_type.includes('image') ? (
                <img
                  src={`${ENV.API_BASE_URL}/api/v1/media/${selectedMedia.id}/download`}
                  alt="Site Attachment"
                  className="max-h-[360px] max-w-full rounded-lg object-contain shadow-md"
                  onError={(e) => {
                    // Fallback visual if endpoint binary not found
                    (e.target as HTMLElement).style.display = 'none';
                  }}
                />
              ) : (
                <div className="flex flex-col items-center gap-space-2 text-on-surface-variant">
                  <FileText className="w-16 h-16 text-outline" />
                  <p className="font-headline-sm text-sm font-semibold">{selectedMedia.media_type}</p>
                </div>
              )}
            </div>

            <div className="flex items-center justify-between border-t border-surface-container-highest pt-space-4">
              <div className="text-xs text-on-surface-variant font-mono">
                Size: {(selectedMedia.file_size_bytes / 1024).toFixed(1)} KB | ID: {selectedMedia.id}
              </div>
              <a
                href={`${ENV.API_BASE_URL}/api/v1/media/${selectedMedia.id}/download`}
                target="_blank"
                rel="noreferrer"
              >
                <Button variant="secondary" size="sm" icon={Download}>
                  Download File
                </Button>
              </a>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
