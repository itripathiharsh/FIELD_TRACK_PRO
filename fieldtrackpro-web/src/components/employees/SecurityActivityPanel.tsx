import React, { useCallback, useEffect, useState } from 'react';
import { History } from 'lucide-react';
import { apiClient } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import type { SecurityAuditLog } from '../../types';
import { isSuperAdmin, roleLabel } from '../../utils/roles';
import { Card, CardHeader, CardSubtitle, CardTitle } from '../ui/Card';

const EVENT_LABELS: Record<string, string> = {
  ADMIN_PASSWORD_RESET: 'Password reset by admin',
  ROLE_CHANGE: 'Role change',
  SUPER_ADMIN_BOOTSTRAP: 'Super Admin established',
  ACCOUNT_DEACTIVATED: 'Account deactivated',
  ACCOUNT_ACTIVATED: 'Account activated',
  USER_CREATE_PRIVILEGED: 'Admin account created',
};

function describe(row: SecurityAuditLog): string {
  const base = EVENT_LABELS[row.event_type] ?? row.event_type;
  if (row.event_type === 'ROLE_CHANGE' && row.previous_role && row.new_role) {
    return `${base}: ${roleLabel(row.previous_role)} → ${roleLabel(row.new_role)}`;
  }
  return base;
}

/** Super-Admin-only: recent security events for one account (the audit trail never contains credentials). */
export const SecurityActivityPanel: React.FC<{ targetUserId: string; refreshKey?: number }> = ({
  targetUserId,
  refreshKey = 0,
}) => {
  const { user } = useAuth();
  const [rows, setRows] = useState<SecurityAuditLog[] | null>(null);
  const [failed, setFailed] = useState(false);
  const allowed = isSuperAdmin(user);

  const load = useCallback(async () => {
    try {
      setRows(await apiClient.getSecurityAuditLogs({ target_user_id: targetUserId, limit: 10 }));
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, [targetUserId]);

  useEffect(() => {
    if (allowed) void load();
  }, [allowed, load, refreshKey]);

  if (!allowed) return null;

  return (
    <Card>
      <CardHeader>
        <div>
          <div className="flex items-center gap-space-2">
            <History className="w-4 h-4 text-primary" />
            <CardTitle>Security activity</CardTitle>
          </div>
          <CardSubtitle>Password resets and role changes for this account.</CardSubtitle>
        </div>
      </CardHeader>
      <div className="p-space-5">
        {failed ? (
          <p className="text-xs text-on-surface-variant">Security activity could not be loaded.</p>
        ) : rows === null ? (
          <p className="text-xs text-on-surface-variant">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="text-xs text-on-surface-variant">No security events recorded.</p>
        ) : (
          <ul className="divide-y divide-surface-container-highest">
            {rows.map((r) => (
              <li key={r.id} className="py-space-2 flex items-center justify-between gap-space-3 text-xs">
                <span className="text-on-surface">{describe(r)}</span>
                <span className="flex items-center gap-space-3 text-on-surface-variant shrink-0">
                  <span className={r.outcome === 'SUCCESS' ? 'text-primary font-semibold' : 'text-error font-semibold'}>
                    {r.outcome}
                  </span>
                  <time dateTime={r.created_at}>{new Date(r.created_at).toLocaleString()}</time>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
};
