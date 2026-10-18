import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { EmployeeDetailPage } from './EmployeeDetailPage';
import { AuthProvider } from '../context/AuthContext';
import { ALLOWED_NEXT_ROLES, canOfferPasswordReset } from '../components/employees/securityRules';
import { ADMIN_USER, baseRoutes, EMPLOYEE, json, mockApi, route, signIn } from '../test/utils';
import type { User, UserRole } from '../types';

const SUPER_ADMIN_USER: User = {
  ...ADMIN_USER,
  id: '99999999-9999-9999-9999-999999999999',
  email: 'owner@fieldtrack.test',
  role: 'SUPER_ADMIN',
};

const TEMP_PASSWORD = 'Kq7m-Rv4t-Xw9z';

interface TargetOpts {
  role?: UserRole;
  userId?: string;
  isActive?: boolean;
  tempExpiresAt?: string | null;
}

function employeePayload({ role = 'EMPLOYEE', userId = EMPLOYEE.user_id, isActive = true, tempExpiresAt = null }: TargetOpts = {}) {
  return {
    id: EMPLOYEE.id,
    user_id: userId,
    full_name: 'Test Field Rep',
    territory_id: EMPLOYEE.territory_id,
    employee_code: 'EMP-001',
    created_at: '2026-01-01T00:00:00Z',
    user: {
      id: userId,
      email: 'rep@fieldtrack.test',
      mobile_number: '+919876543210',
      role,
      is_active: isActive,
      temp_password_expires_at: tempExpiresAt,
    },
  };
}

interface Spies {
  resetCalls: number;
  roleBodies: Array<Record<string, unknown>>;
  logoutCalls: number;
}

