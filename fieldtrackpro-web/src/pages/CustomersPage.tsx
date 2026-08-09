import React, { useCallback, useEffect, useState } from 'react';
import { Plus, MapPin, Building2, Pencil } from 'lucide-react';
import { DataTable, Column } from '../components/ui/DataTable';
import { Modal } from '../components/ui/Modal';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { apiClient } from '../api/client';
import { Customer, Territory } from '../types';

/** Blank form state for creating a customer. */
const emptyForm = {
  name: '',
  contactPerson: '',
  contactNumber: '',
  address: '',
  latitude: '',
  longitude: '',
  geofenceRadius: '75', // FT-054: matches the backend/database default
  territoryId: '',
};

export const CustomersPage: React.FC = () => {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
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
  }, [fetchCustomers]);

  const openCreate = () => {
    setEditingId(null);
    setForm({ ...emptyForm });
    setFormError(null);
    setIsModalOpen(true);
  };

  /** FT-014: editing was impossible; PATCH /customers/{id} had no UI. */
  const openEdit = (customer: Customer) => {
    setEditingId(customer.id);
    setForm({
      name: customer.name,
      contactPerson: customer.contact_person ?? '',
      contactNumber: customer.contact_number,
      address: customer.address,
      latitude: String(customer.location.latitude),
      longitude: String(customer.location.longitude),
      geofenceRadius: String(customer.geofence_radius_m),
      territoryId: customer.territory_id ?? '',
    });
    setFormError(null);
    setIsModalOpen(true);
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

    setIsSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        // FT-013: contact_person and contact_number are distinct fields. The
        // form previously wrote a person's name into contact_number, which is
        // varchar(20) and produced a 500 for any realistic full name.
        contact_person: form.contactPerson.trim() || null,
        contact_number: form.contactNumber.trim(),
        address: form.address.trim(),
        location: { latitude, longitude },
        geofence_radius_m: radius,
        territory_id: form.territoryId || null,
      };

      if (editingId) {
        await apiClient.updateCustomer(editingId, payload);
      } else {
        await apiClient.createCustomer(payload);
      }
      setIsModalOpen(false);
      setForm({ ...emptyForm });
      setEditingId(null);
      fetchCustomers();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to save customer record');
    } finally {
      setIsSaving(false);
    }
  };

  const columns: Column<Customer>[] = [
    {
      header: 'Customer Account',
      accessor: (cust) => (
        <div>
          <p className="font-headline-sm text-sm text-primary font-bold">{cust.name}</p>
          <p className="font-caption text-xs text-on-surface-variant">
            Contact: {cust.contact_person || '—'}
          </p>
        </div>
      ),
    },
    {
      header: 'Address Location',
      accessor: (cust) => (
        <div className="flex items-start gap-space-1.5 max-w-xs font-body-md text-xs text-on-surface">
          <MapPin className="w-4 h-4 text-primary shrink-0 mt-0.5" />
          <span className="truncate">{cust.address}</span>
        </div>
      ),
    },
    {
      header: 'GPS & Geofence',
      accessor: (cust) => (
        /* FT-012: real coordinates. This column was permanently blank because
           CustomerRead did not return the location at all. */
        <div className="font-caption text-xs space-y-0.5">
          <p className="text-on-surface font-mono">
            {cust.location.latitude.toFixed(6)}, {cust.location.longitude.toFixed(6)}
          </p>
          <p className="text-primary font-bold text-[11px] bg-primary-tint/50 px-2 py-0.5 rounded inline-block">
            Geofence: {cust.geofence_radius_m}m
          </p>
        </div>
      ),
    },
    {
      header: 'Contact Number',
      accessor: (cust) => (
        <span className="font-caption text-xs text-on-surface-variant">
          {cust.contact_number || '—'}
        </span>
      ),
    },
    {
      header: 'Action',
      accessor: (cust) => (
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
      ),
    },
  ];

  return (
    <div className="space-y-space-6">
      <PageHeader
        title="Customer Accounts Directory"
        subtitle="Geofenced client sites and visit location parameters."
        actions={
          <Button variant="secondary" size="sm" icon={Plus} onClick={openCreate}>
            Add Account
          </Button>
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
            cust.name.toLowerCase().includes(q.toLowerCase()) ||
            cust.address.toLowerCase().includes(q.toLowerCase())
          }
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
            helperText="Phone number, maximum 20 characters."
          />
          <Input
            label="Address"
            type="text"
            required
            value={form.address}
            onChange={(e) => set('address', e.target.value)}
            placeholder="100 Tech Park Blvd"
          />
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
            label="Territory"
            value={form.territoryId}
            onChange={(e) => set('territoryId', e.target.value)}
          >
            <option value="">-- Unassigned --</option>
            {territories.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
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
    </div>
  );
};
