import React, { useCallback, useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { UserPlus, Phone, Mail, MailOpen, Users, Eye, Filter, Layers } from 'lucide-react';
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

  // Server-side pagination & filter state
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalCount, setTotalCount] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterTerritoryId, setFilterTerritoryId] = useState('');
  const [filterRole, setFilterRole] = useState('');
  const [filterStatus, setFilterStatus] = useState<string>('');

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [mobile, setMobile] = useState('');
  const [employeeCode, setEmployeeCode] = useState('');
  const [workingProfile, setWorkingProfile] = useState('');
  const [territoryId, setTerritoryId] = useState('');
  const [role, setRole] = useState<UserRole>('EMPLOYEE');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const fetchEmployees = useCallback(
    (
      targetPage = page,
      targetSearch = searchQuery,
      targetTerritory = filterTerritoryId,
      targetRole = filterRole,
      targetStatus = filterStatus,
      targetPageSize = pageSize,
    ) => {
      setIsLoading(true);
      const isActiveParam =
        targetStatus === 'ACTIVE' ? true : targetStatus === 'INACTIVE' ? false : undefined;

      apiClient
        .getEmployeesPaginated({
          skip: (targetPage - 1) * targetPageSize,
          limit: targetPageSize,
          search: targetSearch.trim() || undefined,
          territory_id: targetTerritory || undefined,
          role: targetRole || undefined,
          is_active: isActiveParam,
        })
        .then(({ items, total }) => {
          setEmployees(items);
          setTotalCount(total);
          setError(null);
        })
        .catch((err: Error) => {
          setEmployees([]);
          setTotalCount(0);
          setError(err.message || 'Unable to load employees');
        })
        .finally(() => setIsLoading(false));
    },
    [page, pageSize, searchQuery, filterTerritoryId, filterRole, filterStatus],
  );

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchEmployees(page, searchQuery, filterTerritoryId, filterRole, filterStatus);
    }, 250);
    return () => clearTimeout(timer);
  }, [page, searchQuery, filterTerritoryId, filterRole, filterStatus, fetchEmployees]);

  useEffect(() => {
    apiClient.getTerritories().then(setTerritories).catch(() => setTerritories([]));
  }, []);

  const activeTerritories = useMemo(
    () => territories.filter((t) => t.status === 'ACTIVE' || !t.status),
    [territories],
  );

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFieldErrors({});

    const errors: Record<string, string> = {};

    if (!fullName.trim() || fullName.trim().length < 2) {
      errors.full_name = 'Full name must be at least 2 characters.';
    }

    if (!email.trim() && !mobile.trim()) {
      setFormError('Provide an email address or a mobile number.');
      return;
    }

    if (mobile.trim()) {
      const mobileError = validatePhoneNumber(mobile, { required: false });
      if (mobileError) {
        errors.mobile_number = mobileError;
      }
    }

    if (password.length < 8) {
      errors.password = 'Password must be at least 8 characters.';
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setIsSaving(true);
    try {
      await apiClient.registerEmployee({
        user: {
          email: email.trim() || null,
          mobile_number: mobile.trim() || null,
          password,
          role,
        },
        full_name: fullName.trim(),
        territory_id: territoryId || null,
        employee_code: employeeCode.trim().toUpperCase() || null,
        working_profile: workingProfile.trim() || null,
      });

      setIsModalOpen(false);
      setFullName('');
      setEmail('');
      setMobile('');
      setEmployeeCode('');
      setWorkingProfile('');
      setTerritoryId('');
      setPassword('');
      setFieldErrors({});
      fetchEmployees(1);
    } catch (err: any) {
      if (err?.fieldErrors) {
        setFieldErrors(err.fieldErrors);
      }
      setFormError(err instanceof Error ? err.message : 'Failed to create employee');
    } finally {
      setIsSaving(false);
    }
  };

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
            <p className="font-caption text-xs text-on-surface-variant font-mono">
              {emp.employee_code || `ID: ${emp.id.substring(0, 8)}...`}
            </p>
          </div>
        </div>
      ),
    },
    {
      header: 'Role & Profile',
      accessor: (emp) => (
        <div className="space-y-1">
          <StatusBadge status={emp.user?.role ?? 'EMPLOYEE'} size="sm" showDot={false} />
          {emp.working_profile && (
            <span className="inline-block px-2 py-0.5 text-[10px] font-semibold bg-surface-container border border-outline-variant text-on-surface rounded">
              {emp.working_profile}
            </span>
          )}
        </div>
      ),
    },
    {
      header: 'Territory',
      accessor: (emp) => (
        <div className="flex items-center gap-1.5">
          <span className="font-caption text-xs text-on-surface">{territoryName(emp.territory_id)}</span>
          <span
            title="Multi-zone coverage supported"
            className="inline-flex items-center text-outline hover:text-primary cursor-help"
          >
            <Layers className="w-3 h-3" />
          </span>
        </div>
      ),
    },
    {
      header: 'Contact',
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
        subtitle="Manage field agents and system administrator accounts with server-side pagination."
        actions={
          <Button variant="secondary" size="sm" icon={UserPlus} onClick={() => setIsModalOpen(true)}>
            Add Employee
          </Button>
        }
      />

      {error && (
        <ErrorBanner message={error} onRetry={() => fetchEmployees()} onDismiss={() => setError(null)} />
      )}

      {/* Filter Toolbar */}
      <div className="flex flex-row flex-wrap gap-space-3 items-center bg-surface-container p-space-3 rounded-lg border border-outline-variant">
        <div className="flex items-center gap-1.5 text-xs text-on-surface-variant font-medium shrink-0">
          <Filter className="w-3.5 h-3.5" />
          <span>Filters:</span>
        </div>

        <Select
          id="filter-territory"
          value={filterTerritoryId}
          onChange={(e) => {
            setFilterTerritoryId(e.target.value);
            setPage(1);
          }}
          className="w-44 text-xs py-1"
        >
          <option value="">All Territories</option>
          {territories.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </Select>

        <Select
          id="filter-role"
          value={filterRole}
          onChange={(e) => {
            setFilterRole(e.target.value);
            setPage(1);
          }}
          className="w-36 text-xs py-1"
        >
          <option value="">All Roles</option>
          <option value="EMPLOYEE">Field Rep</option>
          <option value="ADMIN">Admin</option>
        </Select>

        <Select
          id="filter-status"
          value={filterStatus}
          onChange={(e) => {
            setFilterStatus(e.target.value);
            setPage(1);
          }}
          className="w-32 text-xs py-1"
        >
          <option value="">All Status</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
        </Select>

        {/* Per-page selector */}
        <div className="flex items-center gap-1.5 ml-auto shrink-0">
          <span className="font-label-md text-xs text-on-surface-variant uppercase tracking-wider font-semibold">Show:</span>
          <select
            value={pageSize}
            onChange={(e) => {
              const next = Number(e.target.value);
              setPageSize(next);
              setPage(1);
              fetchEmployees(1, searchQuery, filterTerritoryId, filterRole, filterStatus, next);
            }}
            className="h-8 bg-surface border border-outline-variant rounded-lg px-2 py-1 text-xs text-primary font-bold focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all cursor-pointer"
            aria-label="Rows per page"
          >
            {[10, 20, 50, 100, 200].map((opt) => (
              <option key={opt} value={opt}>{opt} rows</option>
            ))}
          </select>
        </div>

        {(filterTerritoryId || filterRole || filterStatus || searchQuery) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setFilterTerritoryId('');
              setFilterRole('');
              setFilterStatus('');
              setSearchQuery('');
              setPage(1);
            }}
          >
            Reset Filters
          </Button>
        )}
      </div>

      {!isLoading && !error && employees.length === 0 && !searchQuery && !filterTerritoryId && !filterRole && !filterStatus ? (
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
          searchPlaceholder="Search employees across name, code, email, mobile..."
          serverSide={true}
          totalCount={totalCount}
          page={page}
          pageSize={pageSize}
          onPageChange={(p) => setPage(p)}
          onSearchChange={(q) => {
            setSearchQuery(q);
            setPage(1);
          }}
          onRowClick={(emp) => navigate(`/employees/${emp.id}`)}
        />
      )}

      <Modal
        isOpen={isModalOpen}
        onClose={() => !isSaving && setIsModalOpen(false)}
        disableClose={isSaving}
        title="Register New Field Representative"
        subtitle="Creates the login account and employee profile together."
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
            error={fieldErrors.full_name}
            onChange={(e) => {
              setFullName(e.target.value);
              if (fieldErrors.full_name) {
                setFieldErrors((prev) => ({ ...prev, full_name: '' }));
              }
            }}
            placeholder="John Doe"
          />
          <Input
            label="Email Address"
            type="email"
            value={email}
            error={fieldErrors.email}
            onChange={(e) => {
              setEmail(e.target.value);
              if (fieldErrors.email) {
                setFieldErrors((prev) => ({ ...prev, email: '' }));
              }
            }}
            placeholder="john@fieldtrackpro.com"
            helperText="Email or mobile number is required."
          />
          <Input
            label="Mobile Phone"
            type="tel"
            value={mobile}
            error={fieldErrors.mobile_number}
            onChange={(e) => {
              setMobile(e.target.value);
              if (fieldErrors.mobile_number) {
                setFieldErrors((prev) => ({ ...prev, mobile_number: '' }));
              }
            }}
            placeholder="+919876543210"
          />
          <div className="grid grid-cols-2 gap-space-3">
            <Input
              label="Employee Code"
              type="text"
              value={employeeCode}
              error={fieldErrors.employee_code}
              onChange={(e) => {
                setEmployeeCode(e.target.value);
                if (fieldErrors.employee_code) {
                  setFieldErrors((prev) => ({ ...prev, employee_code: '' }));
                }
              }}
              placeholder="EMP-001"
              helperText="Normalized to uppercase."
            />
          </div>
          <Input
            label="Working Profile"
            type="text"
            value={workingProfile}
            onChange={(e) => setWorkingProfile(e.target.value)}
            placeholder="e.g. SENIOR_SALES / FIELD_OFFICER"
          />
          <Select
            id="employee-territory"
            label="Territory"
            value={territoryId}
            onChange={(e) => setTerritoryId(e.target.value)}
          >
            <option value="">-- Unassigned --</option>
            {activeTerritories.map((t) => (
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
            error={fieldErrors.password}
            onChange={(e) => {
              setPassword(e.target.value);
              if (fieldErrors.password) {
                setFieldErrors((prev) => ({ ...prev, password: '' }));
              }
            }}
            helperText="Minimum 8 characters."
          />
          <div className="pt-space-4 flex justify-end gap-space-3 border-t border-surface-container-highest mt-space-6">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={isSaving}
              onClick={() => setIsModalOpen(false)}
            >
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
