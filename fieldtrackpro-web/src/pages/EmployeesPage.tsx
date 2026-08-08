import React, { useEffect, useState } from 'react';
import { UserPlus, Phone, Mail } from 'lucide-react';
import { DataTable, Column } from '../components/ui/DataTable';
import { Modal } from '../components/ui/Modal';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { StatusBadge } from '../components/ui/StatusBadge';
import { apiClient } from '../api/client';
import { User } from '../types';

export const EmployeesPage: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Form State
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [mobile, setMobile] = useState('');
  const [role, setRole] = useState<'EMPLOYEE' | 'MANAGER' | 'ADMIN'>('EMPLOYEE');
  const [password, setPassword] = useState('Secret@1234');
  const [formError, setFormError] = useState<string | null>(null);

  const fetchUsers = () => {
    setIsLoading(true);
    apiClient.getUsers()
      .then((data) => setUsers(data))
      .catch(() => setUsers([]))
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    try {
      await apiClient.createUser({
        full_name: fullName,
        email: email || null,
        mobile: mobile || null,
        role: role,
        password: password,
      });
      setIsModalOpen(false);
      setFullName('');
      setEmail('');
      setMobile('');
      fetchUsers();
    } catch (err: any) {
      setFormError(err.message || 'Failed to create user account');
    }
  };

  const columns: Column<User>[] = [
    {
      header: 'Full Name',
      accessor: (user) => (
        <div className="flex items-center gap-space-3">
          <div className="w-8 h-8 rounded-full bg-primary-container text-on-primary-container border border-primary-fixed-dim flex items-center justify-center font-headline-sm text-sm uppercase font-bold shrink-0">
            {user.full_name.charAt(0)}
          </div>
          <div>
            <p className="font-headline-sm text-sm text-primary font-bold">{user.full_name}</p>
            <p className="font-caption text-xs text-on-surface-variant">ID: {user.id.substring(0, 8)}...</p>
          </div>
        </div>
      ),
    },
    {
      header: 'Role',
      accessor: (user) => (
        <StatusBadge status={user.role} size="sm" showDot={false} />
      ),
    },
    {
      header: 'Contact Info',
      accessor: (user) => (
        <div className="font-caption text-xs space-y-0.5">
          {user.email && (
            <div className="flex items-center gap-1.5 text-on-surface">
              <Mail className="w-3.5 h-3.5 text-outline shrink-0" />
              <span>{user.email}</span>
            </div>
          )}
          {user.mobile && (
            <div className="flex items-center gap-1.5 text-on-surface-variant">
              <Phone className="w-3.5 h-3.5 text-outline shrink-0" />
              <span>{user.mobile}</span>
            </div>
          )}
        </div>
      ),
    },
    {
      header: 'Account Status',
      accessor: (user) => (
        <StatusBadge status={user.is_active ? 'ACTIVE' : 'DISABLED'} size="sm" />
      ),
    },
  ];

  return (
    <div className="space-y-space-6">
      <PageHeader
        title="Field Representatives & Staff"
        subtitle="Manage field agents, managers, and system administrator accounts."
        actions={
          <Button variant="secondary" size="sm" icon={UserPlus} onClick={() => setIsModalOpen(true)}>
            Add Employee
          </Button>
        }
      />

      <DataTable
        columns={columns}
        data={users}
        isLoading={isLoading}
        searchPlaceholder="Search employees by name, email, role..."
        searchFilter={(user, q) =>
          user.full_name.toLowerCase().includes(q.toLowerCase()) ||
          (user.email ? user.email.toLowerCase().includes(q.toLowerCase()) : false) ||
          user.role.toLowerCase().includes(q.toLowerCase())
        }
      />

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Register New Field Representative"
        subtitle="Provision field agent credentials and access roles."
      >
        {formError && (
          <div className="mb-space-4 font-body-md text-xs text-on-error-container bg-error-container p-space-3 rounded-lg border border-error">
            {formError}
          </div>
        )}
        <form onSubmit={handleCreateUser} className="space-y-space-4">
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
          />
          <Input
            label="Mobile Phone"
            type="text"
            value={mobile}
            onChange={(e) => setMobile(e.target.value)}
            placeholder="+19876543210"
          />
          <div className="flex flex-col gap-space-1.5">
            <label className="font-label-md text-label-md text-on-surface uppercase tracking-wider block font-semibold">
              Role Assignment
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as any)}
              className="w-full h-10 bg-surface border border-outline-variant rounded-lg px-space-3 text-on-surface font-body-md text-sm focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all"
            >
              <option value="EMPLOYEE">Field Representative (EMPLOYEE)</option>
              <option value="MANAGER">Field Manager (MANAGER)</option>
              <option value="ADMIN">System Administrator (ADMIN)</option>
            </select>
          </div>
          <Input
            label="Password"
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <div className="pt-space-4 flex justify-end gap-space-3 border-t border-surface-container-highest mt-space-6">
            <Button type="button" variant="ghost" size="sm" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="secondary" size="sm">
              Save Employee
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
