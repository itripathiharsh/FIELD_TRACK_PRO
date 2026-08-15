import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import userEvent from '@testing-library/user-event';

import { FormFillPage } from './FormFillPage';
import { AuthProvider } from '../context/AuthContext';
import { EMPLOYEE_USER, baseRoutes, json, mockApi, route, signIn } from '../test/utils';
import { FormRender, FormSubmission } from '../types';

function renderFillPage(visitId: string, formId: string) {
  return render(
    <MemoryRouter initialEntries={[`/visits/${visitId}/forms/${formId}`]}>
      <AuthProvider>
        <Routes>
          <Route path="/visits/:visitId/forms/:formId" element={<FormFillPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

const RENDER: FormRender = {
  id: 'form-1',
  name: 'Safety Inspection',
  description: 'Checklist',
  version: 1,
  status: 'PUBLISHED',
  sections: [
    {
      id: 'sec-1',
      form_id: 'form-1',
      title: 'Vehicle Information',
      description: null,
      display_order: 0,
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
      questions: [
        {
          id: 'q-1',
          section_id: 'sec-1',
          form_id: 'form-1',
          question_text: 'Vehicle ID',
          help_text: null,
          question_type: 'SHORT_TEXT',
          required: true,
          display_order: 0,
          placeholder: null,
          validation_config: null,
          created_at: '2026-08-01T00:00:00Z',
          updated_at: '2026-08-01T00:00:00Z',
          options: [],
        },
      ],
    },
  ],
};

const DRAFT_SUBMISSION: FormSubmission = {
  id: 'sub-1',
  form_id: 'form-1',
  form_version: 1,
  visit_id: 'visit-1',
  submitted_by: EMPLOYEE_USER.id,
  status: 'DRAFT',
  started_at: '2026-08-05T00:00:00Z',
  submitted_at: null,
  created_at: '2026-08-05T00:00:00Z',
  updated_at: '2026-08-05T00:00:00Z',
  form_name: 'Safety Inspection',
  employee_name: EMPLOYEE_USER.full_name,
  customer_name: null,
  outlet_code: null,
  visit_scheduled_at: null,
  answers: [],
};

describe('FormFillPage', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(EMPLOYEE_USER);
  });

  it('loads the published form and renders its questions dynamically', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/form-templates/form-1/render': RENDER,
      '/api/v1/form-submissions': [],
    });

    renderFillPage('visit-1', 'form-1');

    expect(await screen.findByText('Safety Inspection')).toBeInTheDocument();
    expect(screen.getByText('Vehicle Information')).toBeInTheDocument();
    expect(screen.getByText('Vehicle ID')).toBeInTheDocument();
  });

  it('blocks submit and shows a field error when a required question is unanswered', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/form-templates/form-1/render': RENDER,
      '/api/v1/form-submissions': [],
    });

    renderFillPage('visit-1', 'form-1');
    await screen.findByText('Safety Inspection');

    await userEvent.click(screen.getByRole('button', { name: /submit form/i }));

    expect(await screen.findByText('This question is required.')).toBeInTheDocument();
  });

  it('answering saves a draft, and submitting shows the success screen', async () => {
    let submitted = false;
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/form-templates/form-1/render': RENDER,
      '/api/v1/form-submissions/sub-1/submit': route(() => {
        submitted = true;
        return json({ ...DRAFT_SUBMISSION, status: 'SUBMITTED', submitted_at: '2026-08-05T01:00:00Z' });
      }),
      '/api/v1/form-submissions': route((_url, init) => {
        if (init?.method === 'POST') {
          return json(DRAFT_SUBMISSION);
        }
        return json([]); // no existing submission on initial load
      }),
    });

    renderFillPage('visit-1', 'form-1');
    await screen.findByText('Safety Inspection');

    await userEvent.type(screen.getByRole('textbox'), 'VH-1002');
    // The draft save is fired on every change; give it a tick to land.
    await waitFor(() => {});

    await userEvent.click(screen.getByRole('button', { name: /submit form/i }));

    await waitFor(() => expect(submitted).toBe(true));
    expect(await screen.findByText('Form submitted')).toBeInTheDocument();
  });

  // --- P1-12: autosave race/debounce fix -----------------------------------

  it('debounces rapid edits into a single save request, not one per keystroke', async () => {
    let saveCount = 0;
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/form-templates/form-1/render': RENDER,
      '/api/v1/form-submissions': route((_url, init) => {
        if (init?.method === 'POST') {
          saveCount += 1;
          return json(DRAFT_SUBMISSION);
        }
        return json([]);
      }),
    });

    renderFillPage('visit-1', 'form-1');
    await screen.findByText('Safety Inspection');

    await userEvent.type(screen.getByRole('textbox'), 'VH-1002');
    // Give the debounce window (600ms) plus a real round trip time to land -
    // deliberately generous since this uses real timers, not fake ones.
    await waitFor(() => expect(saveCount).toBeGreaterThan(0), { timeout: 2000 });

    // A single debounced save, not seven (one per character typed).
    expect(saveCount).toBe(1);
  });

  it('a slow save in flight does not lose an edit that arrives before it resolves - a follow-up save carries the latest value', async () => {
    const savedValues: string[] = [];
    // A boxed ref (rather than a bare `let`) avoids a TypeScript control-flow
    // narrowing limitation: reassigning a `let` inside a deeply-nested
    // closure (Promise executor -> route callback -> mockApi route object)
    // gets narrowed to `never` at the read site below.
    const resolveFirstSaveRef: { current: (() => void) | null } = { current: null };

    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/form-templates/form-1/render': RENDER,
      '/api/v1/form-submissions': route((_url, init) => {
        if (init?.method === 'POST') {
          const body = JSON.parse((init.body as string) ?? '{}');
          const value = body.answers?.[0]?.answer_value ?? '';
          savedValues.push(value);
          if (savedValues.length === 1) {
            // Hold the FIRST save open so a second edit can arrive while it
            // is still in flight - this is exactly the race the old
            // implementation lost: an older value landing after a newer one.
            return new Promise<Response>((resolve) => {
              resolveFirstSaveRef.current = () => resolve(json({ ...DRAFT_SUBMISSION, id: 'sub-1' }));
            });
          }
          return json({ ...DRAFT_SUBMISSION, id: 'sub-1' });
        }
        return json([]);
      }),
    });

    renderFillPage('visit-1', 'form-1');
    await screen.findByText('Safety Inspection');

    const input = screen.getByRole('textbox');
    await userEvent.type(input, 'A');
    await waitFor(() => expect(savedValues.length).toBe(1), { timeout: 2000 });

    // The first save (carrying "A") is deliberately still unresolved. Type
    // more while it's in flight.
    await userEvent.type(input, 'B');
    // Give the debounce window time to elapse - the edit must be queued as
    // "pending" (not fired as a second overlapping request) while the first
    // save is still open.
    await new Promise((r) => setTimeout(r, 700));
    expect(savedValues.length).toBe(1); // still just the one in-flight request

    // Resolve the first save - the queued edit must now fire automatically.
    resolveFirstSaveRef.current?.();
    await waitFor(() => expect(savedValues.length).toBe(2), { timeout: 2000 });
    expect(savedValues[1]).toBe('AB'); // carries the LATEST value, not a stale one
  });

  it('flushes a pending debounced save immediately on unmount, rather than losing it', async () => {
    let saveCount = 0;
    let lastSavedValue = '';
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/form-templates/form-1/render': RENDER,
      '/api/v1/form-submissions': route((_url, init) => {
        if (init?.method === 'POST') {
          saveCount += 1;
          const body = JSON.parse((init.body as string) ?? '{}');
          lastSavedValue = body.answers?.[0]?.answer_value ?? '';
          return json(DRAFT_SUBMISSION);
        }
        return json([]);
      }),
    });

    const { unmount } = renderFillPage('visit-1', 'form-1');
    await screen.findByText('Safety Inspection');

    await userEvent.type(screen.getByRole('textbox'), 'VH-1002');
    // Unmount immediately - well before the 600ms debounce would have fired
    // on its own.
    unmount();

    await waitFor(() => expect(saveCount).toBe(1), { timeout: 2000 });
    expect(lastSavedValue).toBe('VH-1002');
  });

  it('a submission already SUBMITTED renders read-only with no submit button', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/form-templates/form-1/render': RENDER,
      '/api/v1/form-submissions': [{ ...DRAFT_SUBMISSION, status: 'SUBMITTED' }],
      '/api/v1/form-submissions/sub-1': {
        id: 'sub-1', form_id: 'form-1', form_name: 'Safety Inspection', form_version: 1,
        visit_id: 'visit-1', submitted_by: EMPLOYEE_USER.id, employee_name: EMPLOYEE_USER.full_name,
        status: 'SUBMITTED', started_at: '2026-08-05T00:00:00Z', submitted_at: '2026-08-05T01:00:00Z',
        answers: [{ id: 'a1', submission_id: 'sub-1', question_id: 'q-1', answer_value: 'VH-1002', created_at: '2026-08-05T00:00:00Z', updated_at: '2026-08-05T00:00:00Z', question_text: 'Vehicle ID', question_type: 'SHORT_TEXT', options: [] }],
        sections: RENDER.sections,
      },
    });

    renderFillPage('visit-1', 'form-1');

    expect(await screen.findByDisplayValue('VH-1002')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /submit form/i })).not.toBeInTheDocument();
  });
});
