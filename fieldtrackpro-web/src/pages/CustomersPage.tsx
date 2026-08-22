import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, MapPin, Building2, Pencil, Eye } from 'lucide-react';
import { DataTable, Column } from '../components/ui/DataTable';
import { Modal } from '../components/ui/Modal';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { MapPicker } from '../components/ui/MapPicker';
import { apiClient } from '../api/client';
import { Area, Customer, Territory } from '../types';
import { validatePhoneNumber } from '../utils/phoneValidation';

/** Blank form state for creating a customer. */
const emptyForm = {
  name: '',
  contactPerson: '',
  contactNumber: '',
  address: '',
  latitude: '',
  longitude: '',
  geofenceRadius: '75',
  territoryId: '',
  areaId: '',
  outletCode: '',
};

export const CustomersPage: React.FC = () => {
  const navigate = useNavigate();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isMapPickerOpen, setIsMapPickerOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState({ ...emptyForm });
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const set = <K extends keyof typeof emptyForm>(key: K, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const fetchCustomers = useCallback(() => {
    setIsLoading(true);
    apiClient
      .getCustomers()
      .then((data) => {
        setCustomers(data);
        setError(null);
      })
      .catch((err: Error) => {
        setCustomers([]);
        setError(err.message || 'Unable to load customers');
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    fetchCustomers();
    apiClient.getTerritories().then(setTerritories).catch(() => setTerritories([]));
    apiClient.getAreas().then(setAreas).catch(() => setAreas([]));
  }, [fetchCustomers]);

  const areaOptions = form.territoryId ? areas.filter((a) => a.territory_id === form.territoryId) : [];

  const openCreate = () => {
    setEditingId(null);
    setForm({ ...emptyForm });
    setFormError(null);
    setIsModalOpen(true);
  };

  const openEdit = (customer: Customer) => {
    setEditingId(customer.id);
    setForm({
      name: customer.name,
      contactPerson: customer.contact_person ?? '',
      contactNumber: customer.contact_number || '',
      address: customer.address || '',
      latitude: customer.location?.latitude != null ? String(customer.location.latitude) : '',
      longitude: customer.location?.longitude != null ? String(customer.location.longitude) : '',
      geofenceRadius: String(customer.geofence_radius_m || 75),
      territoryId: customer.territory_id ?? '',
      areaId: customer.area_id ?? '',
      outletCode: customer.outlet_code ?? customer.dms_code ?? '',
    });
    setFormError(null);
    setIsModalOpen(true);
  };

  const handleMapPickerConfirm = (pickedLat: number, pickedLng: number, pickedRadius: number) => {
    set('latitude', String(pickedLat));
    set('longitude', String(pickedLng));
    set('geofenceRadius', String(pickedRadius));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const latitude = parseFloat(form.latitude);
    const longitude = parseFloat(form.longitude);
    if (Number.isNaN(latitude) || latitude < -90 || latitude > 90) {
      setFormError('Latitude must be a number between -90 and 90.');
      return;
    }
    if (Number.isNaN(longitude) || longitude < -180 || longitude > 180) {
      setFormError('Longitude must be a number between -180 and 180.');
      return;
    }
    const radius = parseInt(form.geofenceRadius, 10);
    if (Number.isNaN(radius) || radius <= 0) {
      setFormError('Geofence radius must be a positive number of metres.');
      return;
    }

    const phoneError = validatePhoneNumber(form.contactNumber);
    if (phoneError) {
      setFormError(phoneError);
      return;
    }

    setIsSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        contact_person: form.contactPerson.trim() || null,
        contact_number: form.contactNumber.trim(),
        address: form.address.trim(),
        location: { latitude, longitude },
        geofence_radius_m: radius,
        territory_id: form.territoryId || null,
        area_id: form.areaId || null,
        outlet_code: form.outletCode.trim() || null,
      };

      if (editingId) {
        await apiClient.updateCustomer(editingId, payload);
      } else {
        await apiClient.createCustomer(payload);
      }
      setIsModalOpen(false);
      fetchCustomers();
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : 'Unable to save customer');
    } finally {
      setIsSaving(false);
    }
  };

  const columns: Column<Customer>[] = [
    {
      header: 'Customer Account',
      accessor: (cust) => (
        <div>
          <p className="font-headline-sm text-sm text-primary font-bold hover:text-secondary transition-colors">
            {cust.name}
          </p>
          <div className="flex items-center gap-2 mt-1">
            {cust.outlet_code && (
              <span className="font-mono text-[11px] font-bold text-on-primary-container bg-primary-container px-2 py-0.5 rounded shadow-2xs">
                {cust.outlet_code}
              </span>
            )}
            <p className="font-caption text-xs text-on-surface-variant">
              Contact: {cust.contact_person || '—'}
            </p>
          </div>
        </div>
      ),
    },
    {
      header: 'Zone / Area',
      accessor: (cust) => (
        <div className="font-caption text-xs space-y-0.5">
          <p className="font-headline-sm text-xs font-bold text-primary">
            {territories.find((t) => t.id === cust.territory_id)?.name || cust.territory_name || '—'}
          </p>
          <p className="text-on-surface-variant font-caption">
            {cust.area_name || '—'}
          </p>
        </div>
      ),
    },
    {
      header: 'Address Location',
      accessor: (cust) => (
        <div className="flex items-start gap-1.5 max-w-xs font-body-md text-xs text-on-surface">
          <MapPin className="w-3.5 h-3.5 text-secondary-container shrink-0 mt-0.5" />
          <span className="truncate">{cust.address || '—'}</span>
        </div>
      ),
    },
    {
      header: 'GPS & Geofence',
      accessor: (cust) => {
        const hasCoords = cust.location && cust.location.latitude != null && cust.location.longitude != null;
        return (
          <div className="font-caption text-xs space-y-1">
            {hasCoords ? (
              <p className="text-primary font-mono text-xs font-semibold">
                {cust.location!.latitude.toFixed(6)}, {cust.location!.longitude.toFixed(6)}
              </p>
            ) : (
              <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-label-md uppercase tracking-wider font-semibold bg-secondary-fixed text-on-secondary-fixed border border-secondary-fixed-dim rounded">
                Missing GPS
              </span>
            )}
            <p className="text-primary font-label-md font-bold text-[11px] bg-primary-fixed/60 px-2 py-0.5 rounded border border-primary-fixed-dim inline-block">
              Geofence: {cust.geofence_radius_m || 75}m
            </p>
          </div>
        );
      },
    },
    {
      header: 'Contact Number',
      accessor: (cust) => (
        <span className="font-mono text-xs font-semibold text-primary">
          {cust.contact_number || '—'}
        </span>
      ),
    },
    {
      header: 'Action',
      accessor: (cust) => (
        <div className="flex items-center gap-1.5">
          <Button
            variant="outline"
            size="sm"
            icon={Eye}
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/customers/${cust.id}`);
            }}
          >
            View
          </Button>
          <Button
            variant="outline"
            size="sm"
            icon={Pencil}
            onClick={(e) => {
              e.stopPropagation();
              openEdit(cust);
            }}
          >
            Edit
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-space-6">
      <PageHeader
        title="Customer Accounts Directory"
        subtitle="Geofenced client sites and visit location parameters."
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => navigate('/imports')}>
              Import Outlets
            </Button>
            <Button variant="secondary" size="sm" icon={Plus} onClick={openCreate}>
              Add Account
            </Button>
          </div>
        }
      />

      {error && (
        <ErrorBanner message={error} onRetry={fetchCustomers} onDismiss={() => setError(null)} />
      )}

      {!isLoading && !error && customers.length === 0 ? (
        <EmptyState
          icon={Building2}
          title="No customers added yet"
          subtitle="Add your first customer to start scheduling visits."
          action={
            <Button variant="secondary" size="sm" icon={Plus} onClick={openCreate}>
              Add Account
            </Button>
          }
        />
      ) : (
        <DataTable
          columns={columns}
          data={customers}
          isLoading={isLoading}
          searchPlaceholder="Search customers by name, address..."
          searchFilter={(cust, q) =>
            Boolean(
              cust.name.toLowerCase().includes(q.toLowerCase()) ||
              (cust.outlet_code && cust.outlet_code.toLowerCase().includes(q.toLowerCase())) ||
              (cust.address && cust.address.toLowerCase().includes(q.toLowerCase()))
            )
          }
          onRowClick={(cust) => navigate(`/customers/${cust.id}`)}
        />
      )}

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingId ? 'Edit Customer Account' : 'Register Customer Account & Geofence'}
        subtitle="Specify client location parameters and radial bounds."
      >
        {formError && (
          <div className="mb-space-4 font-body-md text-xs text-on-error-container bg-error-container p-space-3 rounded-lg border border-error">
            {formError}
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-space-4">
          <Input
            label="Company / Account Name"
            type="text"
            required
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder="Acme Industrial Corp"
          />
          <Input
            label="DMS Code (External Key)"
            type="text"
            value={form.outletCode}
            onChange={(e) => set('outletCode', e.target.value)}
            placeholder="e.g. SGRGUS1463"
            helperText="Anchor outlet key for BI and Excel import mapping."
          />
          <Input
            label="Contact Person"
            type="text"
            value={form.contactPerson}
            onChange={(e) => set('contactPerson', e.target.value)}
            placeholder="Jane Smith"
            helperText="Name of the site contact (optional)."
          />
          <Input
            label="Contact Number"
            type="tel"
            required
            maxLength={20}
            value={form.contactNumber}
            onChange={(e) => set('contactNumber', e.target.value)}
            placeholder="+91 98765 43210"
            helperText="Phone number: digits, +, -, spaces, parentheses. Max 20 characters."
          />
          <Input
            label="Address"
            type="text"
            required
            value={form.address}
            onChange={(e) => set('address', e.target.value)}
            placeholder="100 Tech Park Blvd"
          />
          <div className="flex items-center justify-between pt-1">
            <span className="text-xs font-bold text-on-surface">Location Coordinates</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setIsMapPickerOpen(true)}
            >
              <MapPin className="w-3.5 h-3.5 mr-1 text-primary" /> Map Picker
            </Button>
          </div>
          <div className="grid grid-cols-2 gap-space-3">
            <Input
              label="Latitude"
              type="number"
              step="any"
              required
              value={form.latitude}
              onChange={(e) => set('latitude', e.target.value)}
              placeholder="12.971600"
            />
            <Input
              label="Longitude"
              type="number"
              step="any"
              required
              value={form.longitude}
              onChange={(e) => set('longitude', e.target.value)}
              placeholder="77.594600"
            />
          </div>
          <Input
            label="Geofence Radius (Meters)"
            type="number"
            required
            min={1}
            value={form.geofenceRadius}
            onChange={(e) => set('geofenceRadius', e.target.value)}
            helperText="Maximum allowed distance from this point at check-in."
          />
          <Select
            id="customer-territory"
            label="Zone"
            value={form.territoryId}
            onChange={(e) => {
              set('territoryId', e.target.value);
              set('areaId', '');
            }}
          >
            <option value="">-- Unassigned --</option>
            {territories.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
          <Select
            id="customer-area"
            label="Area"
            value={form.areaId}
            onChange={(e) => set('areaId', e.target.value)}
            disabled={!form.territoryId}
            helperText={!form.territoryId ? 'Select a Zone first.' : undefined}
          >
            <option value="">-- Unassigned --</option>
            {areaOptions.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
          <div className="pt-space-4 flex justify-end gap-space-3 border-t border-surface-container-highest mt-space-6">
            <Button type="button" variant="ghost" size="sm" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="secondary" size="sm" isLoading={isSaving}>
              {editingId ? 'Save Changes' : 'Save Account'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Interactive Map Picker Modal */}
      <MapPicker
        isOpen={isMapPickerOpen}
        onClose={() => setIsMapPickerOpen(false)}
        initialLat={form.latitude ? parseFloat(form.latitude) : null}
        initialLng={form.longitude ? parseFloat(form.longitude) : null}
        initialRadius={form.geofenceRadius ? parseInt(form.geofenceRadius, 10) : 75}
        outletName={form.name}
        outletAddress={form.address}
        onConfirm={handleMapPickerConfirm}
      />
    </div>
  );
};
