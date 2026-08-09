import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Building2, Phone, MapPin, Navigation } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { EmptyState } from '../components/ui/EmptyState';

import { apiClient } from '../api/client';
import { Customer, Visit } from '../types';

interface CustomerDetailData extends Customer {
    visit_history?: Visit[];
}

/**
 * Customer Detail page — shows customer profile and visit history.
 */
export const CustomerDetailPage: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [customer, setCustomer] = useState<CustomerDetailData | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        if (!id) return;
        try {
            setIsLoading(true);
            const cust = await apiClient.getCustomerById(id);
            setCustomer(cust);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load customer');
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
    if (!customer) return <EmptyState title="Customer not found" subtitle="The requested customer could not be found." />;

    return (
        <div className="space-y-space-6">
            <PageHeader
                title={customer.name}
                subtitle="Customer profile and visit history."
                actions={
                    <button
                        onClick={() => navigate('/customers')}
                        className="flex items-center gap-2 text-sm text-on-surface-variant hover:text-on-surface"
                    >
                        <ArrowLeft className="w-4 h-4" />
                        Back to Customers
                    </button>
                }
            />

            <Card>
                <CardHeader>
                    <CardTitle>Profile</CardTitle>
                    <CardSubtitle>Customer information</CardSubtitle>
                </CardHeader>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-space-4 p-space-5">
                    <div className="flex items-center gap-space-2">
                        <Phone className="w-4 h-4 text-on-surface-variant" />
                        <span className="text-sm">{customer.contact_number}</span>
                    </div>
                    <div className="flex items-center gap-space-2">
                        <Building2 className="w-4 h-4 text-on-surface-variant" />
                        <span className="text-sm">{customer.contact_person || '—'}</span>
                    </div>
                    <div className="flex items-center gap-space-2">
                        <MapPin className="w-4 h-4 text-on-surface-variant" />
                        <span className="text-sm">{customer.address}</span>
                    </div>
                    <div className="flex items-center gap-space-2">
                        <Navigation className="w-4 h-4 text-on-surface-variant" />
                        <span className="text-sm">
                            {customer.location?.latitude.toFixed(4)}, {customer.location?.longitude.toFixed(4)}
                        </span>
                    </div>
                    <div className="flex items-center gap-space-2">
                        <span className="text-sm font-semibold text-primary">Geofence:</span>
                        <span className="text-sm">{customer.geofence_radius_m}m</span>
                    </div>
                </div>
            </Card>
        </div>
    );
};
