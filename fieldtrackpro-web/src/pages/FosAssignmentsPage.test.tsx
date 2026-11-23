import { describe, expect, it, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { FosAssignmentsPage } from './FosAssignmentsPage';
import type { FosGroup, FosSummary, OutletFos } from '../types';
import { ADMIN_USER, EMPLOYEE, baseRoutes, json, mockApi, renderWithProviders, route, signIn } from '../test/utils';

const SUMMARY = (over: Partial<FosSummary> = {}): FosSummary => ({
  total_outlets: 1537, outlets_with_fos: 448, outlets_without_fos: 1089,
  by_status: { ASSIGNED: 448 }, groups: { UNMAPPED: 2, MAPPED: 5 }, sync_enabled: false, legacy_policy: 'REPORT_ONLY',
  last_run_at: null, last_run_trigger: null, last_synced_at: '2026-11-23T10:00:00Z', ...over,
});
const OUTLET = (over: Partial<OutletFos>): OutletFos => ({
  id: 'o1', name: 'Katiyar Watch & Radio', outlet_code: 'UPDD1', tally_group: 'Raunak ZBR',
  fos: [{ employee_id: 'e1', name: 'Raunak', source: 'TALLY' }], fos_status: 'ASSIGNED', fos_synced_at: '2026-11-23T10:00:00Z', ...over,
});
const GROUP = (over: Partial<FosGroup>): FosGroup => ({
  id: 'g1', group_name: 'Raunak Usha', status: 'UNMAPPED', employee_id: null, employee_name: null,
  suggested_employee_id: EMPLOYEE.id, suggested_employee_name: 'Test Field Rep', suggestion_basis: "first name 'raunak' matches exactly",
  outlets: 82, assigned_outlets: 0, decided_at: null, note: null, ...over,
});

function routes(extra: Record<string, unknown> = {}) {
  return {
    ...baseRoutes(ADMIN_USER),
    '/api/v1/employees': [EMPLOYEE],
    '/api/v1/fos-assignments/summary': SUMMARY(),
    '/api/v1/fos-assignments/outlets': { items: [OUTLET({}), OUTLET({ id: 'o2', name: 'Sharma Mobiles', tally_group: 'Sundry Debtors', fos: [], fos_status: 'UNASSIGNED' })], total: 2 },
    '/api/v1/fos-assignments/groups': [GROUP({}), GROUP({ id: 'g2', group_name: 'Sundry Debtors ZBR', suggested_employee_id: null, suggested_employee_name: null, suggestion_basis: null, outlets: 22 })],
    ...extra,
  };
}

describe('FosAssignmentsPage', () => {
  beforeEach(() => localStorage.clear());

  it('shows each outlet with its synchronised FOS, group, status and last-synced time, read-only', async () => {
    signIn(ADMIN_USER);
    mockApi(routes());
    renderWithProviders(<FosAssignmentsPage />);
    expect(await screen.findByText('Katiyar Watch & Radio')).toBeInTheDocument();
    const row = screen.getByText('Katiyar Watch & Radio').closest('tr') as HTMLElement;
    expect(within(row).getByText('Raunak')).toBeInTheDocument();
    expect(within(row).getByText('Raunak ZBR')).toBeInTheDocument();
    expect(within(row).getByText('Assigned')).toBeInTheDocument();
    const row2 = screen.getByText('Sharma Mobiles').closest('tr') as HTMLElement;
    expect(within(row2).getByText('Unassigned')).toBeInTheDocument();
    expect(within(row2).getByText('No FOS in Tally')).toBeInTheDocument();
    expect(screen.getByText('1089')).toBeInTheDocument();
    // The Outlets tab has filters but no control that edits an outlet's FOS.
    expect(screen.queryByRole('button', { name: /assign|change fos|edit/i })).toBeNull();
    // Synchronisation off: the page says so instead of implying Tally changes will show up.
    expect(screen.getByRole('note')).toHaveTextContent(/not switched on/i);
  });

  it('filters by assignment, FOS and status through the API', async () => {
    signIn(ADMIN_USER);
    const urls: string[] = [];
    mockApi(routes({
      '/api/v1/fos-assignments/outlets': route((url) => { urls.push(url); return json({ items: [], total: 0 }); }),
    }));
    renderWithProviders(<FosAssignmentsPage />);
    await waitFor(() => expect(urls.length).toBeGreaterThan(0));
    await userEvent.selectOptions(screen.getByLabelText('Assignment'), 'unassigned');
    await waitFor(() => expect(urls.some((u) => u.includes('assignment=unassigned'))).toBe(true));
    await userEvent.selectOptions(screen.getByLabelText('FOS'), EMPLOYEE.id);
    await waitFor(() => expect(urls.some((u) => u.includes(`employee_id=${EMPLOYEE.id}`))).toBe(true));
    await userEvent.selectOptions(screen.getByLabelText('Status'), 'UNMAPPED_GROUP');
    await waitFor(() => expect(urls.some((u) => u.includes('status=UNMAPPED_GROUP'))).toBe(true));
  });

  it('maps a Tally group to an employee (suggestion pre-selected) and can mark a group as not a FOS group', async () => {
    signIn(ADMIN_USER);
    const puts: { url: string; body: unknown }[] = [];
    mockApi(routes({
      '/api/v1/fos-assignments/groups/g1': route((url, init) => { puts.push({ url, body: JSON.parse(String(init?.body)) }); return json(GROUP({ status: 'MAPPED', employee_id: EMPLOYEE.id })); }),
      '/api/v1/fos-assignments/groups/g2': route((url, init) => { puts.push({ url, body: JSON.parse(String(init?.body)) }); return json(GROUP({ id: 'g2', status: 'NOT_FOS' })); }),
    }));
    renderWithProviders(<FosAssignmentsPage />);
    await userEvent.click(await screen.findByRole('tab', { name: /Tally groups/ }));
    const row1 = (await screen.findByText('Raunak Usha')).closest('tr') as HTMLElement;
    expect(within(row1).getByText(/Suggested: Test Field Rep/)).toBeInTheDocument();
    const select = within(row1).getByLabelText('Employee for Raunak Usha') as HTMLSelectElement;
    expect(select.value).toBe(EMPLOYEE.id);                       // pre-selected, not applied
    expect(puts).toHaveLength(0);
    await userEvent.click(within(row1).getByRole('button', { name: 'Map' }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0].body).toEqual({ employee_id: EMPLOYEE.id });

    const row2 = screen.getByText('Sundry Debtors ZBR').closest('tr') as HTMLElement;
    expect(within(row2).getByRole('button', { name: 'Map' })).toBeDisabled();   // nothing chosen, nothing suggested
    await userEvent.click(within(row2).getByRole('button', { name: 'Not a FOS group' }));
    await waitFor(() => expect(puts).toHaveLength(2));
    expect(puts[1].body).toEqual({ not_fos: true });
  });

  it('runs the read-only reconciliation check and disables "Synchronise now" while sync is off', async () => {
    signIn(ADMIN_USER);
    mockApi(routes({
      '/api/v1/fos-assignments/reconciliation': {
        generated_at: '2026-11-23T10:00:00Z', sync_enabled: false, legacy_policy: 'REPORT_ONLY', outlets_evaluated: 1537,
        outlet_status: {}, counts: { matching: 448, new_from_tally: 5, conflicting: 0, missing_employee_mapping: 486 },
        unmatched_salesperson_groups: ['Sunil Kumar', 'Tejinder pal Singh'], proposed_mappings: [],
      },
    }));
    renderWithProviders(<FosAssignmentsPage />);
    await userEvent.click(await screen.findByRole('tab', { name: 'Reconciliation' }));
    expect(screen.getByRole('button', { name: /Synchronise now/ })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: /Check against Tally/ }));
    expect(await screen.findByText(/Nothing was changed/)).toBeInTheDocument();
    const matching = screen.getByText(/Matching: FieldTrack and Tally agree/).closest('tr') as HTMLElement;
    expect(within(matching).getByText('448')).toBeInTheDocument();
    expect(screen.getByText('Sunil Kumar')).toBeInTheDocument();
    expect(screen.getByText('Tejinder pal Singh')).toBeInTheDocument();
  });

  it('lists the change log with previous and new FOS', async () => {
    signIn(ADMIN_USER);
    mockApi(routes({
      '/api/v1/fos-assignments/audit': [{
        id: 'a1', run_id: 'r1', customer_id: 'o1', customer_name: 'Katiyar Watch & Radio', previous_fos: 'Sahil', new_fos: 'Raunak',
        action: 'CHANGED', source: 'TALLY', tally_group: 'Raunak ZBR', tally_ledger_guid: 'g-1', result: 'APPLIED', detail: null,
        created_at: '2026-11-23T10:00:00Z',
      }],
    }));
    renderWithProviders(<FosAssignmentsPage />);
    await userEvent.click(await screen.findByRole('tab', { name: 'Change log' }));
    expect(await screen.findByText('Sahil')).toBeInTheDocument();
    expect(screen.getByText('CHANGED')).toBeInTheDocument();
  });
});
