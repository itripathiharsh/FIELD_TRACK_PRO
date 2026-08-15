import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Mail, Phone, Shield, Calendar, UserCheck, UserX } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { EmptyState } from '../components/ui/EmptyState';
import { Button } from '../components/ui/Button';
import { StatusBadge } from '../components/ui/StatusBadge';

import { apiClient } from '../api/client';
import { User } from '../types';

/**
 * User Detail page — shows user account details and allows activate/deactivate.
 */
export const UserDetailPage: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isUpdating, setIsUpdating] = useState(false);

    const load = useCallback(async () => {
        if (!id) return;
        try {
            setIsLoading(true);
            const u = await apiClient.getUserById(id);
            setUser(u);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load user');
        } finally {
            setIsLoading(false);
        }
    }, [id]);

    useEffect(() => {
        load();
    }, [load]);

    const handleToggleActive = async (activate: boolean) => {
        if (!user) return;
        try {
            setIsUpdating(true);
            const updated = await apiClient.setUserActive(user.id, activate);
            setUser(updated);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to update account status');
        } finally {
            setIsUpdating(false);
        }
    };

    if (isLoading) return (
        <div className="flex items-center justify-center h-64" role="status">
            <div className="w-10 h-10 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin" />
        </div>
    );
    if (error && !user) return <ErrorBanner message={error} onRetry={load} />;
    if (!user) return <EmptyState title="User not found" subtitle="The requested user could not be found." />;

    return (
        <div className="space-y-space-6">
            <PageHeader
                title={user.full_name}
                subtitle="User account details and status."
                actions={
                    <button
                        onClick={() => navigate('/employees')}
                        className="flex items-center gap-2 text-sm text-on-surface-variant hover:text-on-surface"
                    >
                        <ArrowLeft className="w-4 h-4" />
                        Back to Employees
                    </button>
                }
            />

            {error && (
                <ErrorBanner message={error} onDismiss={() => setError(null)} />
            )}

            <Card>
                <CardHeader>
                    <CardTitle>Account</CardTitle>
                    <CardSubtitle>User account information</CardSubtitle>
                </CardHeader>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-space-4 p-space-5">
                    <div className="flex items-center gap-space-2">
                        <Mail className="w-4 h-4 text-on-surface-variant" />
                        <span className="text-sm">{user.email || '—'}</span>
                    </div>
                    <div className="flex items-center gap-space-2">
                        <Phone className="w-4 h-4 text-on-surface-variant" />
                        <span className="text-sm">{user.mobile_number || '—'}</span>
                    </div>
                    <div className="flex items-center gap-space-2">
                        <Shield className="w-4 h-4 text-on-surface-variant" />
                        <span className="text-sm"><StatusBadge status={user.role} size="sm" showDot={false} /></span>
                    </div>
                    <div className="flex items-center gap-space-2">
                        <Calendar className="w-4 h-4 text-on-surface-variant" />
                        <span className="text-sm">ID: {user.id}</span>
                    </div>
                </div>
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle>Account Status</CardTitle>
                    <CardSubtitle>Activate or deactivate this user account.</CardSubtitle>
                </CardHeader>
                <div className="p-space-5">
                    <div className="flex items-center gap-space-4">
                        <div className="flex items-center gap-space-2">
                            <span className="text-sm font-semibold text-on-surface">Status:</span>
                            <StatusBadge status={user.is_active ? 'ACTIVE' : 'INACTIVE'} size="sm" showDot={true} />
                        </div>
                        <div className="flex items-center gap-space-2">
                            {user.is_active ? (
                                <Button
                                    variant="danger"
                                    size="sm"
                                    icon={UserX}
                                    isLoading={isUpdating}
                                    onClick={() => handleToggleActive(false)}
                                >
                                    Deactivate
                                </Button>
                            ) : (
                                <Button
                                    variant="primary"
                                    size="sm"
                                    icon={UserCheck}
                                    isLoading={isUpdating}
                                    onClick={() => handleToggleActive(true)}
                                >
                                    Activate
                                </Button>
                            )}
                        </div>
                    </div>
                </div>
            </Card>
        </div>
    );
};
