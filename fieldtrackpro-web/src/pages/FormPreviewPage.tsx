import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { StatusBadge } from '../components/ui/StatusBadge';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { QuestionRenderer } from '../components/forms/QuestionRenderer';
import { apiClient } from '../api/client';
import { FormTemplate } from '../types';

/**
 * Read-only render of exactly what an employee would see. No answers are
 * collected, no submission is created - QuestionRenderer is rendered with
 * disabled=true and onChange is a no-op.
 */
export const FormPreviewPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [form, setForm] = useState<FormTemplate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    apiClient.getFormTemplate(id)
      .then((data) => { setForm(data); setError(null); })
      .catch((err: Error) => setError(err.message || 'Unable to load form'))
      .finally(() => setIsLoading(false));
  }, [id]);

  if (isLoading) return <div className="py-space-12 text-center text-on-surface-variant font-caption">Loading preview...</div>;

  return (
    <div className="space-y-space-6 max-w-3xl">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" icon={ArrowLeft} onClick={() => navigate(id ? `/forms/${id}/edit` : '/forms')}>
          Back to Builder
        </Button>
        <span className="font-label-md text-xs uppercase tracking-wider text-on-surface-variant bg-secondary-fixed border border-secondary-fixed-dim px-space-3 py-space-1 rounded-full font-bold">
          Preview Mode — not a real submission
        </span>
      </div>

      {error && <ErrorBanner message={error} />}

      {form && (
        <Card variant="default" className="space-y-space-6">
          <div className="border-b border-surface-container-highest pb-space-4 flex items-start justify-between gap-space-4">
            <div>
              <h1 className="font-headline-lg text-headline-lg text-primary font-bold">{form.name}</h1>
              {form.description && <p className="font-body-md text-sm text-on-surface-variant mt-space-2">{form.description}</p>}
            </div>
            <StatusBadge status={form.status} />
          </div>

          {form.sections.length === 0 ? (
            <p className="font-caption text-xs text-on-surface-variant">This form has no sections yet.</p>
          ) : (
            form.sections.map((section) => (
              <div key={section.id} className="space-y-space-4">
                <div className="border-b border-surface-container-highest pb-space-2">
                  <h2 className="font-headline-sm text-headline-sm text-primary font-bold">{section.title}</h2>
                  {section.description && <p className="font-caption text-xs text-on-surface-variant mt-1">{section.description}</p>}
                </div>
                <div className="space-y-space-4">
                  {section.questions.map((question) => (
                    <QuestionRenderer key={question.id} question={question} value={null} onChange={() => {}} disabled />
                  ))}
                </div>
              </div>
            ))
          )}
        </Card>
      )}
    </div>
  );
};
