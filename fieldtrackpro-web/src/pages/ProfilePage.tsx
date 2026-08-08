import React from 'react';
import { LogOut } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { StatusBadge } from '../components/ui/StatusBadge';

export const ProfilePage: React.FC = () => {
  const { user, logout } = useAuth();

  return (
    <div className="space-y-space-6 max-w-2xl font-body-md text-on-surface">
      <PageHeader
        title="User Profile"
        subtitle="Authenticated administrator credentials and session details."
      />

      <Card variant="default" className="space-y-space-6">
        <div className="flex items-center gap-space-4 border-b border-surface-container-highest pb-space-6">
          <div className="w-14 h-14 rounded-full bg-primary-container text-on-primary-container border border-primary-fixed-dim flex items-center justify-center font-headline-lg text-xl uppercase font-bold shrink-0">
            {user?.full_name?.charAt(0) || 'A'}
          </div>
          <div>
            <h2 className="font-headline-sm text-lg font-bold text-primary">{user?.full_name || 'System Administrator'}</h2>
            <div className="mt-1.5">
              <StatusBadge status={user?.role || 'ADMIN'} size="sm" showDot={false} />
            </div>
          </div>
        </div>

        <div className="space-y-space-4 font-body-md text-xs">
          <div>
            <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold">Account ID</p>
            <p className="text-on-surface font-mono mt-0.5">{user?.id || 'N/A'}</p>
          </div>
          <div>
            <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold">Email Address</p>
            <p className="text-on-surface font-medium mt-0.5">{user?.email || 'admin@fieldtrackpro.com'}</p>
          </div>
          <div>
            <p className="font-label-md text-xs text-on-surface-variant uppercase font-semibold">Mobile Phone</p>
            <p className="text-on-surface font-medium mt-0.5">{user?.mobile || 'Not set'}</p>
          </div>
        </div>

        <div className="pt-space-4 border-t border-surface-container-highest">
          <Button variant="danger" size="md" icon={LogOut} onClick={logout} className="w-full">
            Sign Out Session
          </Button>
        </div>
      </Card>
    </div>
  );
};
