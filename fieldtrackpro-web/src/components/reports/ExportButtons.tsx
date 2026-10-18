import React from 'react';
import { Download, FileSpreadsheet } from 'lucide-react';
import { Button } from '../ui/Button';

export type ExportFormat = 'xlsx' | 'pdf';

export interface ExportButtonsProps {
  onExport: (format: ExportFormat) => void;
  /** Format currently being generated (shows a spinner on that button, disables both). */
  exporting: ExportFormat | null;
  /** True when there is nothing to export (disables both, with `emptyReason` as tooltip). */
  empty?: boolean;
  /** Disabled because the data is still loading. */
  loading?: boolean;
  emptyReason?: string;
  /** Extra buttons (e.g. CSV) rendered before Excel / PDF. */
  children?: React.ReactNode;
}

/** Excel + PDF buttons: server-side files containing ALL filtered rows. */
export const ExportButtons: React.FC<ExportButtonsProps> = ({
  onExport,
  exporting,
  empty = false,
  loading = false,
  emptyReason = 'Nothing to export for the current filters',
  children,
}) => {
  const disabled = loading || empty || exporting !== null;
  const tip = empty ? emptyReason : 'Exports every row matching the current filters (not just this page)';
  return (
    <div className="flex items-center gap-2" title={tip}>
      {children}
      <Button
        variant="outline"
        size="sm"
        icon={FileSpreadsheet}
        onClick={() => onExport('xlsx')}
        disabled={disabled}
        isLoading={exporting === 'xlsx'}
        title={tip}
      >
        Export Excel
      </Button>
      <Button
        variant="outline"
        size="sm"
        icon={Download}
        onClick={() => onExport('pdf')}
        disabled={disabled}
        isLoading={exporting === 'pdf'}
        title={tip}
      >
        Export PDF
      </Button>
    </div>
  );
};
