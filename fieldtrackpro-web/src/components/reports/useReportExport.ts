import { useCallback, useState } from 'react';
import { apiClient } from '../../api/client';
import { saveBlob } from '../../utils/download';
import { ReportRequest } from '../../utils/reportFilters';
import { ExportFormat } from './ExportButtons';

const FALLBACK_NAMES: Record<string, string> = {
  business_summary: 'Financial_BI',
  outstanding: 'Outstanding',
  outlets: 'Outlets',
  visits: 'Visits',
  geo: 'Geo_Verification',
  staff: 'Field_Staff',
  collections_overview: 'Collections_Overview',
  monthly_periods: 'Monthly_Snapshots',
};

/**
 * Download a report through the API (authenticated blob) using the SAME request
 * (report + params) that produced the table on screen. The file name comes from
 * the server's Content-Disposition header.
 */
export function useReportExport(onError: (message: string) => void, onDone?: (filename: string) => void) {
  const [exporting, setExporting] = useState<ExportFormat | null>(null);

  const run = useCallback(
    async (req: ReportRequest, format: ExportFormat, extra?: Record<string, string>) => {
      setExporting(format);
      try {
        const { blob, filename } = await apiClient.downloadReportFile(req.report, req.params, format, extra);
        const name = filename ?? `${FALLBACK_NAMES[req.report] ?? 'report'}.${format}`;
        saveBlob(blob, name);
        onDone?.(name);
      } catch (err) {
        onError(err instanceof Error ? err.message : `${format === 'pdf' ? 'PDF' : 'Excel'} export failed`);
      } finally {
        setExporting(null);
      }
    },
    [onError, onDone],
  );

  return { exporting, run };
}
