import React, { useEffect, useState } from 'react';
import { Upload, X, FileText, Star } from 'lucide-react';
import { Input } from '../ui/Input';
import { Textarea } from '../ui/Textarea';
import { Select } from '../ui/Select';
import { Button } from '../ui/Button';
import { FormQuestion } from '../../types';
import { apiClient } from '../../api/client';

export interface QuestionRendererProps {
  question: FormQuestion;
  /** Backend stores every answer as opaque text. CHECKBOXES encodes its multi-select as a JSON array string. */
  value: string | null;
  onChange: (value: string | null) => void;
  /** Preview mode: renders the real controls but nothing is interactive or persisted. */
  disabled?: boolean;
  error?: string;
  /** Required for FILE_UPLOAD/PHOTO_UPLOAD - reuses the existing visit-media upload endpoint. */
  onUploadFile?: (file: File) => Promise<string>;
}

function parseCheckboxValues(value: string | null): string[] {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/**
 * Renders the correct input control for every backend QuestionType, sharing
 * one abstraction between the admin preview, the employee fill flow, and
 * (in disabled mode) anywhere a question needs to display without editing.
 */
export const QuestionRenderer: React.FC<QuestionRendererProps> = ({
  question,
  value,
  onChange,
  disabled = false,
  error,
  onUploadFile,
}) => {
  const label = (
    <label className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold mb-space-1.5">
      {question.question_text}
      {question.required && <span className="text-error ml-1">*</span>}
    </label>
  );
  const helpText = question.help_text && (
    <p className="font-caption text-xs text-on-surface-variant mb-space-1.5 leading-relaxed">{question.help_text}</p>
  );

  switch (question.question_type) {
    case 'SHORT_TEXT':
    case 'EMAIL':
    case 'PHONE':
    case 'URL':
      return (
        <div>
          {label}
          {helpText}
          <Input
            type={question.question_type === 'EMAIL' ? 'email' : question.question_type === 'URL' ? 'url' : question.question_type === 'PHONE' ? 'tel' : 'text'}
            value={value ?? ''}
            onChange={(e) => onChange(e.target.value || null)}
            placeholder={question.placeholder ?? undefined}
            disabled={disabled}
            error={error}
          />
        </div>
      );

    case 'LONG_TEXT':
      return (
        <div>
          {label}
          {helpText}
          <Textarea
            value={value ?? ''}
            onChange={(e) => onChange(e.target.value || null)}
            placeholder={question.placeholder ?? undefined}
            disabled={disabled}
            error={error}
          />
        </div>
      );

    case 'NUMBER':
      return (
        <div>
          {label}
          {helpText}
          <Input
            type="number"
            value={value ?? ''}
            onChange={(e) => onChange(e.target.value || null)}
            placeholder={question.placeholder ?? undefined}
            disabled={disabled}
            error={error}
            {...(question.validation_config?.min !== undefined ? { min: question.validation_config.min as number } : {})}
            {...(question.validation_config?.max !== undefined ? { max: question.validation_config.max as number } : {})}
          />
        </div>
      );

    case 'DATE':
      return (
        <div>
          {label}
          {helpText}
          <Input type="date" value={value ?? ''} onChange={(e) => onChange(e.target.value || null)} disabled={disabled} error={error} />
        </div>
      );

    case 'TIME':
      return (
        <div>
          {label}
          {helpText}
          <Input type="time" value={value ?? ''} onChange={(e) => onChange(e.target.value || null)} disabled={disabled} error={error} />
        </div>
      );

    case 'DATE_TIME':
      return (
        <div>
          {label}
          {helpText}
          <Input type="datetime-local" value={value ?? ''} onChange={(e) => onChange(e.target.value || null)} disabled={disabled} error={error} />
        </div>
      );

    case 'YES_NO':
      return (
        <div>
          {label}
          {helpText}
          <div className="flex gap-space-2">
            {['YES', 'NO'].map((opt) => (
              <button
                key={opt}
                type="button"
                disabled={disabled}
                onClick={() => onChange(opt)}
                className={`flex-1 h-10 rounded-lg font-label-md text-xs uppercase tracking-wider font-bold transition-all cursor-pointer disabled:cursor-not-allowed ${
                  value === opt
                    ? 'bg-primary text-on-primary shadow-xs'
                    : 'bg-surface border border-outline-variant text-on-surface-variant hover:bg-surface-container-low'
                }`}
              >
                {opt}
              </button>
            ))}
          </div>
          {error && <p className="font-caption text-xs text-error font-medium mt-1">{error}</p>}
        </div>
      );

    case 'MULTIPLE_CHOICE':
      return (
        <div>
          {label}
          {helpText}
          <div className="flex flex-col gap-space-2">
            {question.options.map((opt) => (
              <label
                key={opt.id}
                className={`flex items-center gap-space-2 p-space-2.5 rounded-lg border cursor-pointer transition-colors ${
                  value === opt.value ? 'border-primary-container bg-primary-tint/20' : 'border-outline-variant hover:bg-surface-container-low'
                } ${disabled ? 'cursor-not-allowed opacity-70' : ''}`}
              >
                <input
                  type="radio"
                  name={question.id}
                  checked={value === opt.value}
                  onChange={() => onChange(opt.value)}
                  disabled={disabled}
                  className="accent-primary w-4 h-4"
                />
                <span className="font-body-md text-sm text-on-surface">{opt.label}</span>
              </label>
            ))}
          </div>
          {error && <p className="font-caption text-xs text-error font-medium mt-1">{error}</p>}
        </div>
      );

    case 'CHECKBOXES': {
      const selected = parseCheckboxValues(value);
      const toggle = (optValue: string) => {
        const next = selected.includes(optValue) ? selected.filter((v) => v !== optValue) : [...selected, optValue];
        onChange(next.length ? JSON.stringify(next) : null);
      };
      return (
        <div>
          {label}
          {helpText}
          <div className="flex flex-col gap-space-2">
            {question.options.map((opt) => (
              <label
                key={opt.id}
                className={`flex items-center gap-space-2 p-space-2.5 rounded-lg border cursor-pointer transition-colors ${
                  selected.includes(opt.value) ? 'border-primary-container bg-primary-tint/20' : 'border-outline-variant hover:bg-surface-container-low'
                } ${disabled ? 'cursor-not-allowed opacity-70' : ''}`}
              >
                <input
                  type="checkbox"
                  checked={selected.includes(opt.value)}
                  onChange={() => toggle(opt.value)}
                  disabled={disabled}
                  className="accent-primary w-4 h-4"
                />
                <span className="font-body-md text-sm text-on-surface">{opt.label}</span>
              </label>
            ))}
          </div>
          {error && <p className="font-caption text-xs text-error font-medium mt-1">{error}</p>}
        </div>
      );
    }

    case 'DROPDOWN':
      return (
        <div>
          <Select
            id={`question-${question.id}`}
            label={question.question_text + (question.required ? ' *' : '')}
            value={value ?? ''}
            onChange={(e) => onChange(e.target.value || null)}
            disabled={disabled}
            error={error}
          >
            <option value="">-- Select --</option>
            {question.options.map((opt) => (
              <option key={opt.id} value={opt.value}>{opt.label}</option>
            ))}
          </Select>
          {helpText}
        </div>
      );

    case 'RATING': {
      const max = (question.validation_config?.max as number) || 5;
      const current = value ? parseInt(value, 10) : 0;
      return (
        <div>
          {label}
          {helpText}
          <div className="flex gap-space-1">
            {Array.from({ length: max }).map((_, i) => {
              const star = i + 1;
              return (
                <button
                  key={star}
                  type="button"
                  disabled={disabled}
                  onClick={() => onChange(String(star))}
                  aria-label={`Rate ${star} of ${max}`}
                  className="disabled:cursor-not-allowed"
                >
                  <Star className={`w-6 h-6 ${star <= current ? 'text-secondary-container fill-secondary-container' : 'text-outline-variant'}`} />
                </button>
              );
            })}
          </div>
          {error && <p className="font-caption text-xs text-error font-medium mt-1">{error}</p>}
        </div>
      );
    }

    case 'FILE_UPLOAD':
    case 'PHOTO_UPLOAD':
      return (
        <FileAnswer
          question={question}
          value={value}
          onChange={onChange}
          disabled={disabled}
          error={error}
          onUploadFile={onUploadFile}
          label={label}
          helpText={helpText}
        />
      );

    default:
      return (
        <div>
          {label}
          <p className="font-caption text-xs text-error">Unsupported question type: {question.question_type}</p>
        </div>
      );
  }
};

const FileAnswer: React.FC<{
  question: FormQuestion;
  value: string | null;
  onChange: (value: string | null) => void;
  disabled: boolean;
  error?: string;
  onUploadFile?: (file: File) => Promise<string>;
  label: React.ReactNode;
  helpText: React.ReactNode;
}> = ({ question, value, onChange, disabled, error, onUploadFile, label, helpText }) => {
  const [isUploading, setIsUploading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const isPhoto = question.question_type === 'PHOTO_UPLOAD';

  useEffect(() => {
    if (!value || !isPhoto) {
      setPreviewUrl(null);
      return;
    }
    let revoked: string | null = null;
    let cancelled = false;
    apiClient.getMediaObjectUrl(value).then((url) => {
      if (cancelled) { URL.revokeObjectURL(url); return; }
      revoked = url;
      setPreviewUrl(url);
    }).catch(() => setPreviewUrl(null));
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [value, isPhoto]);

  const handleFile = async (file: File) => {
    if (!onUploadFile) return;
    setIsUploading(true);
    try {
      const mediaId = await onUploadFile(file);
      onChange(mediaId);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDownload = async () => {
    if (!value) return;
    const url = await apiClient.getMediaObjectUrl(value);
    window.open(url, '_blank');
  };

  return (
    <div>
      {label}
      {helpText}
      {value ? (
        <div className="p-space-3 bg-surface-container-low border border-outline-variant rounded-lg flex items-center gap-space-3">
          {isPhoto && previewUrl ? (
            <img src={previewUrl} alt="Uploaded" className="w-14 h-14 rounded-lg object-cover shrink-0" />
          ) : (
            <FileText className="w-8 h-8 text-outline shrink-0" />
          )}
          <span className="font-caption text-xs text-on-surface-variant flex-1">Attachment uploaded</span>
          <Button type="button" variant="outline" size="sm" onClick={() => void handleDownload()}>
            View
          </Button>
          {!disabled && (
            <button
              type="button"
              onClick={() => onChange(null)}
              className="p-1 text-on-surface-variant hover:text-error rounded transition-colors"
              aria-label="Remove attachment"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      ) : (
        <label className={`flex items-center justify-center gap-space-2 h-20 rounded-lg border-2 border-dashed border-outline-variant text-on-surface-variant cursor-pointer hover:border-primary-container hover:bg-surface-container-low transition-all ${disabled ? 'cursor-not-allowed opacity-60' : ''}`}>
          <Upload className="w-4 h-4" />
          <span className="font-caption text-xs">{isUploading ? 'Uploading...' : `Select ${isPhoto ? 'photo' : 'file'} to upload`}</span>
          <input
            type="file"
            className="hidden"
            accept={isPhoto ? 'image/jpeg,image/png,image/webp' : 'image/jpeg,image/png,image/webp,application/pdf'}
            disabled={disabled || isUploading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleFile(file);
              e.target.value = '';
            }}
          />
        </label>
      )}
      {error && <p className="font-caption text-xs text-error font-medium mt-1">{error}</p>}
    </div>
  );
};
