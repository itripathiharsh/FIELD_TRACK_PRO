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
  ShieldAlert,
  Send,
  Package,
  ArrowRightCircle,
  Truck,
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
import {
  CustomerRequirement,
  RequirementItem,
  RequirementItemDecisionUpdate,
  Order,
} from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Line Item editor state
// ---------------------------------------------------------------------------
interface LineItemEdit {
  id: string;
  brand_name: string;
  product_model: string;
  requested_quantity: number;
  expected_rate: number;
  requested_amount: number;
  approved_quantity: string; // string for input binding
  approved_rate: string;
  tally_stock_item_name: string;
  notes: string;
}

function toLineItemEdits(items: RequirementItem[]): LineItemEdit[] {
  return items.map((it) => ({
    id: it.id,
    brand_name: it.brand_name,
    product_model: it.product_model,
    requested_quantity: it.requested_quantity,
    expected_rate: it.expected_rate,
    requested_amount: it.requested_amount,
    approved_quantity: it.approved_quantity != null ? String(it.approved_quantity) : String(it.requested_quantity),
    approved_rate: it.approved_rate != null ? String(it.approved_rate) : String(it.expected_rate),
    tally_stock_item_name: it.tally_stock_item_name || '',
    notes: it.notes || '',
  }));
}

function lineAmount(edit: LineItemEdit): number {
  const q = parseFloat(edit.approved_quantity) || 0;
  const r = parseFloat(edit.approved_rate) || 0;
  return q * r;
}

