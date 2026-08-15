import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  UploadCloud,
  FileSpreadsheet,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Building2,
  Receipt,
  Wallet,
  Download,
  RotateCcw,
  History,
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { StatusBadge } from '../components/ui/StatusBadge';
import { MetricCard } from '../components/ui/MetricCard';
import { EmptyState } from '../components/ui/EmptyState';
import { apiClient } from '../api/client';
import {
  ImportBatchRead,
  ImportPreviewResponse,
  OutletMatchStrategy,
} from '../types';

const STEP_LABELS = [
  'Upload',
  'Select Sheet',
  'Map Columns',
  'Validate & Preview',
  'Review',
  'Confirm Import',
  'Result',
];

const buildSuggestedMapping = (p: ImportPreviewResponse): Record<string, string> => {
  const m: Record<string, string> = {};
  for (const col of p.columns) {
    const suggested = p.suggested_mapping[col];
    if (suggested) m[col] = suggested;
  }
  return m;
};

/** Step indicator bar - no existing Stepper component in the design system, so this follows the same spacing/typography/color conventions as StatusBadge/PageHeader rather than introducing a new visual language. */
const StepIndicator: React.FC<{ current: number }> = ({ current }) => (
  <div className="flex items-center gap-space-1 overflow-x-auto pb-space-1">
    {STEP_LABELS.map((label, idx) => {
      const stepNum = idx + 1;
      const isDone = stepNum < current;
      const isActive = stepNum === current;
      return (
        <React.Fragment key={label}>
          <div className="flex items-center gap-space-2 shrink-0">
            <div
              className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 border ${
                isDone
                  ? 'bg-primary-container text-on-primary-container border-primary-container'
                  : isActive
                    ? 'bg-primary text-on-primary border-primary'
                    : 'bg-surface text-on-surface-variant border-outline-variant'
              }`}
            >
              {isDone ? <CheckCircle2 className="w-4 h-4" /> : stepNum}
            </div>
            <span
              className={`font-label-md text-xs uppercase tracking-wider whitespace-nowrap ${
                isActive ? 'text-primary font-bold' : 'text-on-surface-variant'
              }`}
            >
              {label}
            </span>
          </div>
          {idx < STEP_LABELS.length - 1 && (
            <div className={`w-6 h-px shrink-0 ${isDone ? 'bg-primary-container' : 'bg-outline-variant'}`} />
          )}
        </React.Fragment>
      );
    })}
  </div>
);

export const ImportWizardPage: React.FC = () => {
  const navigate = useNavigate();

  const [step, setStep] = useState(1);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [sheetName, setSheetName] = useState('');
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [strategy, setStrategy] = useState<OutletMatchStrategy>('outlet_code');
  const [allowGenerated, setAllowGenerated] = useState(false);
  const [batch, setBatch] = useState<ImportBatchRead | null>(null);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resetAll = () => {
    setStep(1);
    setFile(null);
    setPreview(null);
    setSheetName('');
    setMapping({});
    setStrategy('outlet_code');
    setAllowGenerated(false);
    setBatch(null);
    setError(null);
  };

  const handleFileSelect = async (f: File) => {
    setError(null);
    setIsLoading(true);
    try {
      const p = await apiClient.previewImportFile(f);
      setFile(f);
      setPreview(p);
      setSheetName(p.sheet_name);
      setMapping(buildSuggestedMapping(p));
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to read the uploaded file');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSheetChange = async (name: string) => {
    if (!file) return;
    setError(null);
    setIsLoading(true);
    try {
      const p = await apiClient.previewImportFile(file, name);
      setPreview(p);
      setSheetName(p.sheet_name);
      setMapping(buildSuggestedMapping(p));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sheet');
    } finally {
      setIsLoading(false);
    }
  };

  const handleValidate = async () => {
    if (!file) return;
    setError(null);
    setIsLoading(true);
    try {
      const mappedColumns = Object.fromEntries(Object.entries(mapping).filter(([, v]) => v));
      const b = await apiClient.validateImportFile(file, {
        sheet_name: sheetName,
        column_mapping: mappedColumns,
        outlet_match_strategy: strategy,
        allow_generated_invoice_numbers: allowGenerated,
      });
      setBatch(b);
      setStep(4);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Validation failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCommit = async () => {
    if (!batch) return;
    setError(null);
    setIsLoading(true);
    try {
      const committed = await apiClient.commitImportBatch(batch.id);
      setBatch(committed);
      setStep(7);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Commit failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownloadErrors = async () => {
    if (!batch) return;
    try {
      const url = await apiClient.getImportErrorsCsvObjectUrl(batch.id);
      const a = document.createElement('a');
      a.href = url;
      a.download = `import_${batch.filename}_errors.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to download error report');
    }
  };

  const summary = batch?.summary;

  return (
    <div className="space-y-space-6">
      <PageHeader
        title="Import Excel / MIS Data"
        subtitle="Upload a client MIS/Tally export and bring outlets, invoices, and collection history into FieldTrack Pro safely."
        actions={
          <Button variant="outline" icon={History} onClick={() => navigate('/imports')}>
            Import History
          </Button>
        }
      />

      <Card>
        <StepIndicator current={step} />
      </Card>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {/* Step 1: Upload */}
      {step === 1 && (
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Step 1 · Upload File</CardTitle>
              <CardSubtitle>Excel workbook (.xlsx or .xls) exported from the client's MIS/Tally system.</CardSubtitle>
            </div>
          </CardHeader>
          <label
            htmlFor="import-file-input"
            className="flex flex-col items-center justify-center gap-space-3 p-space-10 border-2 border-dashed border-outline-variant rounded-2xl bg-surface-container-low/60 hover:border-primary-container hover:bg-surface-container-low transition-colors cursor-pointer text-center"
          >
            <div className="p-space-4 bg-surface rounded-2xl border border-outline-variant/80 text-primary shadow-xs">
              <UploadCloud className="w-8 h-8 stroke-[1.5]" />
            </div>
            <div>
              <p className="font-headline-sm text-sm text-primary font-bold">Click to choose a file, or drag it here</p>
              <p className="font-caption text-xs text-on-surface-variant mt-1">Supported formats: .xlsx, .xls</p>
            </div>
            <input
              id="import-file-input"
              type="file"
              accept=".xlsx,.xls"
              className="hidden"
              disabled={isLoading}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleFileSelect(f);
              }}
            />
          </label>
          {isLoading && <p className="mt-space-3 text-xs text-on-surface-variant text-center">Reading file…</p>}
        </Card>
      )}

      {/* Step 2: Select Sheet */}
      {step === 2 && preview && (
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Step 2 · Select Sheet</CardTitle>
              <CardSubtitle>{file?.name} · {preview.all_sheets.length} sheet(s) found</CardSubtitle>
            </div>
          </CardHeader>
          <div className="max-w-sm mb-space-5">
            <Select
              label="Sheet"
              value={sheetName}
              onChange={(e) => void handleSheetChange(e.target.value)}
              disabled={isLoading}
            >
              {preview.all_sheets.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </Select>
          </div>
          <SamplePreviewTable preview={preview} />
          <div className="flex justify-between mt-space-6">
            <Button variant="ghost" icon={ArrowLeft} onClick={() => setStep(1)}>Back</Button>
            <Button variant="primary" icon={ArrowRight} iconPosition="right" onClick={() => setStep(3)} disabled={isLoading}>
              Continue to Mapping
            </Button>
          </div>
        </Card>
      )}

      {/* Step 3: Map Columns */}
      {step === 3 && preview && (
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Step 3 · Map Columns</CardTitle>
              <CardSubtitle>
                Match each Excel column to a FieldTrack field. Columns left as "Ignore" are not imported. Auto-matched
                columns are pre-filled below - review before continuing, since an incorrect mapping is never silently guessed.
              </CardSubtitle>
            </div>
          </CardHeader>

          <div className="rounded-xl border border-surface-container-highest overflow-hidden mb-space-6">
            <table className="w-full text-left font-body-md text-on-surface">
              <thead className="bg-surface-container-low text-on-surface-variant font-label-md text-xs uppercase tracking-wider border-b border-surface-container-highest">
                <tr>
                  <th className="px-space-6 py-space-3 font-bold text-primary">Excel Column</th>
                  <th className="px-space-6 py-space-3 font-bold text-primary">Sample Value</th>
                  <th className="px-space-6 py-space-3 font-bold text-primary">Maps To</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-container-highest">
                {preview.columns.map((col, idx) => {
                  const targetKey = mapping[col] || '';
                  const targetConfig = targetKey ? preview.target_fields[targetKey] : undefined;
                  const sample = preview.sample_rows[0]?.[idx] ?? '';
                  return (
                    <tr key={col}>
                      <td className="px-space-6 py-space-3 text-sm font-semibold">{col}</td>
                      <td className="px-space-6 py-space-3 text-xs text-on-surface-variant font-mono truncate max-w-[200px]">{sample || '—'}</td>
                      <td className="px-space-6 py-space-3">
                        <select
                          value={targetKey}
                          onChange={(e) => setMapping((m) => ({ ...m, [col]: e.target.value }))}
                          className="w-full h-9 bg-surface border border-outline-variant rounded-lg px-space-3 text-on-surface font-body-md text-sm focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all cursor-pointer"
                        >
                          <option value="">— Ignore this column —</option>
                          {Object.entries(preview.target_fields).map(([key, cfg]) => (
                            <option key={key} value={key}>
                              {cfg.label}{cfg.required ? ' (required)' : ''}
                            </option>
                          ))}
                        </select>
                        {targetConfig?.required && (
                          <span className="inline-flex items-center gap-1 mt-1 text-[11px] font-bold text-secondary uppercase tracking-wider">
                            Required
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-space-4 mb-space-6">
            <Select
              label="Outlet Matching Strategy"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as OutletMatchStrategy)}
              helperText={
                strategy === 'outlet_code'
                  ? 'Outlets are matched by outlet_code (stable identifier). Recommended - never matches purely by display name.'
                  : 'Outlets are matched by name + territory. Only use this when the source has no stable outlet code - ambiguous matches are flagged, never guessed.'
              }
            >
              <option value="outlet_code">Match by Outlet Code (recommended)</option>
              <option value="name_and_territory">Match by Name + Territory</option>
            </Select>

            <div className="flex flex-col gap-space-1.5">
              <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold">
                Missing Invoice Numbers
              </label>
              <label className="flex items-start gap-space-2 p-space-3 border border-outline-variant rounded-lg cursor-pointer bg-surface">
                <input
                  type="checkbox"
                  checked={allowGenerated}
                  onChange={(e) => setAllowGenerated(e.target.checked)}
                  className="mt-0.5 accent-primary"
                />
                <span className="text-sm text-on-surface-variant leading-snug">
                  Generate a deterministic invoice number when the source has none, built from outlet code + date + amount
                  (stable across re-imports). Leave unchecked to flag such rows as errors instead.
                </span>
              </label>
            </div>
          </div>

          <div className="flex justify-between">
            <Button variant="ghost" icon={ArrowLeft} onClick={() => setStep(2)}>Back</Button>
            <Button variant="primary" icon={ArrowRight} iconPosition="right" isLoading={isLoading} onClick={() => void handleValidate()}>
              Validate &amp; Preview
            </Button>
          </div>
        </Card>
      )}

      {/* Step 4: Validate & Preview */}
      {step === 4 && batch && summary && (
        <div className="space-y-space-6">
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Step 4 · Validate &amp; Preview</CardTitle>
                <CardSubtitle>Rows detected: {batch.rows_processed.toLocaleString('en-IN')}</CardSubtitle>
              </div>
              <StatusBadge status={batch.status} />
            </CardHeader>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-space-4">
              <MetricCard title="Will Create" value={summary.customers_created + summary.territories_created + summary.invoices_created + summary.payments_created} icon={Building2} color="primary" subtitle={`Customers ${summary.customers_created} · Territories ${summary.territories_created} · Invoices ${summary.invoices_created} · Payments ${summary.payments_created}`} />
              <MetricCard title="Will Update" value={summary.customers_updated + summary.invoices_updated} icon={Receipt} color="secondary" subtitle={`Customers ${summary.customers_updated} · Invoices ${summary.invoices_updated}`} />
              <MetricCard title="Rows Skipped" value={batch.rows_skipped} icon={Wallet} color="slate" subtitle={`Duplicate invoices skipped: ${summary.invoices_skipped_duplicate}`} />
              <MetricCard title="Rows With Errors" value={batch.rows_error} icon={XCircle} color={batch.rows_error > 0 ? 'rose' : 'slate'} subtitle={`Warnings on ${summary.rows_with_warnings} row(s)`} />
            </div>
          </Card>

          <div className="flex justify-between">
            <Button variant="ghost" icon={ArrowLeft} onClick={() => setStep(3)}>Back to Mapping</Button>
            <Button variant="primary" icon={ArrowRight} iconPosition="right" onClick={() => setStep(5)}>
              Review Warnings &amp; Errors
            </Button>
          </div>
        </div>
      )}

      {/* Step 5: Review warnings/errors */}
      {step === 5 && batch && summary && (
        <div className="space-y-space-6">
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Step 5 · Review Warnings &amp; Errors</CardTitle>
                <CardSubtitle>Rows with errors are skipped entirely and never partially imported. Warnings do not block import.</CardSubtitle>
              </div>
              {(batch.error_report?.length ?? 0) > 0 && (
                <Button variant="outline" size="sm" icon={Download} onClick={() => void handleDownloadErrors()}>
                  Download Error Report
                </Button>
              )}
            </CardHeader>

            {(batch.error_report?.length ?? 0) === 0 && (summary.warnings?.length ?? 0) === 0 ? (
              <EmptyState
                title="No errors or warnings"
                subtitle="Every row in this file resolved cleanly."
                icon={CheckCircle2}
              />
            ) : (
              <div className="space-y-space-5">
                {(batch.error_report?.length ?? 0) > 0 && (
                  <div>
                    <p className="font-label-md text-xs uppercase tracking-wider text-error font-bold mb-space-2">
                      Errors ({batch.error_report?.length}) - these rows will NOT be imported
                    </p>
                    <div className="rounded-xl border border-error/40 overflow-hidden max-h-72 overflow-y-auto">
                      <table className="w-full text-left text-sm">
                        <thead className="bg-error-container/40 text-on-error-container font-label-md text-xs uppercase sticky top-0">
                          <tr>
                            <th className="px-space-4 py-space-2">Row</th>
                            <th className="px-space-4 py-space-2">Error</th>
                            <th className="px-space-4 py-space-2">Suggested Fix</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-error/20">
                          {batch.error_report?.map((e, idx) => (
                            <tr key={idx}>
                              <td className="px-space-4 py-space-2 font-mono">{e.row}</td>
                              <td className="px-space-4 py-space-2">{e.error}</td>
                              <td className="px-space-4 py-space-2 text-on-surface-variant">{e.suggested_fix}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {(summary.warnings?.length ?? 0) > 0 && (
                  <div>
                    <p className="font-label-md text-xs uppercase tracking-wider text-secondary font-bold mb-space-2">
                      Warnings ({summary.warnings.length}) - these rows still import
                    </p>
                    <div className="rounded-xl border border-outline-variant overflow-hidden max-h-72 overflow-y-auto">
                      <table className="w-full text-left text-sm">
                        <thead className="bg-secondary-fixed/40 text-on-secondary-fixed font-label-md text-xs uppercase sticky top-0">
                          <tr>
                            <th className="px-space-4 py-space-2">Row</th>
                            <th className="px-space-4 py-space-2">Warning</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-outline-variant">
                          {summary.warnings.map((w, idx) => (
                            <tr key={idx}>
                              <td className="px-space-4 py-space-2 font-mono">{w.row}</td>
                              <td className="px-space-4 py-space-2">{w.warning}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {summary.duplicate_outlet_codes_with_inconsistent_names.length > 0 && (
                  <div className="p-space-4 bg-secondary-fixed/30 border border-secondary-fixed-dim rounded-xl">
                    <p className="flex items-center gap-2 font-label-md text-xs uppercase tracking-wider text-on-secondary-fixed font-bold mb-space-2">
                      <AlertTriangle className="w-4 h-4" /> Same outlet code, inconsistent names in source file
                    </p>
                    <ul className="text-sm space-y-1">
                      {summary.duplicate_outlet_codes_with_inconsistent_names.map((d) => (
                        <li key={d.outlet_code}>
                          <span className="font-mono">{d.outlet_code}</span>: {d.names_seen.join(' / ')}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </Card>

          <div className="flex justify-between">
            <Button variant="ghost" icon={ArrowLeft} onClick={() => setStep(3)}>Back to Mapping</Button>
            <Button variant="primary" icon={ArrowRight} iconPosition="right" onClick={() => setStep(6)}>
              Continue to Confirm
            </Button>
          </div>
        </div>
      )}

      {/* Step 6: Confirm Import */}
      {step === 6 && batch && summary && (
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Step 6 · Confirm Import</CardTitle>
              <CardSubtitle>This is the only step that writes to the database. It runs as a single transaction - if anything fails, nothing is committed.</CardSubtitle>
            </div>
          </CardHeader>

          <div className="p-space-5 bg-surface-container-low rounded-xl border border-outline-variant font-body-md text-sm leading-relaxed space-y-1 mb-space-6">
            <p>Rows detected: <strong>{batch.rows_processed.toLocaleString('en-IN')}</strong></p>
            <p>Will create: Customers <strong>{summary.customers_created}</strong> · Territories <strong>{summary.territories_created}</strong> · Invoices <strong>{summary.invoices_created}</strong> · Payments <strong>{summary.payments_created}</strong></p>
            <p>Will update: Customers <strong>{summary.customers_updated}</strong> · Invoices <strong>{summary.invoices_updated}</strong></p>
            <p>Skipped duplicate invoices (within file): <strong>{summary.invoices_skipped_duplicate}</strong></p>
            <p>Rows skipped (no actionable data): <strong>{batch.rows_skipped}</strong></p>
            <p className={batch.rows_error > 0 ? 'text-error font-semibold' : ''}>Rows with errors (will be excluded): <strong>{batch.rows_error}</strong></p>
          </div>

          <div className="flex justify-between">
            <Button variant="ghost" icon={ArrowLeft} onClick={() => setStep(5)}>Back</Button>
            <Button variant="primary" icon={CheckCircle2} isLoading={isLoading} onClick={() => void handleCommit()}>
              Confirm Import
            </Button>
          </div>
        </Card>
      )}

      {/* Step 7: Import Result */}
      {step === 7 && batch && (
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Step 7 · Import Result</CardTitle>
              <CardSubtitle>{batch.filename}</CardSubtitle>
            </div>
            <StatusBadge status={batch.status} />
          </CardHeader>

          {batch.status === 'FAILED' ? (
            <ErrorBanner message={batch.failure_reason || 'Import failed and was fully rolled back. No data was written.'} />
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-space-4 mb-space-6">
              <MetricCard title="Created" value={batch.rows_created} icon={Building2} color="primary" />
              <MetricCard title="Updated" value={batch.rows_updated} icon={Receipt} color="secondary" />
              <MetricCard title="Skipped" value={batch.rows_skipped} icon={Wallet} color="slate" />
              <MetricCard title="Errors" value={batch.rows_error} icon={XCircle} color={batch.rows_error > 0 ? 'rose' : 'slate'} />
            </div>
          )}

          <div className="flex flex-wrap gap-space-3">
            {(batch.error_report?.length ?? 0) > 0 && (
              <Button variant="outline" icon={Download} onClick={() => void handleDownloadErrors()}>
                Download Error Report
              </Button>
            )}
            <Button variant="outline" icon={History} onClick={() => navigate('/imports')}>
              View Import History
            </Button>
            <Button variant="primary" icon={RotateCcw} onClick={resetAll}>
              Start New Import
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
};

const SamplePreviewTable: React.FC<{ preview: ImportPreviewResponse }> = ({ preview }) => (
  <div className="rounded-xl border border-surface-container-highest overflow-hidden overflow-x-auto">
    <table className="w-full text-left text-xs">
      <thead className="bg-surface-container-low text-on-surface-variant font-label-md uppercase">
        <tr>
          {preview.columns.map((c) => (
            <th key={c} className="px-space-4 py-space-2 whitespace-nowrap font-bold text-primary">
              <FileSpreadsheet className="w-3 h-3 inline mr-1" />{c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-surface-container-highest">
        {preview.sample_rows.slice(0, 5).map((row, idx) => (
          <tr key={idx}>
            {row.map((cell, cIdx) => (
              <td key={cIdx} className="px-space-4 py-space-2 whitespace-nowrap text-on-surface-variant">{cell || '—'}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
    {preview.truncated && (
      <p className="px-space-4 py-space-2 text-[11px] text-on-surface-variant bg-surface-container-low border-t border-surface-container-highest">
        Showing first {preview.sample_rows.length} of {preview.total_data_rows.toLocaleString('en-IN')} rows.
      </p>
    )}
  </div>
);
