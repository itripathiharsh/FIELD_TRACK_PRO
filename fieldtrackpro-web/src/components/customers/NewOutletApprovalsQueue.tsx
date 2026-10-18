import React, { useCallback, useEffect, useState } from 'react';
import { X, Clock, ShieldCheck, Pencil } from 'lucide-react';
import { DataTable, Column } from '../ui/DataTable';
import { FieldTrackMap } from '../maps/FieldTrackMap';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { ErrorBanner } from '../ui/ErrorBanner';
import { apiClient } from '../../api/client';
import { CustomerProspect, OutletProof, ProspectStatus } from '../../types';
import { ProspectProofPanel } from '../outlet-proofs/ProspectProofPanel';
import { OutletPhotoLightbox } from '../outlet-proofs/OutletProofImage';
import { formatMoney } from '../../utils/money';

interface NewOutletApprovalsQueueProps {
  onProspectReviewed?: () => void;
}

/** Editable copy of a prospect's fields, kept separate from the fetched record so edits
 * can be cancelled without mutating what's shown in the table underneath. */
interface EditableFields {
  name: string;
  contact_number: string;
  contact_person: string;
  gst_number: string;
  address: string;
  outlet_code: string;
  brandsText: string;
}

function toEditable(p: CustomerProspect): EditableFields {
  return {
    name: p.name,
    contact_number: p.contact_number,
    contact_person: p.contact_person || '',
    gst_number: p.gst_number || '',
    address: p.address,
    outlet_code: p.outlet_code || '',
    brandsText: (p.brands || []).join(', '),
  };
}

