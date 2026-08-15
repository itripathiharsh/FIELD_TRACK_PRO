import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UserPlus, Phone, Mail, MailOpen, Users, Eye } from 'lucide-react';
import { DataTable, Column } from '../components/ui/DataTable';
import { Modal } from '../components/ui/Modal';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { StatusBadge } from '../components/ui/StatusBadge';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { apiClient } from '../api/client';
import { Employee, Territory, UserRole } from '../types';
import { validatePhoneNumber } from '../utils/phoneValidation';

export const EmployeesPage: React.FC = () => {
    const navigate = useNavigate();
    const [employees, setEmployees] = useState<Employee[]>([]);
    const [territories, setTerritories] = useState<Territory[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [mobile, setMobile] = useState('');
  const [employeeCode, setEmployeeCode] = useState('');
  const [territoryId, setTerritoryId] = useState('');
  // FT-038: the backend Role enum has exactly ADMIN and EMPLOYEE.
  const [role, setRole] = useState<UserRole>('EMPLOYEE');
  const [password, setPassword] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  /**
   * FT-006: the roster comes from GET /employees. The page previously called
   * GET /api/v1/users, which does not exist, so the table was always empty
   * and the failure was silently swallowed.
   */
  const fetchEmployees = useCallback(() => {
    setIsLoading(true);
    apiClient
      .getEmployees()
      .then((data) => {
        setEmployees(data);
        setError(null);
      })
      .catch((err: Error) => {
        setEmployees([]);
        setError(err.message || 'Unable to load employees');
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    fetchEmployees();
    apiClient.getTerritories().then(setTerritories).catch(() => setTerritories([]));
  }, [fetchEmployees]);

  /**
   * FT-007: a field representative needs BOTH a user account (credentials) and
   * an employee profile (name, territory, and the employees.id that visits
   * reference). The previous single call created only the account, so the new
   * person could never be assigned a visit.
   */
  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!email.trim() && !mobile.trim()) {
      setFormError('Provide an email address or a mobile number.');
      return;
    }
    if (mobile.trim()) {
      const mobileError = validatePhoneNumber(mobile);
      if (mobileError) {
        setFormError(mobileError);
        return;
      }
    }
    if (password.length < 8) {
      setFormError('Password must be at least 8 characters.');
      return;
    }

    setIsSaving(true);
    try {
      const user = await apiClient.createUser({
        email: email.trim() || null,
        mobile_number: mobile.trim() || null,
        password,
        role,
      });

      await apiClient.createEmployee({
        user_id: user.id,
        full_name: fullName.trim(),
        territory_id: territoryId || null,
        employee_code: employeeCode.trim() || null,
      });

      setIsModalOpen(false);
      setFullName('');
      setEmail('');
      setMobile('');
      setEmployeeCode('');
      setTerritoryId('');
      setPassword('');
      fetchEmployees();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to create employee');
    } finally {
      setIsSaving(false);
    }
  };

  /** FT-022: deactivation revokes access immediately (Security Design B1). */
  const handleToggleActive = async (employee: Employee, activate: boolean) => {
    try {
      await apiClient.setUserActive(employee.user_id, activate);
      fetchEmployees();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update account status');
    }
  };

  const territoryName = (id: string | null) =>
    territories.find((t) => t.id === id)?.name ?? 'Unassigned';

  const columns: Column<Employee>[] = [
    {
      header: 'Full Name',
      accessor: (emp) => (
        <div className="flex items-center gap-space-3">
          <div className="w-8 h-8 rounded-full bg-primary-container text-on-primary-container border border-primary-fixed-dim flex items-center justify-center font-headline-sm text-sm uppercase font-bold shrink-0">
            {emp.full_name.charAt(0)}
          </div>
          <div>
            <p className="font-headline-sm text-sm text-primary font-bold">{emp.full_name}</p>
            <p className="font-caption text-xs text-on-surface-variant">
              {emp.employee_code || `ID: ${emp.id.substring(0, 8)}...`}
            </p>
          </div>
        </div>
      ),
    },
    {
      header: 'Role',
      accessor: (emp) => <StatusBadge status={emp.user?.role ?? 'EMPLOYEE'} size="sm" showDot={false} />,
    },
    {
      header: 'Territory',
      accessor: (emp) => (
        <span className="font-caption text-xs text-on-surface">{territoryName(emp.territory_id)}</span>
      ),
    },
    {
      header: 'Contact Info',
      accessor: (emp) => (
        <div className="font-caption text-xs space-y-0.5">
          {emp.user?.email && (
            <div className="flex items-center gap-1.5 text-on-surface">
              <Mail className="w-3.5 h-3.5 text-outline shrink-0" />
              <span>{emp.user.email}</span>
            </div>
          )}
          {emp.user?.mobile_number && (
            <div className="flex items-center gap-1.5 text-on-surface-variant">
              <Phone className="w-3.5 h-3.5 text-outline shrink-0" />
              <span>{emp.user.mobile_number}</span>
            </div>
          )}
          {!emp.user?.email && !emp.user?.mobile_number && (
            <span className="text-outline">—</span>
          )}
        </div>
      ),
    },
    {
      header: 'Status',
      accessor: (emp) => (
        <StatusBadge status={emp.user?.is_active ? 'ACTIVE' : 'INACTIVE'} size="sm" showDot={true} />
      ),
    },
    {
      header: 'Account',
      accessor: (emp) => (
        <div className="flex items-center gap-space-2">
          <Button
            variant="outline"
            size="sm"
            icon={Eye}
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/employees/${emp.id}`);
            }}
          >
            Profile
          </Button>
          <Button
            variant="outline"
            size="sm"
            icon={MailOpen}
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/users/${emp.user_id}`);
            }}
          >
            User
          </Button>
          {emp.user?.is_active ? (
            <Button
              variant="outline"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                void handleToggleActive(emp, false);
              }}
            >
              Deactivate
            </Button>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                void handleToggleActive(emp, true);
              }}
            >
              Activate
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-space-6">
      <PageHeader
        title="Field Representatives & Staff"
        subtitle="Manage field agents and system administrator accounts."
        actions={
          <Button variant="secondary" size="sm" icon={UserPlus} onClick={() => setIsModalOpen(true)}>
            Add Employee
          </Button>
        }
      />

      {error && (
        <ErrorBanner message={error} onRetry={fetchEmployees} onDismiss={() => setError(null)} />
      )}

      {!isLoading && !error && employees.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No employees registered yet"
          subtitle="Register a field representative to start assigning visits."
          action={
            <Button variant="secondary" size="sm" icon={UserPlus} onClick={() => setIsModalOpen(true)}>
              Add Employee
            </Button>
          }
        />
      ) : (
        <DataTable
          columns={columns}
          data={employees}
          isLoading={isLoading}
          searchPlaceholder="Search employees by name, code, email..."
          searchFilter={(emp, q) => {
            const needle = q.toLowerCase();
            return (
              emp.full_name.toLowerCase().includes(needle) ||
              (emp.employee_code?.toLowerCase().includes(needle) ?? false) ||
              (emp.user?.email?.toLowerCase().includes(needle) ?? false)
            );
          }}
          onRowClick={(emp) => navigate(`/employees/${emp.id}`)}
        />
      )}

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Register New Field Representative"
        subtitle="Creates the login account and the employee profile together."
      >
        {formError && (
          <div className="mb-space-4 font-body-md text-xs text-on-error-container bg-error-container p-space-3 rounded-lg border border-error">
            {formError}
          </div>
        )}
        <form onSubmit={handleCreate} className="space-y-space-4">
          <Input
            label="Full Name"
            type="text"
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="John Doe"
          />
          <Input
            label="Email Address"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="john@fieldtrackpro.com"
            helperText="Email or mobile number is required."
          />
          <Input
            label="Mobile Phone"
            type="tel"
            value={mobile}
            onChange={(e) => setMobile(e.target.value)}
            placeholder="+919876543210"
          />
          <Input
            label="Employee Code"
            type="text"
            value={employeeCode}
            onChange={(e) => setEmployeeCode(e.target.value)}
            placeholder="EMP-001"
            helperText="Optional, must be unique."
          />
          <Select
            id="employee-territory"
            label="Territory"
            value={territoryId}
            onChange={(e) => setTerritoryId(e.target.value)}
          >
            <option value="">-- Unassigned --</option>
            {territories.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
          <Select
            id="employee-role"
            label="Role Assignment"
            value={role}
            onChange={(e) => setRole(e.target.value as UserRole)}
          >
            <option value="EMPLOYEE">Field Representative (EMPLOYEE)</option>
            <option value="ADMIN">System Administrator (ADMIN)</option>
          </Select>
          <Input
            label="Password"
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            helperText="Minimum 8 characters."
          />
          <div className="pt-space-4 flex justify-end gap-space-3 border-t border-surface-container-highest mt-space-6">
            <Button type="button" variant="ghost" size="sm" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="secondary" size="sm" isLoading={isSaving}>
              Save Employee
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
