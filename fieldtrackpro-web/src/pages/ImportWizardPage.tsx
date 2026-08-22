import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  UploadCloud,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  Building2,
  Receipt,
  Download,
  RotateCcw,
  History,
  Sparkles,
  Users,
  ShieldCheck,
  Check,
  ArrowRight,
  ArrowLeft,
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { MetricCard } from '../components/ui/MetricCard';
import { apiClient } from '../api/client';
import {
  ImportBatchRead,
  ImportPreviewResponse,
  Employee,
} from '../types';

type WizardScreen = 'UPLOAD' | 'ANALYZING' | 'FOUND_DATA' | 'READY_TO_IMPORT' | 'SUCCESS';

const buildSuggestedMapping = (p: ImportPreviewResponse): Record<string, string> => {
  const m: Record<string, string> = {};
  for (const col of p.columns) {
    const suggested = p.suggested_mapping[col];
    if (suggested) m[col] = suggested;
  }
  return m;
};

export const ImportWizardPage: React.FC = () => {
  const navigate = useNavigate();

  const [screen, setScreen] = useState<WizardScreen>('UPLOAD');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [batch, setBatch] = useState<ImportBatchRead | null>(null);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [fosOverrides, setFosOverrides] = useState<Record<string, string>>({});
  const [showFixDrawer, setShowFixDrawer] = useState(false);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analyzingStatus, setAnalyzingStatus] = useState('Reading Excel structure...');

  useEffect(() => {
    apiClient.getEmployees()
      .then((data) => setEmployees(data || []))
      .catch(() => setEmployees([]));
  }, []);

  const resetAll = () => {
    setScreen('UPLOAD');
    setFile(null);
    setPreview(null);
    setBatch(null);
    setMapping({});
    setFosOverrides({});
    setShowFixDrawer(false);
    setError(null);
    setAnalyzingStatus('');
  };

  const handleFileSelect = async (f: File) => {
    setError(null);
    setIsLoading(true);
    setFile(f);
    setScreen('ANALYZING');
    setAnalyzingStatus('Reading spreadsheet...');

    try {
      // 1. Preview and auto-detect headers/columns
      const p = await apiClient.previewImportFile(f);
      setPreview(p);
      const suggested = buildSuggestedMapping(p);
      setMapping(suggested);

      setAnalyzingStatus('Matching customer accounts and sales reps...');

      // 2. Validate in the background
      const mappedColumns = Object.fromEntries(Object.entries(suggested).filter(([, v]) => v));
      const b = await apiClient.validateImportFile(f, {
        sheet_name: p.sheet_name,
        column_mapping: mappedColumns,
        outlet_match_strategy: 'outlet_code',
        allow_generated_invoice_numbers: false,
        fos_mapping_overrides: {},
      });
      setBatch(b);

      // 3. Move directly to "We found your data"
      setScreen('FOUND_DATA');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to read and analyze spreadsheet');
      setScreen('UPLOAD');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRevalidate = async () => {
    if (!file || !preview) return;
    setError(null);
    setIsLoading(true);
    try {
      const mappedColumns = Object.fromEntries(Object.entries(mapping).filter(([, v]) => v));
      const b = await apiClient.validateImportFile(file, {
        sheet_name: preview.sheet_name,
        column_mapping: mappedColumns,
        outlet_match_strategy: 'outlet_code',
        allow_generated_invoice_numbers: false,
        fos_mapping_overrides: fosOverrides,
      });
      setBatch(b);
      setShowFixDrawer(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to apply adjustments');
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
      setScreen('SUCCESS');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownloadCredentials = async () => {
    if (!batch) return;
    try {
      const url = await apiClient.getImportCredentialsExcelObjectUrl(batch.id);
      const a = document.createElement('a');
      a.href = url;
      a.download = `employee_credentials_${batch.id}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to download credentials');
    }
  };

  const summary = batch?.summary || {};
  const planRows: any[] = summary?.plan_rows || [];
  const detectedType = summary?.detected_type || preview?.detected_type || 'generic';
  const isEmployeeType = detectedType === 'employee_master';
  const unmatchedFosList: string[] = summary?.unmatched_fos_names || [];

  const totalReadyRecords = (batch?.rows_created || 0) + (batch?.rows_updated || 0);
  const totalOutletsFound = batch?.rows_processed || planRows.length;
  const hasIssues = (batch?.rows_error || 0) > 0 || unmatchedFosList.length > 0;

  return (
    <div className="space-y-space-6 max-w-4xl mx-auto pb-space-12">
      <PageHeader
        title="Excel / MIS Import"
        subtitle="Import your SGRG Excel/MIS file to automatically sync customer outlets, balances, and staff."
        actions={
          <Button variant="outline" icon={History} onClick={() => navigate('/imports')}>
            Import History
          </Button>
        }
      />

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {/* SCREEN 1: UPLOAD */}
      {screen === 'UPLOAD' && (
        <Card className="border-outline-variant/70 shadow-sm">
          <CardHeader>
            <div>
              <CardTitle className="text-xl">Upload SGRG Excel / MIS File</CardTitle>
              <CardSubtitle className="text-sm mt-1">
                Upload your SGRG Excel/MIS file. We'll automatically read and prepare the data.
              </CardSubtitle>
            </div>
          </CardHeader>

          <label
            htmlFor="import-file-input"
            className="flex flex-col items-center justify-center gap-space-4 p-space-12 my-space-2 border-2 border-dashed border-primary/30 rounded-2xl bg-surface-container-low/40 hover:border-primary hover:bg-surface-container-low transition-all cursor-pointer text-center group"
          >
            <div className="p-space-5 bg-surface rounded-2xl border border-outline-variant/80 text-primary shadow-sm group-hover:scale-105 transition-transform">
              <UploadCloud className="w-12 h-12 stroke-[1.5]" />
            </div>
            <div>
              <p className="font-headline-sm text-base text-primary font-bold">
                Click to choose an Excel file, or drag and drop it here
              </p>
              <p className="font-caption text-xs text-on-surface-variant mt-1.5">
                Works with VU, Usha, Zebronics OS reports, Combined BI, and Employee rosters (.xlsx, .xls)
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs font-label-md text-on-surface-variant bg-surface-container px-3.5 py-1.5 rounded-full border border-outline-variant/40">
              <Sparkles className="w-4 h-4 text-primary" />
              <span>Automatic data reading &amp; smart detection</span>
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
        </Card>
      )}

      {/* SCREEN: ANALYZING (Progress) */}
      {screen === 'ANALYZING' && (
        <Card className="py-space-16 text-center border-outline-variant/70 shadow-sm">
          <div className="flex flex-col items-center justify-center gap-space-5">
            <div className="relative">
              <div className="w-14 h-14 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
              <FileSpreadsheet className="w-6 h-6 text-primary absolute inset-0 m-auto" />
            </div>
            <div>
              <h3 className="font-headline-sm text-lg text-on-surface font-bold">Analyzing Spreadsheet</h3>
              <p className="font-caption text-sm text-on-surface-variant mt-1.5 max-w-sm mx-auto">
                {analyzingStatus}
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* SCREEN 2: WE FOUND YOUR DATA */}
      {screen === 'FOUND_DATA' && batch && (
        <div className="space-y-space-6">
          <Card className="border-primary/30 bg-primary-container/10">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-3.5">
                <div className="p-3 bg-primary text-on-primary rounded-2xl shadow-xs">
                  <CheckCircle2 className="w-7 h-7" />
                </div>
                <div>
                  <h3 className="font-headline-sm text-lg text-on-surface font-bold">We found your data</h3>
                  <p className="text-xs text-on-surface-variant mt-0.5">
                    File: <strong>{file?.name}</strong>
                  </p>
                </div>
              </div>
              <span className="self-start sm:self-auto px-3 py-1 rounded-full text-xs font-bold bg-primary-container text-on-primary-container border border-primary-container">
                Ready for Review
              </span>
            </div>
          </Card>

          {/* Business-Level Information Metric Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-space-4">
            <MetricCard
              title={isEmployeeType ? 'Employees Found' : 'Outlets Found'}
              value={totalOutletsFound}
              icon={isEmployeeType ? Users : Building2}
              color="primary"
              subtitle="Detected in your file"
            />
            <MetricCard
              title="Records Ready"
              value={totalReadyRecords}
              icon={CheckCircle2}
              color="secondary"
              subtitle="Ready to import safely"
            />
            <MetricCard
              title="Issues"
              value={batch.rows_error}
              icon={batch.rows_error > 0 ? AlertTriangle : ShieldCheck}
              color={batch.rows_error > 0 ? 'rose' : 'slate'}
              subtitle={batch.rows_error > 0 ? 'Will be skipped' : '0 issues detected'}
            />
          </div>

          {/* Detected Data Checklist */}
          <Card className="border-outline-variant/70">
            <h4 className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant font-bold mb-space-3">
              Information Detected
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-space-3">
              <div className="flex items-center gap-2.5 p-3 rounded-xl bg-surface-container-low border border-outline-variant/50">
                <div className="w-5 h-5 rounded-full bg-primary/10 text-primary flex items-center justify-center shrink-0">
                  <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                </div>
                <span className="text-xs font-medium text-on-surface">Customer &amp; Outlet Data</span>
              </div>
              <div className="flex items-center gap-2.5 p-3 rounded-xl bg-surface-container-low border border-outline-variant/50">
                <div className="w-5 h-5 rounded-full bg-primary/10 text-primary flex items-center justify-center shrink-0">
                  <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                </div>
                <span className="text-xs font-medium text-on-surface">Sales Rep (FOS) Assignments</span>
              </div>
              <div className="flex items-center gap-2.5 p-3 rounded-xl bg-surface-container-low border border-outline-variant/50">
                <div className="w-5 h-5 rounded-full bg-primary/10 text-primary flex items-center justify-center shrink-0">
                  <Check className="w-3.5 h-3.5 stroke-[2.5]" />
                </div>
                <span className="text-xs font-medium text-on-surface">Outstanding &amp; Ageing Data</span>
              </div>
            </div>
          </Card>

          {/* Unresolved fields banner (only if issues found) */}
          {hasIssues && (
            <div className="p-space-4 bg-secondary-fixed/30 border border-secondary-fixed-dim rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <AlertTriangle className="w-5 h-5 text-secondary shrink-0" />
                <span className="text-sm font-semibold text-on-secondary-fixed">
                  Some information couldn't be automatically assigned.
                </span>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowFixDrawer(!showFixDrawer)}
              >
                {showFixDrawer ? 'Hide Details' : `Fix ${unmatchedFosList.length || batch.rows_error} fields`}
              </Button>
            </div>
          )}

          {/* Simple Fix Drawer (shown only when clicked) */}
          {showFixDrawer && unmatchedFosList.length > 0 && (
            <Card className="border-secondary/40 bg-surface">
              <CardHeader>
                <div>
                  <CardTitle className="text-sm">Assign Sales Representatives</CardTitle>
                  <CardSubtitle className="text-xs">
                    Choose which employee represents each name found in the file:
                  </CardSubtitle>
                </div>
              </CardHeader>
              <div className="space-y-3 mt-space-2">
                {unmatchedFosList.map((rawFos) => (
                  <div key={rawFos} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 bg-surface-container-low rounded-xl border border-outline-variant/60">
                    <span className="text-sm font-semibold text-on-surface font-mono">
                      "{rawFos}"
                    </span>
                    <div className="flex items-center gap-2">
                      <select
                        value={fosOverrides[rawFos] || ''}
                        onChange={(e) => {
                          const val = e.target.value;
                          setFosOverrides((prev) => ({ ...prev, [rawFos]: val }));
                        }}
                        className="h-8 text-xs bg-surface border border-outline-variant rounded-lg px-2 text-on-surface"
                      >
                        <option value="">— Skip direct assignment —</option>
                        {employees.map((emp) => (
                          <option key={emp.id} value={emp.id}>
                            {emp.full_name} ({emp.employee_code || 'No Code'})
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                ))}
                <div className="flex justify-end pt-2">
                  <Button size="sm" variant="primary" onClick={() => void handleRevalidate()} isLoading={isLoading}>
                    Apply &amp; Update
                  </Button>
                </div>
              </div>
            </Card>
          )}

          {/* Preview of Parsed Records */}
          <Card className="border-outline-variant/70">
            <CardHeader>
              <div>
                <CardTitle className="text-base">Sample Parsed Outlets</CardTitle>
                <CardSubtitle className="text-xs">Preview of records detected in your file.</CardSubtitle>
              </div>
            </CardHeader>
            <div className="rounded-xl border border-surface-container-highest overflow-hidden overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-surface-container-low text-on-surface-variant font-label-md uppercase border-b border-surface-container-highest">
                  <tr>
                    {isEmployeeType ? (
                      <>
                        <th className="px-space-4 py-space-2.5 font-bold text-primary">Emp Code</th>
                        <th className="px-space-4 py-space-2.5 font-bold text-primary">Full Name</th>
                        <th className="px-space-4 py-space-2.5 font-bold text-primary">Role</th>
                        <th className="px-space-4 py-space-2.5 font-bold text-primary">CUG</th>
                      </>
                    ) : (
                      <>
                        <th className="px-space-4 py-space-2.5 font-bold text-primary">DMS Code</th>
                        <th className="px-space-4 py-space-2.5 font-bold text-primary">Outlet Name</th>
                        <th className="px-space-4 py-space-2.5 font-bold text-primary">Zone / Area</th>
                        <th className="px-space-4 py-space-2.5 font-bold text-primary">Sales Rep</th>
                        <th className="px-space-4 py-space-2.5 font-bold text-primary">Market OS</th>
                        <th className="px-space-4 py-space-2.5 font-bold text-primary">&gt;90d Overdue</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-highest">
                  {planRows.slice(0, 5).map((row, idx) => (
                    <tr key={idx} className="hover:bg-surface-container-low/40">
                      {isEmployeeType ? (
                        <>
                          <td className="px-space-4 py-space-2.5 font-mono font-bold text-primary">{row.employee_code || '—'}</td>
                          <td className="px-space-4 py-space-2.5 font-semibold text-on-surface">{row.full_name || '—'}</td>
                          <td className="px-space-4 py-space-2.5 text-on-surface-variant">{row.working_profile || 'FOS'}</td>
                          <td className="px-space-4 py-space-2.5 font-mono text-on-surface-variant">{row.cug || '—'}</td>
                        </>
                      ) : (
                        <>
                          <td className="px-space-4 py-space-2.5 font-mono font-bold text-primary">{row.dms_code || '—'}</td>
                          <td className="px-space-4 py-space-2.5 font-semibold text-on-surface">{row.outlet_name || '—'}</td>
                          <td className="px-space-4 py-space-2.5 text-on-surface-variant">{row.zone_name} · {row.area_name}</td>
                          <td className="px-space-4 py-space-2.5 text-on-surface-variant">{row.raw_fos_name || 'Office / Unassigned'}</td>
                          <td className="px-space-4 py-space-2.5 font-mono font-semibold text-on-surface">
                            {row.market_outstanding ? `₹${parseFloat(row.market_outstanding).toLocaleString('en-IN')}` : '₹0'}
                          </td>
                          <td className="px-space-4 py-space-2.5 font-mono text-secondary">
                            {row.bucket_gt_90 && parseFloat(row.bucket_gt_90) > 0 ? `₹${parseFloat(row.bucket_gt_90).toLocaleString('en-IN')}` : '—'}
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Primary Action Button */}
          <div className="flex items-center justify-between pt-space-2">
            <Button variant="ghost" icon={ArrowLeft} onClick={resetAll}>
              Upload Different File
            </Button>
            <Button
              variant="primary"
              size="lg"
              icon={ArrowRight}
              iconPosition="right"
              onClick={() => setScreen('READY_TO_IMPORT')}
            >
              Review Data ({totalReadyRecords} Records)
            </Button>
          </div>
        </div>
      )}

      {/* SCREEN 3: READY TO IMPORT */}
      {screen === 'READY_TO_IMPORT' && batch && (
        <Card className="border-outline-variant/70 shadow-sm">
          <CardHeader>
            <div>
              <CardTitle className="text-xl">Ready to Import</CardTitle>
              <CardSubtitle className="text-sm mt-1">
                <strong>{totalReadyRecords} records</strong> will be added or updated in FieldTrack Pro.
              </CardSubtitle>
            </div>
          </CardHeader>

          <div className="p-space-6 bg-surface-container-low rounded-2xl border border-outline-variant space-y-3 my-space-4">
            <div className="flex items-center justify-between text-sm">
              <span className="text-on-surface-variant">New Customer Outlets to Create:</span>
              <strong className="text-primary font-bold">{batch.rows_created}</strong>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-on-surface-variant">Existing Outlets &amp; Balances to Update:</span>
              <strong className="text-secondary font-bold">{batch.rows_updated}</strong>
            </div>
            {batch.rows_error > 0 && (
              <div className="flex items-center justify-between text-sm text-error">
                <span>Excluded Rows (Errors):</span>
                <strong>{batch.rows_error}</strong>
              </div>
            )}
            <div className="pt-2 border-t border-surface-container-highest text-xs text-on-surface-variant flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-primary" />
              <span>Safe transactional import — updates all records in one complete step.</span>
            </div>
          </div>

          <div className="flex items-center justify-between pt-space-4">
            <Button variant="ghost" icon={ArrowLeft} onClick={() => setScreen('FOUND_DATA')}>
              Back
            </Button>
            <Button
              variant="primary"
              size="lg"
              icon={CheckCircle2}
              isLoading={isLoading}
              onClick={() => void handleCommit()}
              className="shadow-sm"
            >
              Import {totalReadyRecords} Records
            </Button>
          </div>
        </Card>
      )}

      {/* SCREEN 4: SUCCESS */}
      {screen === 'SUCCESS' && batch && (
        <Card className="border-outline-variant/70 shadow-sm">
          <CardHeader>
            <div>
              <CardTitle className="text-xl">Import Complete</CardTitle>
              <CardSubtitle className="text-sm mt-1">{batch.filename}</CardSubtitle>
            </div>
          </CardHeader>

          {batch.status === 'FAILED' ? (
            <ErrorBanner message={batch.failure_reason || 'Import could not be completed.'} />
          ) : (
            <div className="space-y-space-6 my-space-2">
              <div className="p-space-6 bg-primary-container/10 border border-primary-container/30 rounded-2xl flex items-center gap-4">
                <div className="p-3 bg-primary-container text-on-primary-container rounded-2xl shadow-xs">
                  <CheckCircle2 className="w-8 h-8" />
                </div>
                <div>
                  <h3 className="font-headline-sm text-lg text-on-surface font-bold">Successfully Synchronized!</h3>
                  <p className="text-xs text-on-surface-variant mt-1">
                    All {totalReadyRecords} records from <strong>{batch.filename}</strong> are now live in the system.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-space-4">
                <MetricCard title="New Outlets" value={batch.rows_created} icon={Building2} color="primary" subtitle="Created in system" />
                <MetricCard title="Updated Outlets" value={batch.rows_updated} icon={Receipt} color="secondary" subtitle="Balances refreshed" />
                <MetricCard title="Total Synced" value={totalReadyRecords} icon={CheckCircle2} color="slate" subtitle="Live in database" />
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-space-3 mt-space-6 pt-space-4 border-t border-surface-container-highest">
            {isEmployeeType && (
              <Button variant="primary" icon={Download} onClick={() => void handleDownloadCredentials()}>
                Download Onboarding Credentials (.xlsx)
              </Button>
            )}
            <Button variant="outline" icon={Building2} onClick={() => navigate('/customers')}>
              View Customers Directory
            </Button>
            <Button variant="outline" icon={Receipt} onClick={() => navigate('/reports')}>
              View Financial &amp; BI Reports
            </Button>
            <Button variant="ghost" icon={RotateCcw} onClick={resetAll} className="ml-auto">
              Import Another File
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
};
