import React, { useEffect, useState } from 'react';
import { Card } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { FieldTrackMap, MapMarker, TerritoryCircle } from '../components/maps/FieldTrackMap';
import { apiClient } from '../api/client';
import { Customer, Territory } from '../types';

const MARKER_COLOR = '#ffa515';

export const MapPage: React.FC = () => {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);

  useEffect(() => {
    loadMapData();
  }, []);

  const loadMapData = async () => {
    try {
      setIsLoading(true);
      const [custData, terrData] = await Promise.all([
        apiClient.getCustomers().catch(() => [] as Customer[]),
        apiClient.getTerritories().catch(() => [] as Territory[]),
      ]);
      setCustomers(Array.isArray(custData) ? custData : []);
      setTerritories(Array.isArray(terrData) ? terrData : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load map data');
      setCustomers([]);
      setTerritories([]);
    } finally {
      setIsLoading(false);
    }
  };

  const customersWithLocation = (Array.isArray(customers) ? customers : []).filter(
    (c) =>
      c &&
      c.location &&
      typeof c.location.latitude === 'number' &&
      typeof c.location.longitude === 'number' &&
      c.location.latitude !== 0 &&
      c.location.longitude !== 0 &&
      c.location.latitude >= -90 &&
      c.location.latitude <= 90 &&
      c.location.longitude >= -180 &&
      c.location.longitude <= 180,
  );

  const markers: MapMarker[] = customersWithLocation.map((c) => ({
    id: c.id,
    latitude: c.location!.latitude,
    longitude: c.location!.longitude,
    label: c.name,
    color: MARKER_COLOR,
  }));

  const territoryCircles: TerritoryCircle[] = (
    Array.isArray(territories) ? territories : []
  )
    .filter(
      (t) =>
        t.status !== 'INACTIVE' &&
        t.center_latitude != null &&
        t.center_longitude != null &&
        t.radius_km != null &&
        t.radius_km > 0,
    )
    .map((t) => ({
      id: t.id,
      centerLat: t.center_latitude!,
      centerLng: t.center_longitude!,
      radiusKm: t.radius_km!,
      name: `${t.name} Territory Coverage`,
      color: '#14213D',
    }));

  const centerLat =
    customersWithLocation.length > 0
      ? customersWithLocation.reduce((sum, c) => sum + c.location!.latitude, 0) /
        customersWithLocation.length
      : territoryCircles.length > 0
      ? territoryCircles[0].centerLat
      : undefined;

  const centerLng =
    customersWithLocation.length > 0
      ? customersWithLocation.reduce((sum, c) => sum + c.location!.longitude, 0) /
        customersWithLocation.length
      : territoryCircles.length > 0
      ? territoryCircles[0].centerLng
      : undefined;

  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <PageHeader
        title="Customer & Territory Locations Map"
        subtitle="Geographic distribution of customer sites and active territory coverage zones."
      />

      {error && (
        <ErrorBanner
          message={error}
          onRetry={loadMapData}
          onDismiss={() => setError(null)}
        />
      )}

      {isLoading ? (
        <Card>
          <div className="flex items-center justify-center h-64">
            <div className="w-10 h-10 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin" />
          </div>
        </Card>
      ) : customersWithLocation.length === 0 && territoryCircles.length === 0 ? (
        <EmptyState
          title="No Location Data"
          subtitle="No customers or territories have valid geographic coordinates. Add location data to see them on the map."
        />
      ) : (
        <Card>
          <FieldTrackMap
            centerLat={centerLat}
            centerLng={centerLng}
            zoom={10}
            markers={markers}
            territoryCircles={territoryCircles}
            height="520px"
            enableClustering={true}
            onMarkerClick={(marker) => {
              const customer = customersWithLocation.find(
                (c) => c.id === marker.id,
              );
              setSelectedCustomer(customer || null);
            }}
            onError={(msg) => setError(msg)}
          />
        </Card>
      )}

      {selectedCustomer && (
        <Card variant="flat" className="border border-surface-container-highest p-space-4">
          <h3 className="font-headline-sm text-base text-primary font-bold mb-space-1">
            {selectedCustomer.name}
          </h3>
          <p className="font-caption text-xs text-on-surface-variant">
            Coordinates: {selectedCustomer.location?.latitude.toFixed(6)}°,{' '}
            {selectedCustomer.location?.longitude.toFixed(6)}°
          </p>
          <p className="font-caption text-xs text-on-surface-variant">
            Geofence Radius: {selectedCustomer.geofence_radius_m}m
          </p>
          <p className="font-caption text-xs text-on-surface-variant">
            Address: {selectedCustomer.address}
          </p>
        </Card>
      )}

      <Card>
        <h3 className="font-headline-sm text-sm text-primary font-bold mb-space-2">
          Map Legend
        </h3>
        <div className="flex flex-wrap items-center gap-space-4 font-caption text-xs text-on-surface-variant">
          <div className="flex items-center gap-space-2">
            <div
              className="w-4 h-4 rounded-full border-2 border-white shadow"
              style={{ backgroundColor: MARKER_COLOR }}
            />
            <span>Customer Location</span>
          </div>
          <div className="flex items-center gap-space-2">
            <div
              className="w-5 h-5 rounded-full border-2 border-white shadow flex items-center justify-center text-[8px] font-bold text-white"
              style={{ backgroundColor: '#14213D' }}
            >
              N
            </div>
            <span>Cluster (tap to expand)</span>
          </div>
          <div className="flex items-center gap-space-2">
            <div className="w-4 h-4 rounded-full border-2 border-[#14213D] bg-[#14213D]/20 shadow" />
            <span>Territory Operational Coverage Zone</span>
          </div>
        </div>
      </Card>
    </div>
  );
};
