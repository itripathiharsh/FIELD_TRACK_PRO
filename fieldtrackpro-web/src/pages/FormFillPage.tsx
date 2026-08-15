import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle2 } from 'lucide-react';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { StatusBadge } from '../components/ui/StatusBadge';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { QuestionRenderer } from '../components/forms/QuestionRenderer';
import { apiClient } from '../api/client';
import { FormRender, SubmissionStatus } from '../types';

/** Only the fields this page actually needs, common to both list and detail submission responses. */
interface SubmissionRef {
  id: string;
  status: SubmissionStatus;
}

export const FormFillPage: React.FC = () => {
  const { visitId, formId } = useParams<{ visitId: string; formId: string }>();
  const navigate = useNavigate();

  const [form, setForm] = useState<FormRender | null>(null);
  const [submission, setSubmission] = useState<SubmissionRef | null>(null);
  const [answers, setAnswers] = useState<Record<string, string | null>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [justSubmitted, setJustSubmitted] = useState(false);

  // P1-12: refs backing the autosave-sequencing fix (declared before `load`
  // and the other callbacks that close over them - see their usage below
  // for why plain state variables aren't enough here).
  const latestAnswersRef = useRef(answers);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isSavingRef = useRef(false);
  const hasPendingSaveRef = useRef(false);
  const isMountedRef = useRef(true);
  // Mirrors `submission` state, but readable synchronously right after an
  // awaited save - `handleSubmit` needs the value a just-completed saveDraft()
  // produced, not whatever `submission` happened to be in the closure at the
  // time handleSubmit itself was created (a real render/closure-timing trap:
  // setSubmission() inside an awaited call does not update a plain variable
  // already captured earlier in the same function).
  const latestSubmissionRef = useRef<SubmissionRef | null>(submission);

  const load = useCallback(async () => {
    if (!visitId || !formId) return;
    setIsLoading(true);
    setError(null);
    try {
      const [rendered, submissions] = await Promise.all([
        apiClient.getFormRender(formId),
        apiClient.getFormSubmissions({ form_id: formId, visit_id: visitId }),
      ]);
      setForm(rendered);
      const existing = submissions[0] ?? null;
      if (existing) {
        const detail = await apiClient.getFormSubmission(existing.id);
        latestSubmissionRef.current = { id: detail.id, status: detail.status };
        setSubmission({ id: detail.id, status: detail.status });
        const initial: Record<string, string | null> = {};
        detail.answers.forEach((a) => { initial[a.question_id] = a.answer_value; });
        setAnswers(initial);
        latestAnswersRef.current = initial;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load form');
    } finally {
      setIsLoading(false);
    }
  }, [visitId, formId]);

  useEffect(() => { load(); }, [load]);

  const isReadOnly = submission?.status === 'SUBMITTED';

  // P1-12: autosave race fix.
  //
  // The previous implementation fired a full POST on every keystroke with
  // no sequencing at all: typing "A" -> "AB" -> "ABC" fired three
  // independent, concurrently in-flight requests, and nothing stopped an
  // older one (still carrying just "A") from landing on the server AFTER
  // the newer "ABC" request, silently reverting the saved draft.
  //
  // Fix: debounce rapid edits, and never let two save requests be in
  // flight at once - if a new edit arrives while a save is still in
  // flight, it's recorded as "pending" and triggers exactly one more save
  // (using whatever is the latest state by then) once the current request
  // settles, rather than firing a second overlapping request. This makes
  // requests strictly sequential, so the server is never asked to persist
  // an older snapshot after a newer one.
  const AUTOSAVE_DEBOUNCE_MS = 600;

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const flushSave = useCallback(async () => {
    if (!visitId || !formId) return;
    if (isSavingRef.current) {
      // A save is already in flight - don't overlap it. Its own `finally`
      // block below will notice this flag and run one more save (with
      // whatever is latest by then) once it settles.
      hasPendingSaveRef.current = true;
      return;
    }
    isSavingRef.current = true;
    if (isMountedRef.current) setIsSaving(true);
    const toSave = latestAnswersRef.current;
    try {
      const result = await apiClient.saveFormSubmission({
        form_id: formId,
        visit_id: visitId,
        answers: Object.entries(toSave).map(([question_id, answer_value]) => ({ question_id, answer_value })),
      });
      latestSubmissionRef.current = result;
      if (isMountedRef.current) setSubmission(result);
    } catch (err) {
      if (isMountedRef.current) setError(err instanceof Error ? err.message : 'Failed to save your progress');
    } finally {
      isSavingRef.current = false;
      if (isMountedRef.current) setIsSaving(false);
      if (hasPendingSaveRef.current) {
        hasPendingSaveRef.current = false;
        void flushSave();
      }
    }
  }, [visitId, formId]);

  const scheduleSave = useCallback(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      debounceTimerRef.current = null;
      void flushSave();
    }, AUTOSAVE_DEBOUNCE_MS);
  }, [flushSave]);

  // Flush immediately on unmount (navigating away) rather than losing
  // whatever edit is still sitting in the debounce window.
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
        void flushSave();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveDraft = async (nextAnswers: Record<string, string | null>): Promise<SubmissionRef | null> => {
    // Used by handleSubmit, which must not finalize the submission until
    // the *latest* answers are genuinely persisted - bypasses the debounce
    // and waits out any save already in flight (and any save it queues up
    // behind it) rather than the fire-and-forget behaviour the debounced
    // typing path uses. Returns the resulting submission directly rather
    // than relying on the `submission` state variable, which a caller's own
    // already-created closure cannot see updated until its next render.
    latestAnswersRef.current = nextAnswers;
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    await flushSave();
    while (isSavingRef.current || hasPendingSaveRef.current) {
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    return latestSubmissionRef.current;
  };

  const handleAnswerChange = (questionId: string, value: string | null) => {
    const next = { ...answers, [questionId]: value };
    setAnswers(next);
    latestAnswersRef.current = next;
    setFieldErrors((prev) => { const p = { ...prev }; delete p[questionId]; return p; });
    scheduleSave();
  };

  const handleUploadFile = async (file: File): Promise<string> => {
    if (!visitId) throw new Error('Missing visit');
    const media = await apiClient.uploadMedia(visitId, file);
    return media.id;
  };

  const validate = (): boolean => {
    if (!form) return false;
    const errors: Record<string, string> = {};
    for (const section of form.sections) {
      for (const question of section.questions) {
        if (question.required && !answers[question.id]) {
          errors[question.id] = 'This question is required.';
        }
      }
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    const savedSubmission = await saveDraft(answers);
    if (!savedSubmission) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const result = await apiClient.submitFormSubmission(savedSubmission.id);
      latestSubmissionRef.current = { id: result.id, status: result.status };
      setSubmission({ id: result.id, status: result.status });
      setJustSubmitted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submission failed. Your answers are saved as a draft.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) return <div className="py-space-12 text-center text-on-surface-variant font-caption">Loading form...</div>;

  if (justSubmitted || isReadOnly) {
    return (
      <div className="space-y-space-6 max-w-3xl">
        <Button variant="ghost" size="sm" icon={ArrowLeft} onClick={() => navigate(`/visits/${visitId}`)}>
          Back to Visit
        </Button>
        {justSubmitted && (
          <Card variant="default" className="text-center py-space-8">
            <CheckCircle2 className="w-12 h-12 text-primary mx-auto mb-space-4" />
            <h2 className="font-headline-md text-headline-md text-primary font-bold mb-space-2">Form submitted</h2>
            <p className="font-caption text-xs text-on-surface-variant">Your answers have been recorded.</p>
          </Card>
        )}
        {form && (
          <Card variant="default" className="space-y-space-6">
            <div className="flex items-start justify-between gap-space-4 border-b border-surface-container-highest pb-space-4">
              <div>
                <h1 className="font-headline-lg text-headline-lg text-primary font-bold">{form.name}</h1>
                {form.description && <p className="font-body-md text-sm text-on-surface-variant mt-space-2">{form.description}</p>}
              </div>
              {submission && <StatusBadge status={submission.status} />}
            </div>
            {form.sections.map((section) => (
              <div key={section.id} className="space-y-space-4">
                <h2 className="font-headline-sm text-headline-sm text-primary font-bold border-b border-surface-container-highest pb-space-2">{section.title}</h2>
                {section.questions.map((question) => (
                  <QuestionRenderer key={question.id} question={question} value={answers[question.id] ?? null} onChange={() => {}} disabled />
                ))}
              </div>
            ))}
          </Card>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-space-6 max-w-3xl">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" icon={ArrowLeft} onClick={() => navigate(`/visits/${visitId}`)}>
          Back to Visit
        </Button>
        {isSaving && <span className="font-caption text-xs text-on-surface-variant">Saving...</span>}
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {form && (
        <Card variant="default" className="space-y-space-6">
          <div className="border-b border-surface-container-highest pb-space-4">
            <h1 className="font-headline-lg text-headline-lg text-primary font-bold">{form.name}</h1>
            {form.description && <p className="font-body-md text-sm text-on-surface-variant mt-space-2">{form.description}</p>}
          </div>

          {form.sections.map((section) => (
            <div key={section.id} className="space-y-space-4">
              <div className="border-b border-surface-container-highest pb-space-2">
                <h2 className="font-headline-sm text-headline-sm text-primary font-bold">{section.title}</h2>
                {section.description && <p className="font-caption text-xs text-on-surface-variant mt-1">{section.description}</p>}
              </div>
              <div className="space-y-space-4">
                {section.questions.map((question) => (
                  <QuestionRenderer
                    key={question.id}
                    question={question}
                    value={answers[question.id] ?? null}
                    onChange={(value) => handleAnswerChange(question.id, value)}
                    onUploadFile={handleUploadFile}
                    error={fieldErrors[question.id]}
                  />
                ))}
              </div>
            </div>
          ))}

          <div className="pt-space-4 border-t border-surface-container-highest flex justify-end">
            <Button variant="secondary" size="lg" isLoading={isSubmitting} onClick={() => void handleSubmit()}>
              Submit Form
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
};
