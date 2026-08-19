import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  MapPin,
  Building2,
  Navigation,
  UserCheck,
  Phone,
  User,
  Shield,
  Layers,
  Search,
  RotateCcw,
  ExternalLink,
  Info,
  Compass,
  Crosshair,
  Radio,
} from 'lucide-react';
import { Card } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { FieldTrackMap, MapMarker, TerritoryCircle, CurrentUserLocation } from '../components/maps/FieldTrackMap';
import { apiClient } from '../api/client';
import { Customer, Territory, Area, Employee } from '../types';

const MARKER_COLOR = '#ffa515';

export const MapPage: React.FC = () => {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Live GPS Telemetry state
  const [currentLocation, setCurrentLocation] = useState<CurrentUserLocation | null>(null);
  const [gpsStatus, setGpsStatus] = useState<'idle' | 'locating' | 'active' | 'denied' | 'unavailable'>('locating');
  const [gpsError, setGpsError] = useState<string | null>(null);

  // Selection & filter state
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedZoneId, setSelectedZoneId] = useState<string>('ALL');
  const [selectedAreaId, setSelectedAreaId] = useState<string>('ALL');
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<string>('ALL');

  useEffect(() => {
    loadMapData();
  }, []);

  // Continuous real-time GPS tracking
  useEffect(() => {
    if (!navigator.geolocation) {
      setGpsStatus('unavailable');
      setGpsError('Geolocation is not supported by your browser');
      return;
    }

    setGpsStatus('locating');

    const updatePosition = (position: GeolocationPosition) => {
      const { latitude, longitude, accuracy } = position.coords;
      setCurrentLocation({
        latitude,
        longitude,
        accuracy,
        label: 'Your Current Location',
      });
      setGpsStatus('active');
      setGpsError(null);
    };

    const handleGpsError = (err: GeolocationPositionError) => {
      if (err.code === err.PERMISSION_DENIED) {
        setGpsStatus('denied');
        setGpsError('Location access was denied in browser permissions');
      } else {
        setGpsStatus('unavailable');
        setGpsError(err.message || 'Unable to retrieve current location');
      }
    };

    // Quick initial reading
    navigator.geolocation.getCurrentPosition(updatePosition, handleGpsError, {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 10000,
    });

    // Real-time position watcher
    const watchId = navigator.geolocation.watchPosition(updatePosition, handleGpsError, {
      enableHighAccuracy: true,
      timeout: 15000,
      maximumAge: 5000,
    });

    return () => {
      navigator.geolocation.clearWatch(watchId);
    };
  }, []);

  const loadMapData = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const [custData, terrData, areaData, empData] = await Promise.all([
        apiClient.getCustomers({ limit: 200 }).catch(() => [] as Customer[]),
        apiClient.getTerritories().catch(() => [] as Territory[]),
        apiClient.getAreas().catch(() => [] as Area[]),
        apiClient.getEmployees().catch(() => [] as Employee[]),
      ]);
      setCustomers(Array.isArray(custData) ? custData : []);
      setTerritories(Array.isArray(terrData) ? terrData : []);
      setAreas(Array.isArray(areaData) ? areaData : []);
      setEmployees(Array.isArray(empData) ? empData : []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load map data');
      setCustomers([]);
      setTerritories([]);
      setAreas([]);
      setEmployees([]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleLocateMe = useCallback(() => {
    if (!navigator.geolocation) {
      setError('Geolocation is not supported by your browser');
      return;
    }
    setGpsStatus('locating');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude, accuracy } = pos.coords;
        setCurrentLocation({
          latitude,
          longitude,
          accuracy,
          label: 'Your Current Location',
        });
        setGpsStatus('active');
        setGpsError(null);
      },
      (err) => {
        setGpsStatus(err.code === err.PERMISSION_DENIED ? 'denied' : 'unavailable');
        setGpsError(err.message);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    );
  }, []);

  // Valid customers with coordinates
  const customersWithLocation = useMemo(() => {
    return (Array.isArray(customers) ? customers : []).filter(
      (c) =>
        c &&
        c.location &&
        typeof c.location.latitude === 'number' &&
        typeof c.location.longitude === 'number' &&
        !isNaN(c.location.latitude) &&
        !isNaN(c.location.longitude) &&
        !(c.location.latitude === 0 && c.location.longitude === 0) &&
        c.location.latitude >= -90 &&
        c.location.latitude <= 90 &&
        c.location.longitude >= -180 &&
        c.location.longitude <= 180,
    );
  }, [customers]);

  // Filtered customers based on search and dropdown filters
  const filteredCustomers = useMemo(() => {
    return customersWithLocation.filter((c) => {
      // Search query filter (name, address, contact person, outlet code)
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesName = c.name?.toLowerCase().includes(q);
        const matchesAddress = c.address?.toLowerCase().includes(q);
        const matchesCode = c.outlet_code?.toLowerCase().includes(q);
        const matchesContact = c.contact_person?.toLowerCase().includes(q);
        if (!matchesName && !matchesAddress && !matchesCode && !matchesContact) {
          return false;
        }
      }

      // Zone filter
      if (selectedZoneId !== 'ALL' && c.territory_id !== selectedZoneId) {
        return false;
      }

      // Area filter
      if (selectedAreaId !== 'ALL' && c.area_id !== selectedAreaId) {
        return false;
      }

      // Employee filter (matches employee assigned to the customer's territory)
      if (selectedEmployeeId !== 'ALL') {
        const emp = employees.find((e) => e.id === selectedEmployeeId);
        if (!emp || emp.territory_id !== c.territory_id) {
          return false;
        }
      }

      return true;
    });
  }, [
    customersWithLocation,
    searchQuery,
    selectedZoneId,
    selectedAreaId,
    selectedEmployeeId,
    employees,
  ]);

  // Territory circles for coverage visualization
  const territoryCircles: TerritoryCircle[] = useMemo(() => {
    return (Array.isArray(territories) ? territories : [])
      .filter(
        (t) =>
          t.status !== 'INACTIVE' &&
          t.center_latitude != null &&
          t.center_longitude != null &&
          !isNaN(t.center_latitude) &&
          !isNaN(t.center_longitude) &&
          !(t.center_latitude === 0 && t.center_longitude === 0) &&
          t.radius_km != null &&
          t.radius_km > 0 &&
          (selectedZoneId === 'ALL' || t.id === selectedZoneId),
      )
      .map((t) => ({
        id: t.id,
        centerLat: t.center_latitude!,
        centerLng: t.center_longitude!,
        radiusKm: t.radius_km!,
        name: `${t.name} Zone Coverage`,
        color: '#14213D',
      }));
  }, [territories, selectedZoneId]);

  // Map markers from filtered customers with enriched metadata
  const markers: MapMarker[] = useMemo(() => {
    return filteredCustomers.map((c) => ({
      id: c.id,
      latitude: c.location!.latitude,
      longitude: c.location!.longitude,
      label: c.name,
      outletCode: c.outlet_code || undefined,
      address: c.address || undefined,
      color: MARKER_COLOR,
    }));
  }, [filteredCustomers]);

  // Helper mappings for business context
  const getZoneName = (territoryId: string | null | undefined): string => {
    if (!territoryId) return 'Unassigned';
    const t = territories.find((terr) => terr.id === territoryId);
    return t ? t.name : 'Unknown Zone';
  };

  const getAreaName = (customer: Customer): string => {
    if (customer.area_name) return customer.area_name;
    if (customer.area_id) {
      const a = areas.find((ar) => ar.id === customer.area_id);
      if (a) return a.name;
    }
    return 'Unassigned';
  };

  const getAssignedEmployee = (customer: Customer): Employee | undefined => {
    if (!customer.territory_id) return undefined;
    return employees.find((e) => e.territory_id === customer.territory_id);
  };

  const handleClearSelection = useCallback(() => {
    setSelectedCustomer(null);
  }, []);

  const handleResetFilters = useCallback(() => {
    setSearchQuery('');
    setSelectedZoneId('ALL');
    setSelectedAreaId('ALL');
    setSelectedEmployeeId('ALL');
    setSelectedCustomer(null);
  }, []);

  // Auto-clear selection when the selected outlet is no longer in the filtered dataset
  useEffect(() => {
    if (selectedCustomer && !filteredCustomers.some((c) => c.id === selectedCustomer.id)) {
      setSelectedCustomer(null);
    }
  }, [filteredCustomers, selectedCustomer]);

  const handleMapError = useCallback((msg: string) => setError(msg), []);

  const handleMarkerClick = useCallback(
    (marker: MapMarker) => {
      const customer = customersWithLocation.find((c) => c.id === marker.id);
      setSelectedCustomer(customer || null);
    },
    [customersWithLocation],
  );

  // Whether any filter is currently active
  const isFiltered =
    !!searchQuery || selectedZoneId !== 'ALL' || selectedAreaId !== 'ALL' || selectedEmployeeId !== 'ALL';

  // Filtered areas dropdown options based on selected Zone
  const availableAreas = useMemo(() => {
    if (selectedZoneId === 'ALL') return areas;
    return areas.filter((a) => a.territory_id === selectedZoneId);
  }, [areas, selectedZoneId]);

  const selectedOutletZone = selectedCustomer ? getZoneName(selectedCustomer.territory_id) : '';
  const selectedOutletArea = selectedCustomer ? getAreaName(selectedCustomer) : '';
  const selectedOutletEmployee = selectedCustomer ? getAssignedEmployee(selectedCustomer) : undefined;

  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <PageHeader
        title="Customer & Territory Locations Map"
        subtitle="Interactive geographic telemetry of outlet sites, active operational coverage zones, and assigned field representatives."
      />

      {error && (
        <ErrorBanner
          message={error}
          onRetry={loadMapData}
          onDismiss={() => setError(null)}
        />
      )}

      {/* Operation Metrics & GPS Telemetry Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-space-4">
        <Card variant="flat" className="p-space-3 bg-surface-container-low border border-surface-container-highest">
          <div className="flex items-center gap-space-2 text-on-surface-variant">
            <Building2 className="w-4 h-4 text-primary" />
            <span className="font-caption text-xs font-semibold uppercase tracking-wider">Total Outlets</span>
          </div>
          <p className="font-headline-md text-xl font-bold text-primary mt-1">
            {customersWithLocation.length}
          </p>
        </Card>

        <Card variant="flat" className="p-space-3 bg-surface-container-low border border-surface-container-highest">
          <div className="flex items-center gap-space-2 text-on-surface-variant">
            <Shield className="w-4 h-4 text-secondary-container" />
            <span className="font-caption text-xs font-semibold uppercase tracking-wider">Active Zones</span>
          </div>
          <p className="font-headline-md text-xl font-bold text-primary mt-1">
            {territories.filter((t) => t.status !== 'INACTIVE').length}
          </p>
        </Card>

        <Card variant="flat" className="p-space-3 bg-surface-container-low border border-surface-container-highest">
          <div className="flex items-center gap-space-2 text-on-surface-variant">
            <Layers className="w-4 h-4 text-tertiary" />
            <span className="font-caption text-xs font-semibold uppercase tracking-wider">Covered Areas</span>
          </div>
          <p className="font-headline-md text-xl font-bold text-primary mt-1">
            {areas.length}
          </p>
        </Card>

        {/* GPS Live Telemetry Card */}
        <Card variant="flat" className="p-space-3 bg-surface-container-low border border-surface-container-highest">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-space-2 text-on-surface-variant">
              <Radio className={`w-4 h-4 ${gpsStatus === 'active' ? 'text-sky-500 animate-pulse' : 'text-outline'}`} />
              <span className="font-caption text-xs font-semibold uppercase tracking-wider">Live GPS</span>
            </div>
            {gpsStatus === 'active' && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-sky-100 text-sky-800">
                Online
              </span>
            )}
          </div>
          <p
            className="font-headline-md text-sm font-bold text-on-surface mt-1 truncate"
            title={gpsError || (currentLocation ? `Accuracy: ±${Math.round(currentLocation.accuracy || 0)}m` : 'GPS Position')}
          >
            {gpsStatus === 'active' && currentLocation
              ? `${currentLocation.latitude.toFixed(4)}°, ${currentLocation.longitude.toFixed(4)}°`
              : gpsStatus === 'locating'
              ? 'Acquiring GPS...'
              : gpsStatus === 'denied'
              ? 'Location Denied'
              : gpsError || 'GPS Inactive'}
          </p>
        </Card>
      </div>

      {/* Map Control & Filter Toolbar */}
      <Card className="p-space-4">
        <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-space-4">
          {/* Search Input */}
          <div className="relative flex-1 min-w-[240px]">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search outlet by name, address, or code..."
              className="w-full pl-9 pr-3 py-2 text-sm bg-surface border border-outline-variant rounded-lg focus:outline-none focus:ring-2 focus:ring-secondary-container"
            />
          </div>

          {/* Filter Dropdowns & Actions */}
          <div className="flex flex-wrap items-center gap-space-3">
            {/* Zone Filter */}
            <select
              value={selectedZoneId}
              onChange={(e) => {
                setSelectedZoneId(e.target.value);
                setSelectedAreaId('ALL'); // Reset area when zone changes
              }}
              className="py-2 px-3 text-sm bg-surface border border-outline-variant rounded-lg text-on-surface focus:outline-none focus:ring-2 focus:ring-secondary-container"
              aria-label="Filter by Zone"
            >
              <option value="ALL">All Zones ({territories.length})</option>
              {territories.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>

            {/* Area Filter */}
            <select
              value={selectedAreaId}
              onChange={(e) => setSelectedAreaId(e.target.value)}
              className="py-2 px-3 text-sm bg-surface border border-outline-variant rounded-lg text-on-surface focus:outline-none focus:ring-2 focus:ring-secondary-container"
              aria-label="Filter by Area"
            >
              <option value="ALL">All Areas ({availableAreas.length})</option>
              {availableAreas.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>

            {/* Field Rep Filter */}
            <select
              value={selectedEmployeeId}
              onChange={(e) => setSelectedEmployeeId(e.target.value)}
              className="py-2 px-3 text-sm bg-surface border border-outline-variant rounded-lg text-on-surface focus:outline-none focus:ring-2 focus:ring-secondary-container"
              aria-label="Filter by Field Representative"
            >
              <option value="ALL">All Field Reps ({employees.length})</option>
              {employees.map((emp) => (
                <option key={emp.id} value={emp.id}>
                  {emp.full_name} {emp.employee_code ? `(${emp.employee_code})` : ''}
                </option>
              ))}
            </select>

            {/* Locate Me Button */}
            <Button
              variant="outline"
              size="sm"
              onClick={handleLocateMe}
              className="flex items-center gap-space-1.5 text-sky-700 border-sky-300 hover:bg-sky-50"
              title="Refresh / Locate My GPS Position"
            >
              <Crosshair className="w-3.5 h-3.5 text-sky-600" />
              <span>Locate Me</span>
            </Button>

            {/* Reset Filters / View */}
            {(searchQuery || selectedZoneId !== 'ALL' || selectedAreaId !== 'ALL' || selectedEmployeeId !== 'ALL') && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleResetFilters}
                className="flex items-center gap-space-1.5"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reset Filters
              </Button>
            )}
          </div>
        </div>
      </Card>

      {/* Main Map Card */}
      {isLoading ? (
        <Card>
          <div className="flex items-center justify-center h-96">
            <div className="text-center">
              <div className="w-10 h-10 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin mx-auto mb-space-2.5" />
              <p className="font-caption text-xs text-on-surface-variant">
                Loading telemetry and outlet map...
              </p>
            </div>
          </div>
        </Card>
      ) : customersWithLocation.length === 0 && territoryCircles.length === 0 && !currentLocation ? (
        <EmptyState
          title="No Location Data"
          subtitle="No customers or territories have valid geographic coordinates. Add location data to see them on the map."
        />
      ) : (
        <Card className="overflow-hidden p-0 border border-surface-container-highest relative">
          {/* Zero-result overlay — shown inside the map card so tiles remain visible */}
          {isFiltered && filteredCustomers.length === 0 && (
            <div
              style={{ position: 'absolute', top: 0, left: 0, right: 0, zIndex: 20 }}
              className="flex items-center justify-center p-space-3 pointer-events-none"
            >
              <div className="bg-surface/95 backdrop-blur-sm border border-outline-variant rounded-lg px-space-5 py-space-3 flex items-center gap-space-3 shadow-md pointer-events-auto">
                <Info className="w-4 h-4 text-on-surface-variant shrink-0" />
                <div>
                  <p className="font-body-md text-sm text-on-surface font-semibold">
                    No outlets match the selected filters.
                  </p>
                  <button
                    onClick={handleResetFilters}
                    className="font-caption text-xs text-secondary-container underline mt-0.5 cursor-pointer"
                  >
                    Reset Filters to restore all outlets
                  </button>
                </div>
              </div>
            </div>
          )}
          <FieldTrackMap
            markers={markers}
            territoryCircles={territoryCircles}
            selectedMarkerId={selectedCustomer?.id || null}
            currentLocation={currentLocation}
            autoFitBounds={true}
            height="520px"
            enableClustering={true}
            onMarkerClick={handleMarkerClick}
            onError={handleMapError}
          />
        </Card>
      )}

      {/* Lower Panel: Selected Outlet Details OR Helpful Guide State */}
      {selectedCustomer ? (
        <Card
          variant="flat"
          className="border-2 border-secondary-container/60 bg-surface-container-lowest shadow-md p-space-6 animate-in fade-in-50 duration-200"
          aria-label="Selected Outlet Details"
        >
          {/* Header Row */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-space-4 pb-space-4 border-b border-surface-container-high">
            <div>
              <div className="flex items-center gap-space-2 mb-space-1">
                <span className="px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider bg-secondary-container text-primary">
                  Selected Outlet
                </span>
                {selectedCustomer.outlet_code && (
                  <span className="px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-surface-container-high text-on-surface-variant">
                    Code: {selectedCustomer.outlet_code}
                  </span>
                )}
              </div>
              <h2 className="font-headline-lg text-xl text-primary font-bold">
                {selectedCustomer.name}
              </h2>
            </div>

            <div className="flex flex-wrap items-center gap-space-3">
              {/* Google Maps External Navigation */}
              {selectedCustomer.location && (
                <a
                  href={`https://www.google.com/maps/dir/?api=1&destination=${selectedCustomer.location.latitude},${selectedCustomer.location.longitude}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Button
                    variant="secondary"
                    size="sm"
                    className="flex items-center gap-space-1.5 font-semibold"
                    title="Open turn-by-turn directions in Google Maps"
                  >
                    <Navigation className="w-3.5 h-3.5 text-primary" />
                    <span>Navigate (Google Maps)</span>
                    <ExternalLink className="w-3 h-3 ml-0.5 opacity-75" />
                  </Button>
                </a>
              )}

              <Link to={`/customers/${selectedCustomer.id}`}>
                <Button variant="primary" size="sm" className="flex items-center gap-space-1.5">
                  <span>View Full Profile</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </Button>
              </Link>

              <Button
                variant="outline"
                size="sm"
                onClick={handleClearSelection}
                className="flex items-center gap-space-1.5"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Clear Selection
              </Button>
            </div>
          </div>

          {/* Details Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-space-5 pt-space-4">
            {/* Address */}
            <div className="space-y-1">
              <div className="flex items-center gap-space-1.5 text-on-surface-variant font-caption text-xs font-semibold uppercase tracking-wider">
                <MapPin className="w-3.5 h-3.5 text-secondary-container" />
                <span>Physical Address</span>
              </div>
              <p className="font-body-md text-sm text-on-surface font-medium">
                {selectedCustomer.address || 'No physical address provided'}
              </p>
            </div>

            {/* Zone & Area Hierarchy */}
            <div className="space-y-1">
              <div className="flex items-center gap-space-1.5 text-on-surface-variant font-caption text-xs font-semibold uppercase tracking-wider">
                <Shield className="w-3.5 h-3.5 text-primary" />
                <span>Zone & Area Hierarchy</span>
              </div>
              <p className="font-body-md text-sm text-on-surface font-medium">
                <span className="font-bold text-primary">Zone:</span> {selectedOutletZone}
              </p>
              <p className="font-caption text-xs text-on-surface-variant">
                <span className="font-semibold">Area:</span> {selectedOutletArea}
              </p>
            </div>

            {/* Assigned Field Representative */}
            <div className="space-y-1">
              <div className="flex items-center gap-space-1.5 text-on-surface-variant font-caption text-xs font-semibold uppercase tracking-wider">
                <UserCheck className="w-3.5 h-3.5 text-success" />
                <span>Assigned Field Rep</span>
              </div>
              {selectedOutletEmployee ? (
                <div>
                  <p className="font-body-md text-sm text-on-surface font-medium">
                    {selectedOutletEmployee.full_name}
                  </p>
                  <p className="font-caption text-xs text-on-surface-variant">
                    Code: {selectedOutletEmployee.employee_code || 'N/A'}
                  </p>
                </div>
              ) : (
                <p className="font-body-md text-sm text-on-surface-variant italic">
                  No representative assigned
                </p>
              )}
            </div>

            {/* Geofence & Coordinates */}
            <div className="space-y-1">
              <div className="flex items-center gap-space-1.5 text-on-surface-variant font-caption text-xs font-semibold uppercase tracking-wider">
                <Compass className="w-3.5 h-3.5 text-tertiary" />
                <span>Geofence & Coordinates</span>
              </div>
              <p className="font-body-md text-sm text-on-surface font-medium">
                Geofence: <span className="font-bold text-secondary-container">{selectedCustomer.geofence_radius_m}m</span>
              </p>
              <p className="font-caption text-xs text-on-surface-variant font-mono">
                {selectedCustomer.location?.latitude.toFixed(6)}°, {selectedCustomer.location?.longitude.toFixed(6)}°
              </p>
            </div>
          </div>

          {/* Secondary Details Footer */}
          <div className="mt-space-4 pt-space-3 border-t border-surface-container-high flex flex-wrap items-center justify-between gap-space-3 font-caption text-xs text-on-surface-variant">
            <div className="flex items-center gap-space-4">
              {selectedCustomer.contact_person && (
                <div className="flex items-center gap-space-1">
                  <User className="w-3.5 h-3.5 text-outline" />
                  <span>Contact: <strong>{selectedCustomer.contact_person}</strong></span>
                </div>
              )}
              {selectedCustomer.contact_number && (
                <div className="flex items-center gap-space-1">
                  <Phone className="w-3.5 h-3.5 text-outline" />
                  <span>Phone: <strong>{selectedCustomer.contact_number}</strong></span>
                </div>
              )}
            </div>
            <div className="font-mono text-[11px] text-outline">
              Outlet ID: {selectedCustomer.id}
            </div>
          </div>
        </Card>
      ) : (
        <Card variant="flat" className="border border-surface-container-highest bg-surface-container-low p-space-5">
          <div className="flex items-center gap-space-3">
            <div className="w-9 h-9 rounded-full bg-secondary-container/20 text-secondary-container flex items-center justify-center shrink-0">
              <Info className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-headline-sm text-sm text-primary font-bold">
                Select an Outlet on the Map
              </h3>
              <p className="font-caption text-xs text-on-surface-variant mt-0.5">
                Click on any orange outlet marker or use the filters above to inspect physical address, zone coverage, assigned area hierarchy, and designated field representative details.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Map Legend */}
      <Card>
        <h3 className="font-headline-sm text-sm text-primary font-bold mb-space-2">
          Map Legend & Telemetry Indicators
        </h3>
        <div className="flex flex-wrap items-center gap-space-6 font-caption text-xs text-on-surface-variant">
          <div className="flex items-center gap-space-2">
            <div
              className="w-4 h-4 rounded-full border-2 border-white shadow"
              style={{ backgroundColor: MARKER_COLOR }}
            />
            <span>Customer Outlet Marker</span>
          </div>

          <div className="flex items-center gap-space-2">
            <div className="relative flex items-center justify-center w-4 h-4">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-sky-500 border border-white"></span>
            </div>
            <span className="font-medium text-sky-800">Your Current Location (Live GPS)</span>
          </div>

          <div className="flex items-center gap-space-2">
            <div className="w-5 h-5 rounded-full border-2 border-primary bg-secondary-container/40 ring-2 ring-secondary-container shadow" />
            <span>Selected Outlet (active inspection)</span>
          </div>

          <div className="flex items-center gap-space-2">
            <div className="w-4 h-4 rounded-full border-2 border-[#14213D] bg-[#14213D]/20 shadow" />
            <span>Operational Zone Coverage Area</span>
          </div>
        </div>
      </Card>
    </div>
  );
};
