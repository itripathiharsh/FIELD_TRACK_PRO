import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  MapPin,
  Users,
  Building2,
  Target,
  Edit,
  Trash2,
  Plus,
  X,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  AlertCircle,
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Modal } from '../components/ui/Modal';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { EmptyState } from '../components/ui/EmptyState';
import { FieldTrackMap, MapMarker, TerritoryCircle } from '../components/maps/FieldTrackMap';
import { apiClient } from '../api/client';
import { Territory, Employee, Customer } from '../types';

/**
 * Haversine formula to calculate distance in kilometers between two lat/lng points.
 */
function calculateDistanceKm(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const R = 6371; // Earth radius in km
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

export const TerritoryDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [territory, setTerritory] = useState<Territory | null>(null);
  const [assignedEmployees, setAssignedEmployees] = useState<Employee[]>([]);
  const [allEmployees, setAllEmployees] = useState<Employee[]>([]);
  const [assignedCustomers, setAssignedCustomers] = useState<Customer[]>([]);
  const [allCustomers, setAllCustomers] = useState<Customer[]>([]);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit Modal State
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [editName, setEditName] = useState('');
  const [editCenterLat, setEditCenterLat] = useState('');
  const [editCenterLng, setEditCenterLng] = useState('');
  const [editRadiusKm, setEditRadiusKm] = useState('10');
  const [editStatus, setEditStatus] = useState<'ACTIVE' | 'INACTIVE'>('ACTIVE');
  const [editFormError, setEditFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Assignment Modal States
  const [isAssignEmpModalOpen, setIsAssignEmpModalOpen] = useState(false);
  const [selectedEmpId, setSelectedEmpId] = useState('');
  const [isAssignCustModalOpen, setIsAssignCustModalOpen] = useState(false);
  const [selectedCustId, setSelectedCustId] = useState('');

  const load = useCallback(async () => {
    if (!id) return;
    try {
      setIsLoading(true);
      const terr = await apiClient.getTerritoryById(id);
      setTerritory(terr);

      const [emps, custs] = await Promise.all([
        apiClient.getEmployees().catch(() => [] as Employee[]),
        apiClient.getCustomers().catch(() => [] as Customer[]),
      ]);

      setAllEmployees(emps);
      setAssignedEmployees(emps.filter((e) => e.territory_id === id));

      setAllCustomers(custs);
      setAssignedCustomers(custs.filter((c) => c.territory_id === id));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load territory');
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const openEditModal = () => {
    if (!territory) return;
    setEditName(territory.name);
    setEditCenterLat(
      territory.center_latitude != null ? territory.center_latitude.toString() : '',
    );
    setEditCenterLng(
      territory.center_longitude != null ? territory.center_longitude.toString() : '',
    );
    setEditRadiusKm(
      territory.radius_km != null ? territory.radius_km.toString() : '10',
    );
    setEditStatus(territory.status || 'ACTIVE');
    setEditFormError(null);
    setIsEditModalOpen(true);
  };

  const handleUpdateTerritory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;
    setEditFormError(null);

    const nameVal = editName.trim();
    if (!nameVal) {
      setEditFormError('Territory name cannot be empty.');
      return;
    }

    let latNum: number | null = null;
    let lngNum: number | null = null;
    let radNum: number | null = null;

    if (editCenterLat || editCenterLng || editRadiusKm) {
      if (!editCenterLat || !editCenterLng || !editRadiusKm) {
        setEditFormError(
          'Latitude, longitude, and radius must all be provided together.',
        );
        return;
      }
      latNum = parseFloat(editCenterLat);
      lngNum = parseFloat(editCenterLng);
      radNum = parseFloat(editRadiusKm);

      if (isNaN(latNum) || latNum < -90 || latNum > 90) {
        setEditFormError('Latitude must be between -90 and 90.');
        return;
      }
      if (isNaN(lngNum) || lngNum < -180 || lngNum > 180) {
        setEditFormError('Longitude must be between -180 and 180.');
        return;
      }
      if (isNaN(radNum) || radNum <= 0 || radNum > 500) {
        setEditFormError('Radius must be greater than 0 km and at most 500 km.');
        return;
      }
      if (!Number.isInteger(radNum)) {
        setEditFormError('Coverage radius must be a whole number of km (e.g. 10, not 10.5).');
        return;
      }
    }

    setIsSaving(true);
    try {
      await apiClient.updateTerritory(id, {
        name: nameVal,
        center_latitude: latNum,
        center_longitude: lngNum,
        radius_km: radNum,
        status: editStatus,
      });
      setIsEditModalOpen(false);
      load();
    } catch (err) {
      setEditFormError(
        err instanceof Error ? err.message : 'Failed to update territory',
      );
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteTerritory = async () => {
    if (!id || !territory) return;
    if (
      !window.confirm(
        `Are you sure you want to delete territory "${territory.name}"?`,
      )
    ) {
      return;
    }
    try {
      await apiClient.deleteTerritory(id);
      navigate('/territories');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete territory');
    }
  };

  const handleAssignEmployee = async () => {
    if (!selectedEmpId || !id) return;
    try {
      // P2-D: goes through the history-safe reassignment endpoint (a
      // PERMANENT assignment effective today) instead of directly
      // overwriting Employee.territory_id - the same silent-overwrite this
      // page used to do, with zero audit trail. See EmployeeDetailPage's
      // Territory Assignment section for the full history.
      await apiClient.createTerritoryAssignment(selectedEmpId, {
        territory_id: id,
        assignment_type: 'PERMANENT',
        start_date: new Date().toISOString().slice(0, 10),
      });
      setIsAssignEmpModalOpen(false);
      setSelectedEmpId('');
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to assign representative');
    }
  };

  const handleUnassignEmployee = async (empId: string, name: string) => {
    if (!window.confirm(`Unassign ${name} from this territory?`)) return;
    try {
      // Note (P2-D): "no territory" has no equivalent in the reassignment
      // history model (every assignment names a target territory), so this
      // still writes the legacy column directly. If this employee already
      // has assignment history, their effective territory (as seen at
      // login and on the Activity page) is resolved from that history and
      // will NOT reflect this unassignment - reassign them to a different
      // territory instead if they have prior history.
      await apiClient.updateEmployee(empId, { territory_id: null });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to unassign representative');
    }
  };

  const handleAssignCustomer = async () => {
    if (!selectedCustId || !id) return;
    try {
      await apiClient.updateCustomer(selectedCustId, { territory_id: id });
      setIsAssignCustModalOpen(false);
      setSelectedCustId('');
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to assign customer');
    }
  };

  const handleUnassignCustomer = async (custId: string, name: string) => {
    if (!window.confirm(`Remove ${name} from this territory?`)) return;
    try {
      await apiClient.updateCustomer(custId, { territory_id: null });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove customer');
    }
  };

  if (isLoading)
    return (
      <div className="flex items-center justify-center h-64" role="status">
        <div className="w-10 h-10 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin" />
      </div>
    );
  if (error && !territory)
    return <ErrorBanner message={error} onRetry={load} />;
  if (!territory)
    return (
      <EmptyState
        title="Territory not found"
        subtitle="The requested territory could not be found."
      />
    );

  const hasGeo =
    territory.center_latitude != null &&
    territory.center_longitude != null &&
    territory.radius_km != null;
  const isActive = territory.status !== 'INACTIVE';

  // Build Map Markers & Circles for Territory Coverage
  const mapMarkers: MapMarker[] = [];
  const territoryCircles: TerritoryCircle[] = [];

  if (hasGeo) {
    // Territory Center Pin
    mapMarkers.push({
      id: `center-${territory.id}`,
      latitude: territory.center_latitude!,
      longitude: territory.center_longitude!,
      label: `Territory Center (${territory.name})`,
      color: '#14213D',
    });

    // Coverage Zone Circle
    territoryCircles.push({
      id: territory.id,
      centerLat: territory.center_latitude!,
      centerLng: territory.center_longitude!,
      radiusKm: territory.radius_km!,
      name: `${territory.name} Coverage`,
      color: '#14213D',
    });
  }

  // Add assigned customer markers
  assignedCustomers.forEach((cust) => {
    if (
      cust.location &&
      cust.location.latitude &&
      cust.location.longitude &&
      !(cust.location.latitude === 0 && cust.location.longitude === 0)
    ) {
      mapMarkers.push({
        id: cust.id,
        latitude: cust.location.latitude,
        longitude: cust.location.longitude,
        label: cust.name,
        color: '#fca311',
      });
    }
  });

  const unassignedEmployees = allEmployees.filter(
    (e) => e.territory_id !== territory.id,
  );
  const unassignedCustomers = allCustomers.filter(
    (c) => c.territory_id !== territory.id,
  );

  // Modal map preview values
  const editLatNum = editCenterLat ? parseFloat(editCenterLat) : undefined;
  const editLngNum = editCenterLng ? parseFloat(editCenterLng) : undefined;
  const editRadNum = editRadiusKm ? parseFloat(editRadiusKm) : undefined;

  const modalMarkers: MapMarker[] =
    editLatNum && editLngNum && !isNaN(editLatNum) && !isNaN(editLngNum)
      ? [
          {
            id: 'edit-modal-center-pin',
            latitude: editLatNum,
            longitude: editLngNum,
            label: editName || 'Center Pin',
            color: '#14213D',
          },
        ]
      : [];

  const modalCircles: TerritoryCircle[] =
    editLatNum &&
    editLngNum &&
    editRadNum &&
    !isNaN(editLatNum) &&
    !isNaN(editLngNum) &&
    !isNaN(editRadNum) &&
    editRadNum > 0
      ? [
          {
            id: 'edit-modal-circle-preview',
            centerLat: editLatNum,
            centerLng: editLngNum,
            radiusKm: editRadNum,
            name: editName || 'Coverage Zone',
            color: '#14213D',
          },
        ]
      : [];

  return (
    <div className="space-y-space-6 font-body-md text-on-surface">
      <PageHeader
        title={territory.name}
        subtitle="Geographic operational boundary zone details, representative rosters, and account eligibility."
        actions={
          <div className="flex items-center gap-space-3">
            <Button
              variant="outline"
              size="sm"
              icon={ArrowLeft}
              onClick={() => navigate('/territories')}
            >
              Back
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon={Edit}
              onClick={openEditModal}
            >
              Edit Territory
            </Button>
            <Button
              variant="ghost"
              size="sm"
              icon={Trash2}
              className="text-error hover:bg-error-container/30"
              onClick={handleDeleteTerritory}
            >
              Delete
            </Button>
          </div>
        }
      />

      {error && (
        <ErrorBanner
          message={error}
          onRetry={load}
          onDismiss={() => setError(null)}
        />
      )}

      {/* Territory Details Header Card */}
      <Card variant="flat" className="p-space-6 border border-surface-container-highest">
        <div className="flex flex-wrap items-center justify-between gap-space-4 border-b border-surface-container-highest pb-space-4 mb-space-4">
          <div className="flex items-center gap-space-3">
            <h2 className="font-headline-md text-xl font-bold text-primary">
              {territory.name}
            </h2>
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
          </div>

          <div className="flex items-center gap-space-4 text-xs text-on-surface-variant">
            <span>Created: {new Date(territory.created_at).toLocaleDateString()}</span>
            {territory.updated_at && (
              <span>Updated: {new Date(territory.updated_at).toLocaleDateString()}</span>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-space-4">
          <div className="p-space-3 bg-surface-container-low rounded-lg border border-surface-container-highest">
            <div className="flex items-center gap-2 text-xs text-on-surface-variant font-medium mb-1">
              <Target className="w-4 h-4 text-secondary shrink-0" />
              <span>Coverage Radius</span>
            </div>
            <p className="font-headline-sm text-base font-bold text-primary">
              {hasGeo ? `${Math.round(territory.radius_km!)} km` : 'Not Configured'}
            </p>
          </div>

          <div className="p-space-3 bg-surface-container-low rounded-lg border border-surface-container-highest">
            <div className="flex items-center gap-2 text-xs text-on-surface-variant font-medium mb-1">
              <MapPin className="w-4 h-4 text-primary shrink-0" />
              <span>Geographic Center</span>
            </div>
            <p className="font-headline-sm text-base font-bold text-primary">
              {hasGeo
                ? `${territory.center_latitude?.toFixed(4)}°, ${territory.center_longitude?.toFixed(4)}°`
                : 'Not Configured'}
            </p>
          </div>

          <div className="p-space-3 bg-surface-container-low rounded-lg border border-surface-container-highest">
            <div className="flex items-center gap-2 text-xs text-on-surface-variant font-medium mb-1">
              <Users className="w-4 h-4 text-outline shrink-0" />
              <span>Field Representatives</span>
            </div>
            <p className="font-headline-sm text-base font-bold text-primary">
              {assignedEmployees.length}
            </p>
          </div>

          <div className="p-space-3 bg-surface-container-low rounded-lg border border-surface-container-highest">
            <div className="flex items-center gap-2 text-xs text-on-surface-variant font-medium mb-1">
              <Building2 className="w-4 h-4 text-outline shrink-0" />
              <span>Customer Accounts</span>
            </div>
            <p className="font-headline-sm text-base font-bold text-primary">
              {assignedCustomers.length}
            </p>
          </div>
        </div>
      </Card>

      {/* Map & Geographic Coverage Section */}
      <Card>
        <CardHeader>
          <CardTitle>Territory Coverage & Operational Boundaries</CardTitle>
          <CardSubtitle>
            Geofenced operational zone map displaying territory radius, center location, and customer accounts.
          </CardSubtitle>
        </CardHeader>

        <div className="p-space-5 pt-0">
          {hasGeo ? (
            <div className="border border-surface-container-highest rounded-lg overflow-hidden">
              <FieldTrackMap
                centerLat={territory.center_latitude!}
                centerLng={territory.center_longitude!}
                zoom={10}
                markers={mapMarkers}
                territoryCircles={territoryCircles}
                height="420px"
                enableClustering={true}
              />
            </div>
          ) : (
            <div className="p-space-8 text-center bg-surface-container-low rounded-lg border border-dashed border-surface-container-highest">
              <MapPin className="w-12 h-12 text-outline mx-auto mb-space-3 opacity-60" />
              <h4 className="font-headline-sm text-base font-bold text-primary mb-1">
                Territory Location Not Configured
              </h4>
              <p className="font-caption text-xs text-on-surface-variant max-w-md mx-auto mb-space-4">
                Set a center coordinate and coverage radius for this territory to enable map visualization, distance verification, and account geofencing.
              </p>
              <Button
                variant="secondary"
                size="sm"
                icon={Edit}
                onClick={openEditModal}
              >
                Configure Location & Radius
              </Button>
            </div>
          )}
        </div>
      </Card>

      {/* Field Representatives Section */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Assigned Field Representatives</CardTitle>
            <CardSubtitle>
              Field sales agents operating within this territory
            </CardSubtitle>
          </div>
          <Button
            variant="outline"
            size="sm"
            icon={Plus}
            onClick={() => setIsAssignEmpModalOpen(true)}
          >
            Assign Representative
          </Button>
        </CardHeader>

        <div className="p-space-5 pt-0">
          {assignedEmployees.length === 0 ? (
            <p className="text-xs text-on-surface-variant italic bg-surface-container-low p-space-4 rounded-lg text-center border border-surface-container-highest">
              No field representatives currently assigned to this territory.
            </p>
          ) : (
            <div className="space-y-space-3">
              {assignedEmployees.map((emp) => (
                <div
                  key={emp.id}
                  className="flex items-center justify-between p-space-3 rounded-lg border border-surface-container-highest hover:bg-surface-container-low transition-colors"
                >
                  <div
                    className="cursor-pointer"
                    onClick={() => navigate(`/employees/${emp.id}`)}
                  >
                    <p className="text-sm font-semibold text-primary hover:underline">
                      {emp.full_name}
                    </p>
                    <p className="text-xs text-on-surface-variant">
                      Code: {emp.employee_code || 'N/A'} • {emp.user?.email || 'No Email'}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={X}
                    className="text-error hover:bg-error-container/30"
                    onClick={() => handleUnassignEmployee(emp.id, emp.full_name)}
                  >
                    Unassign
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </Card>

      {/* Customer Accounts Section with Coverage Status Badges */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Customer Accounts</CardTitle>
            <CardSubtitle>
              Accounts assigned to this territory with distance verification against territory center
            </CardSubtitle>
          </div>
          <Button
            variant="outline"
            size="sm"
            icon={Plus}
            onClick={() => setIsAssignCustModalOpen(true)}
          >
            Assign Account
          </Button>
        </CardHeader>

        <div className="p-space-5 pt-0">
          {assignedCustomers.length === 0 ? (
            <p className="text-xs text-on-surface-variant italic bg-surface-container-low p-space-4 rounded-lg text-center border border-surface-container-highest">
              No customer accounts currently assigned to this territory.
            </p>
          ) : (
            <div className="space-y-space-3">
              {assignedCustomers.map((cust) => {
                let distKm: number | null = null;
                let isInside = false;

                if (
                  hasGeo &&
                  cust.location &&
                  cust.location.latitude &&
                  cust.location.longitude &&
                  !(cust.location.latitude === 0 && cust.location.longitude === 0)
                ) {
                  distKm = calculateDistanceKm(
                    territory.center_latitude!,
                    territory.center_longitude!,
                    cust.location.latitude,
                    cust.location.longitude,
                  );
                  isInside = distKm <= territory.radius_km!;
                }

                return (
                  <div
                    key={cust.id}
                    className="flex flex-col sm:flex-row sm:items-center justify-between p-space-3.5 rounded-lg border border-surface-container-highest hover:bg-surface-container-low transition-colors gap-3"
                  >
                    <div
                      className="cursor-pointer"
                      onClick={() => navigate(`/customers/${cust.id}`)}
                    >
                      <p className="text-sm font-semibold text-primary hover:underline">
                        {cust.name}
                      </p>
                      <p className="text-xs text-on-surface-variant">
                        Phone: {cust.contact_number} • Address: {cust.address}
                      </p>
                    </div>

                    <div className="flex items-center gap-3 shrink-0">
                      {/* Radius Distance Badge */}
                      {!hasGeo ? (
                        <span className="text-xs px-2.5 py-1 rounded-full bg-gray-100 text-gray-600 border border-gray-300 flex items-center gap-1 font-medium">
                          <HelpCircle className="w-3.5 h-3.5" />
                          Location Pending
                        </span>
                      ) : distKm == null ? (
                        <span className="text-xs px-2.5 py-1 rounded-full bg-gray-100 text-gray-600 border border-gray-300 flex items-center gap-1 font-medium">
                          <HelpCircle className="w-3.5 h-3.5" />
                          No Account Lat/Lng
                        </span>
                      ) : isInside ? (
                        <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300 flex items-center gap-1 font-medium">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                          Inside Radius ({distKm.toFixed(1)} km)
                        </span>
                      ) : (
                        <span className="text-xs px-2.5 py-1 rounded-full bg-amber-100 text-amber-800 border border-amber-300 flex items-center gap-1 font-medium">
                          <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                          Outside Radius ({distKm.toFixed(1)} km)
                        </span>
                      )}

                      <Button
                        variant="ghost"
                        size="sm"
                        icon={X}
                        className="text-error hover:bg-error-container/30"
                        onClick={() => handleUnassignCustomer(cust.id, cust.name)}
                      >
                        Remove
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </Card>

      {/* Edit Territory Modal */}
      <Modal
        isOpen={isEditModalOpen}
        onClose={() => setIsEditModalOpen(false)}
        title="Edit Geographic Territory"
        subtitle="Update territory center, operational radius, and status."
      >
        {editFormError && (
          <div className="mb-space-4 font-body-md text-xs text-on-error-container bg-error-container p-space-3 rounded-lg border border-error flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-error shrink-0" />
            <span>{editFormError}</span>
          </div>
        )}

        <form onSubmit={handleUpdateTerritory} className="space-y-space-4">
          <Input
            label="Territory Name"
            type="text"
            required
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
          />

          <div className="grid grid-cols-2 gap-space-3">
            <Input
              label="Center Latitude"
              type="number"
              step="any"
              value={editCenterLat}
              onChange={(e) => setEditCenterLat(e.target.value)}
              placeholder="e.g. 26.8467"
            />
            <Input
              label="Center Longitude"
              type="number"
              step="any"
              value={editCenterLng}
              onChange={(e) => setEditCenterLng(e.target.value)}
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
                value={editRadiusKm || '10'}
                onChange={(e) => setEditRadiusKm(e.target.value)}
                className="w-full accent-secondary"
              />
              <input
                type="number"
                min="1"
                max="500"
                step="1"
                value={editRadiusKm}
                onChange={(e) => setEditRadiusKm(e.target.value)}
                className="w-20 px-2 py-1 border border-surface-container-highest rounded text-sm text-center"
              />
              <span className="text-xs text-on-surface-variant font-medium">km</span>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-on-surface mb-1">
              Map Location Picker (Click to reposition center)
            </label>
            <div className="border border-surface-container-highest rounded-lg overflow-hidden">
              <FieldTrackMap
                centerLat={editLatNum || 26.8467}
                centerLng={editLngNum || 80.9462}
                zoom={10}
                markers={modalMarkers}
                territoryCircles={modalCircles}
                height="220px"
                onMapClick={(lat, lng) => {
                  setEditCenterLat(lat.toFixed(6));
                  setEditCenterLng(lng.toFixed(6));
                }}
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-on-surface mb-1">
              Status
            </label>
            <select
              value={editStatus}
              onChange={(e) =>
                setEditStatus(e.target.value as 'ACTIVE' | 'INACTIVE')
              }
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
              onClick={() => setIsEditModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="secondary"
              size="sm"
              isLoading={isSaving}
            >
              Save Changes
            </Button>
          </div>
        </form>
      </Modal>

      {/* Modal: Assign Representative */}
      <Modal
        isOpen={isAssignEmpModalOpen}
        onClose={() => setIsAssignEmpModalOpen(false)}
        title="Assign Field Representative"
        subtitle={`Select an unassigned employee to add to ${territory.name}.`}
      >
        <div className="space-y-space-4">
          {unassignedEmployees.length === 0 ? (
            <p className="text-xs text-on-surface-variant">
              All employees are already assigned to this territory.
            </p>
          ) : (
            <div>
              <label className="block text-xs font-semibold text-on-surface mb-2">
                Select Representative
              </label>
              <select
                value={selectedEmpId}
                onChange={(e) => setSelectedEmpId(e.target.value)}
                className="w-full px-3 py-2 border border-surface-container-highest rounded-lg text-sm bg-surface"
              >
                <option value="">-- Choose Employee --</option>
                {unassignedEmployees.map((emp) => (
                  <option key={emp.id} value={emp.id}>
                    {emp.full_name} ({emp.employee_code || 'No Code'})
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="pt-space-4 flex justify-end gap-space-3 border-t border-surface-container-highest mt-space-6">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsAssignEmpModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={!selectedEmpId}
              onClick={handleAssignEmployee}
            >
              Confirm Assignment
            </Button>
          </div>
        </div>
      </Modal>

      {/* Modal: Assign Customer Account */}
      <Modal
        isOpen={isAssignCustModalOpen}
        onClose={() => setIsAssignCustModalOpen(false)}
        title="Assign Customer Account"
        subtitle={`Select a customer account to add to ${territory.name}.`}
      >
        <div className="space-y-space-4">
          {unassignedCustomers.length === 0 ? (
            <p className="text-xs text-on-surface-variant">
              All customer accounts are already assigned to this territory.
            </p>
          ) : (
            <div>
              <label className="block text-xs font-semibold text-on-surface mb-2">
                Select Customer Account
              </label>
              <select
                value={selectedCustId}
                onChange={(e) => setSelectedCustId(e.target.value)}
                className="w-full px-3 py-2 border border-surface-container-highest rounded-lg text-sm bg-surface"
              >
                <option value="">-- Choose Customer --</option>
                {unassignedCustomers.map((cust) => (
                  <option key={cust.id} value={cust.id}>
                    {cust.name} ({cust.address})
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="pt-space-4 flex justify-end gap-space-3 border-t border-surface-container-highest mt-space-6">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsAssignCustModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={!selectedCustId}
              onClick={handleAssignCustomer}
            >
              Confirm Assignment
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
