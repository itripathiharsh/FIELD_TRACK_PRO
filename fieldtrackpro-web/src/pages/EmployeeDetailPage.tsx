import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Mail, Phone, MapPin, Calendar } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { EmptyState } from '../components/ui/EmptyState';

import { apiClient } from '../api/client';
import { Employee, Visit } from '../types';

interface EmployeeDetailData extends Employee {
    visit_history?: Visit[];
}

/**
 * Employee Detail page — shows employee profile and visit history.
 */
export const EmployeeDetailPage: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [employee, setEmployee] = useState<EmployeeDetailData | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        if (!id) return;
        try {
            setIsLoading(true);
            const emp = await apiClient.getEmployeeById(id);
            setEmployee(emp);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load employee');
        } finally {
            setIsLoading(false);
        }
    }, [id]);

    useEffect(() => {
        load();
    }, [load]);

    if (isLoading) return (
        <div className="flex items-center justify-center h-64">
            <div className="w-10 h-10 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin" />
        </div>
    );
    if (error) return <ErrorBanner message={error} onRetry={load} />;
    if (!employee) return <EmptyState title="Employee not found" subtitle="The requested employee could not be found." />;

    return (
        <div className="space-y-space-6">
            <PageHeader
                title={employee.full_name}
                subtitle="Employee profile and visit history."
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

            <Card>
                <CardHeader>
                    <CardTitle>Profile</CardTitle>
                    <CardSubtitle>Employee information</CardSubtitle>
                </CardHeader>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-space-4 p-space-5">
                    <div className="flex items-center gap-space-2">
                        <Mail className="w-4 h-4 text-on-surface-variant" />
                        <span className="text-sm">{employee.user?.email || employee.user_id || '—'}</span>
                    </div>
                    <div className="flex items-center gap-space-2">
                        <Phone className="w-4 h-4 text-on-surface-variant" />
                        <span className="text-sm">{employee.user?.mobile_number || '—'}</span>
                    </div>
                    <div className="flex items-center gap-space-2">
                        <MapPin className="w-4 h-4 text-on-surface-variant" />
                        <span className="text-sm">Territory: {employee.territory_id || 'Unassigned'}</span>
                    </div>
                    <div className="flex items-center gap-space-2">
                        <Calendar className="w-4 h-4 text-on-surface-variant" />
                        <span className="text-sm">Code: {employee.employee_code || '—'}</span>
                    </div>
                </div>
            </Card>
        </div>
    );
};
