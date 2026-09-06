import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ClipboardList,
  Clock,
  CheckCircle2,
  AlertCircle,
  XCircle,
  Eye,
  Search,
  Building2,
  Calendar,
  User,
  Image as ImageIcon,
  ShieldAlert,
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { MetricCard } from '../components/ui/MetricCard';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Textarea } from '../components/ui/Textarea';
import { Modal } from '../components/ui/Modal';
import { StatusBadge } from '../components/ui/StatusBadge';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { EmptyState } from '../components/ui/EmptyState';
import { apiClient } from '../api/client';
import { CustomerRequirement } from '../types';

const formatCurrency = (val?: number | null): string => {
  if (val == null) return '—';
  return `₹${Number(val).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
};

const formatDate = (isoStr?: string | null): string => {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    return d.toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return isoStr;
  }
};

const formatDateTime = (isoStr?: string | null): string => {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    return d.toLocaleString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoStr;
  }
};

export const RequirementsPage: React.FC = () => {
  const [requirements, setRequirements] = useState<CustomerRequirement[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  // Selected requirement for modal view & decision
  const [selectedReq, setSelectedReq] = useState<CustomerRequirement | null>(null);
  const [decisionTab, setDecisionTab] = useState<'APPROVE' | 'PARTIALLY_APPROVE' | 'REJECT'>('APPROVE');
  const [approvedQty, setApprovedQty] = useState<string>('');
  const [approvedVal, setApprovedVal] = useState<string>('');
  const [adminNotes, setAdminNotes] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Image preview modal
  const [previewImage, setPreviewImage] = useState<string | null>(null);

  const loadRequirements = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getAllRequirements();
      setRequirements(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch customer requirements');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRequirements();
  }, [loadRequirements]);

  // Compute KPI counts
  const kpis = useMemo(() => {
    let total = requirements.length;
    let pending = 0;
    let partiallyApproved = 0;
    let approved = 0;
    let rejected = 0;

    for (const r of requirements) {
      const s = (r.status || '').toUpperCase();
      if (s === 'PENDING' || s === 'OPEN') pending++;
      else if (s === 'PARTIALLY_APPROVED') partiallyApproved++;
      else if (s === 'APPROVED') approved++;
      else if (s === 'REJECTED') rejected++;
    }

    return { total, pending, partiallyApproved, approved, rejected };
  }, [requirements]);

  // Filtered requirements list
  const filteredRequirements = useMemo(() => {
    return requirements.filter((req) => {
      // Status filter
      const reqStatus = (req.status || '').toUpperCase();
      if (statusFilter === 'PENDING' && reqStatus !== 'PENDING' && reqStatus !== 'OPEN') {
        return false;
      }
      if (statusFilter === 'PARTIALLY_APPROVED' && reqStatus !== 'PARTIALLY_APPROVED') {
        return false;
      }
      if (statusFilter === 'APPROVED' && reqStatus !== 'APPROVED') {
        return false;
      }
      if (statusFilter === 'REJECTED' && reqStatus !== 'REJECTED') {
        return false;
      }

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const customerName = (req.customer_name || '').toLowerCase();
        const outletCode = (req.outlet_code || '').toLowerCase();
        const brand = (req.brand || '').toLowerCase();
        const productDetails = (req.product_details || '').toLowerCase();
        const employeeName = (req.employee_name || req.creator_name || '').toLowerCase();
        const notes = (req.notes || '').toLowerCase();
        const adminNotesStr = (req.admin_notes || '').toLowerCase();

        return (
          customerName.includes(q) ||
          outletCode.includes(q) ||
          brand.includes(q) ||
          productDetails.includes(q) ||
          employeeName.includes(q) ||
          notes.includes(q) ||
          adminNotesStr.includes(q)
        );
      }

      return true;
    });
  }, [requirements, statusFilter, searchQuery]);

  // Open requirement detail & decision modal
  const handleOpenDetail = (req: CustomerRequirement) => {
    setSelectedReq(req);
    setActionError(null);
    setActionSuccess(null);

    // If already partially approved, prepopulate the values
    if (req.status === 'PARTIALLY_APPROVED') {
      setDecisionTab('PARTIALLY_APPROVE');
      setApprovedQty(req.approved_quantity != null ? String(req.approved_quantity) : '');
      setApprovedVal(req.approved_value != null ? String(req.approved_value) : '');
    } else if (req.status === 'REJECTED') {
      setDecisionTab('REJECT');
      setApprovedQty('');
      setApprovedVal('');
    } else {
      setDecisionTab('APPROVE');
      setApprovedQty(req.quantity != null ? String(req.quantity) : '');
      setApprovedVal(req.expected_value != null ? String(req.expected_value) : '');
    }

    setAdminNotes(req.admin_notes || '');
  };

  const handleCloseDetail = () => {
    setSelectedReq(null);
    setActionError(null);
    setActionSuccess(null);
    setIsSubmitting(false);
  };

  // Submit decision
  const handleSubmitDecision = async () => {
    if (!selectedReq) return;
    setIsSubmitting(true);
    setActionError(null);
    setActionSuccess(null);

    try {
      let updated: CustomerRequirement;

      if (decisionTab === 'APPROVE') {
        const q = approvedQty.trim() !== '' ? Number(approvedQty) : undefined;
        const v = approvedVal.trim() !== '' ? Number(approvedVal) : undefined;
        updated = await apiClient.approveRequirement(selectedReq.id, {
          approved_quantity: q,
          approved_value: v,
          admin_notes: adminNotes.trim() || undefined,
        });
        setActionSuccess('Requirement successfully approved in full.');
      } else if (decisionTab === 'PARTIALLY_APPROVE') {
        const q = Number(approvedQty);
        const v = Number(approvedVal);

        if (isNaN(q) || q <= 0) {
          throw new Error('Please enter a valid approved quantity greater than 0.');
        }
        if (isNaN(v) || v <= 0) {
          throw new Error('Please enter a valid approved value (₹) greater than 0.');
        }

        updated = await apiClient.partiallyApproveRequirement(selectedReq.id, {
          approved_quantity: q,
          approved_value: v,
          admin_notes: adminNotes.trim() || undefined,
        });
        setActionSuccess('Requirement partially approved successfully.');
      } else {
        // REJECT
        updated = await apiClient.rejectRequirement(selectedReq.id, {
          admin_notes: adminNotes.trim() || undefined,
        });
        setActionSuccess('Requirement rejected.');
      }

      // Update in local state
      setRequirements((prev) =>
        prev.map((item) => (item.id === updated.id ? { ...item, ...updated } : item))
      );
      setSelectedReq(updated);

      // Auto close after 1.2s or let admin review
      setTimeout(() => {
        handleCloseDetail();
      }, 1400);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to record decision');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Page Header */}
      <PageHeader
        title="Customer Requirements"
        subtitle="Review, approve, partially allocate, or reject customer order requests and product indents submitted by field reps."
      />

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <MetricCard
          title="Total Requests"
          value={kpis.total}
          icon={ClipboardList}
          color="slate"
          onClick={() => setStatusFilter('ALL')}
        />
        <MetricCard
          title="Pending Review"
          value={kpis.pending}
          icon={Clock}
          color="amber"
          onClick={() => setStatusFilter('PENDING')}
        />
        <MetricCard
          title="Partially Approved"
          value={kpis.partiallyApproved}
          icon={AlertCircle}
          color="secondary"
          onClick={() => setStatusFilter('PARTIALLY_APPROVED')}
        />
        <MetricCard
          title="Approved"
          value={kpis.approved}
          icon={CheckCircle2}
          color="emerald"
          onClick={() => setStatusFilter('APPROVED')}
        />
        <MetricCard
          title="Rejected"
          value={kpis.rejected}
          icon={XCircle}
          color="rose"
          onClick={() => setStatusFilter('REJECTED')}
        />
      </div>

      {/* Filters and Search Bar */}
      <Card className="!p-4">
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
          {/* Status Filter Tabs */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0 text-xs">
            {[
              { id: 'ALL', label: 'All Requests', count: kpis.total },
              { id: 'PENDING', label: 'Pending Review', count: kpis.pending },
              { id: 'PARTIALLY_APPROVED', label: 'Partially Approved', count: kpis.partiallyApproved },
              { id: 'APPROVED', label: 'Approved', count: kpis.approved },
              { id: 'REJECTED', label: 'Rejected', count: kpis.rejected },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setStatusFilter(tab.id)}
                className={`px-3 py-1.5 rounded-lg font-medium transition-all shrink-0 flex items-center gap-1.5 ${
                  statusFilter === tab.id
                    ? 'bg-primary text-on-primary shadow-xs font-semibold'
                    : 'bg-surface-container text-on-surface-variant hover:bg-surface-container-high'
                }`}
              >
                <span>{tab.label}</span>
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                    statusFilter === tab.id
                      ? 'bg-on-primary/20 text-on-primary'
                      : 'bg-surface-container-highest text-on-surface-variant'
                  }`}
                >
                  {tab.count}
                </span>
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div className="relative w-full md:w-72 shrink-0">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant" />
            <input
              type="text"
              placeholder="Search outlet, product, rep..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-surface-container border border-outline-variant rounded-lg focus:outline-hidden focus:border-primary text-on-surface placeholder:text-on-surface-variant"
            />
          </div>
        </div>
      </Card>

      {/* Main Requirements Table */}
      <Card className="!p-0 overflow-hidden">
        {isLoading ? (
          <div className="p-12 flex flex-col items-center justify-center text-on-surface-variant">
            <div className="w-8 h-8 border-3 border-primary-container border-t-primary rounded-full animate-spin mb-3" />
            <p className="text-xs">Loading customer requirements...</p>
          </div>
        ) : filteredRequirements.length === 0 ? (
          <div className="p-8">
            <EmptyState
              icon={ClipboardList}
              title="No Requirements Found"
              subtitle={
                searchQuery || statusFilter !== 'ALL'
                  ? 'No customer requirements match the selected filters or search keyword.'
                  : 'Customer requirements captured during field visits will appear here for admin review.'
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-surface-container-low text-on-surface-variant uppercase tracking-wider font-semibold border-b border-surface-container-highest">
                <tr>
                  <th className="px-4 py-3">Customer / Outlet</th>
                  <th className="px-4 py-3">Field Rep / Date</th>
                  <th className="px-4 py-3">Brand & Product</th>
                  <th className="px-4 py-3 text-right">Requested Qty & Value</th>
                  <th className="px-4 py-3 text-right">Admin Approved</th>
                  <th className="px-4 py-3 text-center">Photo</th>
                  <th className="px-4 py-3 text-center">Status</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-container-highest">
                {filteredRequirements.map((req) => {
                  const isPartial = req.status === 'PARTIALLY_APPROVED';
                  const isApproved = req.status === 'APPROVED';

                  return (
                    <tr
                      key={req.id}
                      className="hover:bg-surface-container-low/70 transition-colors"
                    >
                      {/* Customer / Outlet */}
                      <td className="px-4 py-3">
                        <div className="font-semibold text-on-surface text-sm">
                          {req.customer_name || '—'}
                        </div>
                        <div className="text-[11px] text-on-surface-variant flex items-center gap-1 mt-0.5">
                          <Building2 className="w-3 h-3 shrink-0" />
                          <span>Code: {req.outlet_code || '—'}</span>
                        </div>
                      </td>

                      {/* Rep / Date */}
                      <td className="px-4 py-3">
                        <div className="text-on-surface flex items-center gap-1">
                          <User className="w-3 h-3 text-on-surface-variant shrink-0" />
                          <span>{req.employee_name || req.creator_name || 'Field Rep'}</span>
                        </div>
                        <div className="text-[11px] text-on-surface-variant flex items-center gap-1 mt-0.5">
                          <Calendar className="w-3 h-3 shrink-0" />
                          <span>{formatDate(req.created_at)}</span>
                        </div>
                      </td>

                      {/* Brand & Product */}
                      <td className="px-4 py-3 max-w-xs">
                        <div className="flex items-center gap-1.5 mb-0.5">
                          {req.brand && (
                            <span className="bg-primary/10 text-primary font-bold px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide">
                              {req.brand}
                            </span>
                          )}
                          {req.requirement_type && (
                            <span className="text-[10px] text-on-surface-variant">
                              • {req.requirement_type}
                            </span>
                          )}
                        </div>
                        <div className="font-medium text-on-surface truncate">
                          {req.product_details || '—'}
                        </div>
                        {req.notes && (
                          <div className="text-[11px] text-on-surface-variant italic truncate mt-0.5">
                            "{req.notes}"
                          </div>
                        )}
                      </td>

                      {/* Requested Qty & Value */}
                      <td className="px-4 py-3 text-right font-mono">
                        <div className="font-bold text-on-surface">
                          {req.quantity != null ? `${req.quantity} units` : '—'}
                        </div>
                        <div className="text-primary font-semibold">
                          {formatCurrency(req.expected_value)}
                        </div>
                      </td>

                      {/* Admin Approved */}
                      <td className="px-4 py-3 text-right font-mono">
                        {isPartial ? (
                          <div>
                            <div className="font-bold text-secondary-container">
                              {req.approved_quantity != null ? `${req.approved_quantity} units` : '—'}
                            </div>
                            <div className="text-secondary-container font-semibold">
                              {formatCurrency(req.approved_value)}
                            </div>
                            <span className="inline-block text-[9px] font-bold text-amber-700 bg-amber-100 px-1 rounded mt-0.5">
                              Partial
                            </span>
                          </div>
                        ) : isApproved ? (
                          <div>
                            <div className="font-bold text-emerald-700">
                              {req.approved_quantity != null
                                ? `${req.approved_quantity} units`
                                : `${req.quantity} units`}
                            </div>
                            <div className="text-emerald-700 font-semibold">
                              {formatCurrency(req.approved_value ?? req.expected_value)}
                            </div>
                          </div>
                        ) : req.status === 'REJECTED' ? (
                          <span className="text-error font-medium text-[11px]">Rejected</span>
                        ) : (
                          <span className="text-on-surface-variant/60 text-[11px] italic">
                            Awaiting review
                          </span>
                        )}
                      </td>

                      {/* Photo Thumbnail */}
                      <td className="px-4 py-3 text-center">
                        {req.photo_url ? (
                          <button
                            onClick={() => setPreviewImage(req.photo_url || null)}
                            className="relative group inline-block rounded border border-outline-variant overflow-hidden hover:ring-2 hover:ring-primary transition-all"
                            title="Click to zoom requirement indent image"
                          >
                            <img
                              src={req.photo_url}
                              alt="Requirement Indent"
                              className="w-10 h-10 object-cover"
                            />
                            <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity text-white">
                              <Eye className="w-3.5 h-3.5" />
                            </div>
                          </button>
                        ) : (
                          <span className="text-on-surface-variant/40 text-[11px]">—</span>
                        )}
                      </td>

                      {/* Status */}
                      <td className="px-4 py-3 text-center">
                        <StatusBadge status={req.status} size="sm" />
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-3 text-right">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => handleOpenDetail(req)}
                          className="!py-1 !px-2.5 !text-xs font-semibold"
                        >
                          Review & Decide
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Review & Decision Modal */}
      {selectedReq && (
        <Modal
          isOpen={Boolean(selectedReq)}
          onClose={handleCloseDetail}
          title={`Review Requirement #${selectedReq.id.slice(0, 8)}`}
          size="xl"
        >
          <div className="space-y-5 text-xs">
            {/* Header info strip */}
            <div className="bg-surface-container-low p-3.5 rounded-lg border border-surface-container-highest flex flex-wrap items-center justify-between gap-3">
              <div>
                <span className="text-on-surface-variant font-medium">Customer:</span>{' '}
                <span className="font-bold text-on-surface text-sm ml-1">
                  {selectedReq.customer_name || '—'}
                </span>
                <span className="text-on-surface-variant text-[11px] ml-2">
                  (Outlet: {selectedReq.outlet_code || '—'})
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-on-surface-variant">Current Status:</span>
                <StatusBadge status={selectedReq.status} size="sm" />
              </div>
            </div>

            {actionError && <ErrorBanner message={actionError} onDismiss={() => setActionError(null)} />}
            {actionSuccess && (
              <div className="p-3 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded-lg flex items-center gap-2 font-medium">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>{actionSuccess}</span>
              </div>
            )}

            {/* Two-column layout: Left = Immutable Field Request, Right = Admin Decision */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {/* Left Column: Immutable Request */}
              <div className="space-y-3 bg-surface-container-low/40 p-4 rounded-xl border border-surface-container-highest">
                <div className="flex items-center justify-between pb-2 border-b border-surface-container-highest">
                  <h3 className="font-bold text-primary flex items-center gap-1.5 uppercase tracking-wider text-[11px]">
                    <ClipboardList className="w-4 h-4 text-primary" />
                    Original Field Request (Preserved)
                  </h3>
                  <span className="text-[10px] bg-surface-container text-on-surface-variant px-2 py-0.5 rounded font-mono">
                    Read-Only
                  </span>
                </div>

                <div className="space-y-2.5">
                  <div>
                    <span className="text-on-surface-variant block text-[10px] uppercase font-semibold">
                      Brand & Product Details
                    </span>
                    <div className="font-bold text-on-surface text-sm mt-0.5">
                      {selectedReq.brand ? `[${selectedReq.brand}] ` : ''}
                      {selectedReq.product_details || '—'}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3 pt-1">
                    <div className="bg-surface p-2.5 rounded-lg border border-surface-container">
                      <span className="text-on-surface-variant block text-[10px] uppercase font-semibold">
                        Requested Quantity
                      </span>
                      <span className="font-headline-sm text-base font-bold text-on-surface font-mono">
                        {selectedReq.quantity != null ? `${selectedReq.quantity} units` : '—'}
                      </span>
                    </div>
                    <div className="bg-surface p-2.5 rounded-lg border border-surface-container">
                      <span className="text-on-surface-variant block text-[10px] uppercase font-semibold">
                        Expected Value
                      </span>
                      <span className="font-headline-sm text-base font-bold text-primary font-mono">
                        {formatCurrency(selectedReq.expected_value)}
                      </span>
                    </div>
                  </div>

                  <div>
                    <span className="text-on-surface-variant block text-[10px] uppercase font-semibold">
                      Employee Notes
                    </span>
                    <div className="bg-surface p-2.5 rounded-lg border border-surface-container text-on-surface italic text-[11px] mt-0.5">
                      {selectedReq.notes ? `"${selectedReq.notes}"` : 'No additional field notes.'}
                    </div>
                  </div>

                  <div className="pt-1 text-[11px] text-on-surface-variant space-y-1">
                    <div>
                      <span className="font-medium">Submitted By:</span>{' '}
                      {selectedReq.employee_name || selectedReq.creator_name || 'Field Representative'}
                    </div>
                    <div>
                      <span className="font-medium">Submitted On:</span>{' '}
                      {formatDateTime(selectedReq.created_at)}
                    </div>
                    {selectedReq.visit_id && (
                      <div className="font-mono text-[10px]">
                        <span className="font-medium">Visit Ref:</span> {selectedReq.visit_id}
                      </div>
                    )}
                  </div>

                  {/* Client Indent Photo */}
                  <div className="pt-2">
                    <span className="text-on-surface-variant block text-[10px] uppercase font-semibold mb-1.5">
                      Indent / Client Photo
                    </span>
                    {selectedReq.photo_url ? (
                      <div className="relative group rounded-lg overflow-hidden border border-outline-variant bg-surface">
                        <img
                          src={selectedReq.photo_url}
                          alt="Requirement Photo"
                          className="w-full h-40 object-contain bg-black/5"
                        />
                        <button
                          type="button"
                          onClick={() => setPreviewImage(selectedReq.photo_url || null)}
                          className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white text-xs font-semibold gap-1.5 transition-opacity"
                        >
                          <Eye className="w-4 h-4" />
                          <span>View Full Image</span>
                        </button>
                      </div>
                    ) : (
                      <div className="p-4 bg-surface rounded-lg border border-surface-container text-center text-on-surface-variant/60 flex flex-col items-center gap-1">
                        <ImageIcon className="w-6 h-6 text-on-surface-variant/40" />
                        <span className="text-[11px]">No photo attached by representative</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Right Column: Admin Decision Panel */}
              <div className="space-y-4 flex flex-col justify-between">
                <div className="space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-surface-container-highest">
                    <h3 className="font-bold text-primary flex items-center gap-1.5 uppercase tracking-wider text-[11px]">
                      <ShieldAlert className="w-4 h-4 text-secondary-container" />
                      Admin Decision & Allocation
                    </h3>
                  </div>

                  {/* Previous decision info if available */}
                  {selectedReq.decided_at && (
                    <div className="p-3 bg-surface-container rounded-lg border border-surface-container-highest text-[11px] space-y-1">
                      <div className="font-semibold text-on-surface flex items-center justify-between">
                        <span>Last Decided By: {selectedReq.decider_name || 'Admin'}</span>
                        <span className="text-on-surface-variant font-normal">
                          {formatDateTime(selectedReq.decided_at)}
                        </span>
                      </div>
                      {selectedReq.admin_notes && (
                        <p className="text-on-surface-variant italic mt-1">
                          Admin Note: "{selectedReq.admin_notes}"
                        </p>
                      )}
                    </div>
                  )}

                  {/* Decision Action Selector Tabs */}
                  <div className="flex p-1 bg-surface-container rounded-xl border border-surface-container-highest text-xs">
                    <button
                      type="button"
                      onClick={() => {
                        setDecisionTab('APPROVE');
                        setApprovedQty(selectedReq.quantity != null ? String(selectedReq.quantity) : '');
                        setApprovedVal(
                          selectedReq.expected_value != null ? String(selectedReq.expected_value) : ''
                        );
                      }}
                      className={`flex-1 py-1.5 rounded-lg font-bold flex items-center justify-center gap-1 transition-all ${
                        decisionTab === 'APPROVE'
                          ? 'bg-emerald-600 text-white shadow-xs'
                          : 'text-on-surface-variant hover:text-on-surface'
                      }`}
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Approve Full</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        setDecisionTab('PARTIALLY_APPROVE');
                        // Prepopulate with current approved values or half/requested
                        if (!approvedQty) {
                          setApprovedQty(
                            selectedReq.approved_quantity != null
                              ? String(selectedReq.approved_quantity)
                              : String(selectedReq.quantity || 1)
                          );
                        }
                        if (!approvedVal) {
                          setApprovedVal(
                            selectedReq.approved_value != null
                              ? String(selectedReq.approved_value)
                              : String(selectedReq.expected_value || 0)
                          );
                        }
                      }}
                      className={`flex-1 py-1.5 rounded-lg font-bold flex items-center justify-center gap-1 transition-all ${
                        decisionTab === 'PARTIALLY_APPROVE'
                          ? 'bg-amber-600 text-white shadow-xs'
                          : 'text-on-surface-variant hover:text-on-surface'
                      }`}
                    >
                      <AlertCircle className="w-3.5 h-3.5" />
                      <span>Partially Approve</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setDecisionTab('REJECT')}
                      className={`flex-1 py-1.5 rounded-lg font-bold flex items-center justify-center gap-1 transition-all ${
                        decisionTab === 'REJECT'
                          ? 'bg-rose-600 text-white shadow-xs'
                          : 'text-on-surface-variant hover:text-on-surface'
                      }`}
                    >
                      <XCircle className="w-3.5 h-3.5" />
                      <span>Reject</span>
                    </button>
                  </div>

                  {/* Form fields depending on decision tab */}
                  <div className="space-y-3 pt-1">
                    {decisionTab === 'APPROVE' && (
                      <div className="p-3 bg-emerald-50/50 rounded-lg border border-emerald-200 text-[11px] space-y-2">
                        <div className="font-semibold text-emerald-800">
                          Approving full requirement as requested by field staff:
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-xs">
                          <div>
                            <span className="text-on-surface-variant block text-[10px]">Approved Qty</span>
                            <span className="font-bold text-on-surface font-mono">
                              {selectedReq.quantity != null ? `${selectedReq.quantity} units` : '—'}
                            </span>
                          </div>
                          <div>
                            <span className="text-on-surface-variant block text-[10px]">Approved Value</span>
                            <span className="font-bold text-emerald-700 font-mono">
                              {formatCurrency(selectedReq.expected_value)}
                            </span>
                          </div>
                        </div>
                      </div>
                    )}

                    {decisionTab === 'PARTIALLY_APPROVE' && (
                      <div className="p-3 bg-amber-50/50 rounded-lg border border-amber-200 space-y-3">
                        <div className="text-[11px] font-semibold text-amber-900">
                          Specify the quantity and value allocated by management:
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <label className="block text-[11px] font-bold text-on-surface mb-1">
                              Approved Quantity <span className="text-error">*</span>
                            </label>
                            <Input
                              type="number"
                              min="1"
                              value={approvedQty}
                              onChange={(e) => setApprovedQty(e.target.value)}
                              placeholder="e.g. 5"
                              required
                            />
                            <span className="text-[10px] text-on-surface-variant mt-0.5 block">
                              Requested: {selectedReq.quantity || '—'} units
                            </span>
                          </div>

                          <div>
                            <label className="block text-[11px] font-bold text-on-surface mb-1">
                              Approved Value (₹) <span className="text-error">*</span>
                            </label>
                            <Input
                              type="number"
                              min="0"
                              step="0.01"
                              value={approvedVal}
                              onChange={(e) => setApprovedVal(e.target.value)}
                              placeholder="e.g. 25000"
                              required
                            />
                            <span className="text-[10px] text-on-surface-variant mt-0.5 block">
                              Requested: {formatCurrency(selectedReq.expected_value)}
                            </span>
                          </div>
                        </div>
                      </div>
                    )}

                    {decisionTab === 'REJECT' && (
                      <div className="p-3 bg-rose-50/50 rounded-lg border border-rose-200 text-[11px] space-y-2">
                        <div className="font-semibold text-rose-800">
                          Mark requirement as rejected.
                        </div>
                        <p className="text-on-surface-variant text-[11px]">
                          Please provide a clear rationale for the field staff (e.g. discontinued model, credit hold, out of territory).
                        </p>
                      </div>
                    )}

                    {/* Admin Notes / Rationale */}
                    <div>
                      <label className="block text-[11px] font-bold text-on-surface mb-1">
                        Admin Notes / Decision Rationale
                        {decisionTab === 'REJECT' && <span className="text-error ml-0.5">*</span>}
                      </label>
                      <Textarea
                        value={adminNotes}
                        onChange={(e) => setAdminNotes(e.target.value)}
                        placeholder={
                          decisionTab === 'APPROVE'
                            ? 'Optional allocation notes (e.g. Dispatched from North Depot)'
                            : decisionTab === 'PARTIALLY_APPROVE'
                            ? 'Reason for partial allocation (e.g. Regional inventory allocation limited)'
                            : 'State reason for rejection (e.g. Model discontinued, stock unavailable)'
                        }
                        rows={3}
                      />
                    </div>
                  </div>
                </div>

                {/* Footer buttons */}
                <div className="pt-4 border-t border-surface-container-highest flex items-center justify-end gap-2">
                  <Button variant="outline" onClick={handleCloseDetail} disabled={isSubmitting}>
                    Cancel
                  </Button>
                  <Button
                    variant="primary"
                    onClick={handleSubmitDecision}
                    disabled={isSubmitting}
                    className={
                      decisionTab === 'REJECT'
                        ? '!bg-rose-600 hover:!bg-rose-700 !text-white'
                        : decisionTab === 'PARTIALLY_APPROVE'
                        ? '!bg-amber-600 hover:!bg-amber-700 !text-white'
                        : '!bg-emerald-600 hover:!bg-emerald-700 !text-white'
                    }
                  >
                    {isSubmitting
                      ? 'Saving Decision...'
                      : decisionTab === 'APPROVE'
                      ? 'Confirm Full Approval'
                      : decisionTab === 'PARTIALLY_APPROVE'
                      ? 'Confirm Partial Approval'
                      : 'Confirm Rejection'}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </Modal>
      )}

      {/* Image Preview Modal */}
      {previewImage && (
        <Modal
          isOpen={Boolean(previewImage)}
          onClose={() => setPreviewImage(null)}
          title="Customer Indent / Requirement Document"
          size="lg"
        >
          <div className="flex flex-col items-center justify-center p-2">
            <img
              src={previewImage}
              alt="Requirement Indent Full View"
              className="max-h-[70vh] w-auto object-contain rounded-lg shadow-md"
            />
            <div className="mt-4 flex justify-end w-full">
              <Button variant="secondary" size="sm" onClick={() => setPreviewImage(null)}>
                Close Preview
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
export default RequirementsPage;
