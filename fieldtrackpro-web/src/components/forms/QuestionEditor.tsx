import React, { useState } from 'react';
import { GripVertical, Plus, X, Copy, Trash2, ChevronUp, ChevronDown } from 'lucide-react';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import { Button } from '../ui/Button';
import { FormQuestion, QuestionOption, QuestionType } from '../../types';

const QUESTION_TYPE_LABELS: Record<QuestionType, string> = {
  SHORT_TEXT: 'Short Text',
  LONG_TEXT: 'Long Text',
  MULTIPLE_CHOICE: 'Multiple Choice',
  CHECKBOXES: 'Checkboxes',
  DROPDOWN: 'Dropdown',
  YES_NO: 'Yes / No',
  NUMBER: 'Number',
  DATE: 'Date',
  TIME: 'Time',
  DATE_TIME: 'Date & Time',
  FILE_UPLOAD: 'File Upload',
  PHOTO_UPLOAD: 'Photo Upload',
  EMAIL: 'Email',
  PHONE: 'Phone',
  URL: 'URL',
  RATING: 'Rating',
};

const NEEDS_OPTIONS: QuestionType[] = ['MULTIPLE_CHOICE', 'CHECKBOXES', 'DROPDOWN'];

export interface QuestionEditorProps {
  question: FormQuestion;
  onUpdateQuestion: (patch: Partial<Pick<FormQuestion, 'question_text' | 'help_text' | 'question_type' | 'required' | 'placeholder'>>) => void;
  onDeleteQuestion: () => void;
  onDuplicateQuestion: () => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  onAddOption: (label: string) => void;
  onUpdateOption: (optionId: string, label: string) => void;
  onDeleteOption: (optionId: string) => void;
}

export const QuestionEditor: React.FC<QuestionEditorProps> = ({
  question,
  onUpdateQuestion,
  onDeleteQuestion,
  onDuplicateQuestion,
  onMoveUp,
  onMoveDown,
  onAddOption,
  onUpdateOption,
  onDeleteOption,
}) => {
  const [text, setText] = useState(question.question_text);
  const [newOptionLabel, setNewOptionLabel] = useState('');

  return (
    <div className="p-space-4 bg-surface border border-outline-variant rounded-xl space-y-space-3">
      <div className="flex items-start gap-space-2">
        <GripVertical className="w-4 h-4 text-outline mt-space-3 shrink-0" />
        <div className="flex-1 space-y-space-3">
          <Input
            id={`question-text-${question.id}`}
            label="Question"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onBlur={() => text.trim() && text !== question.question_text && onUpdateQuestion({ question_text: text })}
            placeholder="Enter your question"
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-space-3">
            <Select
              id={`question-type-${question.id}`}
              label="Question Type"
              value={question.question_type}
              onChange={(e) => onUpdateQuestion({ question_type: e.target.value as QuestionType })}
            >
              {Object.entries(QUESTION_TYPE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </Select>

            <div className="flex items-end pb-space-2.5">
              <label className="flex items-center gap-space-2 cursor-pointer select-none">
                <button
                  type="button"
                  role="switch"
                  aria-checked={question.required}
                  onClick={() => onUpdateQuestion({ required: !question.required })}
                  className={`relative w-11 h-6 rounded-full transition-colors shrink-0 ${question.required ? 'bg-primary' : 'bg-surface-container-high'}`}
                >
                  <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${question.required ? 'translate-x-5' : ''}`} />
                </button>
                <span className="font-label-md text-xs text-on-surface uppercase tracking-wider font-semibold">Required</span>
              </label>
            </div>
          </div>

          {NEEDS_OPTIONS.includes(question.question_type) && (
            <div className="space-y-space-2">
              <span className="font-label-md text-xs text-on-surface-variant uppercase tracking-wider font-semibold block">Options</span>
              {question.options.map((opt) => (
                <OptionRow key={opt.id} option={opt} onUpdate={(label) => onUpdateOption(opt.id, label)} onDelete={() => onDeleteOption(opt.id)} />
              ))}
              <div className="flex gap-space-2">
                <Input
                  value={newOptionLabel}
                  onChange={(e) => setNewOptionLabel(e.target.value)}
                  placeholder="New option"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && newOptionLabel.trim()) {
                      e.preventDefault();
                      onAddOption(newOptionLabel.trim());
                      setNewOptionLabel('');
                    }
                  }}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="md"
                  icon={Plus}
                  onClick={() => {
                    if (newOptionLabel.trim()) {
                      onAddOption(newOptionLabel.trim());
                      setNewOptionLabel('');
                    }
                  }}
                >
                  Add Option
                </Button>
              </div>
            </div>
          )}

          {question.question_type === 'RATING' && (
            <p className="font-caption text-xs text-on-surface-variant">Employees rate from 1 to 5 stars.</p>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between pt-space-3 border-t border-surface-container-highest">
        <div className="flex items-center gap-space-1">
          {onMoveUp && (
            <button type="button" onClick={onMoveUp} className="p-1.5 text-on-surface-variant hover:text-on-surface hover:bg-surface-container rounded transition-colors" aria-label="Move question up">
              <ChevronUp className="w-4 h-4" />
            </button>
          )}
          {onMoveDown && (
            <button type="button" onClick={onMoveDown} className="p-1.5 text-on-surface-variant hover:text-on-surface hover:bg-surface-container rounded transition-colors" aria-label="Move question down">
              <ChevronDown className="w-4 h-4" />
            </button>
          )}
        </div>
        <div className="flex items-center gap-space-2">
          <Button type="button" variant="ghost" size="sm" icon={Copy} onClick={onDuplicateQuestion}>
            Duplicate
          </Button>
          <Button type="button" variant="danger" size="sm" icon={Trash2} onClick={onDeleteQuestion}>
            Delete
          </Button>
        </div>
      </div>
    </div>
  );
};

const OptionRow: React.FC<{ option: QuestionOption; onUpdate: (label: string) => void; onDelete: () => void }> = ({ option, onUpdate, onDelete }) => {
  const [label, setLabel] = useState(option.label);
  return (
    <div className="flex items-center gap-space-2">
      <span className="w-4 h-4 rounded-full border-2 border-outline-variant shrink-0" />
      <input
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        onBlur={() => label.trim() && label !== option.label && onUpdate(label.trim())}
        className="flex-1 h-9 bg-surface border border-outline-variant rounded-lg px-space-3 text-on-surface font-body-md text-sm focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all"
      />
      <button type="button" onClick={onDelete} className="p-1.5 text-on-surface-variant hover:text-error rounded transition-colors shrink-0" aria-label={`Remove option ${option.label}`}>
        <X className="w-4 h-4" />
      </button>
    </div>
  );
};
