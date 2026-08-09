import React, { useEffect, useState } from 'react';
import { Card } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';
import { EmptyState } from '../components/ui/EmptyState';
import { FieldTrackMap, MapMarker } from '../components/maps/FieldTrackMap';
import { apiClient } from '../api/client';
import { Customer } from '../types';

/**
 * Map page for visualizing customer locations.
 *
 * Phase 4 Section 1 (MapLibre decision):
 * - Shows customer locations on an interactive map
 * - Uses real backend data only
 * - No fake/demo geographic data
 */
export const MapPage: React.FC = () => {
    const [customers, setCustomers] = useState<Customer[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);

    useEffect(() => {
        loadCustomers();
    }, []);

    const loadCustomers = async () => {
        try {
            setIsLoading(true);
            const data = await apiClient.getCustomers();
            setCustomers(data);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to load customers');
        } finally {
            setIsLoading(false);
        }
    };

    // Filter customers with valid coordinates (not Null Island)
    const customersWithLocation = customers.filter(
        (c) => c.location &&
            c.location.latitude !== 0 &&
            c.location.longitude !== 0 &&
            c.location.latitude >= -90 && c.location.latitude <= 90 &&
            c.location.longitude >= -180 && c.location.longitude <= 180
    );

    const markers: MapMarker[] = customersWithLocation.map((c) => ({
        id: c.id,
        latitude: c.location!.latitude,
        longitude: c.location!.longitude,
        label: c.name,
        color: '#1976D2',
    }));

    // Calculate center from valid customer locations
    const centerLat = customersWithLocation.length > 0
        ? customersWithLocation.reduce((sum, c) => sum + c.location!.latitude, 0) / customersWithLocation.length
        : undefined;
    const centerLng = customersWithLocation.length > 0
        ? customersWithLocation.reduce((sum, c) => sum + c.location!.longitude, 0) / customersWithLocation.length
        : undefined;

    return (
        <div className="space-y-6">
            <PageHeader
                title="Customer Locations Map"
                subtitle="Geographic distribution of customer sites."
            />

            {error && (
                <Card>
                    <p className="text-error">{error}</p>
                </Card>
            )}

            {isLoading ? (
                <Card>
                    <div className="flex items-center justify-center h-64">
                        <div className="w-10 h-10 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin" />
                    </div>
                </Card>
            ) : customersWithLocation.length === 0 ? (
                <EmptyState
                    title="No Location Data"
                    subtitle="No customers have valid geographic coordinates. Add customer locations to see them on the map."
                />
            ) : (
                <Card>
                    <FieldTrackMap
                        centerLat={centerLat}
                        centerLng={centerLng}
                        zoom={10}
                        markers={markers}
                        height="500px"
                        onMarkerClick={(marker) => {
                            const customer = customersWithLocation.find((c) => c.id === marker.id);
                            setSelectedCustomer(customer || null);
                        }}
                        onError={(msg) => setError(msg)}
                    />
                </Card>
            )}

            {selectedCustomer && (
                <Card>
                    <h3 className="text-lg font-bold text-on-surface mb-2">{selectedCustomer.name}</h3>
                    <p className="text-sm text-on-surface-variant">
                        Lat: {selectedCustomer.location?.latitude.toFixed(6)}, Lng: {selectedCustomer.location?.longitude.toFixed(6)}
                    </p>
                    <p className="text-sm text-on-surface-variant">
                        Geofence: {selectedCustomer.geofence_radius_m}m
                    </p>
                    <p className="text-sm text-on-surface-variant">
                        Address: {selectedCustomer.address}
                    </p>
                </Card>
            )}

            <Card>
                <h3 className="text-lg font-bold text-on-surface mb-2">Legend</h3>
                <div className="flex items-center gap-4 text-sm text-on-surface-variant">
                    <div className="flex items-center gap-2">
                        <div className="w-4 h-4 rounded-full bg-primary border-2 border-white shadow" />
                        <span>Customer Location</span>
                    </div>
                </div>
            </Card>
        </div>
    );
};
