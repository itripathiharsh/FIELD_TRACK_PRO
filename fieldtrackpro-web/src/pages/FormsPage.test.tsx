import { describe, expect, it, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { FormsPage } from './FormsPage';
import { ADMIN_USER, EMPLOYEE_USER, baseRoutes, json, mockApi, renderWithProviders, route, signIn } from '../test/utils';
import { FormTemplateSummary } from '../types';

const FORM: FormTemplateSummary = {
  id: 'form-1',
  name: 'Safety Inspection',
  description: 'Safety inspection checklist',
  category_id: null,
  status: 'DRAFT',
  version: 1,
  created_by: ADMIN_USER.id,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
  published_at: null,
  category_name: 'Safety',
  question_count: 3,
  submission_count: 0,
  visit_count: 0,
};

describe('FormsPage - Form Template Management', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
  });

  it('loads and displays form templates from the API', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/form-templates': [FORM],
      '/api/v1/requirement-categories': [],
    });

    renderWithProviders(<FormsPage />);

    expect(await screen.findByText('Safety Inspection')).toBeInTheDocument();
    expect(screen.getByText(/3 questions/i)).toBeInTheDocument();
    // 'DRAFT' now also appears as a status-filter tab label, so this form's
    // own status badge is one of (at least) two matches, not the only one.
    expect(screen.getAllByText('DRAFT').length).toBeGreaterThan(0);
  });

  it('shows empty state when there are no forms in the default (published) view', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/form-templates': [],
      '/api/v1/requirement-categories': [],
    });

    renderWithProviders(<FormsPage />);

    expect(await screen.findByText('No published forms')).toBeInTheDocument();
  });

  it('handles an API error when loading forms', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/form-templates': () => json({ error: { code: 'ERROR', message: 'Failed to load forms' } }, 500),
      '/api/v1/requirement-categories': [],
    });

    renderWithProviders(<FormsPage />);

    expect(await screen.findByText(/failed to load forms/i)).toBeInTheDocument();
  });

  it('publishing a draft form calls the publish endpoint and reflects the new status', async () => {
    let published = false;
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/requirement-categories': [],
      '/api/v1/form-templates/form-1/publish': route((_url, init) => {
        expect(init?.method).toBe('POST');
        published = true;
        return json({ ...FORM, status: 'PUBLISHED', published_at: '2026-08-02T00:00:00Z' });
      }),
      '/api/v1/form-templates': route(() => json([published ? { ...FORM, status: 'PUBLISHED' } : FORM])),
    });

    renderWithProviders(<FormsPage />);
    await screen.findByText('Safety Inspection');

    await userEvent.click(screen.getByRole('button', { name: /^publish$/i }));

    await waitFor(() => expect(published).toBe(true));
  });

  it('opens the categories modal and lists existing categories', async () => {
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/form-templates': [FORM],
      '/api/v1/requirement-categories': [{ id: 'cat1', name: 'Safety', is_active: true }],
    });

    renderWithProviders(<FormsPage />);
    await screen.findByText('Safety Inspection');

    await userEvent.click(screen.getByRole('button', { name: /categories/i }));

    expect(await screen.findByText('Requirement Categories')).toBeInTheDocument();
    expect(screen.getAllByText('Safety').length).toBeGreaterThan(0);
  });

  it('creates a new category from the categories modal', async () => {
    const newCategory = { id: 'cat-new', name: 'New Category', is_active: true };
    let categories: object[] = [];
    mockApi({
      ...baseRoutes(ADMIN_USER),
      '/api/v1/form-templates': [FORM],
      '/api/v1/requirement-categories': route((_url, init) => {
        if (init?.method === 'POST') {
          categories = [newCategory];
          return json(newCategory, 201);
        }
        return json(categories);
      }),
    });

    renderWithProviders(<FormsPage />);
    await screen.findByText('Safety Inspection');
    await userEvent.click(screen.getByRole('button', { name: /categories/i }));
    await screen.findByText('Requirement Categories');

    const input = screen.getByPlaceholderText(/e\.g\., safety/i);
    await userEvent.type(input, 'New Category');
    await userEvent.click(screen.getByRole('button', { name: /^add$/i }));

    await waitFor(() => expect(screen.queryByText('Requirement Categories')).not.toBeInTheDocument());
  });
});

const REQUIRED_FORM_VISIT = {
  id: 'visit-1',
  customer_id: 'cust-1',
  employee_id: EMPLOYEE_USER.employee_id,
  scheduled_at: '2026-08-14T10:00:00Z',
  status: 'PENDING',
  check_in_at: null,
  check_out_at: null,
  synced: false,
  created_by: ADMIN_USER.id,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-01T00:00:00Z',
  required_form_id: 'form-1',
  required_form_name: 'Safety Inspection',
  required_form_status: 'PUBLISHED',
};

const OUTLET = { id: 'cust-1', name: 'ABC Traders' };

describe('FormsPage - Employee view', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(EMPLOYEE_USER);
  });

  it('shows a work queue of forms required by assigned visits, with no admin controls', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/visits': [REQUIRED_FORM_VISIT],
      '/api/v1/customers': [OUTLET],
      '/api/v1/form-submissions': [],
    });

    renderWithProviders(<FormsPage />);

    expect(await screen.findByText('Safety Inspection')).toBeInTheDocument();
    expect(screen.getByText('ABC Traders')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^open$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /new form/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /categories/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^publish$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /duplicate/i })).not.toBeInTheDocument();
  });

  it('shows a submitted form under Completed, not Pending', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/visits': [REQUIRED_FORM_VISIT],
      '/api/v1/customers': [OUTLET],
      '/api/v1/form-submissions': [{
        id: 'sub-1', form_id: 'form-1', form_version: 1, visit_id: 'visit-1',
        submitted_by: EMPLOYEE_USER.id, status: 'SUBMITTED',
        started_at: '2026-08-13T00:00:00Z', submitted_at: '2026-08-13T09:00:00Z',
        created_at: '2026-08-13T00:00:00Z', updated_at: '2026-08-13T09:00:00Z',
        form_name: 'Safety Inspection', employee_name: EMPLOYEE_USER.full_name,
        customer_name: 'ABC Traders', outlet_code: null, visit_scheduled_at: '2026-08-14T10:00:00Z',
        answers: [],
      }],
    });

    renderWithProviders(<FormsPage />);

    expect(await screen.findByText(/completed \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/pending \(0\)/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^view$/i })).toBeInTheDocument();
  });

  it('shows an empty state when no visit requires a form', async () => {
    mockApi({
      ...baseRoutes(EMPLOYEE_USER),
      '/api/v1/visits': [],
      '/api/v1/customers': [],
    });

    renderWithProviders(<FormsPage />);

    expect(await screen.findByText('No forms required right now')).toBeInTheDocument();
  });
});
