import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Download, ExternalLink } from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { StatusBadge } from '../components/ui/StatusBadge';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { QuestionRenderer } from '../components/forms/QuestionRenderer';
import { apiClient } from '../api/client';
import { FormSubmissionDetail } from '../types';

/**
 * Admin review of one submission. Renders dynamically from whatever
 * sections/questions/answers the backend returns for this submission's own
 * recorded version - never assumes the current live form structure, so an
 * old submission reviewed after the form has moved on to a later version
 * still displays correctly (see backend FormTemplateVersion snapshotting).
 */
export const FormSubmissionDetailPage: React.FC = () => {
  const { id: formId, submissionId } = useParams<{ id: string; submissionId: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<FormSubmissionDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);

  const load = useCallback(() => {
    if (!submissionId) return;
    setIsLoading(true);
    apiClient.getFormSubmission(submissionId)
      .then((data) => { setDetail(data); setError(null); })
      .catch((err: Error) => setError(err.message || 'Unable to load submission'))
      .finally(() => setIsLoading(false));
  }, [submissionId]);

  useEffect(() => { load(); }, [load]);

  const handleDownloadPdf = async () => {
    if (!submissionId) return;
    setIsDownloading(true);
    try {
      const url = await apiClient.getSubmissionPdfObjectUrl(submissionId);
      window.open(url, '_blank');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate PDF');
    } finally {
      setIsDownloading(false);
    }
  };

  const answerFor = (questionId: string) => detail?.answers.find((a) => a.question_id === questionId)?.answer_value ?? null;

  if (isLoading) return <div className="py-space-12 text-center text-on-surface-variant font-caption">Loading submission...</div>;

  return (
    <div className="space-y-space-6 max-w-3xl">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" icon={ArrowLeft} onClick={() => navigate(`/forms/${formId}/submissions`)}>
          Back to Submissions
        </Button>
        <Button variant="outline" size="sm" icon={Download} isLoading={isDownloading} onClick={() => void handleDownloadPdf()}>
          Download PDF
        </Button>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} onDismiss={() => setError(null)} />}

      {detail && (
        <Card variant="default" className="space-y-space-6">
          <div className="border-b border-surface-container-highest pb-space-4 flex flex-col md:flex-row md:items-start justify-between gap-space-3">
            <div>
              <h1 className="font-headline-lg text-headline-lg text-primary font-bold">{detail.form_name}</h1>
              <StatusBadge status={detail.status} />
            </div>
            <Button variant="outline" size="sm" icon={ExternalLink} onClick={() => navigate(`/visits/${detail.visit_id}`)}>
              Open Visit
            </Button>
          </div>

          {/* Context: who filled it, for which outlet, during which visit,
              using which form version - never an orphaned answer set. */}
          <div className="grid grid-cols-2 md:grid-cols-3 gap-space-4 -mt-space-2">
            <div>
              <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold mb-space-1">Employee</p>
              <p className="font-body-md text-sm text-on-surface">{detail.employee_name || detail.submitted_by.substring(0, 8)}</p>
            </div>
            <div>
              <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold mb-space-1">Outlet</p>
              <p className="font-body-md text-sm text-on-surface">{detail.customer_name || `#${detail.visit_id.substring(0, 8)}`}</p>
              {detail.outlet_code && <p className="font-caption text-xs text-on-surface-variant font-mono">{detail.outlet_code}</p>}
            </div>
            <div>
              <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold mb-space-1">Territory</p>
              <p className="font-body-md text-sm text-on-surface">{detail.territory_name || '—'}</p>
            </div>
            <div>
              <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold mb-space-1">Visit</p>
              <p className="font-body-md text-sm text-on-surface">
                {detail.visit_scheduled_at ? new Date(detail.visit_scheduled_at).toLocaleDateString() : '—'}
              </p>
            </div>
            <div>
              <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold mb-space-1">Form Version</p>
              <p className="font-body-md text-sm text-on-surface">v{detail.form_version}</p>
            </div>
            <div>
              <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold mb-space-1">Submitted</p>
              <p className="font-body-md text-sm text-on-surface">
                {detail.submitted_at ? new Date(detail.submitted_at).toLocaleString() : 'Not yet submitted'}
              </p>
            </div>
          </div>

          {detail.sections.map((section) => (
            <div key={section.id} className="space-y-space-4">
              <h2 className="font-headline-sm text-headline-sm text-primary font-bold border-b border-surface-container-highest pb-space-2">{section.title}</h2>
              <div className="space-y-space-4">
                {section.questions.map((question) => (
                  <QuestionRenderer key={question.id} question={question} value={answerFor(question.id)} onChange={() => {}} disabled />
                ))}
              </div>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
};
