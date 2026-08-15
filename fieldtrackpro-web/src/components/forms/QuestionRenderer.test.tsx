import React, { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { QuestionRenderer } from './QuestionRenderer';
import { FormQuestion } from '../../types';

/** Mirrors how a real parent (FormFillPage) holds and updates answer state, so typing accumulates correctly. */
const ControlledQuestion: React.FC<{ question: FormQuestion; onChange: (v: string | null) => void }> = ({ question, onChange }) => {
  const [value, setValue] = useState<string | null>(null);
  return <QuestionRenderer question={question} value={value} onChange={(v) => { setValue(v); onChange(v); }} />;
};

function makeQuestion(overrides: Partial<FormQuestion>): FormQuestion {
  return {
    id: 'q-1',
    section_id: 'sec-1',
    form_id: 'form-1',
    question_text: 'Test question',
    help_text: null,
    question_type: 'SHORT_TEXT',
    required: false,
    display_order: 0,
    placeholder: null,
    validation_config: null,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    options: [],
    ...overrides,
  };
}

describe('QuestionRenderer', () => {
  it('SHORT_TEXT: typing accumulates into onChange as a real controlled input would', async () => {
    const onChange = vi.fn();
    render(<ControlledQuestion question={makeQuestion({ question_text: 'Vehicle ID' })} onChange={onChange} />);

    await userEvent.type(screen.getByRole('textbox'), 'VH-1002');

    expect(onChange).toHaveBeenLastCalledWith('VH-1002');
  });

  it('marks a required question with an asterisk', () => {
    render(<QuestionRenderer question={makeQuestion({ required: true })} value={null} onChange={vi.fn()} />);
    expect(screen.getByText('*')).toBeInTheDocument();
  });

  it('MULTIPLE_CHOICE: selecting an option calls onChange with that option\'s value', async () => {
    const onChange = vi.fn();
    const question = makeQuestion({
      question_type: 'MULTIPLE_CHOICE',
      options: [
        { id: 'o1', question_id: 'q-1', label: 'Good', value: 'good', display_order: 0 },
        { id: 'o2', question_id: 'q-1', label: 'Unsafe', value: 'unsafe', display_order: 1 },
      ],
    });
    render(<QuestionRenderer question={question} value={null} onChange={onChange} />);

    await userEvent.click(screen.getByLabelText('Unsafe'));

    expect(onChange).toHaveBeenCalledWith('unsafe');
  });

  it('CHECKBOXES: toggling two options encodes both as a JSON array string', async () => {
    const onChange = vi.fn();
    const question = makeQuestion({
      question_type: 'CHECKBOXES',
      options: [
        { id: 'o1', question_id: 'q-1', label: 'Fire extinguisher', value: 'fire_ext', display_order: 0 },
        { id: 'o2', question_id: 'q-1', label: 'First aid kit', value: 'first_aid', display_order: 1 },
      ],
    });
    const { rerender } = render(<QuestionRenderer question={question} value={null} onChange={onChange} />);

    await userEvent.click(screen.getByText('Fire extinguisher'));
    expect(onChange).toHaveBeenLastCalledWith(JSON.stringify(['fire_ext']));

    rerender(<QuestionRenderer question={question} value={JSON.stringify(['fire_ext'])} onChange={onChange} />);
    await userEvent.click(screen.getByText('First aid kit'));
    expect(onChange).toHaveBeenLastCalledWith(JSON.stringify(['fire_ext', 'first_aid']));
  });

  it('YES_NO: clicking YES calls onChange("YES")', async () => {
    const onChange = vi.fn();
    render(<QuestionRenderer question={makeQuestion({ question_type: 'YES_NO' })} value={null} onChange={onChange} />);

    await userEvent.click(screen.getByRole('button', { name: 'YES' }));

    expect(onChange).toHaveBeenCalledWith('YES');
  });

  it('DROPDOWN: renders the shared Select with all options', () => {
    const question = makeQuestion({
      question_type: 'DROPDOWN',
      options: [{ id: 'o1', question_id: 'q-1', label: 'North', value: 'north', display_order: 0 }],
    });
    render(<QuestionRenderer question={question} value={null} onChange={vi.fn()} />);

    expect(screen.getByRole('combobox')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'North' })).toBeInTheDocument();
  });

  it('disabled mode (preview) never calls onChange', async () => {
    const onChange = vi.fn();
    render(<QuestionRenderer question={makeQuestion({ question_type: 'YES_NO' })} value={null} onChange={onChange} disabled />);

    await userEvent.click(screen.getByRole('button', { name: 'YES' }));

    expect(onChange).not.toHaveBeenCalled();
  });

  it('shows a field-level error message when provided', () => {
    render(<QuestionRenderer question={makeQuestion({ required: true })} value={null} onChange={vi.fn()} error="This question is required." />);
    expect(screen.getByText('This question is required.')).toBeInTheDocument();
  });
});
