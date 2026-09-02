import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, MapPin, Building2, Pencil, Eye, AlertTriangle, Clock, ShieldCheck } from 'lucide-react';
import { DataTable, Column } from '../components/ui/DataTable';
import { Modal } from '../components/ui/Modal';
import { PageHeader } from '../components/ui/PageHeader';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { EmptyState } from '../components/ui/EmptyState';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { MapPicker } from '../components/ui/MapPicker';
import { LocationApprovalsQueue } from '../components/customers/LocationApprovalsQueue';
import { BrandSelect } from '../components/ui/BrandSelect';
import { apiClient, ApiError } from '../api/client';
import { Area, Customer, Territory } from '../types';
import { validatePhoneNumber } from '../utils/phoneValidation';

/** Blank form state for creating a customer. */
const emptyForm = {
  name: '',
  contactPerson: '',
  contactNumber: '',
  gstNumber: '',
  address: '',
  latitude: '',
  longitude: '',
  geofenceRadius: '75',
  territoryId: '',
  areaId: '',
  outletCode: '',
  brands: '',
};

export const CustomersPage: React.FC = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'directory' | 'approvals'>('directory');
  const [pendingProposalsCount, setPendingProposalsCount] = useState(0);

  const [customers, setCustomers] = useState<Customer[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [pageSize, setPageSize] = useState(25);
  const [filterTerritoryId, setFilterTerritoryId] = useState('');
  const [filterAreaId, setFilterAreaId] = useState('');

  const [areas, setAreas] = useState<Area[]>([]);
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isMapPickerOpen, setIsMapPickerOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [initialForm, setInitialForm] = useState<typeof emptyForm | null>(null);
  const [form, setForm] = useState({ ...emptyForm });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Inline Zone & Area creation state
  const [isAddingNewZone, setIsAddingNewZone] = useState(false);
  const [newZoneName, setNewZoneName] = useState('');
  const [isCreatingZone, setIsCreatingZone] = useState(false);
  const [zoneCreateError, setZoneCreateError] = useState<string | null>(null);

  const [isAddingNewArea, setIsAddingNewArea] = useState(false);
  const [newAreaName, setNewAreaName] = useState('');
  const [isCreatingArea, setIsCreatingArea] = useState(false);
  const [areaCreateError, setAreaCreateError] = useState<string | null>(null);

  const fetchPendingProposalsCount = useCallback(async () => {
    try {
      const pendingList = await apiClient.getLocationProposals({ status: 'PENDING', limit: 100 });
      setPendingProposalsCount(pendingList.length);
    } catch {
      // Non-blocking
    }
  }, []);

  const set = <K extends keyof typeof emptyForm>(key: K, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    const fieldMapping: Record<string, string> = {
      name: 'name',
      contactPerson: 'contact_person',
      contactNumber: 'contact_number',
      gstNumber: 'gst_number',
      address: 'address',
      latitude: 'latitude',
      longitude: 'longitude',
      geofenceRadius: 'geofence_radius_m',
      territoryId: 'territory_id',
      areaId: 'area_id',
      outletCode: 'outlet_code',
      brands: 'brands',
    };
    const mapped = fieldMapping[key];
    if (mapped && fieldErrors[mapped]) {
      setFieldErrors((prev) => {
        const next = { ...prev };
        delete next[mapped];
        return next;
      });
    }
  };

  const isDirty = useMemo(() => {
    if (!editingId || !initialForm) return true;
    return (
      form.name.trim() !== initialForm.name.trim() ||
      form.contactPerson.trim() !== initialForm.contactPerson.trim() ||
      form.contactNumber.trim() !== initialForm.contactNumber.trim() ||
      form.address.trim() !== initialForm.address.trim() ||
      form.latitude.trim() !== initialForm.latitude.trim() ||
      form.longitude.trim() !== initialForm.longitude.trim() ||
      form.geofenceRadius.trim() !== initialForm.geofenceRadius.trim() ||
      form.territoryId !== initialForm.territoryId ||
      form.areaId !== initialForm.areaId ||
      form.outletCode.trim() !== initialForm.outletCode.trim()
    );
  }, [editingId, form, initialForm]);

  const isAddressChanged = Boolean(
    editingId &&
    initialForm &&
    form.address.trim() !== initialForm.address.trim() &&
    form.latitude.trim() === initialForm.latitude.trim() &&
    form.longitude.trim() === initialForm.longitude.trim()
  );

  const fetchCustomers = useCallback(
    (
      targetPage = page,
      targetSearch = searchQuery,
      targetTerritory = filterTerritoryId,
      targetArea = filterAreaId,
      targetPageSize = pageSize,
    ) => {
      setIsLoading(true);
      apiClient
        .getCustomersPaginated({
          skip: (targetPage - 1) * targetPageSize,
          limit: targetPageSize,
          search: targetSearch.trim() || undefined,
          territory_id: targetTerritory || undefined,
          area_id: targetArea || undefined,
        })
        .then(({ items, total }) => {
          setCustomers(items);
          setTotalCount(total);
          setError(null);
        })
        .catch((err: Error) => {
          setCustomers([]);
          setTotalCount(0);
          setError(err.message || 'Unable to load customers');
        })
        .finally(() => setIsLoading(false));
    },
    [page, pageSize, searchQuery, filterTerritoryId, filterAreaId],
  );

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchCustomers(page, searchQuery, filterTerritoryId, filterAreaId);
    }, 250);
    return () => clearTimeout(timer);
  }, [page, searchQuery, filterTerritoryId, filterAreaId, fetchCustomers]);

  useEffect(() => {
    apiClient.getTerritories().then(setTerritories).catch(() => setTerritories([]));
    apiClient.getAreas().then(setAreas).catch(() => setAreas([]));
  }, []);

  // Filter out inactive territories for assignment dropdown
  const activeTerritories = useMemo(
    () => territories.filter((t) => t.status === 'ACTIVE' || !t.status),
    [territories]
  );

  const areaOptions = form.territoryId ? areas.filter((a) => a.territory_id === form.territoryId) : [];

  const handleCreateZone = async () => {
    const name = newZoneName.trim();
    if (!name) {
      setZoneCreateError('Zone name cannot be empty.');
      return;
    }
    setZoneCreateError(null);
    setIsCreatingZone(true);
    try {
      const existing = territories.find((t) => t.name.trim().toLowerCase() === name.toLowerCase());
      if (existing) {
        set('territoryId', existing.id);
        set('areaId', '');
        setIsAddingNewZone(false);
        setNewZoneName('');
        return;
      }
      const created = await apiClient.createTerritory({ name });
      setTerritories((prev) => [...prev, created]);
      set('territoryId', created.id);
      set('areaId', '');
      setIsAddingNewZone(false);
      setNewZoneName('');
    } catch (err: unknown) {
      setZoneCreateError(err instanceof Error ? err.message : 'Unable to create zone');
    } finally {
      setIsCreatingZone(false);
    }
  };

  const handleCreateArea = async () => {
    const name = newAreaName.trim();
    if (!name) {
      setAreaCreateError('Area name cannot be empty.');
      return;
    }
    if (!form.territoryId) {
      setAreaCreateError('Please select a Zone first.');
      return;
    }
    setAreaCreateError(null);
    setIsCreatingArea(true);
    try {
      const existing = areas.find(
        (a) => a.territory_id === form.territoryId && a.name.trim().toLowerCase() === name.toLowerCase()
      );
      if (existing) {
        set('areaId', existing.id);
        setIsAddingNewArea(false);
        setNewAreaName('');
        return;
      }
      const created = await apiClient.createArea({ name, territory_id: form.territoryId });
      setAreas((prev) => [...prev, created]);
      set('areaId', created.id);
      setIsAddingNewArea(false);
      setNewAreaName('');
    } catch (err: unknown) {
      setAreaCreateError(err instanceof Error ? err.message : 'Unable to create area');
    } finally {
      setIsCreatingArea(false);
    }
  };

  const openCreate = () => {
    setEditingId(null);
    setInitialForm(null);
    setForm({ ...emptyForm });
    setFieldErrors({});
    setFormError(null);
    setIsAddingNewZone(false);
    setNewZoneName('');
    setZoneCreateError(null);
    setIsAddingNewArea(false);
    setNewAreaName('');
    setAreaCreateError(null);
    setIsModalOpen(true);
  };

  const openEdit = (customer: Customer) => {
    setEditingId(customer.id);
    const populated = {
      name: customer.name,
      contactPerson: customer.contact_person ?? '',
      contactNumber: customer.contact_number || '',
      gstNumber: customer.gst_number || '',
      address: customer.address || '',
      latitude: customer.location?.latitude != null ? String(customer.location.latitude) : '',
      longitude: customer.location?.longitude != null ? String(customer.location.longitude) : '',
      geofenceRadius: String(customer.geofence_radius_m || 75),
      territoryId: customer.territory_id ?? '',
      areaId: customer.area_id ?? '',
      outletCode: customer.outlet_code ?? customer.dms_code ?? '',
      brands: customer.brands ? customer.brands.join(', ') : '',
    };
    setForm(populated);
    setInitialForm(populated);
    setFieldErrors({});
    setFormError(null);
    setIsAddingNewZone(false);
    setNewZoneName('');
    setZoneCreateError(null);
    setIsAddingNewArea(false);
    setNewAreaName('');
    setAreaCreateError(null);
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
    setFieldErrors({});

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
      setFieldErrors((prev) => ({ ...prev, contact_number: phoneError }));
      return;
    }

    setIsSaving(true);
    try {
      const parsedBrands = form.brands
        ? form.brands.split(',').map((b) => b.trim()).filter(Boolean)
        : [];

      const payload = {
        name: form.name.trim(),
        contact_person: form.contactPerson.trim() || null,
        contact_number: form.contactNumber.trim(),
        gst_number: form.gstNumber.trim() || null,
        address: form.address.trim(),
        location: { latitude, longitude },
        geofence_radius_m: radius,
        territory_id: form.territoryId || null,
        area_id: form.areaId || null,
        outlet_code: form.outletCode.trim() || null,
        brands: parsedBrands,
      };

      if (editingId) {
        await apiClient.updateCustomer(editingId, payload);
        fetchCustomers(page, searchQuery, filterTerritoryId, filterAreaId);
      } else {
        await apiClient.createCustomer(payload);
        setPage(1);
        setSearchQuery('');
        fetchCustomers(1, '', filterTerritoryId, filterAreaId);
      }
      setIsModalOpen(false);
      fetchPendingProposalsCount();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.fieldErrors && Object.keys(err.fieldErrors).length > 0) {
          setFieldErrors(err.fieldErrors);
        }
        if (err.code === 'OUTLET_CODE_EXISTS') {
          setFieldErrors((prev) => ({ ...prev, outlet_code: err.message }));
        }
        setFormError(err.message);
      } else {
        setFormError(err instanceof Error ? err.message : 'Unable to save customer');
      }
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
          {cust.gst_number && (
            <p className="font-mono text-[11px] text-on-surface-variant mt-0.5">
              GST: <span className="font-semibold text-on-surface">{cust.gst_number}</span>
            </p>
          )}
        </div>
      ),
    },
    {
      header: 'Status & Brands',
      accessor: (cust) => {
        const st = cust.location_status || 'MISSING';
        return (
          <div className="space-y-1.5 font-caption text-xs">
            <div>
              {st === 'VERIFIED' && (
                <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-100 text-emerald-900 border border-emerald-300">
                  <ShieldCheck className="w-3 h-3" /> VERIFIED
                </span>
              )}
              {st === 'PENDING_APPROVAL' && (
                <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded bg-amber-100 text-amber-900 border border-amber-300">
                  <Clock className="w-3 h-3" /> PENDING APPROVAL
                </span>
              )}
              {st === 'NEEDS_REVIEW' && (
                <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded bg-orange-100 text-orange-900 border border-orange-300">
                  <AlertTriangle className="w-3 h-3" /> NEEDS REVIEW
                </span>
              )}
              {st === 'MISSING' && (
                <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-300">
                  MISSING
                </span>
              )}
            </div>
            {cust.brands && cust.brands.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {cust.brands.map((b) => (
                  <span key={b} className="text-[10px] font-semibold bg-primary/10 text-primary px-1.5 py-0.5 rounded border border-primary/20">
                    {b}
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      },
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
        <div className="flex items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => navigate(`/customers/${cust.id}`)}
            className="p-1.5 text-primary hover:bg-surface-container rounded-lg transition-colors cursor-pointer"
            title="View Details"
          >
            <Eye className="w-4 h-4" />
          </button>
          <button
            onClick={() => openEdit(cust)}
            className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-surface-container rounded-lg transition-colors cursor-pointer"
            title="Edit Customer"
          >
            <Pencil className="w-4 h-4" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-space-6 max-w-7xl mx-auto">
      <PageHeader
        title="Customer Accounts Directory"
        subtitle="Manage client outlets, brand portfolios, location verification, and territory associations."
        actions={
          <Button variant="secondary" size="md" icon={Plus} onClick={openCreate}>
            Add Account
          </Button>
        }
      />

      {/* Tab Switcher */}
      <div className="flex items-center gap-2 border-b border-outline-variant pb-2">
        <button
          onClick={() => setActiveTab('directory')}
          className={`px-4 py-2 text-xs font-bold rounded-lg transition-colors cursor-pointer ${
            activeTab === 'directory'
              ? 'bg-primary text-on-primary shadow-xs'
              : 'bg-surface text-on-surface-variant hover:text-on-surface'
          }`}
        >
          Outlets Directory ({totalCount})
        </button>
        <button
          onClick={() => setActiveTab('approvals')}
          className={`px-4 py-2 text-xs font-bold rounded-lg transition-colors cursor-pointer flex items-center gap-2 ${
            activeTab === 'approvals'
              ? 'bg-primary text-on-primary shadow-xs'
              : 'bg-surface text-on-surface-variant hover:text-on-surface'
          }`}
        >
          <span>Location Approvals Queue</span>
          {pendingProposalsCount > 0 && (
            <span className="px-2 py-0.5 text-[11px] font-black rounded-full bg-amber-400 text-amber-950">
              {pendingProposalsCount}
            </span>
          )}
        </button>
      </div>

      {error && <ErrorBanner message={error} />}

      {activeTab === 'approvals' ? (
        <LocationApprovalsQueue onProposalReviewed={fetchPendingProposalsCount} />
      ) : (
        <>
          {/* Filter Bar */}
          <div className="flex flex-wrap items-center gap-space-3 bg-surface p-space-4 rounded-xl border border-surface-container-highest shadow-xs">
            <div className="w-48">
              <Select
                id="territory-filter"
                value={filterTerritoryId}
                onChange={(e) => {
                  setFilterTerritoryId(e.target.value);
                  setFilterAreaId('');
                  setPage(1);
                }}
              >
                <option value="">All Zones</option>
                {territories.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="w-48">
              <Select
                id="area-filter"
                value={filterAreaId}
                onChange={(e) => {
                  setFilterAreaId(e.target.value);
                  setPage(1);
                }}
                disabled={!filterTerritoryId}
              >
                <option value="">All Areas</option>
                {areas
                  .filter((a) => !filterTerritoryId || a.territory_id === filterTerritoryId)
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
              </Select>
            </div>
            {(filterTerritoryId || filterAreaId || searchQuery) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setFilterTerritoryId('');
                  setFilterAreaId('');
                  setSearchQuery('');
                  setPage(1);
                }}
              >
                Reset Filters
              </Button>
            )}

            {/* Per-page selector */}
            <div className="flex items-center gap-1.5 ml-auto shrink-0">
              <span className="font-label-md text-xs text-on-surface-variant uppercase tracking-wider font-semibold">Show:</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  const next = Number(e.target.value);
                  setPageSize(next);
                  setPage(1);
                  fetchCustomers(1, searchQuery, filterTerritoryId, filterAreaId, next);
                }}
                className="h-8 bg-surface border border-outline-variant rounded-lg px-2 py-1 text-xs text-primary font-bold focus:outline-none focus:border-primary-container focus:ring-2 focus:ring-primary-container/20 transition-all cursor-pointer"
                aria-label="Rows per page"
              >
                {[10, 25, 50, 100, 200].map((opt) => (
                  <option key={opt} value={opt}>{opt} rows</option>
                ))}
              </select>
            </div>
          </div>

          {customers.length === 0 && !isLoading && !filterTerritoryId && !filterAreaId && !searchQuery ? (
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
              searchPlaceholder="Search customers by name, code, GST, address, contact..."
              serverSide={true}
              totalCount={totalCount}
              page={page}
              pageSize={pageSize}
              onPageChange={(p) => setPage(p)}
              onSearchChange={(q) => {
                setSearchQuery(q);
                setPage(1);
                fetchCustomers(1, q, filterTerritoryId, filterAreaId);
              }}
            />
          )}
        </>
      )}

      {/* Create / Edit Customer Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingId ? 'Edit Customer Account' : 'Add New Customer Account'}
      >
        {formError && <ErrorBanner message={formError} />}
        {isAddressChanged && (
          <div className="mb-space-4 p-space-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-amber-700 dark:text-amber-300 text-xs flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 text-amber-500" />
            <span>Address changed — map location coordinates may need updating.</span>
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-space-4">
          <Input
            label="Company / Account Name"
            type="text"
            required
            value={form.name}
            error={fieldErrors.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder="Acme Industrial Corp"
          />
          <div className="grid grid-cols-2 gap-space-3">
            <Input
              label="DMS Code (External Key)"
              type="text"
              value={form.outletCode}
              error={fieldErrors.outlet_code}
              onChange={(e) => set('outletCode', e.target.value)}
              placeholder="e.g. SGRGUS1463"
              helperText="Anchor outlet key for BI/MIS."
            />
            <Input
              label="GST Number"
              type="text"
              value={form.gstNumber}
              error={fieldErrors.gst_number}
              onChange={(e) => set('gstNumber', e.target.value.toUpperCase())}
              placeholder="e.g. 07AAAAA0000A1Z5"
              helperText="15-character GST identification (optional)."
            />
          </div>
          <BrandSelect
            label="Associated Brands"
            selectedBrands={form.brands ? form.brands.split(',').map((b) => b.trim()).filter(Boolean) : []}
            onChange={(brands) => set('brands', brands.join(', '))}
            error={fieldErrors.brands}
            helperText="Product brands associated with this outlet."
          />
          <Input
            label="Contact Person"
            type="text"
            value={form.contactPerson}
            error={fieldErrors.contact_person}
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
            error={fieldErrors.contact_number}
            onChange={(e) => set('contactNumber', e.target.value)}
            placeholder="+91 98765 43210"
            helperText="Phone number: digits, +, -, spaces, parentheses. Max 20 characters."
          />
          <Input
            label="Address"
            type="text"
            required
            value={form.address}
            error={fieldErrors.address}
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
              error={fieldErrors.latitude}
              onChange={(e) => set('latitude', e.target.value)}
              placeholder="12.971600"
            />
            <Input
              label="Longitude"
              type="number"
              step="any"
              required
              value={form.longitude}
              error={fieldErrors.longitude}
              onChange={(e) => set('longitude', e.target.value)}
              placeholder="77.594600"
            />
          </div>
          <Input
            label="Geofence Radius (meters)"
            type="number"
            required
            min={1}
            value={form.geofenceRadius}
            error={fieldErrors.geofence_radius_m}
            onChange={(e) => set('geofenceRadius', e.target.value)}
            helperText="Maximum allowed distance in meters from this point at check-in."
          />
          {/* Zone (Territory) Selection & Quick Create */}
          <div className="w-full flex flex-col gap-space-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="customer-territory" className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold">
                Zone
              </label>
              {!isAddingNewZone && (
                <button
                  type="button"
                  className="text-xs text-primary font-semibold hover:underline inline-flex items-center gap-1 cursor-pointer"
                  onClick={() => {
                    setIsAddingNewZone(true);
                    setZoneCreateError(null);
                  }}
                >
                  <Plus className="w-3.5 h-3.5" /> Add New Zone
                </button>
              )}
            </div>
            {isAddingNewZone ? (
              <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant space-y-2">
                <div className="flex items-center gap-2">
                  <div className="flex-1">
                    <Input
                      type="text"
                      placeholder="e.g. Lucknow East"
                      value={newZoneName}
                      onChange={(e) => setNewZoneName(e.target.value)}
                      autoFocus
                    />
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    isLoading={isCreatingZone}
                    onClick={handleCreateZone}
                  >
                    Save Zone
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={isCreatingZone}
                    onClick={() => {
                      setIsAddingNewZone(false);
                      setNewZoneName('');
                      setZoneCreateError(null);
                    }}
                  >
                    Cancel
                  </Button>
                </div>
                {zoneCreateError && (
                  <p className="font-caption text-xs text-error font-medium">{zoneCreateError}</p>
                )}
              </div>
            ) : (
              <Select
                id="customer-territory"
                value={form.territoryId}
                onChange={(e) => {
                  set('territoryId', e.target.value);
                  set('areaId', '');
                }}
              >
                <option value="">-- Unassigned --</option>
                {activeTerritories.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </Select>
            )}
          </div>

          {/* Area Selection & Quick Create */}
          <div className="w-full flex flex-col gap-space-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="customer-area" className="font-label-md text-xs text-on-surface uppercase tracking-wider block font-semibold">
                Area
              </label>
              {form.territoryId && !isAddingNewArea && (
                <button
                  type="button"
                  className="text-xs text-primary font-semibold hover:underline inline-flex items-center gap-1 cursor-pointer"
                  onClick={() => {
                    setIsAddingNewArea(true);
                    setAreaCreateError(null);
                  }}
                >
                  <Plus className="w-3.5 h-3.5" /> Add New Area
                </button>
              )}
            </div>
            {isAddingNewArea ? (
              <div className="p-space-3 bg-surface-container-low rounded-lg border border-outline-variant space-y-2">
                <div className="flex items-center gap-2">
                  <div className="flex-1">
                    <Input
                      type="text"
                      placeholder="e.g. Hazratganj Market"
                      value={newAreaName}
                      onChange={(e) => setNewAreaName(e.target.value)}
                      autoFocus
                    />
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    isLoading={isCreatingArea}
                    onClick={handleCreateArea}
                  >
                    Save Area
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={isCreatingArea}
                    onClick={() => {
                      setIsAddingNewArea(false);
                      setNewAreaName('');
                      setAreaCreateError(null);
                    }}
                  >
                    Cancel
                  </Button>
                </div>
                {areaCreateError && (
                  <p className="font-caption text-xs text-error font-medium">{areaCreateError}</p>
                )}
              </div>
            ) : (
              <Select
                id="customer-area"
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
            )}
          </div>
          <div className="pt-space-4 flex justify-end gap-space-3 border-t border-surface-container-highest mt-space-6">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={isSaving}
              onClick={() => setIsModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="secondary"
              size="sm"
              isLoading={isSaving}
              disabled={isSaving || (Boolean(editingId) && !isDirty)}
            >
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
