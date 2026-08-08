import React, { useEffect, useState } from 'react';
import { Plus, MapPin } from 'lucide-react';
import { DataTable, Column } from '../components/ui/DataTable';
import { Modal } from '../components/ui/Modal';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { apiClient } from '../api/client';
import { Customer } from '../types';

export const CustomersPage: React.FC = () => {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Form State
  const [name, setName] = useState('');
  const [contactPerson, setContactPerson] = useState('');
  const [address, setAddress] = useState('');
  const [latitude, setLatitude] = useState('12.9716');
  const [longitude, setLongitude] = useState('77.5946');
  const [geofenceRadius, setGeofenceRadius] = useState('100');
  const [formError, setFormError] = useState<string | null>(null);

  const fetchCustomers = () => {
    setIsLoading(true);
    apiClient.getCustomers()
      .then((data) => setCustomers(data))
      .catch(() => setCustomers([]))
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    fetchCustomers();
  }, []);

  const handleCreateCustomer = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    try {
      await apiClient.createCustomer({
        name,
        contact_number: contactPerson || '+1-555-0100',
        address,
        location: {
          latitude: parseFloat(latitude),
          longitude: parseFloat(longitude),
        },
        geofence_radius_m: parseInt(geofenceRadius) || 75,
      } as any);
      setIsModalOpen(false);
      setName('');
      setContactPerson('');
      setAddress('');
      fetchCustomers();
    } catch (err: any) {
      setFormError(err.message || 'Failed to create customer record');
    }
  };

  const columns: Column<Customer>[] = [
    {
      header: 'Customer Account',
      accessor: (cust) => (
        <div>
          <p className="font-headline-sm text-sm text-primary font-bold">{cust.name}</p>
          <p className="font-caption text-xs text-on-surface-variant">Contact: {cust.contact_person || 'N/A'}</p>
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
        <div className="font-caption text-xs space-y-0.5">
          <p className="text-on-surface">{cust.latitude}, {cust.longitude}</p>
          <p className="text-primary font-bold text-[11px] bg-primary-tint/50 px-2 py-0.5 rounded inline-block">
            Geofence: {cust.geofence_radius_m}m
          </p>
        </div>
      ),
    },
    {
      header: 'Contact Info',
      accessor: (cust) => (
        <div className="font-caption text-xs space-y-0.5 text-on-surface-variant">
          {cust.phone && <p>📞 {cust.phone}</p>}
          {cust.email && <p>✉️ {cust.email}</p>}
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
          <Button variant="secondary" size="sm" icon={Plus} onClick={() => setIsModalOpen(true)}>
            Add Account
          </Button>
        }
      />

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

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Register Customer Account & Geofence"
        subtitle="Specify client location parameters and radial bounds."
      >
        {formError && (
          <div className="mb-space-4 font-body-md text-xs text-on-error-container bg-error-container p-space-3 rounded-lg border border-error">
            {formError}
          </div>
        )}
        <form onSubmit={handleCreateCustomer} className="space-y-space-4">
          <Input
            label="Company / Account Name"
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Acme Industrial Corp"
          />
          <Input
            label="Contact Person"
            type="text"
            value={contactPerson}
            onChange={(e) => setContactPerson(e.target.value)}
            placeholder="Jane Smith"
          />
          <Input
            label="Address"
            type="text"
            required
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="100 Tech Park Blvd"
          />
          <div className="grid grid-cols-2 gap-space-3">
            <Input
              label="Latitude"
              type="number"
              step="any"
              required
              value={latitude}
              onChange={(e) => setLatitude(e.target.value)}
            />
            <Input
              label="Longitude"
              type="number"
              step="any"
              required
              value={longitude}
              onChange={(e) => setLongitude(e.target.value)}
            />
          </div>
          <Input
            label="Geofence Radius (Meters)"
            type="number"
            required
            value={geofenceRadius}
            onChange={(e) => setGeofenceRadius(e.target.value)}
          />
          <div className="pt-space-4 flex justify-end gap-space-3 border-t border-surface-container-highest mt-space-6">
            <Button type="button" variant="ghost" size="sm" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="secondary" size="sm">
              Save Account
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
