import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Building2, Phone, MapPin, Navigation, Calendar, PackagePlus } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { EmptyState } from '../components/ui/EmptyState';
import { StatusBadge } from '../components/ui/StatusBadge';

import { apiClient, CustomerHistoryRow } from '../api/client';
import { AccountSummary, Customer, OrderRead, Territory } from '../types';
import { AccountSummaryCard } from '../components/ui/AccountSummaryCard';

/**
 * Customer Detail page — shows customer profile, account/collections, and visit history.
 */
export const CustomerDetailPage: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const [customer, setCustomer] = useState<Customer | null>(null);
    const [visitHistory, setVisitHistory] = useState<CustomerHistoryRow[]>([]);
    const [account, setAccount] = useState<AccountSummary | null>(null);
    const [orders, setOrders] = useState<OrderRead[]>([]);
    const [territories, setTerritories] = useState<Territory[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        if (!id) return;
        try {
            setIsLoading(true);
            const [cust, history, acct, orderHistory, territoryList] = await Promise.all([
                apiClient.getCustomerById(id),
                apiClient.getCustomerVisitHistory(id).catch(() => [] as CustomerHistoryRow[]),
                apiClient.getCustomerAccount(id).catch(() => null),
                apiClient.getCustomerOrders(id).catch(() => [] as OrderRead[]),
                apiClient.getTerritories().catch(() => [] as Territory[]),
            ]);
            setCustomer(cust);
            setVisitHistory(history);
            setAccount(acct);
            setOrders(orderHistory);
            setTerritories(territoryList);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load customer');
        } finally {
            setIsLoading(false);
        }
    }, [id]);

    // Zone (Territory) - client-side lookup since CustomerRead only carries
    // territory_id. Area is denormalized straight onto Customer by the
    // backend (area_name), so it needs no lookup.
    const territoryName = customer?.territory_id
        ? territories.find((t) => t.id === customer.territory_id)?.name
        : null;

    useEffect(() => {
        load();
    }, [load]);

    if (isLoading) return (
        <div className="flex items-center justify-center h-64" role="status">
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
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-5">
                    <div className="flex items-center gap-2">
                        <Phone className="w-4 h-4 text-secondary-container" />
                        <span className="text-sm font-mono text-on-surface">{customer.contact_number || '—'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <Building2 className="w-4 h-4 text-primary" />
                        <span className="text-sm text-on-surface">{customer.contact_person || '—'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <MapPin className="w-4 h-4 text-secondary-container" />
                        <span className="text-sm text-on-surface">{customer.address || '—'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <Navigation className="w-4 h-4 text-primary" />
                        <span className="text-sm font-mono text-on-surface">
                            {customer.location?.latitude != null && customer.location?.longitude != null
                                ? `${customer.location.latitude.toFixed(4)}, ${customer.location.longitude.toFixed(4)}`
                                : 'Missing GPS'}
                        </span>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="text-xs font-label-md uppercase tracking-wider font-bold text-primary">Geofence:</span>
                        <span className="font-label-md text-xs font-bold text-primary bg-primary-fixed/60 px-2 py-0.5 rounded border border-primary-fixed-dim">{customer.geofence_radius_m || 75}m</span>
                    </div>
                    {customer.outlet_code && (
                        <div className="flex items-center gap-2">
                            <span className="text-xs font-label-md uppercase tracking-wider font-bold text-primary">Outlet Code:</span>
                            <span className="font-mono text-xs font-bold text-on-primary-container bg-primary-container px-2 py-0.5 rounded shadow-2xs">{customer.outlet_code}</span>
                        </div>
                    )}
                    <div className="flex items-center gap-2">
                        <span className="text-xs font-label-md uppercase tracking-wider font-bold text-primary">Zone:</span>
                        <span className="text-sm text-on-surface font-semibold">{territoryName || '—'}</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <span className="text-xs font-label-md uppercase tracking-wider font-bold text-primary">Area:</span>
                        <span className="text-sm text-on-surface font-semibold">{customer.area_name || '—'}</span>
                    </div>
                </div>
            </Card>

            {account && <AccountSummaryCard account={account} />}

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <PackagePlus className="w-5 h-5" />
                        Order History
                    </CardTitle>
                    <CardSubtitle>{orders.length} order{orders.length !== 1 ? 's' : ''} captured across this outlet's visits</CardSubtitle>
                </CardHeader>
                {orders.length === 0 ? (
                    <div className="p-space-5">
                        <EmptyState icon={PackagePlus} title="No orders captured" subtitle="Orders captured during field visits to this outlet will appear here." />
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-left">
                            <thead className="bg-surface-container-low text-on-surface-variant text-xs uppercase tracking-wider border-b border-surface-container-highest">
                                <tr>
                                    <th className="px-space-4 py-space-3 font-bold text-primary">Date</th>
                                    <th className="px-space-4 py-space-3 font-bold text-primary">Employee</th>
                                    <th className="px-space-4 py-space-3 font-bold text-primary">Note</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-surface-container-highest">
                                {orders.map((order) => (
                                    <tr key={order.id} className="hover:bg-surface-container-low/80">
                                        <td className="px-space-4 py-space-3 text-sm text-on-surface-variant">
                                            {new Date(order.uploaded_at).toLocaleString()}
                                        </td>
                                        <td className="px-space-4 py-space-3 text-sm">{order.employee_name || '—'}</td>
                                        <td className="px-space-4 py-space-3 text-sm max-w-md truncate" title={order.note || ''}>
                                            {order.note || '—'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>

            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Calendar className="w-5 h-5" />
                        Visit History
                    </CardTitle>
                    <CardSubtitle>{visitHistory.length} visit{visitHistory.length !== 1 ? 's' : ''} recorded</CardSubtitle>
                </CardHeader>
                {visitHistory.length === 0 ? (
                    <div className="p-space-5">
                        <EmptyState title="No visits recorded" subtitle="No visits have been scheduled or completed for this customer yet." />
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-left">
                            <thead className="bg-surface-container-low text-on-surface-variant text-xs uppercase tracking-wider border-b border-surface-container-highest">
                                <tr>
                                    <th className="px-space-4 py-space-3 font-bold text-primary">Visit ID</th>
                                    <th className="px-space-4 py-space-3 font-bold text-primary">Scheduled</th>
                                    <th className="px-space-4 py-space-3 font-bold text-primary">Status</th>
                                    <th className="px-space-4 py-space-3 font-bold text-primary">Employee</th>
                                    <th className="px-space-4 py-space-3 font-bold text-primary">Check-In</th>
                                    <th className="px-space-4 py-space-3 font-bold text-primary">Check-Out</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-surface-container-highest">
                                {visitHistory.map((row) => (
                                    <tr key={row.visit_id} className="hover:bg-surface-container-low/80">
                                        <td className="px-space-4 py-space-3 font-mono text-xs text-on-surface-variant">
                                            {row.visit_id.substring(0, 8)}...
                                        </td>
                                        <td className="px-space-4 py-space-3 text-sm">
                                            {new Date(row.scheduled_at).toLocaleString()}
                                        </td>
                                        <td className="px-space-4 py-space-3">
                                            <StatusBadge status={row.status} size="sm" />
                                        </td>
                                        <td className="px-space-4 py-space-3 text-sm">{row.employee_name}</td>
                                        <td className="px-space-4 py-space-3 text-sm text-on-surface-variant">
                                            {row.check_in_at ? new Date(row.check_in_at).toLocaleString() : '—'}
                                        </td>
                                        <td className="px-space-4 py-space-3 text-sm text-on-surface-variant">
                                            {row.check_out_at ? new Date(row.check_out_at).toLocaleString() : '—'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>
        </div>
    );
};
