import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Eye, Plus, Send, Archive, Undo2 } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardHeader } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Textarea } from '../components/ui/Textarea';
import { Select } from '../components/ui/Select';
import { StatusBadge } from '../components/ui/StatusBadge';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { QuestionEditor } from '../components/forms/QuestionEditor';
import { apiClient, RequirementCategory } from '../api/client';
import { FormTemplate } from '../types';

/** First step: name/description/category, then the template is created for real. */
const CreateFormStep: React.FC = () => {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [categories, setCategories] = useState<RequirementCategory[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient.getRequirementCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setIsSaving(true);
    setError(null);
    try {
      const template = await apiClient.createFormTemplate({
        name: name.trim(),
        description: description.trim() || null,
        category_id: categoryId || null,
      });
      navigate(`/forms/${template.id}/edit`, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create form');
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-space-6 max-w-2xl">
      <PageHeader title="New Requirement Form" subtitle="Give it a name to start building." />
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      <Card variant="default">
        <form onSubmit={handleCreate} className="space-y-space-4">
          <Input label="Form Name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Safety Inspection" />
          <Textarea
            label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Enter form description..."
            helperText="Shown to employees above the form."
          />
          <Select label="Category" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">-- None --</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </Select>
          <div className="pt-space-4 flex justify-end gap-space-3 border-t border-surface-container-highest mt-space-6">
            <Button type="button" variant="ghost" size="sm" onClick={() => navigate('/forms')}>
              Cancel
            </Button>
            <Button type="submit" variant="secondary" size="sm" isLoading={isSaving}>
              Continue to Builder
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
};

export const FormBuilderPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [form, setForm] = useState<FormTemplate | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const load = useCallback(() => {
    if (!id) return;
    setIsLoading(true);
    apiClient.getFormTemplate(id)
      .then((data) => { setForm(data); setError(null); })
      .catch((err: Error) => setError(err.message || 'Unable to load form'))
      .finally(() => setIsLoading(false));
  }, [id]);

  useEffect(() => { load(); }, [load]);

  if (!id) return <CreateFormStep />;
  if (isLoading) return <div className="py-space-12 text-center text-on-surface-variant font-caption">Loading form builder...</div>;
  if (error || !form) {
    return (
      <div className="space-y-space-4">
        <Button variant="ghost" size="sm" icon={ArrowLeft} onClick={() => navigate('/forms')}>Back to Forms</Button>
        <ErrorBanner message={error || 'Form not found'} onRetry={load} />
      </div>
    );
  }

  const isDraft = form.status === 'DRAFT';

  const runAction = async (action: () => Promise<FormTemplate>) => {
    setIsBusy(true);
    setActionError(null);
    try {
      const updated = await action();
      setForm(updated);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Action failed');
    } finally {
      setIsBusy(false);
    }
  };

  const handleAddSection = () => runAction(async () => {
    await apiClient.addFormSection(form.id, { title: `Section ${form.sections.length + 1}`, display_order: form.sections.length });
    return apiClient.getFormTemplate(form.id);
  });

  const handleUpdateSection = (sectionId: string, title: string) => runAction(async () => {
    await apiClient.updateFormSection(sectionId, { title });
    return apiClient.getFormTemplate(form.id);
  });

  const handleDeleteSection = (sectionId: string) => runAction(async () => {
    await apiClient.deleteFormSection(sectionId);
    return apiClient.getFormTemplate(form.id);
  });

  const handleAddQuestion = (sectionId: string) => runAction(async () => {
    const section = form.sections.find((s) => s.id === sectionId)!;
    await apiClient.addFormQuestion(form.id, {
      section_id: sectionId,
      question_text: 'New question',
      question_type: 'SHORT_TEXT',
      display_order: section.questions.length,
    });
    return apiClient.getFormTemplate(form.id);
  });

  return (
    <div className="space-y-space-6">
      <Button variant="ghost" size="sm" icon={ArrowLeft} onClick={() => navigate('/forms')}>Back to Forms</Button>

      <Card variant="default">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-space-4">
          <div className="flex-1 space-y-space-3 max-w-2xl">
            <Input
              label="Form Name"
              value={form.name}
              disabled={!isDraft}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              onBlur={() => isDraft && runAction(async () => { await apiClient.updateFormTemplate(form.id, { name: form.name }); return apiClient.getFormTemplate(form.id); })}
            />
            <Textarea
              label="Description"
              value={form.description ?? ''}
              disabled={!isDraft}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              onBlur={() => isDraft && runAction(async () => { await apiClient.updateFormTemplate(form.id, { description: form.description }); return apiClient.getFormTemplate(form.id); })}
              placeholder="Enter form description..."
            />
          </div>
          <div className="flex flex-col items-start md:items-end gap-space-3 shrink-0">
            <div className="flex items-center gap-space-2">
              <span className="font-label-md text-xs text-on-surface-variant uppercase tracking-wider">Status:</span>
              <StatusBadge status={form.status} />
              <span className="font-caption text-xs text-on-surface-variant">v{form.version}</span>
            </div>
            <div className="flex flex-wrap items-center gap-space-2 justify-end">
              <Button variant="outline" size="sm" icon={Eye} onClick={() => navigate(`/forms/${form.id}/preview`)}>
                Preview
              </Button>
              {isDraft && (
                <Button variant="secondary" size="sm" icon={Send} isLoading={isBusy} onClick={() => runAction(() => apiClient.publishFormTemplate(form.id))}>
                  Publish
                </Button>
              )}
              {form.status === 'PUBLISHED' && (
                <>
                  <Button variant="outline" size="sm" icon={Undo2} isLoading={isBusy} onClick={() => runAction(() => apiClient.unpublishFormTemplate(form.id))}>
                    Unpublish to Edit
                  </Button>
                  <Button variant="danger" size="sm" icon={Archive} isLoading={isBusy} onClick={() => runAction(() => apiClient.archiveFormTemplate(form.id))}>
                    Archive
                  </Button>
                </>
              )}
              <Button variant="ghost" size="sm" onClick={() => navigate(`/forms/${form.id}/submissions`)}>
                Submissions
              </Button>
            </div>
          </div>
        </div>
      </Card>

      {actionError && <ErrorBanner message={actionError} onDismiss={() => setActionError(null)} />}
      {!isDraft && (
        <p className="font-caption text-xs text-on-surface-variant bg-surface-container-low border border-outline-variant rounded-lg p-space-3">
          This form is {form.status.toLowerCase()}. Structure is read-only{form.status === 'PUBLISHED' ? ' — unpublish it to make changes.' : '.'}
        </p>
      )}

      <div className="space-y-space-4">
        {form.sections.map((section) => (
          <Card key={section.id} variant="default">
            <CardHeader>
              <div className="flex-1">
                <Input
                  id={`section-title-${section.id}`}
                  value={section.title}
                  disabled={!isDraft}
                  onChange={(e) => setForm({ ...form, sections: form.sections.map((s) => s.id === section.id ? { ...s, title: e.target.value } : s) })}
                  onBlur={(e) => isDraft && e.target.value.trim() && handleUpdateSection(section.id, e.target.value.trim())}
                  className="font-headline-sm text-headline-sm text-primary font-bold border-transparent hover:border-outline-variant"
                />
              </div>
              {isDraft && (
                <Button variant="ghost" size="sm" onClick={() => handleDeleteSection(section.id)}>
                  Delete Section
                </Button>
              )}
            </CardHeader>

            <div className="space-y-space-3">
              {section.questions.map((question) => (
                <QuestionEditor
                  key={question.id}
                  question={question}
                  onUpdateQuestion={(patch) => runAction(async () => { await apiClient.updateFormQuestion(question.id, patch); return apiClient.getFormTemplate(form.id); })}
                  onDeleteQuestion={() => runAction(async () => { await apiClient.deleteFormQuestion(question.id); return apiClient.getFormTemplate(form.id); })}
                  onDuplicateQuestion={() => runAction(async () => { await apiClient.duplicateFormQuestion(question.id); return apiClient.getFormTemplate(form.id); })}
                  onAddOption={(labelText) => runAction(async () => { await apiClient.addQuestionOption(question.id, { label: labelText, value: labelText }); return apiClient.getFormTemplate(form.id); })}
                  onUpdateOption={(optionId, labelText) => runAction(async () => { await apiClient.updateQuestionOption(optionId, { label: labelText }); return apiClient.getFormTemplate(form.id); })}
                  onDeleteOption={(optionId) => runAction(async () => { await apiClient.deleteQuestionOption(optionId); return apiClient.getFormTemplate(form.id); })}
                />
              ))}
              {isDraft && (
                <Button variant="outline" size="sm" icon={Plus} onClick={() => handleAddQuestion(section.id)}>
                  Add Question
                </Button>
              )}
            </div>
          </Card>
        ))}

        {isDraft && (
          <Button variant="secondary" size="md" icon={Plus} onClick={handleAddSection} isLoading={isBusy}>
            Add Section
          </Button>
        )}
      </div>
    </div>
  );
};
