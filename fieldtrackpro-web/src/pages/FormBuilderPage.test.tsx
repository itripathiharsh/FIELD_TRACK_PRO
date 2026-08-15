import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import userEvent from '@testing-library/user-event';

import { FormBuilderPage } from './FormBuilderPage';
import { AuthProvider } from '../context/AuthContext';
import { ADMIN_USER, baseRoutes, json, mockApi, route, signIn } from '../test/utils';
import { FormTemplate } from '../types';

function renderBuilder(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/forms/new" element={<FormBuilderPage />} />
          <Route path="/forms/:id/edit" element={<FormBuilderPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

const DRAFT_FORM: FormTemplate = {
  id: 'form-1',
  name: 'Safety Inspection',
  description: 'Checklist',
  category_id: null,
  status: 'DRAFT',
  version: 1,
  created_by: ADMIN_USER.id,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
  published_at: null,
  archived_at: null,
  category_name: null,
  question_count: 1,
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

describe('FormBuilderPage', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
  });

  it('creating a new form (no id) posts name/description/category and navigates to the builder', async () => {
    let capturedMethod: string | undefined;
    let capturedBody: { name?: string } = {};
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/requirement-categories': [],
      '/api/v1/form-templates': route((_url, init) => {
        capturedMethod = init?.method;
        capturedBody = JSON.parse(String(init?.body));
        return json({ ...DRAFT_FORM, id: 'new-form', name: 'Vehicle Check', sections: [] });
      }),
      '/api/v1/form-templates/new-form': DRAFT_FORM,
    });

    renderBuilder('/forms/new');

    await userEvent.type(await screen.findByLabelText(/form name/i), 'Vehicle Check');
    await userEvent.click(screen.getByRole('button', { name: /continue to builder/i }));

    // Navigates to /forms/new-form/edit, which renders the builder for the newly created form.
    await screen.findByDisplayValue('Vehicle Information');
    expect(capturedMethod).toBe('POST');
    expect(capturedBody.name).toBe('Vehicle Check');
  });

  it('loads an existing draft form and renders its sections and questions', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/form-templates/form-1': DRAFT_FORM,
    });

    renderBuilder('/forms/form-1/edit');

    expect(await screen.findByDisplayValue('Vehicle Information')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Vehicle ID')).toBeInTheDocument();
    expect(screen.getByText('DRAFT')).toBeInTheDocument();
  });

  it('a published form hides structural edit controls', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/form-templates/form-1': { ...DRAFT_FORM, status: 'PUBLISHED', published_at: '2026-08-02T00:00:00Z' },
    });

    renderBuilder('/forms/form-1/edit');

    await screen.findByDisplayValue('Vehicle Information');
    expect(screen.queryByRole('button', { name: /add section/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /unpublish to edit/i })).toBeInTheDocument();
  });

  it('publishing calls the publish endpoint', async () => {
    let published = false;
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/form-templates/form-1/publish': route((_url, init) => {
        expect(init?.method).toBe('POST');
        published = true;
        return json({ ...DRAFT_FORM, status: 'PUBLISHED', published_at: '2026-08-02T00:00:00Z' });
      }),
      '/api/v1/form-templates/form-1': route(() => json(published ? { ...DRAFT_FORM, status: 'PUBLISHED' } : DRAFT_FORM)),
    });

    renderBuilder('/forms/form-1/edit');
    await screen.findByDisplayValue('Vehicle Information');

    await userEvent.click(screen.getByRole('button', { name: /^publish$/i }));

    await waitFor(() => expect(published).toBe(true));
  });

  it('surfaces a load error rather than rendering a blank builder', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/form-templates/form-1': () => json({ error: { code: 'FORM_NOT_FOUND', message: 'Form template not found' } }, 404),
    });

    renderBuilder('/forms/form-1/edit');

    expect(await screen.findByText(/form template not found/i)).toBeInTheDocument();
  });
});