// ---------------------------------------------------------------------------
// Tab type
// ---------------------------------------------------------------------------
type PageTab = 'REQUIREMENTS' | 'ORDERS';

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const RequirementsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<PageTab>('REQUIREMENTS');
  const [requirements, setRequirements] = useState<CustomerRequirement[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  // Selected requirement for modal view & decision
  const [selectedReq, setSelectedReq] = useState<CustomerRequirement | null>(null);
  const [decisionTab, setDecisionTab] = useState<'APPROVE' | 'PARTIALLY_APPROVE' | 'REJECT'>('APPROVE');
  const [lineEdits, setLineEdits] = useState<LineItemEdit[]>([]);
  const [approvedQty, setApprovedQty] = useState<string>('');
  const [approvedVal, setApprovedVal] = useState<string>('');
  const [adminNotes, setAdminNotes] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Confirm-order modal
  const [confirmReq, setConfirmReq] = useState<CustomerRequirement | null>(null);
  const [confirmEdits, setConfirmEdits] = useState<LineItemEdit[]>([]);
  const [confirmNotes, setConfirmNotes] = useState('');
  const [isConfirming, setIsConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [confirmSuccess, setConfirmSuccess] = useState<string | null>(null);

  // Image preview modal
  const [previewImage, setPreviewImage] = useState<string | null>(null);

  // Order detail modal
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);

  // ---------------------------------------------------------------------------
  // Data Loading
  // ---------------------------------------------------------------------------

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

  const loadOrders = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getOrders();
      setOrders(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch confirmed orders');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'REQUIREMENTS') {
      void loadRequirements();
    } else {
      void loadOrders();
    }
  }, [activeTab, loadRequirements, loadOrders]);

  // ---------------------------------------------------------------------------
  // KPIs
  // ---------------------------------------------------------------------------

  const kpis = useMemo(() => {
    let total = requirements.length;
    let pending = 0;
    let partiallyApproved = 0;
    let approved = 0;
    let rejected = 0;
    let convertedToOrder = 0;

    for (const r of requirements) {
      const s = (r.status || '').toUpperCase();
      if (s === 'PENDING' || s === 'OPEN') pending++;
      else if (s === 'PARTIALLY_APPROVED') partiallyApproved++;
      else if (s === 'APPROVED') approved++;
      else if (s === 'REJECTED') rejected++;
      else if (s === 'CONVERTED_TO_ORDER') convertedToOrder++;
    }

    return { total, pending, partiallyApproved, approved, rejected, convertedToOrder };
  }, [requirements]);

  // Filtered requirements list
  const filteredRequirements = useMemo(() => {
    return requirements.filter((req) => {
      const reqStatus = (req.status || '').toUpperCase();
      if (statusFilter === 'PENDING' && reqStatus !== 'PENDING' && reqStatus !== 'OPEN') return false;
      if (statusFilter === 'PARTIALLY_APPROVED' && reqStatus !== 'PARTIALLY_APPROVED') return false;
      if (statusFilter === 'APPROVED' && reqStatus !== 'APPROVED') return false;
      if (statusFilter === 'REJECTED' && reqStatus !== 'REJECTED') return false;
      if (statusFilter === 'CONVERTED_TO_ORDER' && reqStatus !== 'CONVERTED_TO_ORDER') return false;

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const fields = [
          req.customer_name, req.outlet_code, req.brand, req.product_details,
          req.employee_name || req.creator_name, req.notes, req.admin_notes,
        ];
        // Also search inside line items
        const itemFields = (req.items || []).flatMap(i => [i.brand_name, i.product_model, i.notes]);
        return [...fields, ...itemFields].some(f => (f || '').toLowerCase().includes(q));
      }
      return true;
    });
  }, [requirements, statusFilter, searchQuery]);

  // ---------------------------------------------------------------------------
  // Open requirement detail & decision modal
  // ---------------------------------------------------------------------------

  const handleOpenDetail = (req: CustomerRequirement) => {
    setSelectedReq(req);
    setActionError(null);
    setActionSuccess(null);

    const hasItems = req.items && req.items.length > 0;

    if (req.status === 'PARTIALLY_APPROVED') {
      setDecisionTab('PARTIALLY_APPROVE');
    } else if (req.status === 'REJECTED') {
      setDecisionTab('REJECT');
    } else {
      setDecisionTab('APPROVE');
    }

    if (hasItems) {
      setLineEdits(toLineItemEdits(req.items));
    } else {
      setLineEdits([]);
    }

    setApprovedQty(req.approved_quantity != null ? String(req.approved_quantity) : (req.quantity != null ? String(req.quantity) : ''));
    setApprovedVal(req.approved_value != null ? String(req.approved_value) : (req.expected_value != null ? String(req.expected_value) : ''));
    setAdminNotes(req.admin_notes || '');
  };

  const handleCloseDetail = () => {
    setSelectedReq(null);
    setActionError(null);
    setActionSuccess(null);
    setIsSubmitting(false);
    setLineEdits([]);
  };

  // ---------------------------------------------------------------------------
  // Submit decision (Approve / Partially Approve / Reject)
  // ---------------------------------------------------------------------------

  const handleSubmitDecision = async () => {
    if (!selectedReq) return;
    setIsSubmitting(true);
    setActionError(null);
    setActionSuccess(null);

    try {
      let updated: CustomerRequirement;
      const hasItems = lineEdits.length > 0;

      // Build per-line item updates if we have items
      const itemUpdates: RequirementItemDecisionUpdate[] | undefined = hasItems
        ? lineEdits.map(e => ({
            id: e.id,
            approved_quantity: e.approved_quantity ? parseInt(e.approved_quantity) : null,
            approved_rate: e.approved_rate ? parseFloat(e.approved_rate) : null,
            tally_stock_item_name: e.tally_stock_item_name || null,
            notes: e.notes || null,
          }))
        : undefined;

      if (decisionTab === 'APPROVE') {
        const q = approvedQty.trim() !== '' ? Number(approvedQty) : undefined;
        const v = approvedVal.trim() !== '' ? Number(approvedVal) : undefined;
        updated = await apiClient.decideRequirement(selectedReq.id, {
          action: 'APPROVE',
          approved_quantity: q,
          approved_value: v,
          admin_notes: adminNotes.trim() || undefined,
          items: itemUpdates,
        });
        setActionSuccess('Requirement successfully approved in full.');
      } else if (decisionTab === 'PARTIALLY_APPROVE') {
        const q = Number(approvedQty);
        const v = Number(approvedVal);

        if (!hasItems && (isNaN(q) || q <= 0)) {
          throw new Error('Please enter a valid approved quantity greater than 0.');
        }
        if (!hasItems && (isNaN(v) || v <= 0)) {
          throw new Error('Please enter a valid approved value (₹) greater than 0.');
        }

        updated = await apiClient.decideRequirement(selectedReq.id, {
          action: 'PARTIALLY_APPROVE',
          approved_quantity: hasItems ? undefined : q,
          approved_value: hasItems ? undefined : v,
          admin_notes: adminNotes.trim() || undefined,
          items: itemUpdates,
        });
        setActionSuccess('Requirement partially approved successfully.');
      } else {
        updated = await apiClient.decideRequirement(selectedReq.id, {
          action: 'REJECT',
          admin_notes: adminNotes.trim() || undefined,
        });
        setActionSuccess('Requirement rejected.');
      }

      setRequirements((prev) =>
        prev.map((item) => (item.id === updated.id ? { ...item, ...updated } : item))
      );
      setSelectedReq(updated);

      setTimeout(() => {
        handleCloseDetail();
      }, 1400);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to record decision');
    } finally {
      setIsSubmitting(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Confirm & Send to Tally
  // ---------------------------------------------------------------------------

  const handleOpenConfirmOrder = (req: CustomerRequirement) => {
    setConfirmReq(req);
    setConfirmError(null);
    setConfirmSuccess(null);
    setConfirmNotes('');
    if (req.items && req.items.length > 0) {
      setConfirmEdits(toLineItemEdits(req.items));
    } else {
      setConfirmEdits([]);
    }
  };

  const handleConfirmOrder = async () => {
    if (!confirmReq) return;
    setIsConfirming(true);
    setConfirmError(null);
    setConfirmSuccess(null);

    try {
      const itemUpdates: RequirementItemDecisionUpdate[] | undefined =
        confirmEdits.length > 0
          ? confirmEdits.map((e) => ({
              id: e.id,
              approved_quantity: e.approved_quantity ? parseInt(e.approved_quantity) : null,
              approved_rate: e.approved_rate ? parseFloat(e.approved_rate) : null,
              tally_stock_item_name: e.tally_stock_item_name || null,
              notes: e.notes || null,
            }))
          : undefined;

      const order = await apiClient.confirmRequirementOrder(confirmReq.id, {
        admin_notes: confirmNotes.trim() || undefined,
        items: itemUpdates,
      });

      setConfirmSuccess(
        `Order ${order.order_number} created and sent to Tally! (Status: ${order.status})`
      );

      // Update requirement status in local list
      setRequirements((prev) =>
        prev.map((item) =>
          item.id === confirmReq.id ? { ...item, status: 'CONVERTED_TO_ORDER' } : item
        )
      );

      setTimeout(() => {
        setConfirmReq(null);
        setConfirmSuccess(null);
      }, 2500);
    } catch (err) {
      setConfirmError(err instanceof Error ? err.message : 'Failed to confirm order');
    } finally {
      setIsConfirming(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Computed totals for line-item edits
  // ---------------------------------------------------------------------------

  const editTotals = useMemo(() => {
    const totalRequested = lineEdits.reduce((s, e) => s + e.requested_amount, 0);
    const totalApproved = lineEdits.reduce((s, e) => s + lineAmount(e), 0);
    return { totalRequested, totalApproved, shortage: totalRequested - totalApproved };
  }, [lineEdits]);

  const confirmTotals = useMemo(() => {
    const totalRequested = confirmEdits.reduce((s, e) => s + e.requested_amount, 0);
    const totalApproved = confirmEdits.reduce((s, e) => s + lineAmount(e), 0);
    return { totalRequested, totalApproved };
  }, [confirmEdits]);

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  const updateLineEdit = (idx: number, field: keyof LineItemEdit, value: string) => {
    setLineEdits((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: value };
      return next;
    });
  };

  const updateConfirmEdit = (idx: number, field: keyof LineItemEdit, value: string) => {
    setConfirmEdits((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: value };
      return next;
    });
  };

  const canConfirmOrder = (req: CustomerRequirement) => {
    const s = (req.status || '').toUpperCase();
    return s === 'APPROVED' || s === 'PARTIALLY_APPROVED';
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6 pb-12">
      <PageHeader
        title="Customer Requirements & Orders"
        subtitle="Review multi-item customer demand requests, approve line-by-line, and confirm orders to TallyPrime."
      />

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {/* Page-level Tabs: Requirements vs Confirmed Orders */}
      <div className="flex items-center gap-1 bg-surface-container p-1 rounded-xl border border-outline-variant w-fit">
        <button
          onClick={() => setActiveTab('REQUIREMENTS')}
          className={`px-5 py-2 rounded-lg font-bold text-sm flex items-center gap-2 transition-all ${
            activeTab === 'REQUIREMENTS'
              ? 'bg-primary text-on-primary shadow-md'
              : 'text-on-surface-variant hover:bg-surface-container-high'
          }`}
        >
          <ClipboardList className="w-4 h-4" />
          Requirements
        </button>
        <button
          onClick={() => setActiveTab('ORDERS')}
          className={`px-5 py-2 rounded-lg font-bold text-sm flex items-center gap-2 transition-all ${
            activeTab === 'ORDERS'
              ? 'bg-primary text-on-primary shadow-md'
              : 'text-on-surface-variant hover:bg-surface-container-high'
          }`}
        >
          <Truck className="w-4 h-4" />
          Confirmed Orders
          {orders.length > 0 && (
            <span className="text-[10px] bg-on-primary/20 text-on-primary px-1.5 py-0.5 rounded-full">
              {orders.length}
            </span>
          )}
        </button>
      </div>

      {/* ================================================================= */}
      {/* REQUIREMENTS TAB                                                  */}
      {/* ================================================================= */}
      {activeTab === 'REQUIREMENTS' && (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
            <MetricCard title="Total Requests" value={kpis.total} icon={ClipboardList} color="slate" onClick={() => setStatusFilter('ALL')} />
            <MetricCard title="Pending Review" value={kpis.pending} icon={Clock} color="amber" onClick={() => setStatusFilter('PENDING')} />
            <MetricCard title="Partially Approved" value={kpis.partiallyApproved} icon={AlertCircle} color="secondary" onClick={() => setStatusFilter('PARTIALLY_APPROVED')} />
            <MetricCard title="Approved" value={kpis.approved} icon={CheckCircle2} color="emerald" onClick={() => setStatusFilter('APPROVED')} />
            <MetricCard title="Rejected" value={kpis.rejected} icon={XCircle} color="rose" onClick={() => setStatusFilter('REJECTED')} />
            <MetricCard title="Sent to Tally" value={kpis.convertedToOrder} icon={Send} color="primary" onClick={() => setStatusFilter('CONVERTED_TO_ORDER')} />
          </div>

          {/* Filters and Search */}
          <Card className="!p-4">
            <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
              <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0 text-xs">
                {[
                  { id: 'ALL', label: 'All', count: kpis.total },
                  { id: 'PENDING', label: 'Pending', count: kpis.pending },
                  { id: 'PARTIALLY_APPROVED', label: 'Partial', count: kpis.partiallyApproved },
                  { id: 'APPROVED', label: 'Approved', count: kpis.approved },
                  { id: 'REJECTED', label: 'Rejected', count: kpis.rejected },
                  { id: 'CONVERTED_TO_ORDER', label: 'Ordered', count: kpis.convertedToOrder },
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
                    <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                      statusFilter === tab.id
                        ? 'bg-on-primary/20 text-on-primary'
                        : 'bg-surface-container-highest text-on-surface-variant'
                    }`}>{tab.count}</span>
                  </button>
                ))}
              </div>
              <div className="relative w-full md:w-72 shrink-0">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant" />
                <input
                  type="text"
                  placeholder="Search outlet, product, rep, brand..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-3 py-1.5 text-xs bg-surface-container border border-outline-variant rounded-lg focus:outline-hidden focus:border-primary text-on-surface placeholder:text-on-surface-variant"
                />
              </div>
            </div>
          </Card>

          {/* Requirements Table */}
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
                      ? 'No customer requirements match the selected filters.'
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
                      <th className="px-4 py-3">Items / Products</th>
                      <th className="px-4 py-3 text-right">Requested Total</th>
                      <th className="px-4 py-3 text-right">Approved Total</th>
                      <th className="px-4 py-3 text-center">Photo</th>
                      <th className="px-4 py-3 text-center">Status</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-container-highest">
                    {filteredRequirements.map((req) => {
                      const hasItems = req.items && req.items.length > 0;
                      const isConvertedToOrder = (req.status || '').toUpperCase() === 'CONVERTED_TO_ORDER';

                      return (
                        <tr key={req.id} className="hover:bg-surface-container-low/70 transition-colors">
                          {/* Customer */}
                          <td className="px-4 py-3">
                            <div className="font-semibold text-on-surface text-sm">{req.customer_name || '—'}</div>
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

                          {/* Items / Products */}
                          <td className="px-4 py-3 max-w-xs">
                            {hasItems ? (
                              <div className="space-y-0.5">
                                {req.items.slice(0, 3).map((it, idx) => (
                                  <div key={idx} className="flex items-center gap-1.5">
                                    <span className="bg-primary/10 text-primary font-bold px-1 py-0.5 rounded text-[9px] uppercase tracking-wide shrink-0">
                                      {it.brand_name}
                                    </span>
                                    <span className="truncate text-on-surface">{it.product_model}</span>
                                    <span className="text-on-surface-variant shrink-0">×{it.requested_quantity}</span>
                                  </div>
                                ))}
                                {req.items.length > 3 && (
                                  <span className="text-[10px] text-primary font-semibold">+{req.items.length - 3} more items</span>
                                )}
                              </div>
                            ) : (
                              <div>
                                <div className="flex items-center gap-1.5 mb-0.5">
                                  {req.brand && (
                                    <span className="bg-primary/10 text-primary font-bold px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide">
                                      {req.brand}
                                    </span>
                                  )}
                                </div>
                                <div className="font-medium text-on-surface truncate">{req.product_details || '—'}</div>
                              </div>
                            )}
                          </td>

                          {/* Requested Total */}
                          <td className="px-4 py-3 text-right font-mono">
                            {hasItems ? (
                              <div>
                                <div className="font-bold text-on-surface">
                                  {req.items.reduce((s, i) => s + i.requested_quantity, 0)} units
                                </div>
                                <div className="text-primary font-semibold">
                                  {formatCurrency(req.total_requested_value ?? req.items.reduce((s, i) => s + i.requested_amount, 0))}
                                </div>
                                <span className="text-[9px] text-on-surface-variant">{req.items.length} lines</span>
                              </div>
                            ) : (
                              <div>
                                <div className="font-bold text-on-surface">{req.quantity != null ? `${req.quantity} units` : '—'}</div>
                                <div className="text-primary font-semibold">{formatCurrency(req.expected_value)}</div>
                              </div>
                            )}
                          </td>

                          {/* Approved Total */}
                          <td className="px-4 py-3 text-right font-mono">
                            {isConvertedToOrder ? (
                              <div className="flex flex-col items-end gap-0.5">
                                <span className="text-primary font-bold text-[11px] flex items-center gap-1">
                                  <Send className="w-3 h-3" /> Ordered
                                </span>
                                {req.total_approved_value != null && (
                                  <span className="text-primary font-semibold">{formatCurrency(req.total_approved_value)}</span>
                                )}
                              </div>
                            ) : (req.status || '').toUpperCase() === 'APPROVED' || (req.status || '').toUpperCase() === 'PARTIALLY_APPROVED' ? (
                              <div>
                                <div className="font-bold text-emerald-700">
                                  {formatCurrency(req.total_approved_value ?? req.approved_value)}
                                </div>
                              </div>
                            ) : (req.status || '').toUpperCase() === 'REJECTED' ? (
                              <span className="text-error font-medium text-[11px]">Rejected</span>
                            ) : (
                              <span className="text-on-surface-variant/60 text-[11px] italic">Awaiting review</span>
                            )}
                          </td>

                          {/* Photo */}
                          <td className="px-4 py-3 text-center">
                            {req.photo_url ? (
                              <button
                                onClick={() => setPreviewImage(req.photo_url || null)}
                                className="relative group inline-block rounded border border-outline-variant overflow-hidden hover:ring-2 hover:ring-primary transition-all"
                                title="View requirement indent image"
                              >
                                <img src={req.photo_url} alt="Indent" className="w-10 h-10 object-cover" />
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
                            <div className="flex flex-col items-end gap-1">
                              <Button
                                variant="secondary"
                                size="sm"
                                onClick={() => handleOpenDetail(req)}
                                className="!py-1 !px-2.5 !text-xs font-semibold"
                              >
                                Review & Decide
                              </Button>
                              {canConfirmOrder(req) && (
                                <Button
                                  variant="primary"
                                  size="sm"
                                  onClick={() => handleOpenConfirmOrder(req)}
                                  className="!py-1 !px-2.5 !text-xs font-semibold !bg-primary hover:!bg-primary/90"
                                >
                                  <Send className="w-3 h-3 mr-1" />
                                  Confirm → Tally
                                </Button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}

      {/* ================================================================= */}
      {/* CONFIRMED ORDERS TAB                                              */}
      {/* ================================================================= */}
      {activeTab === 'ORDERS' && (
        <Card className="!p-0 overflow-hidden">
          {isLoading ? (
            <div className="p-12 flex flex-col items-center justify-center text-on-surface-variant">
              <div className="w-8 h-8 border-3 border-primary-container border-t-primary rounded-full animate-spin mb-3" />
              <p className="text-xs">Loading confirmed orders...</p>
            </div>
          ) : orders.length === 0 ? (
            <div className="p-8">
              <EmptyState
                icon={Truck}
                title="No Confirmed Orders Yet"
                subtitle="Approved requirements that are confirmed and sent to TallyPrime will appear here."
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-surface-container-low text-on-surface-variant uppercase tracking-wider font-semibold border-b border-surface-container-highest">
                  <tr>
                    <th className="px-4 py-3">Order #</th>
                    <th className="px-4 py-3">Customer</th>
                    <th className="px-4 py-3">Field Rep</th>
                    <th className="px-4 py-3 text-center">Items</th>
                    <th className="px-4 py-3 text-right">Total Amount</th>
                    <th className="px-4 py-3 text-center">Tally Status</th>
                    <th className="px-4 py-3">Tally Voucher</th>
                    <th className="px-4 py-3 text-right">Created</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-highest">
                  {orders.map((order) => {
                    const statusColor =
                      order.status === 'TALLY_CONFIRMED' ? 'text-emerald-700 bg-emerald-50'
                      : order.status === 'TALLY_FAILED' ? 'text-rose-700 bg-rose-50'
                      : order.status === 'PENDING_TALLY' ? 'text-amber-700 bg-amber-50'
                      : 'text-blue-700 bg-blue-50';

                    return (
                      <tr key={order.id} className="hover:bg-surface-container-low/70 transition-colors">
                        <td className="px-4 py-3">
                          <span className="font-bold text-primary text-sm font-mono">{order.order_number}</span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-semibold text-on-surface">{order.customer_name || '—'}</div>
                          <div className="text-[11px] text-on-surface-variant">{order.outlet_code || '—'}</div>
                        </td>
                        <td className="px-4 py-3 text-on-surface">
                          {order.employee_name || order.creator_name || '—'}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <span className="bg-surface-container text-on-surface-variant font-bold px-2 py-0.5 rounded-full text-[10px]">
                            {order.items?.length || 0} lines
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-mono font-bold text-on-surface">
                          {formatCurrency(order.total_amount)}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold ${statusColor}`}>
                            {order.status.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-mono text-[11px] text-on-surface-variant">
                          {order.tally_voucher_number || '—'}
                          {order.tally_guid && (
                            <div className="text-[9px] text-on-surface-variant/60 truncate max-w-[120px]" title={order.tally_guid}>
                              {order.tally_guid.slice(0, 12)}...
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right text-[11px] text-on-surface-variant">
                          {formatDateTime(order.created_at)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => setSelectedOrder(order)}
                            className="!py-1 !px-2.5 !text-xs font-semibold"
                          >
                            <Eye className="w-3 h-3 mr-1" /> View
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
      )}

      {/* ================================================================= */}
      {/* REVIEW & DECISION MODAL (multi-item aware)                        */}
      {/* ================================================================= */}
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
                <span className="font-bold text-on-surface text-sm ml-1">{selectedReq.customer_name || '—'}</span>
                <span className="text-on-surface-variant text-[11px] ml-2">(Outlet: {selectedReq.outlet_code || '—'})</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-on-surface-variant">Status:</span>
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

            {/* Line Items Table (if multi-item) */}
            {lineEdits.length > 0 && (
              <div className="space-y-2">
                <h3 className="font-bold text-primary flex items-center gap-1.5 uppercase tracking-wider text-[11px]">
                  <Package className="w-4 h-4" /> Line Items ({lineEdits.length})
                </h3>
                <div className="overflow-x-auto border border-surface-container-highest rounded-lg">
                  <table className="w-full text-xs border-collapse">
                    <thead className="bg-surface-container-low text-on-surface-variant font-semibold">
                      <tr>
                        <th className="px-3 py-2 text-left">Brand</th>
                        <th className="px-3 py-2 text-left">Product / Model</th>
                        <th className="px-3 py-2 text-right">Req. Qty</th>
                        <th className="px-3 py-2 text-right">Req. Rate</th>
                        <th className="px-3 py-2 text-right">Req. Amt</th>
                        <th className="px-3 py-2 text-right bg-primary/5">Appr. Qty</th>
                        <th className="px-3 py-2 text-right bg-primary/5">Appr. Rate</th>
                        <th className="px-3 py-2 text-right bg-primary/5">Appr. Amt</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-container-highest">
                      {lineEdits.map((edit, idx) => (
                        <tr key={edit.id} className="hover:bg-surface-container-low/50">
                          <td className="px-3 py-2">
                            <span className="bg-primary/10 text-primary font-bold px-1.5 py-0.5 rounded text-[9px] uppercase">{edit.brand_name}</span>
                          </td>
                          <td className="px-3 py-2 font-medium text-on-surface">{edit.product_model}</td>
                          <td className="px-3 py-2 text-right font-mono">{edit.requested_quantity}</td>
                          <td className="px-3 py-2 text-right font-mono">{formatCurrency(edit.expected_rate)}</td>
                          <td className="px-3 py-2 text-right font-mono">{formatCurrency(edit.requested_amount)}</td>
                          <td className="px-3 py-2 text-right bg-primary/5">
                            {decisionTab !== 'REJECT' ? (
                              <input
                                type="number"
                                min="0"
                                value={edit.approved_quantity}
                                onChange={(e) => updateLineEdit(idx, 'approved_quantity', e.target.value)}
                                className="w-16 text-right bg-surface border border-outline-variant rounded px-1 py-0.5 text-xs font-mono focus:border-primary focus:outline-hidden"
                              />
                            ) : (
                              <span className="text-on-surface-variant/50">—</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-right bg-primary/5">
                            {decisionTab !== 'REJECT' ? (
                              <input
                                type="number"
                                min="0"
                                step="0.01"
                                value={edit.approved_rate}
                                onChange={(e) => updateLineEdit(idx, 'approved_rate', e.target.value)}
                                className="w-20 text-right bg-surface border border-outline-variant rounded px-1 py-0.5 text-xs font-mono focus:border-primary focus:outline-hidden"
                              />
                            ) : (
                              <span className="text-on-surface-variant/50">—</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-right bg-primary/5 font-mono font-bold text-primary">
                            {decisionTab !== 'REJECT' ? formatCurrency(lineAmount(edit)) : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    {decisionTab !== 'REJECT' && (
                      <tfoot className="bg-surface-container-low font-bold">
                        <tr>
                          <td colSpan={4} className="px-3 py-2 text-right text-on-surface-variant uppercase text-[10px]">Totals:</td>
                          <td className="px-3 py-2 text-right font-mono">{formatCurrency(editTotals.totalRequested)}</td>
                          <td colSpan={2} className="px-3 py-2 text-right bg-primary/5 text-on-surface-variant uppercase text-[10px]">Approved Total:</td>
                          <td className="px-3 py-2 text-right bg-primary/5 font-mono text-primary text-sm">{formatCurrency(editTotals.totalApproved)}</td>
                        </tr>
                        {editTotals.shortage > 0 && (
                          <tr>
                            <td colSpan={7} className="px-3 py-1 text-right text-[10px] text-amber-700 font-semibold">Unapproved / Shortage:</td>
                            <td className="px-3 py-1 text-right bg-amber-50 font-mono text-amber-700">{formatCurrency(editTotals.shortage)}</td>
                          </tr>
                        )}
                      </tfoot>
                    )}
                  </table>
                </div>
              </div>
            )}

            {/* Legacy single-item view */}
            {lineEdits.length === 0 && (
              <div className="space-y-3 bg-surface-container-low/40 p-4 rounded-xl border border-surface-container-highest">
                <h3 className="font-bold text-primary flex items-center gap-1.5 uppercase tracking-wider text-[11px]">
                  <ClipboardList className="w-4 h-4 text-primary" /> Original Field Request
                </h3>
                <div className="space-y-2.5">
                  <div>
                    <span className="text-on-surface-variant block text-[10px] uppercase font-semibold">Brand & Product</span>
                    <div className="font-bold text-on-surface text-sm mt-0.5">
                      {selectedReq.brand ? `[${selectedReq.brand}] ` : ''}{selectedReq.product_details || '—'}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3 pt-1">
                    <div className="bg-surface p-2.5 rounded-lg border border-surface-container">
                      <span className="text-on-surface-variant block text-[10px] uppercase font-semibold">Requested Quantity</span>
                      <span className="font-bold text-on-surface font-mono text-base">{selectedReq.quantity != null ? `${selectedReq.quantity} units` : '—'}</span>
                    </div>
                    <div className="bg-surface p-2.5 rounded-lg border border-surface-container">
                      <span className="text-on-surface-variant block text-[10px] uppercase font-semibold">Expected Value</span>
                      <span className="font-bold text-primary font-mono text-base">{formatCurrency(selectedReq.expected_value)}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Submitted by info */}
            <div className="text-[11px] text-on-surface-variant space-y-1">
              <div><span className="font-medium">Submitted By:</span> {selectedReq.employee_name || selectedReq.creator_name || 'Field Rep'}</div>
              <div><span className="font-medium">Submitted On:</span> {formatDateTime(selectedReq.created_at)}</div>
            </div>

            {/* Photo */}
            {selectedReq.photo_url && (
              <div>
                <span className="text-on-surface-variant block text-[10px] uppercase font-semibold mb-1.5">Indent / Client Photo</span>
                <div className="relative group rounded-lg overflow-hidden border border-outline-variant bg-surface">
                  <img src={selectedReq.photo_url} alt="Requirement Photo" className="w-full h-40 object-contain bg-black/5" />
                  <button
                    type="button"
                    onClick={() => setPreviewImage(selectedReq.photo_url || null)}
                    className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white text-xs font-semibold gap-1.5 transition-opacity"
                  >
                    <Eye className="w-4 h-4" /> View Full Image
                  </button>
                </div>
              </div>
            )}

            {/* Admin Decision Panel */}
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-surface-container-highest">
                <h3 className="font-bold text-primary flex items-center gap-1.5 uppercase tracking-wider text-[11px]">
                  <ShieldAlert className="w-4 h-4 text-secondary-container" /> Admin Decision
                </h3>
              </div>

              {selectedReq.decided_at && (
                <div className="p-3 bg-surface-container rounded-lg border border-surface-container-highest text-[11px] space-y-1">
                  <div className="font-semibold text-on-surface flex items-center justify-between">
                    <span>Last Decided By: {selectedReq.decider_name || 'Admin'}</span>
                    <span className="text-on-surface-variant font-normal">{formatDateTime(selectedReq.decided_at)}</span>
                  </div>
                  {selectedReq.admin_notes && (
                    <p className="text-on-surface-variant italic mt-1">Admin Note: "{selectedReq.admin_notes}"</p>
                  )}
                </div>
              )}

              {/* Decision tabs */}
              <div className="flex p-1 bg-surface-container rounded-xl border border-surface-container-highest text-xs">
                <button
                  type="button"
                  onClick={() => {
                    setDecisionTab('APPROVE');
                    setApprovedQty(selectedReq.quantity != null ? String(selectedReq.quantity) : '');
                    setApprovedVal(selectedReq.expected_value != null ? String(selectedReq.expected_value) : '');
                  }}
                  className={`flex-1 py-1.5 rounded-lg font-bold flex items-center justify-center gap-1 transition-all ${
                    decisionTab === 'APPROVE' ? 'bg-emerald-600 text-white shadow-xs' : 'text-on-surface-variant hover:text-on-surface'
                  }`}
                >
                  <CheckCircle2 className="w-3.5 h-3.5" /> Approve Full
                </button>
                <button
                  type="button"
                  onClick={() => setDecisionTab('PARTIALLY_APPROVE')}
                  className={`flex-1 py-1.5 rounded-lg font-bold flex items-center justify-center gap-1 transition-all ${
                    decisionTab === 'PARTIALLY_APPROVE' ? 'bg-amber-600 text-white shadow-xs' : 'text-on-surface-variant hover:text-on-surface'
                  }`}
                >
                  <AlertCircle className="w-3.5 h-3.5" /> Partially Approve
                </button>
                <button
                  type="button"
                  onClick={() => setDecisionTab('REJECT')}
                  className={`flex-1 py-1.5 rounded-lg font-bold flex items-center justify-center gap-1 transition-all ${
                    decisionTab === 'REJECT' ? 'bg-rose-600 text-white shadow-xs' : 'text-on-surface-variant hover:text-on-surface'
                  }`}
                >
                  <XCircle className="w-3.5 h-3.5" /> Reject
                </button>
              </div>

              {/* Legacy qty/value inputs for single-item requirements */}
              {lineEdits.length === 0 && decisionTab === 'PARTIALLY_APPROVE' && (
                <div className="p-3 bg-amber-50/50 rounded-lg border border-amber-200 space-y-3">
                  <div className="text-[11px] font-semibold text-amber-900">Specify the quantity and value allocated by management:</div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] font-bold text-on-surface mb-1">Approved Quantity <span className="text-error">*</span></label>
                      <Input type="number" min="1" value={approvedQty} onChange={(e) => setApprovedQty(e.target.value)} placeholder="e.g. 5" required />
                      <span className="text-[10px] text-on-surface-variant mt-0.5 block">Requested: {selectedReq.quantity || '—'} units</span>
                    </div>
                    <div>
                      <label className="block text-[11px] font-bold text-on-surface mb-1">Approved Value (₹) <span className="text-error">*</span></label>
                      <Input type="number" min="0" step="0.01" value={approvedVal} onChange={(e) => setApprovedVal(e.target.value)} placeholder="e.g. 25000" required />
                      <span className="text-[10px] text-on-surface-variant mt-0.5 block">Requested: {formatCurrency(selectedReq.expected_value)}</span>
                    </div>
                  </div>
                </div>
              )}

              {decisionTab === 'REJECT' && (
                <div className="p-3 bg-rose-50/50 rounded-lg border border-rose-200 text-[11px] space-y-2">
                  <div className="font-semibold text-rose-800">Mark requirement as rejected.</div>
                  <p className="text-on-surface-variant">Please provide a clear rationale for the field staff.</p>
                </div>
              )}

              {/* Admin Notes */}
              <div>
                <label className="block text-[11px] font-bold text-on-surface mb-1">
                  Admin Notes / Decision Rationale
                  {decisionTab === 'REJECT' && <span className="text-error ml-0.5">*</span>}
                </label>
                <Textarea
                  value={adminNotes}
                  onChange={(e) => setAdminNotes(e.target.value)}
                  placeholder={
                    decisionTab === 'APPROVE' ? 'Optional allocation notes'
                    : decisionTab === 'PARTIALLY_APPROVE' ? 'Reason for partial allocation'
                    : 'State reason for rejection'
                  }
                  rows={3}
                />
              </div>
            </div>

            {/* Footer buttons */}
            <div className="pt-4 border-t border-surface-container-highest flex items-center justify-end gap-2">
              <Button variant="outline" onClick={handleCloseDetail} disabled={isSubmitting}>Cancel</Button>
              <Button
                variant="primary"
                onClick={handleSubmitDecision}
                disabled={isSubmitting}
                className={
                  decisionTab === 'REJECT' ? '!bg-rose-600 hover:!bg-rose-700 !text-white'
                  : decisionTab === 'PARTIALLY_APPROVE' ? '!bg-amber-600 hover:!bg-amber-700 !text-white'
                  : '!bg-emerald-600 hover:!bg-emerald-700 !text-white'
                }
              >
                {isSubmitting ? 'Saving Decision...'
                  : decisionTab === 'APPROVE' ? 'Confirm Full Approval'
                  : decisionTab === 'PARTIALLY_APPROVE' ? 'Confirm Partial Approval'
                  : 'Confirm Rejection'}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* ================================================================= */}
      {/* CONFIRM & SEND TO TALLY MODAL                                     */}
      {/* ================================================================= */}
      {confirmReq && (
        <Modal
          isOpen={Boolean(confirmReq)}
          onClose={() => { setConfirmReq(null); setConfirmError(null); setConfirmSuccess(null); }}
          title="Confirm Order & Send to TallyPrime"
          size="xl"
        >
          <div className="space-y-5 text-xs">
            <div className="bg-primary/5 p-3.5 rounded-lg border border-primary/20 flex items-start gap-3">
              <ArrowRightCircle className="w-5 h-5 text-primary shrink-0 mt-0.5" />
              <div>
                <div className="font-bold text-on-surface text-sm">
                  Create Order for: {confirmReq.customer_name || '—'}
                </div>
                <div className="text-[11px] text-on-surface-variant mt-0.5">
                  Outlet: {confirmReq.outlet_code || '—'} • Requirement #{confirmReq.id.slice(0, 8)}
                </div>
                <div className="text-[11px] text-primary font-semibold mt-1">
                  This will create a formal Order and enqueue a Sales Order voucher to TallyPrime.
                </div>
              </div>
            </div>

            {confirmError && <ErrorBanner message={confirmError} onDismiss={() => setConfirmError(null)} />}
            {confirmSuccess && (
              <div className="p-3 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded-lg flex items-center gap-2 font-medium">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>{confirmSuccess}</span>
              </div>
            )}

            {/* Line items review */}
            {confirmEdits.length > 0 && (
              <div className="overflow-x-auto border border-surface-container-highest rounded-lg">
                <table className="w-full text-xs border-collapse">
                  <thead className="bg-surface-container-low text-on-surface-variant font-semibold">
                    <tr>
                      <th className="px-3 py-2 text-left">Brand</th>
                      <th className="px-3 py-2 text-left">Product / Model</th>
                      <th className="px-3 py-2 text-right">Qty</th>
                      <th className="px-3 py-2 text-right">Rate</th>
                      <th className="px-3 py-2 text-right">Line Amount</th>
                      <th className="px-3 py-2 text-left">Tally Stock Item</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-container-highest">
                    {confirmEdits.map((edit, idx) => (
                      <tr key={edit.id}>
                        <td className="px-3 py-2">
                          <span className="bg-primary/10 text-primary font-bold px-1.5 py-0.5 rounded text-[9px] uppercase">{edit.brand_name}</span>
                        </td>
                        <td className="px-3 py-2 font-medium text-on-surface">{edit.product_model}</td>
                        <td className="px-3 py-2 text-right">
                          <input
                            type="number"
                            min="0"
                            value={edit.approved_quantity}
                            onChange={(e) => updateConfirmEdit(idx, 'approved_quantity', e.target.value)}
                            className="w-16 text-right bg-surface border border-outline-variant rounded px-1 py-0.5 text-xs font-mono focus:border-primary focus:outline-hidden"
                          />
                        </td>
                        <td className="px-3 py-2 text-right">
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={edit.approved_rate}
                            onChange={(e) => updateConfirmEdit(idx, 'approved_rate', e.target.value)}
                            className="w-20 text-right bg-surface border border-outline-variant rounded px-1 py-0.5 text-xs font-mono focus:border-primary focus:outline-hidden"
                          />
                        </td>
                        <td className="px-3 py-2 text-right font-mono font-bold text-primary">{formatCurrency(lineAmount(edit))}</td>
                        <td className="px-3 py-2">
                          <input
                            type="text"
                            value={edit.tally_stock_item_name}
                            onChange={(e) => updateConfirmEdit(idx, 'tally_stock_item_name', e.target.value)}
                            placeholder="Auto-resolved"
                            className="w-full bg-surface border border-outline-variant rounded px-1 py-0.5 text-xs focus:border-primary focus:outline-hidden"
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="bg-surface-container-low font-bold">
                    <tr>
                      <td colSpan={4} className="px-3 py-2 text-right uppercase text-[10px] text-on-surface-variant">Order Total:</td>
                      <td className="px-3 py-2 text-right font-mono text-primary text-sm">{formatCurrency(confirmTotals.totalApproved)}</td>
                      <td></td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}

            <div>
              <label className="block text-[11px] font-bold text-on-surface mb-1">Admin Notes (Optional)</label>
              <Textarea
                value={confirmNotes}
                onChange={(e) => setConfirmNotes(e.target.value)}
                placeholder="Additional notes for the Tally Sales Order..."
                rows={2}
              />
            </div>

            <div className="pt-4 border-t border-surface-container-highest flex items-center justify-end gap-2">
              <Button variant="outline" onClick={() => setConfirmReq(null)} disabled={isConfirming}>Cancel</Button>
              <Button
                variant="primary"
                onClick={handleConfirmOrder}
                disabled={isConfirming || !!confirmSuccess}
                className="!bg-primary hover:!bg-primary/90"
              >
                {isConfirming ? (
                  <><div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" /> Creating Order...</>
                ) : (
                  <><Send className="w-3.5 h-3.5 mr-2" /> Confirm & Send to Tally</>
                )}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* ================================================================= */}
      {/* ORDER DETAIL MODAL                                                */}
      {/* ================================================================= */}
      {selectedOrder && (
        <Modal
          isOpen={Boolean(selectedOrder)}
          onClose={() => setSelectedOrder(null)}
          title={`Order ${selectedOrder.order_number}`}
          size="lg"
        >
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <div className="bg-surface p-2.5 rounded-lg border border-surface-container">
                <span className="text-on-surface-variant block text-[10px] uppercase font-semibold">Customer</span>
                <span className="font-bold text-on-surface">{selectedOrder.customer_name || '—'}</span>
              </div>
              <div className="bg-surface p-2.5 rounded-lg border border-surface-container">
                <span className="text-on-surface-variant block text-[10px] uppercase font-semibold">Total Amount</span>
                <span className="font-bold text-primary font-mono">{formatCurrency(selectedOrder.total_amount)}</span>
              </div>
              <div className="bg-surface p-2.5 rounded-lg border border-surface-container">
                <span className="text-on-surface-variant block text-[10px] uppercase font-semibold">Status</span>
                <StatusBadge status={selectedOrder.status} size="sm" />
              </div>
              {selectedOrder.tally_voucher_number && (
                <div className="bg-surface p-2.5 rounded-lg border border-surface-container">
                  <span className="text-on-surface-variant block text-[10px] uppercase font-semibold">Tally Voucher #</span>
                  <span className="font-bold text-on-surface font-mono">{selectedOrder.tally_voucher_number}</span>
                </div>
              )}
              {selectedOrder.tally_guid && (
                <div className="bg-surface p-2.5 rounded-lg border border-surface-container col-span-2">
                  <span className="text-on-surface-variant block text-[10px] uppercase font-semibold">Tally GUID</span>
                  <span className="font-mono text-[10px] text-on-surface break-all">{selectedOrder.tally_guid}</span>
                </div>
              )}
            </div>

            {selectedOrder.items && selectedOrder.items.length > 0 && (
              <div className="overflow-x-auto border border-surface-container-highest rounded-lg">
                <table className="w-full text-xs border-collapse">
                  <thead className="bg-surface-container-low text-on-surface-variant font-semibold">
                    <tr>
                      <th className="px-3 py-2 text-left">Brand</th>
                      <th className="px-3 py-2 text-left">Product</th>
                      <th className="px-3 py-2 text-left">Tally Stock Item</th>
                      <th className="px-3 py-2 text-right">Qty</th>
                      <th className="px-3 py-2 text-right">Rate</th>
                      <th className="px-3 py-2 text-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-container-highest">
                    {selectedOrder.items.map((item) => (
                      <tr key={item.id}>
                        <td className="px-3 py-2">
                          <span className="bg-primary/10 text-primary font-bold px-1.5 py-0.5 rounded text-[9px] uppercase">{item.brand_name}</span>
                        </td>
                        <td className="px-3 py-2 font-medium text-on-surface">{item.product_model}</td>
                        <td className="px-3 py-2 text-on-surface-variant font-mono text-[10px]">{item.stock_item_name}</td>
                        <td className="px-3 py-2 text-right font-mono">{item.quantity} {item.unit}</td>
                        <td className="px-3 py-2 text-right font-mono">{formatCurrency(item.rate)}</td>
                        <td className="px-3 py-2 text-right font-mono font-bold text-primary">{formatCurrency(item.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="bg-surface-container-low font-bold">
                    <tr>
                      <td colSpan={5} className="px-3 py-2 text-right uppercase text-[10px]">Total:</td>
                      <td className="px-3 py-2 text-right font-mono text-primary text-sm">{formatCurrency(selectedOrder.total_amount)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}

            <div className="text-[11px] text-on-surface-variant space-y-1">
              <div><span className="font-medium">Created:</span> {formatDateTime(selectedOrder.created_at)}</div>
              {selectedOrder.admin_notes && <div><span className="font-medium">Admin Notes:</span> {selectedOrder.admin_notes}</div>}
            </div>

            <div className="pt-3 border-t border-surface-container-highest flex justify-end">
              <Button variant="secondary" size="sm" onClick={() => setSelectedOrder(null)}>Close</Button>
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
            <img src={previewImage} alt="Requirement Indent Full View" className="max-h-[70vh] w-auto object-contain rounded-lg shadow-md" />
            <div className="mt-4 flex justify-end w-full">
              <Button variant="secondary" size="sm" onClick={() => setPreviewImage(null)}>Close Preview</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
export default RequirementsPage;
