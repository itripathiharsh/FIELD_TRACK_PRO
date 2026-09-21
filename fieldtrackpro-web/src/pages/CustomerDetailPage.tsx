import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Building2,
  Phone,
  MapPin,
  Navigation,
  Calendar,
  PackagePlus,
  ShieldCheck,
  Clock,
  AlertTriangle,
  Tag,
  Plus,
  Briefcase,
  ExternalLink,
  Check,
  X,
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../components/ui/Card';
import { PageHeader } from '../components/ui/PageHeader';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { EmptyState } from '../components/ui/EmptyState';
import { StatusBadge } from '../components/ui/StatusBadge';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Textarea } from '../components/ui/Textarea';
import { BrandSelect } from '../components/ui/BrandSelect';
import { AccountSummaryCard } from '../components/ui/AccountSummaryCard';
import { AddBrandModal } from '../components/ui/AddBrandModal';

import { apiClient, CustomerHistoryRow } from '../api/client';
import { AccountSummary, Brand, Customer, CustomerRequirement, LocationProposal, VisitOrderPhotoRead, Territory } from '../types';

/**
 * Customer Detail page — shows customer profile, location proposals, requirements, account, and visit history.
 */
export const CustomerDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [visitHistory, setVisitHistory] = useState<CustomerHistoryRow[]>([]);
  const [account, setAccount] = useState<AccountSummary | null>(null);
  const [orders, setOrders] = useState<VisitOrderPhotoRead[]>([]);
  const [territories, setTerritories] = useState<Territory[]>([]);
  const [requirements, setRequirements] = useState<CustomerRequirement[]>([]);
  const [proposals, setProposals] = useState<LocationProposal[]>([]);
  const [masterBrands, setMasterBrands] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New Requirement Modal state
  const [isAddReqOpen, setIsAddReqOpen] = useState(false);
  const [reqForm, setReqForm] = useState({
    brand: '',
    requirement_type: '',
    product_details: '',
    quantity: '',
    expected_value: '',
    follow_up_date: '',
    notes: '',
  });
  const [isSavingReq, setIsSavingReq] = useState(false);
  const [reqError, setReqError] = useState<string | null>(null);

  // Brand creation & management modal
  const [isAddBrandOpen, setIsAddBrandOpen] = useState(false);
  const [brandContext, setBrandContext] = useState<'requirement' | 'customer'>('requirement');
  const [isManageBrandsOpen, setIsManageBrandsOpen] = useState(false);
  const [isSavingBrands, setIsSavingBrands] = useState(false);
  const [brandActionError, setBrandActionError] = useState<string | null>(null);
  const [customReqType, setCustomReqType] = useState('');

  // Rejection modal
  const [rejectingProposal, setRejectingProposal] = useState<LocationProposal | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [isRejecting, setIsRejecting] = useState(false);

  // Approval modal
  const [approvingProposal, setApprovingProposal] = useState<LocationProposal | null>(null);
  const [isApproving, setIsApproving] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      setIsLoading(true);
      const [cust, history, acct, orderHistory, territoryList, reqs, propsList, brandsList] = await Promise.all([
        apiClient.getCustomerById(id),
        apiClient.getCustomerVisitHistory(id).catch(() => [] as CustomerHistoryRow[]),
        apiClient.getCustomerAccount(id).catch(() => null),
        apiClient.getCustomerOrders(id).catch(() => [] as VisitOrderPhotoRead[]),
        apiClient.getTerritories().catch(() => [] as Territory[]),
        apiClient.getCustomerRequirements(id).catch(() => [] as CustomerRequirement[]),
        apiClient.getCustomerLocationProposals(id).catch(() => [] as LocationProposal[]),
        apiClient.getBrands().catch(() => [] as Brand[]),
      ]);
      setCustomer(cust);
      setVisitHistory(Array.isArray(history) ? history : []);
      setAccount(acct);
      setOrders(Array.isArray(orderHistory) ? orderHistory : []);
      setTerritories(Array.isArray(territoryList) ? territoryList : []);
      setRequirements(Array.isArray(reqs) ? reqs : []);
      setProposals(Array.isArray(propsList) ? propsList : []);
      const brandNames = Array.isArray(brandsList)
        ? brandsList.map((b: any) => (typeof b === 'string' ? b : b.name))
        : [];
      setMasterBrands(brandNames);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load customer');
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const handleConfirmApproveProposal = async () => {
    if (!approvingProposal) return;
    setIsApproving(true);
    setApproveError(null);
    try {
      await apiClient.approveLocationProposal(approvingProposal.id);
      setApprovingProposal(null);
      load();
    } catch (err) {
      setApproveError(err instanceof Error ? err.message : 'Failed to approve proposal');
    } finally {
      setIsApproving(false);
    }
  };

  const handleRejectProposal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rejectingProposal) return;
    if (!rejectionReason.trim()) {
      alert('Please enter a rejection reason.');
      return;
    }
    setIsRejecting(true);
    try {
      await apiClient.rejectLocationProposal(rejectingProposal.id, rejectionReason.trim());
      setRejectingProposal(null);
      setRejectionReason('');
      load();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to reject proposal');
    } finally {
      setIsRejecting(false);
    }
  };

  const handleSaveRequirement = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id) return;
    setIsSavingReq(true);
    setReqError(null);
    try {
      const finalReqType =
        reqForm.requirement_type === 'Other'
          ? customReqType.trim() || 'Other'
          : reqForm.requirement_type.trim();

      await apiClient.createCustomerRequirement(id, {
        brand: reqForm.brand.trim() || undefined,
        requirement_type: finalReqType || undefined,
        product_details: reqForm.product_details.trim() || undefined,
        quantity: reqForm.quantity ? parseInt(reqForm.quantity, 10) : undefined,
        expected_value: reqForm.expected_value ? parseFloat(reqForm.expected_value) : undefined,
        follow_up_date: reqForm.follow_up_date || undefined,
        notes: reqForm.notes.trim() || undefined,
      });
      setIsAddReqOpen(false);
      setReqForm({
        brand: '',
        requirement_type: '',
        product_details: '',
        quantity: '',
        expected_value: '',
        follow_up_date: '',
        notes: '',
      });
      setCustomReqType('');
      load();
    } catch (err) {
      setReqError(err instanceof Error ? err.message : 'Failed to create requirement');
    } finally {
      setIsSavingReq(false);
    }
  };

  const handleRemoveBrandFromCustomer = async (brandToRemove: string) => {
    if (!customer) return;
    const updated = (customer.brands || []).filter(
      (b) => b.trim().toLowerCase() !== brandToRemove.trim().toLowerCase()
    );
    try {
      setBrandActionError(null);
      await apiClient.updateCustomer(customer.id, { brands: updated });
      setCustomer({ ...customer, brands: updated });
    } catch (err) {
      setBrandActionError(err instanceof Error ? err.message : 'Failed to remove brand');
    }
  };

  const handleBrandsChange = async (newBrands: string[]) => {
    if (!customer) return;
    setIsSavingBrands(true);
    setBrandActionError(null);
    try {
      await apiClient.updateCustomer(customer.id, { brands: newBrands });
      setCustomer({ ...customer, brands: newBrands });
      newBrands.forEach((b) => {
        if (!masterBrands.includes(b)) {
          setMasterBrands((prev) => [...prev, b].sort());
        }
      });
    } catch (err) {
      setBrandActionError(err instanceof Error ? err.message : 'Failed to update customer brands');
    } finally {
      setIsSavingBrands(false);
    }
  };

  const handleBrandCreated = async (newBrand: Brand) => {
    if (!masterBrands.includes(newBrand.name)) {
      setMasterBrands((prev) => [...prev, newBrand.name].sort());
    }
    if (brandContext === 'requirement') {
      setReqForm((prev) => ({ ...prev, brand: newBrand.name }));
    } else if (brandContext === 'customer' && customer) {
      const updatedBrands = Array.from(new Set([...(customer.brands || []), newBrand.name]));
      try {
        setBrandActionError(null);
        await apiClient.updateCustomer(customer.id, { brands: updatedBrands });
        setCustomer({ ...customer, brands: updatedBrands });
      } catch (err) {
        setBrandActionError(err instanceof Error ? err.message : 'Failed to associate brand');
      }
    }
  };

  const territoryName = territories.find((t) => t.id === customer?.territory_id)?.name;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64" role="status">
        <div className="w-10 h-10 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin" />
      </div>
    );
  }
  if (error) return <ErrorBanner message={error} onRetry={load} />;
  if (!customer) return <EmptyState title="Customer not found" subtitle="The requested customer could not be found." />;

  const locationStatus = customer.location_status || 'MISSING';

  return (
    <div className="space-y-space-6 max-w-7xl mx-auto">
      <PageHeader
        title={customer.name}
        subtitle="Customer profile, brand portfolio, location proposals, requirements, and visit history."
        actions={
          <button
            onClick={() => navigate('/customers')}
            className="flex items-center gap-2 text-sm text-on-surface-variant hover:text-on-surface cursor-pointer"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Customers
          </button>
        }
      />

      {/* Profile Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between w-full">
            <div>
              <CardTitle>Profile & Master Details</CardTitle>
              <CardSubtitle>Outlet identity, contact information, and brands</CardSubtitle>
            </div>
            <div>
              {locationStatus === 'VERIFIED' && (
                <span className="inline-flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-900 border border-emerald-300">
                  <ShieldCheck className="w-3.5 h-3.5" /> GPS VERIFIED
                </span>
              )}
              {locationStatus === 'PENDING_APPROVAL' && (
                <span className="inline-flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-full bg-amber-100 text-amber-900 border border-amber-300">
                  <Clock className="w-3.5 h-3.5" /> GPS PENDING APPROVAL
                </span>
              )}
              {locationStatus === 'NEEDS_REVIEW' && (
                <span className="inline-flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-full bg-orange-100 text-orange-900 border border-orange-300">
                  <AlertTriangle className="w-3.5 h-3.5" /> NEEDS REVIEW
                </span>
              )}
              {locationStatus === 'MISSING' && (
                <span className="inline-flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 border border-slate-300">
                  MISSING GPS
                </span>
              )}
            </div>
          </div>
        </CardHeader>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-5 text-sm">
          <div className="flex items-center gap-2">
            <Phone className="w-4 h-4 text-secondary-container shrink-0" />
            <span className="font-mono text-on-surface font-semibold">{customer.contact_number || '—'}</span>
          </div>
          <div className="flex items-center gap-2">
            <Building2 className="w-4 h-4 text-primary shrink-0" />
            <span className="text-on-surface">{customer.contact_person || '—'}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-label-md uppercase tracking-wider font-bold text-primary">GST No:</span>
            <span className="font-mono text-xs font-semibold text-on-surface">{customer.gst_number || '—'}</span>
          </div>
          <div className="flex items-center gap-2 md:col-span-2">
            <MapPin className="w-4 h-4 text-secondary-container shrink-0" />
            <span className="text-on-surface">{customer.address || '—'}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-label-md uppercase tracking-wider font-bold text-primary">Outlet Code:</span>
            <span className="font-mono text-xs font-bold text-on-primary-container bg-primary-container px-2 py-0.5 rounded shadow-2xs">
              {customer.outlet_code || customer.dms_code || '—'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Navigation className="w-4 h-4 text-primary shrink-0" />
            <span className="font-mono text-on-surface">
              {customer.location?.latitude != null && customer.location?.longitude != null ? (
                <a
                  href={`https://maps.google.com/?q=${customer.location.latitude},${customer.location.longitude}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline inline-flex items-center gap-1"
                >
                  {customer.location.latitude.toFixed(6)}, {customer.location.longitude.toFixed(6)}
                  <ExternalLink className="w-3 h-3" />
                </a>
              ) : (
                'Missing GPS'
              )}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-label-md uppercase tracking-wider font-bold text-primary">Geofence:</span>
            <span className="font-label-md text-xs font-bold text-primary bg-primary-fixed/60 px-2 py-0.5 rounded border border-primary-fixed-dim">
              {customer.geofence_radius_m || 75}m
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-label-md uppercase tracking-wider font-bold text-primary">Zone / Area:</span>
            <span className="text-on-surface font-semibold">
              {territoryName || '—'} / {customer.area_name || '—'}
            </span>
          </div>
        </div>

        {/* Brand Action Error Feedback */}
        {brandActionError && (
          <div className="mx-5 mb-2">
            <ErrorBanner message={brandActionError} />
          </div>
        )}

        {/* Brand Badges Bar */}
        <div className="px-5 pb-5 pt-3 border-t border-surface-container-highest flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant flex items-center gap-1.5">
              <Tag className="w-3.5 h-3.5 text-primary" /> Associated Brands:
            </span>
            {customer.brands && customer.brands.length > 0 ? (
              customer.brands.map((b) => (
                <span
                  key={b}
                  className="inline-flex items-center gap-1.5 text-xs font-bold bg-primary/10 text-primary px-2.5 py-1 rounded-md border border-primary/20 shadow-2xs"
                >
                  <span>{b}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveBrandFromCustomer(b)}
                    className="text-primary/50 hover:text-rose-600 hover:bg-rose-100 rounded-full p-0.5 transition-colors cursor-pointer"
                    title={`Remove ${b} from customer`}
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))
            ) : (
              <span className="text-xs text-on-surface-variant italic">No brands explicitly tagged</span>
            )}
          </div>
          <button
            type="button"
            onClick={() => {
              setBrandActionError(null);
              setIsManageBrandsOpen(true);
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold text-secondary hover:bg-secondary/10 border border-secondary/30 transition-colors shadow-2xs cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Manage Brands</span>
          </button>
        </div>
      </Card>

      {/* Location Proposals & Verification Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between w-full">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Navigation className="w-5 h-5 text-primary" />
                Location Verification & Proposals History
              </CardTitle>
              <CardSubtitle>Field employee GPS suggestions and admin review lifecycle</CardSubtitle>
            </div>
          </div>
        </CardHeader>
        {proposals.length === 0 ? (
          <div className="p-5">
            <p className="text-xs text-on-surface-variant">No location update proposals submitted for this customer.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-surface-container-low text-on-surface-variant uppercase tracking-wider border-b border-surface-container-highest">
                <tr>
                  <th className="px-4 py-3 font-bold text-primary">Proposed GPS</th>
                  <th className="px-4 py-3 font-bold text-primary">Accuracy</th>
                  <th className="px-4 py-3 font-bold text-primary">Submitted By</th>
                  <th className="px-4 py-3 font-bold text-primary">Submitted At</th>
                  <th className="px-4 py-3 font-bold text-primary">Status</th>
                  <th className="px-4 py-3 font-bold text-primary">Review Details</th>
                  <th className="px-4 py-3 font-bold text-primary text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-container-highest">
                {proposals.map((p) => (
                  <tr key={p.id} className="hover:bg-surface-container-low/80">
                    <td className="px-4 py-3 font-mono font-semibold text-primary">
                      <a
                        href={`https://maps.google.com/?q=${p.proposed_latitude},${p.proposed_longitude}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:underline inline-flex items-center gap-1"
                      >
                        {p.proposed_latitude.toFixed(6)}, {p.proposed_longitude.toFixed(6)}
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    </td>
                    <td className="px-4 py-3 font-mono">
                      {p.gps_accuracy_meters != null ? `±${Math.round(p.gps_accuracy_meters)}m` : '—'}
                    </td>
                    <td className="px-4 py-3">{p.submitter_name || 'Employee'}</td>
                    <td className="px-4 py-3 text-on-surface-variant">{new Date(p.submitted_at).toLocaleString()}</td>
                    <td className="px-4 py-3">
                      {p.status === 'PENDING' && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold bg-amber-100 text-amber-900 border border-amber-300 rounded-full">
                          <Clock className="w-3 h-3" /> PENDING
                        </span>
                      )}
                      {p.status === 'APPROVED' && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold bg-emerald-100 text-emerald-900 border border-emerald-300 rounded-full">
                          <ShieldCheck className="w-3 h-3" /> APPROVED
                        </span>
                      )}
                      {p.status === 'REJECTED' && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold bg-rose-100 text-rose-900 border border-rose-300 rounded-full">
                          <X className="w-3 h-3" /> REJECTED
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 max-w-xs truncate">
                      {p.rejection_reason && <span className="text-rose-700 font-medium">Reason: {p.rejection_reason}</span>}
                      {p.reviewer_name && <span className="text-on-surface-variant block text-[11px]">Reviewed by {p.reviewer_name}</span>}
                      {!p.rejection_reason && !p.reviewer_name && '—'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {p.status === 'PENDING' && (
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => {
                              setApprovingProposal(p);
                              setApproveError(null);
                            }}
                            className="p-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded cursor-pointer"
                            title="Approve Location"
                          >
                            <Check className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => {
                              setRejectingProposal(p);
                              setRejectionReason('');
                            }}
                            className="p-1 bg-rose-600 hover:bg-rose-700 text-white rounded cursor-pointer"
                            title="Reject Location"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Customer Requirements & Opportunities Card */}
      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 w-full">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Briefcase className="w-5 h-5 text-primary" />
                Business Requirements & Opportunities
              </CardTitle>
              <CardSubtitle>Tracked order demands, product stock requirements, and follow-ups</CardSubtitle>
            </div>
            <Button
              variant="secondary"
              size="sm"
              icon={Plus}
              onClick={() => {
                setReqError(null);
                if (!reqForm.brand && customer.brands && customer.brands.length > 0) {
                  setReqForm((prev) => ({ ...prev, brand: customer.brands![0] }));
                }
                setIsAddReqOpen(true);
              }}
              className="shrink-0 font-bold shadow-xs"
            >
              Add Requirement
            </Button>
          </div>
        </CardHeader>
        {requirements.length === 0 ? (
          <div className="p-5">
            <EmptyState
              icon={Briefcase}
              title="No Requirements Registered"
              subtitle="Capture business requirements and orders requested by this customer."
              action={
                <Button variant="secondary" size="sm" icon={Plus} onClick={() => setIsAddReqOpen(true)}>
                  Add Requirement
                </Button>
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-surface-container-low text-on-surface-variant uppercase tracking-wider border-b border-surface-container-highest">
                <tr>
                  <th className="px-4 py-3 font-bold text-primary">Brand</th>
                  <th className="px-4 py-3 font-bold text-primary">Type</th>
                  <th className="px-4 py-3 font-bold text-primary">Product Details</th>
                  <th className="px-4 py-3 font-bold text-primary">Requested Qty & Value</th>
                  <th className="px-4 py-3 font-bold text-primary">Approved Allocation</th>
                  <th className="px-4 py-3 font-bold text-primary">Follow-up Date</th>
                  <th className="px-4 py-3 font-bold text-primary">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-container-highest">
                {requirements.map((req) => (
                  <tr key={req.id} className="hover:bg-surface-container-low/80">
                    <td className="px-4 py-3 font-bold text-primary">
                      <span className="bg-primary/10 text-primary px-2 py-0.5 rounded font-semibold">{req.brand || '—'}</span>
                    </td>
                    <td className="px-4 py-3">{req.requirement_type || 'General'}</td>
                    <td className="px-4 py-3 max-w-xs">{req.product_details || req.notes || '—'}</td>
                    <td className="px-4 py-3 font-mono">
                      <div>{req.quantity != null ? `${req.quantity} units` : '—'}</div>
                      <div className="font-semibold text-primary">
                        {req.expected_value != null ? `₹${Number(req.expected_value).toLocaleString('en-IN')}` : '—'}
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono">
                      {req.status === 'PARTIALLY_APPROVED' ? (
                        <div>
                          <div className="font-bold text-secondary-container">{req.approved_quantity != null ? `${req.approved_quantity} units` : '—'}</div>
                          <div className="text-secondary-container font-semibold">
                            {req.approved_value != null ? `₹${Number(req.approved_value).toLocaleString('en-IN')}` : '—'}
                          </div>
                        </div>
                      ) : req.status === 'APPROVED' ? (
                        <div>
                          <div className="font-bold text-emerald-700">{req.approved_quantity != null ? `${req.approved_quantity} units` : `${req.quantity} units`}</div>
                          <div className="text-emerald-700 font-semibold">
                            {req.approved_value != null
                              ? `₹${Number(req.approved_value).toLocaleString('en-IN')}`
                              : req.expected_value != null
                              ? `₹${Number(req.expected_value).toLocaleString('en-IN')}`
                              : '—'}
                          </div>
                        </div>
                      ) : (
                        <span className="text-on-surface-variant/50 text-[11px]">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-on-surface-variant font-mono">
                      {req.follow_up_date || '—'}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={req.status} size="sm" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {account && <AccountSummaryCard account={account} />}

      {/* Order History */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle className="flex items-center gap-2">
              <PackagePlus className="w-5 h-5 text-primary" />
              Order History
            </CardTitle>
            <CardSubtitle>{orders.length} order{orders.length !== 1 ? 's' : ''} captured across this outlet's visits</CardSubtitle>
          </div>
        </CardHeader>
        {orders.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={PackagePlus} title="No orders captured" subtitle="Orders captured during field visits to this outlet will appear here." />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-surface-container-low text-on-surface-variant uppercase tracking-wider border-b border-surface-container-highest">
                <tr>
                  <th className="px-4 py-3 font-bold text-primary">Date</th>
                  <th className="px-4 py-3 font-bold text-primary">Employee</th>
                  <th className="px-4 py-3 font-bold text-primary">Note</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-container-highest">
                {orders.map((order) => (
                  <tr key={order.id} className="hover:bg-surface-container-low/80">
                    <td className="px-4 py-3 text-on-surface-variant">
                      {new Date(order.uploaded_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">{order.employee_name || '—'}</td>
                    <td className="px-4 py-3 max-w-md truncate" title={order.note || ''}>
                      {order.note || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Visit History */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle className="flex items-center gap-2">
              <Calendar className="w-5 h-5 text-primary" />
              Visit History
            </CardTitle>
            <CardSubtitle>{visitHistory.length} visit{visitHistory.length !== 1 ? 's' : ''} recorded</CardSubtitle>
          </div>
        </CardHeader>
        {visitHistory.length === 0 ? (
          <div className="p-5">
            <EmptyState title="No visits recorded" subtitle="No visits have been scheduled or completed for this customer yet." />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-surface-container-low text-on-surface-variant uppercase tracking-wider border-b border-surface-container-highest">
                <tr>
                  <th className="px-4 py-3 font-bold text-primary">Visit ID</th>
                  <th className="px-4 py-3 font-bold text-primary">Scheduled</th>
                  <th className="px-4 py-3 font-bold text-primary">Status</th>
                  <th className="px-4 py-3 font-bold text-primary">Employee</th>
                  <th className="px-4 py-3 font-bold text-primary">Check-In</th>
                  <th className="px-4 py-3 font-bold text-primary">Check-Out</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-container-highest">
                {visitHistory.map((row) => (
                  <tr key={row.visit_id} className="hover:bg-surface-container-low/80">
                    <td className="px-4 py-3 font-mono text-on-surface-variant">
                      {row.visit_id.substring(0, 8)}...
                    </td>
                    <td className="px-4 py-3">
                      {new Date(row.scheduled_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={row.status} size="sm" />
                    </td>
                    <td className="px-4 py-3">{row.employee_name}</td>
                    <td className="px-4 py-3 text-on-surface-variant">
                      {row.check_in_at ? new Date(row.check_in_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3 text-on-surface-variant">
                      {row.check_out_at ? new Date(row.check_out_at).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Add Requirement Modal */}
      {isAddReqOpen && (
        <Modal
          isOpen={true}
          onClose={() => setIsAddReqOpen(false)}
          title={`Add Business Requirement: ${customer.name}`}
        >
          {reqError && <ErrorBanner message={reqError} />}
          <form onSubmit={handleSaveRequirement} className="space-y-4 text-xs">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Select
                label="Target Brand"
                value={reqForm.brand}
                onChange={(e) => {
                  if (e.target.value === '__ADD_NEW_BRAND__') {
                    setBrandContext('requirement');
                    setIsAddBrandOpen(true);
                  } else {
                    setReqForm({ ...reqForm, brand: e.target.value });
                  }
                }}
              >
                <option value="">-- Select Brand --</option>
                {customer.brands && customer.brands.length > 0 && (
                  <optgroup label="Associated Brands">
                    {customer.brands.map((b) => (
                      <option key={`assoc-${b}`} value={b}>
                        ★ {b} (Associated)
                      </option>
                    ))}
                  </optgroup>
                )}
                <optgroup label="All Master Brands">
                  {masterBrands
                    .filter((b) => !(customer.brands || []).includes(b))
                    .map((b) => (
                      <option key={`master-${b}`} value={b}>
                        {b}
                      </option>
                    ))}
                </optgroup>
                <option value="__ADD_NEW_BRAND__" className="font-bold text-secondary">
                  + Register New Brand...
                </option>
              </Select>

              <Select
                label="Requirement Type"
                value={reqForm.requirement_type}
                onChange={(e) => setReqForm({ ...reqForm, requirement_type: e.target.value })}
              >
                <option value="">-- Select Type --</option>
                <option value="Initial Dealership & Stock">Initial Dealership &amp; Stock</option>
                <option value="Regular Stock Refill">Regular Stock Refill</option>
                <option value="Display Unit / POSM Setup">Display Unit / POSM Setup</option>
                <option value="Product Replacement / Warranty">Product Replacement / Warranty</option>
                <option value="Pricing & Scheme Inquiry">Pricing &amp; Scheme Inquiry</option>
                <option value="Bulk / Festive Demand">Bulk / Festive Demand</option>
                <option value="New Product Launch">New Product Launch</option>
                <option value="Other">Other / Custom</option>
              </Select>
            </div>

            {reqForm.requirement_type === 'Other' && (
              <Input
                label="Specify Custom Requirement Type"
                type="text"
                value={customReqType}
                onChange={(e) => setCustomReqType(e.target.value)}
                placeholder="e.g. Annual Dealership Contract Renewal"
                autoFocus
              />
            )}

            <Input
              label="Product / SKU Details *"
              type="text"
              required
              value={reqForm.product_details}
              onChange={(e) => setReqForm({ ...reqForm, product_details: e.target.value })}
              placeholder="e.g. 50 Ceiling Fans, 20 Water Heaters (Model X)"
              helperText="Specify models, variants, sizes or specific SKU requirements"
            />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Input
                label="Estimated Quantity"
                type="number"
                min={1}
                value={reqForm.quantity}
                onChange={(e) => setReqForm({ ...reqForm, quantity: e.target.value })}
                placeholder="e.g. 25"
              />
              <Input
                label="Expected Value (₹)"
                type="number"
                step="any"
                value={reqForm.expected_value}
                onChange={(e) => setReqForm({ ...reqForm, expected_value: e.target.value })}
                placeholder="e.g. 150000"
                helperText={
                  reqForm.expected_value && !isNaN(Number(reqForm.expected_value))
                    ? `Value: ₹${Number(reqForm.expected_value).toLocaleString('en-IN')}`
                    : undefined
                }
              />
            </div>

            <Input
              label="Follow-up / Target Date"
              type="date"
              value={reqForm.follow_up_date}
              onChange={(e) => setReqForm({ ...reqForm, follow_up_date: e.target.value })}
            />

            <Textarea
              label="Field Notes & Observations"
              value={reqForm.notes}
              onChange={(e) => setReqForm({ ...reqForm, notes: e.target.value })}
              placeholder="e.g. Retailer interested in festive discount scheme; requires delivery by next Friday."
              rows={3}
            />

            <div className="flex justify-end gap-2 pt-3 border-t border-surface-container-highest">
              <Button variant="outline" onClick={() => setIsAddReqOpen(false)} disabled={isSavingReq}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" isLoading={isSavingReq}>
                Save Requirement
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {/* Manage Associated Brands Modal */}
      {isManageBrandsOpen && customer && (
        <Modal
          isOpen={true}
          onClose={() => setIsManageBrandsOpen(false)}
          title={`Manage Brands: ${customer.name}`}
        >
          {brandActionError && <ErrorBanner message={brandActionError} />}
          <div className="space-y-4 text-xs">
            <p className="text-on-surface-variant">
              Tag the product brands carried, sold, or serviced by this outlet. Selected brands appear on visit logs, requirement filters, and reporting.
            </p>

            <BrandSelect
              label="Associated Brands"
              selectedBrands={customer.brands || []}
              onChange={handleBrandsChange}
              disabled={isSavingBrands}
              placeholder="Search or select master brands..."
            />

            <div className="flex justify-end gap-2 pt-3 border-t border-surface-container-highest">
              <Button
                variant="primary"
                onClick={() => setIsManageBrandsOpen(false)}
              >
                Done
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Approve Proposal Modal */}
      {approvingProposal && (
        <Modal
          isOpen={true}
          onClose={() => setApprovingProposal(null)}
          title="Approve Location Proposal"
        >
          <div className="space-y-4 text-xs">
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-800">
              <p className="font-bold">Update Official Coordinates</p>
              <p className="mt-1">
                Approving this proposal will update the customer's official GPS coordinates and mark them as VERIFIED.
              </p>
            </div>

            <div className="p-3 bg-surface-container rounded-lg border border-outline-variant space-y-1.5 font-caption">
              <div className="flex justify-between">
                <span className="text-on-surface-variant font-medium">Proposed GPS:</span>
                <span className="font-mono font-bold text-emerald-600">
                  {approvingProposal.proposed_latitude.toFixed(6)}, {approvingProposal.proposed_longitude.toFixed(6)}
                </span>
              </div>
              {approvingProposal.gps_accuracy_meters != null && (
                <div className="flex justify-between">
                  <span className="text-on-surface-variant font-medium">Capture Accuracy:</span>
                  <span className="font-mono">±{Math.round(approvingProposal.gps_accuracy_meters)}m</span>
                </div>
              )}
              {approvingProposal.submitter_name && (
                <div className="flex justify-between">
                  <span className="text-on-surface-variant font-medium">Submitted By:</span>
                  <span>{approvingProposal.submitter_name}</span>
                </div>
              )}
            </div>

            {approveError && <ErrorBanner message={approveError} />}

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setApprovingProposal(null)} disabled={isApproving}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleConfirmApproveProposal}
                isLoading={isApproving}
                className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold"
              >
                Confirm &amp; Update Location
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Reject Proposal Modal */}
      {rejectingProposal && (
        <Modal
          isOpen={true}
          onClose={() => setRejectingProposal(null)}
          title="Reject Location Proposal"
        >
          <form onSubmit={handleRejectProposal} className="space-y-4 text-xs">
            <p className="text-on-surface-variant">
              Please enter a reason for rejecting this proposed location ({rejectingProposal.proposed_latitude.toFixed(6)}, {rejectingProposal.proposed_longitude.toFixed(6)}).
            </p>
            <div>
              <label className="block font-bold text-on-surface mb-1">
                Rejection Reason <span className="text-rose-600">*</span>
              </label>
              <textarea
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="e.g. Coordinates outside boundary of this outlet."
                rows={3}
                className="w-full p-2 rounded border border-outline bg-surface text-on-surface"
                required
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setRejectingProposal(null)} disabled={isRejecting}>
                Cancel
              </Button>
              <Button type="submit" variant="danger" isLoading={isRejecting}>
                Confirm Rejection
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {/* Add Brand Modal */}
      <AddBrandModal
        isOpen={isAddBrandOpen}
        onClose={() => setIsAddBrandOpen(false)}
        onBrandCreated={handleBrandCreated}
      />
    </div>
  );
};