function setup(actor: User, target: TargetOpts = {}, extra: Record<string, unknown> = {}) {
  const spies: Spies = { resetCalls: 0, roleBodies: [], logoutCalls: 0 };
  let current = employeePayload(target);
  mockApi({
    ...baseRoutes(actor),
    '/api/v1/auth/logout': route(() => {
      spies.logoutCalls += 1;
      return new Response(null, { status: 204 });
    }),
    '/api/v1/security-audit-logs': [],
    '/api/v1/users': route((url, init) => {
      if (url.endsWith('/role') && init?.method === 'PATCH') {
        const body = JSON.parse(String(init.body));
        spies.roleBodies.push(body);
        current = employeePayload({ ...target, role: body.role });
        return json({ id: current.user_id, role: body.role, is_active: true });
      }
      return json(null, 404);
    }),
    '/api/v1/employees': route((url, init) => {
      if (url.endsWith('/reset-password') && init?.method === 'POST') {
        spies.resetCalls += 1;
        return json({
          employee_id: EMPLOYEE.id,
          user_id: current.user_id,
          temporary_password: TEMP_PASSWORD,
          expires_at: '2026-10-18T10:30:00Z',
          expires_in_minutes: 30,
          must_change_password: true,
        });
      }
      if (url.includes('/activity') || url.includes('/territory-assignments')) return json(null, 404);
      if (url.includes('/areas')) return json([]);
      if (url.includes(EMPLOYEE.id)) return json(current);
      return json([]);
    }),
    ...extra,
  });
  signIn(actor);
  return spies;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/employees/${EMPLOYEE.id}`]}>
      <AuthProvider>
        <Routes>
          <Route path="/employees/:id" element={<EmployeeDetailPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

async function loaded() {
  await screen.findByText('Test Field Rep');
}

describe('canOfferPasswordReset (visibility only; the backend is the authority)', () => {
  const emp = (role: UserRole, userId = 'target', active = true) => ({
    user_id: userId,
    user: { id: userId, email: null, mobile_number: null, role, is_active: active },
  });
  it('Admin: employees only', () => {
    expect(canOfferPasswordReset(ADMIN_USER, emp('EMPLOYEE'))).toBe(true);
    expect(canOfferPasswordReset(ADMIN_USER, emp('ADMIN'))).toBe(false);
    expect(canOfferPasswordReset(ADMIN_USER, emp('SUPER_ADMIN'))).toBe(false);
  });
  it('Super Admin: employees and admins, never super admins or themselves', () => {
    expect(canOfferPasswordReset(SUPER_ADMIN_USER, emp('EMPLOYEE'))).toBe(true);
    expect(canOfferPasswordReset(SUPER_ADMIN_USER, emp('ADMIN'))).toBe(true);
    expect(canOfferPasswordReset(SUPER_ADMIN_USER, emp('SUPER_ADMIN'))).toBe(false);
    expect(canOfferPasswordReset(SUPER_ADMIN_USER, emp('EMPLOYEE', SUPER_ADMIN_USER.id))).toBe(false);
  });
  it('nobody is offered a reset for a disabled account; employees and signed-out users never are', () => {
    expect(canOfferPasswordReset(ADMIN_USER, emp('EMPLOYEE', 'x', false))).toBe(false);
    expect(canOfferPasswordReset({ id: 'e', role: 'EMPLOYEE' }, emp('EMPLOYEE'))).toBe(false);
    expect(canOfferPasswordReset(null, emp('EMPLOYEE'))).toBe(false);
  });
});

describe('role transition options mirror the backend', () => {
  it('one step at a time', () => {
    expect(ALLOWED_NEXT_ROLES.EMPLOYEE).toEqual(['ADMIN']);
    expect(ALLOWED_NEXT_ROLES.ADMIN).toEqual(['EMPLOYEE', 'SUPER_ADMIN']);
    expect(ALLOWED_NEXT_ROLES.SUPER_ADMIN).toEqual(['ADMIN']);
  });
});

describe('Reset Password on the employee profile', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the action to an Admin for an employee, with the current role', async () => {
    setup(ADMIN_USER);
    renderPage();
    await loaded();
    expect(screen.getByRole('button', { name: /reset password/i })).toBeInTheDocument();
    expect(screen.getByTestId('role-badge')).toHaveTextContent('Employee');
    expect(screen.queryByRole('button', { name: /change role/i })).not.toBeInTheDocument();
  });

  it('hides the action for an Admin looking at an Admin or Super Admin', async () => {
    setup(ADMIN_USER, { role: 'ADMIN' });
    const { unmount } = renderPage();
    await loaded();
    expect(screen.queryByRole('button', { name: /reset password/i })).not.toBeInTheDocument();
    unmount();

    setup(ADMIN_USER, { role: 'SUPER_ADMIN' });
    renderPage();
    await loaded();
    expect(screen.queryByRole('button', { name: /reset password/i })).not.toBeInTheDocument();
  });

  it('hides the action on your own profile and for a disabled account', async () => {
    setup(SUPER_ADMIN_USER, { role: 'SUPER_ADMIN', userId: SUPER_ADMIN_USER.id });
    const { unmount } = renderPage();
    await loaded();
    expect(screen.queryByRole('button', { name: /reset password/i })).not.toBeInTheDocument();
    unmount();

    setup(ADMIN_USER, { isActive: false });
    renderPage();
    await loaded();
    expect(screen.queryByRole('button', { name: /reset password/i })).not.toBeInTheDocument();
  });

  it('asks for confirmation first and explains the consequences; cancelling calls nothing', async () => {
    const spies = setup(ADMIN_USER);
    const user = userEvent.setup();
    renderPage();
    await loaded();

    await user.click(screen.getByRole('button', { name: /reset password/i }));
    const dialog = await screen.findByRole('dialog', { name: /reset password\?/i });
    expect(within(dialog).getByText(/all of their existing sessions/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/choose a new password/i)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: /cancel/i }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(spies.resetCalls).toBe(0);
  });

  it('calls the real API once (even on rapid double clicks) and shows the password exactly once', async () => {
    const spies = setup(ADMIN_USER);
    const user = userEvent.setup(); // installs its own clipboard stub; spy on it afterwards
    const writeText = vi.spyOn(navigator.clipboard, 'writeText');
    renderPage();
    await loaded();

    await user.click(screen.getByRole('button', { name: /reset password/i }));
    const confirm = within(await screen.findByRole('dialog', { name: /reset password\?/i })).getByRole('button', {
      name: /^reset password$/i,
    });
    await user.dblClick(confirm);

    const secret = await screen.findByRole('dialog', { name: /temporary password/i });
    expect(spies.resetCalls).toBe(1);
    expect(within(secret).getByTestId('temp-password-value')).toHaveTextContent(TEMP_PASSWORD);
    expect(within(secret).getByText(/will not be shown again/i)).toBeInTheDocument();
    expect(within(secret).getByText(/privately/i)).toBeInTheDocument();
    expect(within(secret).getByText(/expires in 30 minutes/i)).toBeInTheDocument();

    // never in the URL or any browser storage
    expect(window.location.href).not.toContain(TEMP_PASSWORD);
    expect(JSON.stringify({ ...localStorage })).not.toContain(TEMP_PASSWORD);
    expect(JSON.stringify({ ...sessionStorage })).not.toContain(TEMP_PASSWORD);

    await user.click(within(secret).getByRole('button', { name: /copy/i }));
    expect(writeText).toHaveBeenCalledWith(TEMP_PASSWORD);
    expect(await within(secret).findByRole('button', { name: /copied/i })).toBeInTheDocument();

    // closing wipes it from the page for good
    await user.click(within(secret).getByRole('button', { name: /i have shared it/i }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain(TEMP_PASSWORD);
    expect(JSON.stringify({ ...localStorage })).not.toContain(TEMP_PASSWORD);
  });

  it('drops the password when the page is left (unmount) and there is no way to fetch it again', async () => {
    setup(ADMIN_USER);
    const user = userEvent.setup();
    const { unmount } = renderPage();
    await loaded();
    await user.click(screen.getByRole('button', { name: /reset password/i }));
    await user.click(
      within(await screen.findByRole('dialog', { name: /reset password\?/i })).getByRole('button', { name: /^reset password$/i }),
    );
    await screen.findByTestId('temp-password-value');
    unmount();
    expect(document.body.textContent).not.toContain(TEMP_PASSWORD);

    // a fresh visit to the profile shows no password, only the (non-secret) pending status
    setup(ADMIN_USER, {}, {});
    renderPage();
    await loaded();
    expect(document.body.textContent).not.toContain(TEMP_PASSWORD);
  });

  it('shows the server error and allows a retry when the reset fails', async () => {
    let calls = 0;
    setup(ADMIN_USER, {}, {
      '/api/v1/employees': route((url, init) => {
        if (url.endsWith('/reset-password') && init?.method === 'POST') {
          calls += 1;
          if (calls === 1) {
            return json({ error: { code: 'TARGET_PRIVILEGE_TOO_HIGH', message: 'Only a Super Admin can reset an Admin\'s password.' } }, 403);
          }
          return json({
            employee_id: EMPLOYEE.id, user_id: EMPLOYEE.user_id, temporary_password: TEMP_PASSWORD,
            expires_at: '2026-10-18T10:30:00Z', expires_in_minutes: 30, must_change_password: true,
          });
        }
        if (url.includes('/activity') || url.includes('/territory-assignments')) return json(null, 404);
        if (url.includes('/areas')) return json([]);
        return json(employeePayload());
      }),
    });
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.click(screen.getByRole('button', { name: /reset password/i }));
    const dialog = await screen.findByRole('dialog', { name: /reset password\?/i });
    await user.click(within(dialog).getByRole('button', { name: /^reset password$/i }));

    expect(await within(dialog).findByText(/only a super admin can reset/i)).toBeInTheDocument();
    expect(screen.queryByTestId('temp-password-value')).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: /^reset password$/i }));
    expect(await screen.findByTestId('temp-password-value')).toHaveTextContent(TEMP_PASSWORD);
  });

  it('shows the pending temporary-password status from the profile', async () => {
    const future = new Date(Date.now() + 20 * 60_000).toISOString();
    setup(ADMIN_USER, { tempExpiresAt: future });
    renderPage();
    await loaded();
    expect(await screen.findByTestId('temp-password-status')).toHaveTextContent(/temporary password issued/i);
  });
});

describe('Change Role on the employee profile (Super Admin only)', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('is invisible to Admins and to everyone who is not a Super Admin', async () => {
    setup(ADMIN_USER);
    renderPage();
    await loaded();
    expect(screen.queryByRole('button', { name: /change role/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/security activity/i)).not.toBeInTheDocument();
  });

  it('promotes an employee: re-auth password is required, payload is exact, and the profile refreshes', async () => {
    const spies = setup(SUPER_ADMIN_USER);
    const user = userEvent.setup();
    renderPage();
    await loaded();
    expect(screen.getByText(/security activity/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /change role/i }));
    const dialog = await screen.findByRole('dialog', { name: /change role/i });
    expect(within(dialog).getByText(/administrator access/i)).toBeInTheDocument();
    const submit = within(dialog).getByRole('button', { name: /^change role$/i });
    expect(submit).toBeDisabled(); // no password yet

    await user.type(within(dialog).getByLabelText(/your password/i), 'MyOwnPassword1!');
    expect(submit).toBeEnabled();
    await user.click(submit);

    await waitFor(() => expect(spies.roleBodies).toHaveLength(1));
    expect(spies.roleBodies[0]).toEqual({ role: 'ADMIN', current_password: 'MyOwnPassword1!', confirm: false });
    expect(await screen.findByRole('status')).toHaveTextContent(/role changed to admin/i);
    await waitFor(() => expect(screen.getByTestId('role-badge')).toHaveTextContent('Admin'));
    // password never lingers in the DOM/state of a closed dialog
    expect(screen.queryByLabelText(/your password/i)).not.toBeInTheDocument();
  });

  it('requires an explicit confirmation to grant Super Admin', async () => {
    const spies = setup(SUPER_ADMIN_USER, { role: 'ADMIN' });
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.click(screen.getByRole('button', { name: /change role/i }));
    const dialog = await screen.findByRole('dialog', { name: /change role/i });

    await user.selectOptions(within(dialog).getByLabelText(/new role/i), 'SUPER_ADMIN');
    expect(within(dialog).getByText(/power to change roles/i)).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText(/your password/i), 'MyOwnPassword1!');
    const submit = within(dialog).getByRole('button', { name: /^change role$/i });
    expect(submit).toBeDisabled(); // password typed but not confirmed
    await user.click(within(dialog).getByRole('checkbox'));
    expect(submit).toBeEnabled();
    await user.click(submit);

    await waitFor(() => expect(spies.roleBodies).toHaveLength(1));
    expect(spies.roleBodies[0]).toEqual({ role: 'SUPER_ADMIN', current_password: 'MyOwnPassword1!', confirm: true });
  });

  it('shows the server error and keeps the dialog open when the change is refused', async () => {
    setup(SUPER_ADMIN_USER, {}, {
      '/api/v1/users': route(() => json({ error: { code: 'AUTH_INVALID_PASSWORD', message: 'Incorrect password.' } }, 401)),
    });
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.click(screen.getByRole('button', { name: /change role/i }));
    const dialog = await screen.findByRole('dialog', { name: /change role/i });
    await user.type(within(dialog).getByLabelText(/your password/i), 'wrong');
    await user.click(within(dialog).getByRole('button', { name: /^change role$/i }));
    expect(await within(dialog).findByText(/incorrect password/i)).toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: /change role/i })).toBeInTheDocument();
  });

  it('signs you out after changing your own role (the server ended the session)', async () => {
    const spies = setup(SUPER_ADMIN_USER, { role: 'SUPER_ADMIN', userId: SUPER_ADMIN_USER.id });
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.click(screen.getByRole('button', { name: /change role/i }));
    const dialog = await screen.findByRole('dialog', { name: /change role/i });
    expect(within(dialog).getByText(/you will be signed out/i)).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText(/your password/i), 'MyOwnPassword1!');
    await user.click(within(dialog).getByRole('checkbox'));
    await user.click(within(dialog).getByRole('button', { name: /^change role$/i }));
    await waitFor(() => expect(spies.roleBodies).toHaveLength(1));
    await waitFor(() => expect(spies.logoutCalls).toBeGreaterThanOrEqual(1));
  });
});
