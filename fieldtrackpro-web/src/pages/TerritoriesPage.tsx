import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Map, Building2, Users, Plus, Target, MapPin, AlertCircle } from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Modal } from '../components/ui/Modal';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { FieldTrackMap, MapMarker, TerritoryCircle } from '../components/maps/FieldTrackMap';
import { apiClient } from '../api/client';
import { Customer, Employee, Territory } from '../types';

const CITY_PRESETS = [
  { name: 'Lucknow', lat: 26.8467, lng: 80.9462 },
  { name: 'New Delhi', lat: 28.6139, lng: 77.209 },
  { name: 'Mumbai', lat: 19.076, lng: 72.8777 },
  { name: 'Bengaluru', lat: 12.9716, lng: 77.5946 },
  { name: 'Kolkata', lat: 22.5726, lng: 88.3639 },
  { name: 'Hyderabad', lat: 17.385, lng: 78.4867 },
  { name: 'Ahmedabad', lat: 23.0225, lng: 72.5714 },
];

export const TerritoriesPage: React.FC = () => {
  const navigate = useNavigate();
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [name, setName] = useState('');
  const [centerLat, setCenterLat] = useState<string>('');
  const [centerLng, setCenterLng] = useState<string>('');
  const [radiusKm, setRadiusKm] = useState<string>('10');
  const [status, setStatus] = useState<'ACTIVE' | 'INACTIVE'>('ACTIVE');
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const load = useCallback(() => {
    setIsLoading(true);
    Promise.all([
      apiClient.getTerritories(),
      apiClient.getEmployees().catch(() => [] as Employee[]),
      apiClient.getCustomers().catch(() => [] as Customer[]),
    ])
      .then(([t, e, c]) => {
        setTerritories(t);
        setEmployees(e);
        setCustomers(c);
        setError(null);
      })
      .catch((err: Error) => {
        setTerritories([]);
        setError(err.message || 'Unable to load territories');
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const resetForm = () => {
    setName('');
    setCenterLat('');
    setCenterLng('');
    setRadiusKm('10');
    setStatus('ACTIVE');
    setFormError(null);
  };

  const handleOpenModal = () => {
    resetForm();
    setIsModalOpen(true);
  };

  const handlePresetSelect = (presetName: string) => {
    const preset = CITY_PRESETS.find((p) => p.name === presetName);
    if (preset) {
      setCenterLat(preset.lat.toString());
      setCenterLng(preset.lng.toString());
      if (!name) setName(`${preset.name} Territory`);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const trimmedName = name.trim();
    if (!trimmedName) {
      setFormError('Territory name is required.');
      return;
    }

    let latNum: number | null = null;
    let lngNum: number | null = null;
    let radNum: number | null = null;

    if (centerLat || centerLng || radiusKm) {
      if (!centerLat || !centerLng || !radiusKm) {
        setFormError(
          'Latitude, longitude, and radius must all be provided together.',
        );
        return;
      }

      latNum = parseFloat(centerLat);
      lngNum = parseFloat(centerLng);
      radNum = parseFloat(radiusKm);

      if (isNaN(latNum) || latNum < -90 || latNum > 90) {
        setFormError('Latitude must be a valid number between -90 and 90.');
        return;
      }

      if (isNaN(lngNum) || lngNum < -180 || lngNum > 180) {
        setFormError('Longitude must be a valid number between -180 and 180.');
        return;
      }

      if (isNaN(radNum) || radNum <= 0 || radNum > 500) {
        setFormError('Coverage radius must be greater than 0 km and at most 500 km.');
        return;
      }

      if (!Number.isInteger(radNum)) {
        setFormError('Coverage radius must be a whole number of km (e.g. 10, not 10.5).');
        return;
      }
    }

    setIsSaving(true);
    try {
      await apiClient.createTerritory({
        name: trimmedName,
        center_latitude: latNum,
        center_longitude: lngNum,
        radius_km: radNum,
        status,
      });
      setIsModalOpen(false);
      resetForm();
      load();
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : 'Failed to create territory',
      );
    } finally {
      setIsSaving(false);
    }
  };

  const countEmployees = (territoryId: string) =>
    employees.filter((e) => e.territory_id === territoryId).length;
  const countCustomers = (territoryId: string) =>
    customers.filter((c) => c.territory_id === territoryId).length;

  // Modal map preview parameters
  const previewLat = centerLat ? parseFloat(centerLat) : undefined;
  const previewLng = centerLng ? parseFloat(centerLng) : undefined;
  const previewRad = radiusKm ? parseFloat(radiusKm) : undefined;

  const modalMarkers: MapMarker[] =
    previewLat && previewLng && !isNaN(previewLat) && !isNaN(previewLng)
      ? [
          {
            id: 'modal-center-pin',
            latitude: previewLat,
            longitude: previewLng,
            label: name || 'Territory Center',
            color: '#14213D',
          },
        ]
      : [];

  const modalCircles: TerritoryCircle[] =
    previewLat &&
    previewLng &&
    previewRad &&
    !isNaN(previewLat) &&
    !isNaN(previewLng) &&
    !isNaN(previewRad) &&
    previewRad > 0
      ? [
          {
            id: 'modal-circle-preview',
            centerLat: previewLat,
            centerLng: previewLng,
            radiusKm: previewRad,
            name: name || 'Coverage Zone',
            color: '#14213D',
          },
        ]
      : [];

  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <PageHeader
        title="Territory Management"
        subtitle="Configure geographic operational coverage zones and territory assignments."
        actions={
          <Button
            variant="secondary"
            size="sm"
            icon={Plus}
            onClick={handleOpenModal}
          >
            New Territory
          </Button>
        }
      />

      {error && (
        <ErrorBanner
          message={error}
          onRetry={load}
          onDismiss={() => setError(null)}
        />
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-space-6">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={i} variant="flat" className="animate-pulse">
              <div className="h-4 bg-surface-container-high rounded w-1/3 mb-space-4" />
              <div className="h-5 bg-surface-container-high rounded w-2/3 mb-space-2" />
              <div className="h-3 bg-surface-container-high rounded w-1/2" />
            </Card>
          ))}
        </div>
      ) : territories.length === 0 && !error ? (
        <EmptyState
          icon={Map}
          title="No territories yet"
          subtitle="Create your first geographic territory to define operational boundaries for reps and accounts."
          action={
            <Button
              variant="secondary"
              size="sm"
              icon={Plus}
              onClick={handleOpenModal}
            >
              New Territory
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-space-6">
          {territories.map((territory) => {
            const hasGeo =
              territory.center_latitude != null &&
              territory.center_longitude != null &&
              territory.radius_km != null;
            const isActive = territory.status !== 'INACTIVE';

            return (
              <Card
                key={territory.id}
                variant="hover"
                className="flex flex-col justify-between cursor-pointer border border-surface-container-highest hover:border-primary/40 transition-colors"
                onClick={() => navigate(`/territories/${territory.id}`)}
              >
                <div>
                  <div className="flex items-center justify-between mb-space-3">
                    <span
                      className={`font-label-md text-xs font-semibold px-2.5 py-0.5 rounded-full flex items-center gap-1 ${
                        isActive
                          ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                          : 'bg-gray-100 text-gray-700 border border-gray-300'
                      }`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${
                          isActive ? 'bg-emerald-500' : 'bg-gray-400'
                        }`}
                      />
                      {isActive ? 'Active' : 'Inactive'}
                    </span>
                    <Map className="w-5 h-5 text-primary" />
                  </div>

                  <h3 className="font-headline-sm text-base font-bold text-primary mb-space-2">
                    {territory.name}
                  </h3>

                  <div className="space-y-space-2 mb-space-4">
                    <div className="flex items-center gap-space-2 text-xs">
                      <Target className="w-3.5 h-3.5 text-secondary shrink-0" />
                      <span className="font-medium text-on-surface">
                        {hasGeo
                          ? `${Math.round(territory.radius_km!)} km Coverage Radius`
                          : 'Coverage Not Configured'}
                      </span>
                    </div>

                    {hasGeo && (
                      <div className="flex items-center gap-space-2 text-xs text-on-surface-variant">
                        <MapPin className="w-3.5 h-3.5 text-outline shrink-0" />
                        <span>
                          {territory.center_latitude?.toFixed(4)}°,{' '}
                          {territory.center_longitude?.toFixed(4)}°
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-space-4 border-t border-surface-container-highest pt-space-3 font-body-md text-xs">
                  <div className="flex items-center gap-space-2 text-on-surface">
                    <Users className="w-4 h-4 text-outline shrink-0" />
                    <span>
                      {countEmployees(territory.id)} Representative
                      {countEmployees(territory.id) === 1 ? '' : 's'}
                    </span>
                  </div>
                  <div className="flex items-center gap-space-2 text-on-surface">
                    <Building2 className="w-4 h-4 text-outline shrink-0" />
                    <span>
                      {countCustomers(territory.id)} Account
                      {countCustomers(territory.id) === 1 ? '' : 's'}
                    </span>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Create Territory Modal with Map Location Picker */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Create Geographic Territory"
        subtitle="Define an operational center and coverage radius for field sales representatives."
      >
        {formError && (
          <div className="mb-space-4 font-body-md text-xs text-on-error-container bg-error-container p-space-3 rounded-lg border border-error flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-error shrink-0" />
            <span>{formError}</span>
          </div>
        )}

        <form onSubmit={handleCreate} className="space-y-space-4">
          <Input
            label="Territory Name"
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Lucknow Sales Zone"
          />

          <div>
            <label className="block text-xs font-semibold text-on-surface mb-1">
              Quick Select Center Location
            </label>
            <div className="flex flex-wrap gap-1.5 mb-3">
              {CITY_PRESETS.map((preset) => (
                <button
                  key={preset.name}
                  type="button"
                  onClick={() => handlePresetSelect(preset.name)}
                  className="text-xs px-2.5 py-1 rounded border border-surface-container-highest bg-surface-container-low hover:bg-primary-container hover:text-primary transition-colors"
                >
                  {preset.name}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-space-3">
            <Input
              label="Center Latitude"
              type="number"
              step="any"
              value={centerLat}
              onChange={(e) => setCenterLat(e.target.value)}
              placeholder="e.g. 26.8467"
            />
            <Input
              label="Center Longitude"
              type="number"
              step="any"
              value={centerLng}
              onChange={(e) => setCenterLng(e.target.value)}
              placeholder="e.g. 80.9462"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-on-surface mb-1">
              Coverage Radius (km)
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min="1"
                max="100"
                value={radiusKm || '10'}
                onChange={(e) => setRadiusKm(e.target.value)}
                className="w-full accent-secondary"
              />
              <input
                type="number"
                min="1"
                max="500"
                step="1"
                value={radiusKm}
                onChange={(e) => setRadiusKm(e.target.value)}
                className="w-20 px-2 py-1 border border-surface-container-highest rounded text-sm text-center"
              />
              <span className="text-xs text-on-surface-variant font-medium">km</span>
            </div>
            <div className="flex gap-1.5 mt-2">
              {[5, 10, 15, 25, 50].map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRadiusKm(r.toString())}
                  className={`text-xs px-2 py-0.5 rounded border ${
                    radiusKm === r.toString()
                      ? 'bg-secondary text-on-secondary border-secondary font-bold'
                      : 'bg-surface-container-low border-surface-container-highest'
                  }`}
                >
                  {r} km
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-on-surface mb-1">
              Location Picker & Live Preview (Click map to position center pin)
            </label>
            <div className="border border-surface-container-highest rounded-lg overflow-hidden">
              <FieldTrackMap
                centerLat={previewLat || 26.8467}
                centerLng={previewLng || 80.9462}
                zoom={10}
                markers={modalMarkers}
                territoryCircles={modalCircles}
                height="220px"
                onMapClick={(lat, lng) => {
                  setCenterLat(lat.toFixed(6));
                  setCenterLng(lng.toFixed(6));
                }}
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-on-surface mb-1">
              Status
            </label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as 'ACTIVE' | 'INACTIVE')}
              className="w-full px-3 py-2 border border-surface-container-highest rounded-lg text-sm bg-surface"
            >
              <option value="ACTIVE">ACTIVE</option>
              <option value="INACTIVE">INACTIVE</option>
            </select>
          </div>

          <div className="pt-space-4 flex justify-end gap-space-3 border-t border-surface-container-highest mt-space-6">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setIsModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="secondary"
              size="sm"
              isLoading={isSaving}
            >
              Save Territory
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