export const NewOutletApprovalsQueue: React.FC<NewOutletApprovalsQueueProps> = ({ onProspectReviewed }) => {
  const [prospects, setProspects] = useState<CustomerProspect[]>([]);
  const [statusFilter, setStatusFilter] = useState<ProspectStatus | 'ALL'>('PENDING');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  // Live outlet proofs keyed by prospect id (the prospect read model does not expose its proof id).
  const [proofsByProspect, setProofsByProspect] = useState<Record<string, OutletProof>>({});
  const [proofLightbox, setProofLightbox] = useState<OutletProof | null>(null);

  // Review / edit modal
  const [reviewing, setReviewing] = useState<CustomerProspect | null>(null);
  const [fields, setFields] = useState<EditableFields | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Reject modal
  const [rejecting, setRejecting] = useState<CustomerProspect | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [rejectError, setRejectError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const fetchProspects = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getCustomerProspects(statusFilter === 'ALL' ? undefined : { status: statusFilter });
      setProspects(data);
      try {
        const res = await apiClient.getOutletProofs({ status: statusFilter === 'PENDING' ? 'PENDING' : 'ALL', limit: 200 });
        const map: Record<string, OutletProof> = {};
        for (const pr of Array.isArray(res.items) ? res.items : []) {
          if (pr && pr.prospect_id && !map[pr.prospect_id]) map[pr.prospect_id] = pr;
        }
        setProofsByProspect(map);
      } catch {
        setProofsByProspect({});
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load new-outlet submissions');
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchProspects();
  }, [fetchProspects]);

  const openReview = (p: CustomerProspect) => {
    setReviewing(p);
    setFields(toEditable(p));
    setSaveError(null);
  };

  const closeReview = () => {
    setReviewing(null);
    setFields(null);
  };

  /** Saves any edits (if changed) first, then approves - one action from the admin's perspective. */
  const handleApprove = async () => {
    if (!reviewing || !fields) return;
    setIsSaving(true);
    setSaveError(null);
    try {
      const original = toEditable(reviewing);
      const changed = JSON.stringify(original) !== JSON.stringify(fields);
      if (changed) {
        await apiClient.updateCustomerProspect(reviewing.id, {
          name: fields.name,
          contact_number: fields.contact_number,
          contact_person: fields.contact_person || null,
          gst_number: fields.gst_number || null,
          address: fields.address,
          outlet_code: fields.outlet_code || null,
          brands: fields.brandsText.split(',').map((b) => b.trim()).filter(Boolean),
        });
      }
      const customer = await apiClient.approveCustomerProspect(reviewing.id);
      setSuccessMessage(
        `Approved '${customer.name}'. It is now live. Remember to add it to TallyPrime manually - it will show a "Not in Tally" badge in the Outlets Directory until you mark it done.`
      );
      closeReview();
      fetchProspects();
      onProspectReviewed?.();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Failed to approve submission');
    } finally {
      setIsSaving(false);
    }
  };

  const openReject = (p: CustomerProspect) => {
    setRejecting(p);
    setRejectionReason('');
    setRejectError(null);
  };

  const handleConfirmReject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rejecting) return;
    if (!rejectionReason.trim() || rejectionReason.trim().length < 3) {
      setRejectError('Please provide a valid rejection reason (minimum 3 characters).');
      return;
    }
    setIsProcessing(true);
    setRejectError(null);
    try {
      await apiClient.rejectCustomerProspect(rejecting.id, rejectionReason.trim());
      setSuccessMessage(`Rejected submission for '${rejecting.name}'.`);
      setRejecting(null);
      closeReview();
      fetchProspects();
      onProspectReviewed?.();
    } catch (err) {
      setRejectError(err instanceof Error ? err.message : 'Failed to reject submission');
    } finally {
      setIsProcessing(false);
    }
  };

  const columns: Column<CustomerProspect>[] = [
    {
      header: 'Outlet',
      accessor: (p) => (
        <div>
          <p className="font-headline-sm text-sm text-primary font-bold">{p.name}</p>
          <div className="flex items-center gap-2 mt-1">
            {p.outlet_code && (
              <span className="font-mono text-[11px] font-bold text-on-primary-container bg-primary-container px-2 py-0.5 rounded">
                {p.outlet_code}
              </span>
            )}
            <span className="text-xs text-on-surface-variant font-caption">{p.address}</span>
          </div>
        </div>
      ),
    },
    {
      header: 'Contact',
      accessor: (p) => (
        <div className="font-caption text-xs">
          <p className="text-on-surface">{p.contact_person || '—'}</p>
          <p className="font-mono text-on-surface-variant">{p.contact_number}</p>
        </div>
      ),
    },
    {
      header: 'Brands',
      accessor: (p) => (
        <div className="flex flex-wrap gap-1">
          {(p.brands || []).length === 0 ? (
            <span className="text-xs text-on-surface-variant italic">None</span>
          ) : (
            p.brands.map((b) => (
              <span key={b} className="text-[10px] bg-surface-container-high px-1.5 py-0.5 rounded font-medium">
                {b}
              </span>
            ))
          )}
          {p.requirement && (
            <span className="text-[10px] bg-amber-50 text-amber-800 border border-amber-200 px-1.5 py-0.5 rounded font-mono">
              +requirement
            </span>
          )}
        </div>
      ),
    },
    {
      header: 'Live Proof',
      accessor: (p) => <ProspectProofPanel compact proof={proofsByProspect[p.id]} onOpenPhoto={setProofLightbox} />,
    },
    {
      header: 'Submitted By',
      accessor: (p) => (
        <div className="font-caption text-xs">
          <p className="font-semibold text-on-surface">{p.submitted_by_name || 'Field Employee'}</p>
          <p className="text-on-surface-variant text-[11px] mt-0.5">
            {new Date(p.submitted_at).toLocaleDateString()} at{' '}
            {new Date(p.submitted_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </p>
        </div>
      ),
    },
    {
      header: 'Status',
      accessor: (p) => {
        if (p.status === 'PENDING') {
          return (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-bold bg-amber-100 text-amber-900 border border-amber-300 rounded-full">
              <Clock className="w-3 h-3" /> PENDING
            </span>
          );
        }
        if (p.status === 'APPROVED') {
          return (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-bold bg-emerald-100 text-emerald-900 border border-emerald-300 rounded-full">
              <ShieldCheck className="w-3 h-3" /> APPROVED
            </span>
          );
        }
        return (
          <span
            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-bold bg-rose-100 text-rose-900 border border-rose-300 rounded-full"
            title={p.rejection_reason || undefined}
          >
            <X className="w-3 h-3" /> REJECTED
          </span>
        );
      },
    },
    {
      header: 'Actions',
      accessor: (p) => (
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => openReview(p)}>
            <Pencil className="w-3.5 h-3.5 mr-1" /> Review
          </Button>
          {p.status === 'PENDING' && (
            <button
              onClick={() => openReject(p)}
              disabled={isProcessing}
              className="p-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-md transition-colors cursor-pointer disabled:opacity-50"
              title="Reject"
              aria-label="Reject"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-1 bg-surface-container p-1 rounded-lg border border-outline-variant">
          {(['PENDING', 'APPROVED', 'REJECTED', 'ALL'] as const).map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-3 py-1.5 text-xs font-bold rounded-md transition-colors cursor-pointer ${
                statusFilter === st ? 'bg-surface text-primary shadow-xs' : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              {st === 'PENDING' ? 'Pending Approval' : st.charAt(0) + st.slice(1).toLowerCase()}
            </button>
          ))}
        </div>

        <Button variant="outline" size="sm" onClick={fetchProspects} isLoading={isLoading}>
          Refresh Queue
        </Button>
      </div>

      {successMessage && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-sm flex items-center justify-between gap-3">
          <span>{successMessage}</span>
          <button onClick={() => setSuccessMessage(null)} className="text-emerald-700 hover:text-emerald-900 text-xs font-bold cursor-pointer shrink-0">
            Dismiss
          </button>
        </div>
      )}

      {error && <ErrorBanner message={error} onRetry={fetchProspects} />}

      <DataTable
        columns={columns}
        data={prospects}
        rowKey={(p: CustomerProspect) => p.id}
        isLoading={isLoading}
        emptyMessage={`No ${statusFilter === 'ALL' ? '' : statusFilter.toLowerCase() + ' '}new-outlet submissions found.`}
      />

      {/* Review / edit modal */}
      {reviewing && fields && (
        <Modal isOpen={true} onClose={closeReview} title={`Review New Outlet: ${reviewing.name}`}>
          <div className="space-y-4">
            {reviewing.status !== 'PENDING' && (
              <div className="p-2.5 bg-surface-container rounded-lg text-xs text-on-surface-variant">
                This submission is already <strong>{reviewing.status}</strong>
                {reviewing.rejection_reason ? `: ${reviewing.rejection_reason}` : '.'}
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="block text-xs font-bold text-on-surface mb-1">Outlet Name</label>
                <input
                  className="w-full text-sm p-2 rounded border border-outline bg-surface text-on-surface disabled:opacity-60"
                  value={fields.name}
                  disabled={reviewing.status !== 'PENDING'}
                  onChange={(e) => setFields({ ...fields, name: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-on-surface mb-1">Contact Person</label>
                <input
                  className="w-full text-sm p-2 rounded border border-outline bg-surface text-on-surface disabled:opacity-60"
                  value={fields.contact_person}
                  disabled={reviewing.status !== 'PENDING'}
                  onChange={(e) => setFields({ ...fields, contact_person: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-on-surface mb-1">Contact Number</label>
                <input
                  className="w-full text-sm p-2 rounded border border-outline bg-surface text-on-surface disabled:opacity-60"
                  value={fields.contact_number}
                  disabled={reviewing.status !== 'PENDING'}
                  onChange={(e) => setFields({ ...fields, contact_number: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-on-surface mb-1">GST Number</label>
                <input
                  className="w-full text-sm p-2 rounded border border-outline bg-surface text-on-surface disabled:opacity-60"
                  value={fields.gst_number}
                  disabled={reviewing.status !== 'PENDING'}
                  onChange={(e) => setFields({ ...fields, gst_number: e.target.value })}
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-on-surface mb-1">Outlet / DMS Code</label>
                <input
                  className="w-full text-sm p-2 rounded border border-outline bg-surface text-on-surface font-mono disabled:opacity-60"
                  value={fields.outlet_code}
                  disabled={reviewing.status !== 'PENDING'}
                  onChange={(e) => setFields({ ...fields, outlet_code: e.target.value })}
                />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-bold text-on-surface mb-1">Address</label>
                <textarea
                  rows={2}
                  className="w-full text-sm p-2 rounded border border-outline bg-surface text-on-surface disabled:opacity-60"
                  value={fields.address}
                  disabled={reviewing.status !== 'PENDING'}
                  onChange={(e) => setFields({ ...fields, address: e.target.value })}
                />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-bold text-on-surface mb-1">Brands (comma-separated)</label>
                <input
                  className="w-full text-sm p-2 rounded border border-outline bg-surface text-on-surface disabled:opacity-60"
                  value={fields.brandsText}
                  disabled={reviewing.status !== 'PENDING'}
                  onChange={(e) => setFields({ ...fields, brandsText: e.target.value })}
                  placeholder="e.g. Havells, Finolex"
                />
              </div>
            </div>

            {reviewing.requirement && (
              <div className="p-3 bg-surface-container rounded-lg space-y-1 text-xs text-on-surface">
                <p className="font-bold">Initial Requirement / Order</p>
                {reviewing.requirement.brand && <p><strong>Brand:</strong> {reviewing.requirement.brand}</p>}
                {reviewing.requirement.requirement_type && <p><strong>Type:</strong> {reviewing.requirement.requirement_type}</p>}
                {reviewing.requirement.product_details && <p><strong>Details:</strong> {reviewing.requirement.product_details}</p>}
                {reviewing.requirement.quantity != null && <p><strong>Quantity:</strong> {reviewing.requirement.quantity}</p>}
                {reviewing.requirement.expected_value != null && <p><strong>Expected Value:</strong> {formatMoney(reviewing.requirement.expected_value)}</p>}
                {reviewing.requirement.notes && <p><strong>Notes:</strong> {reviewing.requirement.notes}</p>}
              </div>
            )}

            <ProspectProofPanel proof={proofsByProspect[reviewing.id]} onOpenPhoto={setProofLightbox} />

            {reviewing.location && (
              <div className="rounded-xl overflow-hidden border border-outline-variant shadow-xs">
                <FieldTrackMap
                  height="240px"
                  markers={[
                    {
                      id: 'proposed',
                      latitude: reviewing.location.latitude,
                      longitude: reviewing.location.longitude,
                      label: fields.name,
                      color: '#059669',
                    },
                  ]}
                  territoryCircles={[
                    {
                      id: 'proposed-circle',
                      centerLat: reviewing.location.latitude,
                      centerLng: reviewing.location.longitude,
                      radiusKm: 0.1,
                      color: '#059669',
                    },
                  ]}
                />
                {reviewing.gps_accuracy_meters != null && (
                  <div className="px-2 py-1 bg-surface-container text-[11px] text-on-surface-variant">
                    GPS accuracy: ±{Math.round(reviewing.gps_accuracy_meters)}m
                  </div>
                )}
              </div>
            )}
            {!reviewing.location && (
              <p className="text-xs text-on-surface-variant italic">No GPS pin was captured for this submission.</p>
            )}

            {saveError && <ErrorBanner message={saveError} />}

            {reviewing.status === 'PENDING' && (
              <div className="flex justify-end gap-2 pt-2 border-t border-outline-variant">
                <Button variant="outline" onClick={closeReview} disabled={isSaving}>
                  Cancel
                </Button>
                <Button
                  variant="danger"
                  onClick={() => {
                    const p = reviewing;
                    closeReview();
                    openReject(p);
                  }}
                  disabled={isSaving}
                >
                  Reject
                </Button>
                <Button
                  variant="primary"
                  onClick={handleApprove}
                  isLoading={isSaving}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold"
                >
                  Save &amp; Approve
                </Button>
              </div>
            )}
          </div>
        </Modal>
      )}

      <OutletPhotoLightbox
        proofId={proofLightbox?.id ?? null}
        title={proofLightbox ? 'New outlet live photo' : undefined}
        onClose={() => setProofLightbox(null)}
      />

      {/* Reject modal */}
      {rejecting && (
        <Modal isOpen={true} onClose={() => setRejecting(null)} title={`Reject Submission for ${rejecting.name}`}>
          <form onSubmit={handleConfirmReject} className="space-y-4">
            <p className="text-xs text-on-surface-variant">
              The employee will be notified with this reason. No outlet will be created.
            </p>
            <div>
              <label className="block text-xs font-bold text-on-surface mb-1">
                Rejection Reason <span className="text-rose-600">*</span>
              </label>
              <textarea
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="e.g. Duplicate of an existing outlet nearby - please search before adding a new one."
                rows={3}
                className="w-full text-xs p-2 rounded border border-outline bg-surface text-on-surface focus:outline-hidden focus:ring-1 focus:ring-primary"
                required
              />
            </div>
            {rejectError && <ErrorBanner message={rejectError} />}
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setRejecting(null)} disabled={isProcessing}>
                Cancel
              </Button>
              <Button type="submit" variant="danger" isLoading={isProcessing}>
                Confirm Rejection
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
};
