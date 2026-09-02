import React, { useCallback, useEffect, useState } from 'react';
import { Check, X, Clock, ShieldCheck } from 'lucide-react';
import { DataTable, Column } from '../ui/DataTable';
import { FieldTrackMap } from '../maps/FieldTrackMap';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { ErrorBanner } from '../ui/ErrorBanner';
import { apiClient } from '../../api/client';
import { LocationProposal } from '../../types';

interface LocationApprovalsQueueProps {
  onProposalReviewed?: () => void;
}

export const LocationApprovalsQueue: React.FC<LocationApprovalsQueueProps> = ({ onProposalReviewed }) => {
  const [proposals, setProposals] = useState<LocationProposal[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('PENDING');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Review / Map Modal
  const [selectedProposal, setSelectedProposal] = useState<LocationProposal | null>(null);

  // Approve Modal
  const [approvingProposal, setApprovingProposal] = useState<LocationProposal | null>(null);
  const [approveError, setApproveError] = useState<string | null>(null);

  // Reject Modal
  const [rejectingProposal, setRejectingProposal] = useState<LocationProposal | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [rejectError, setRejectError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  // Success message toast/banner
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const fetchProposals = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getLocationProposals({ status: statusFilter, limit: 100 });
      setProposals(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load location proposals');
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchProposals();
  }, [fetchProposals]);

  const handleOpenApprove = (proposal: LocationProposal) => {
    setApprovingProposal(proposal);
    setApproveError(null);
  };

  const handleConfirmApprove = async () => {
    if (!approvingProposal) return;
    setIsProcessing(true);
    setApproveError(null);
    try {
      await apiClient.approveLocationProposal(approvingProposal.id);
      setSuccessMessage(`Approved location for ${approvingProposal.customer_name || 'customer'}. Official coordinates updated.`);
      setApprovingProposal(null);
      setSelectedProposal(null);
      fetchProposals();
      onProposalReviewed?.();
    } catch (err) {
      setApproveError(err instanceof Error ? err.message : 'Failed to approve location proposal');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleOpenReject = (proposal: LocationProposal) => {
    setRejectingProposal(proposal);
    setRejectionReason('');
    setRejectError(null);
  };

  const handleConfirmReject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rejectingProposal) return;
    if (!rejectionReason.trim() || rejectionReason.trim().length < 3) {
      setRejectError('Please provide a valid rejection reason (minimum 3 characters).');
      return;
    }
    setIsProcessing(true);
    setRejectError(null);
    try {
      await apiClient.rejectLocationProposal(rejectingProposal.id, rejectionReason.trim());
      setSuccessMessage(`Rejected location proposal for ${rejectingProposal.customer_name || 'customer'}.`);
      setRejectingProposal(null);
      setSelectedProposal(null);
      fetchProposals();
      onProposalReviewed?.();
    } catch (err) {
      setRejectError(err instanceof Error ? err.message : 'Failed to reject location proposal');
    } finally {
      setIsProcessing(false);
    }
  };

  const columns: Column<LocationProposal>[] = [
    {
      header: 'Outlet / Customer',
      accessor: (p) => (
        <div>
          <p className="font-headline-sm text-sm text-primary font-bold">{p.customer_name || '—'}</p>
          <div className="flex items-center gap-2 mt-1">
            {p.customer_outlet_code && (
              <span className="font-mono text-[11px] font-bold text-on-primary-container bg-primary-container px-2 py-0.5 rounded">
                {p.customer_outlet_code}
              </span>
            )}
            <span className="text-xs text-on-surface-variant font-caption">ID: {p.customer_id.slice(0, 8)}...</span>
          </div>
        </div>
      ),
    },
    {
      header: 'Current GPS',
      accessor: (p) => (
        <div className="font-caption text-xs">
          {p.current_latitude != null && p.current_longitude != null ? (
            <span className="font-mono text-on-surface">
              {p.current_latitude.toFixed(6)}, {p.current_longitude.toFixed(6)}
            </span>
          ) : (
            <span className="text-on-surface-variant italic">Not registered</span>
          )}
        </div>
      ),
    },
    {
      header: 'Proposed GPS & Fix',
      accessor: (p) => (
        <div className="space-y-1 font-caption text-xs">
          <p className="font-mono text-emerald-700 font-bold">
            {p.proposed_latitude.toFixed(6)}, {p.proposed_longitude.toFixed(6)}
          </p>
          <div className="flex items-center gap-1.5 flex-wrap">
            {p.gps_accuracy_meters != null && (
              <span className="text-[10px] bg-emerald-50 text-emerald-800 border border-emerald-200 px-1.5 py-0.5 rounded font-mono font-medium">
                ±{Math.round(p.gps_accuracy_meters)}m accuracy
              </span>
            )}
            {p.distance_meters != null && (
              <span className="text-[10px] bg-amber-50 text-amber-800 border border-amber-200 px-1.5 py-0.5 rounded font-mono">
                {p.distance_meters > 1000 ? `${(p.distance_meters / 1000).toFixed(1)}km` : `${Math.round(p.distance_meters)}m`} shift
              </span>
            )}
          </div>
        </div>
      ),
    },
    {
      header: 'Submitted By',
      accessor: (p) => (
        <div className="font-caption text-xs">
          <p className="font-semibold text-on-surface">{p.submitter_name || 'Field Employee'}</p>
          <p className="text-on-surface-variant text-[11px] mt-0.5">
            {new Date(p.submitted_at).toLocaleDateString()} at {new Date(p.submitted_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
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
          <span className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-bold bg-rose-100 text-rose-900 border border-rose-300 rounded-full" title={p.rejection_reason || undefined}>
            <X className="w-3 h-3" /> REJECTED
          </span>
        );
      },
    },
    {
      header: 'Actions',
      accessor: (p) => (
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setSelectedProposal(p)}
          >
            Review on Map
          </Button>
          {p.status === 'PENDING' && (
            <>
              <button
                onClick={() => handleOpenApprove(p)}
                disabled={isProcessing}
                className="p-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-md transition-colors cursor-pointer disabled:opacity-50"
                title="Approve Location"
                aria-label="Approve Location"
              >
                <Check className="w-4 h-4" />
              </button>
              <button
                onClick={() => handleOpenReject(p)}
                disabled={isProcessing}
                className="p-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-md transition-colors cursor-pointer disabled:opacity-50"
                title="Reject Location"
                aria-label="Reject Location"
              >
                <X className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      {/* Filter Tabs */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-1 bg-surface-container p-1 rounded-lg border border-outline-variant">
          {(['PENDING', 'APPROVED', 'REJECTED', 'ALL'] as const).map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-3 py-1.5 text-xs font-bold rounded-md transition-colors cursor-pointer ${
                statusFilter === st
                  ? 'bg-surface text-primary shadow-xs'
                  : 'text-on-surface-variant hover:text-on-surface'
              }`}
            >
              {st === 'PENDING' ? 'Pending Approval' : st.charAt(0) + st.slice(1).toLowerCase()}
            </button>
          ))}
        </div>

        <Button variant="outline" size="sm" onClick={fetchProposals} isLoading={isLoading}>
          Refresh Queue
        </Button>
      </div>

      {successMessage && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-sm flex items-center justify-between">
          <span>{successMessage}</span>
          <button onClick={() => setSuccessMessage(null)} className="text-emerald-700 hover:text-emerald-900 text-xs font-bold cursor-pointer">
            Dismiss
          </button>
        </div>
      )}

      {error && <ErrorBanner message={error} onRetry={fetchProposals} />}

      {/* Proposals Data Table */}
      <DataTable
        columns={columns}
        data={proposals}
        rowKey={(p: LocationProposal) => p.id}
        isLoading={isLoading}
        emptyMessage={`No ${statusFilter.toLowerCase()} location proposals found.`}
      />

      {/* Review On Map Modal */}
      {selectedProposal && (
        <Modal
          isOpen={true}
          onClose={() => setSelectedProposal(null)}
          title={`Location Verification: ${selectedProposal.customer_name || 'Customer'}`}
        >
          <div className="space-y-4">
            {/* Map Preview */}
            <div className="rounded-xl overflow-hidden border border-outline-variant shadow-xs">
              <FieldTrackMap
                height="320px"
                markers={[
                  ...(selectedProposal.current_latitude != null && selectedProposal.current_longitude != null
                    ? [
                        {
                          id: 'current',
                          latitude: selectedProposal.current_latitude,
                          longitude: selectedProposal.current_longitude,
                          label: `Registered: ${selectedProposal.customer_name || 'Outlet'}`,
                          color: '#64748b',
                        },
                      ]
                    : []),
                  {
                    id: 'proposed',
                    latitude: selectedProposal.proposed_latitude,
                    longitude: selectedProposal.proposed_longitude,
                    label: `Proposed: ${selectedProposal.customer_name || 'Outlet'}`,
                    color: '#059669',
                  },
                ]}
                territoryCircles={[
                  ...(selectedProposal.current_latitude != null && selectedProposal.current_longitude != null
                    ? [
                        {
                          id: 'current-circle',
                          centerLat: selectedProposal.current_latitude,
                          centerLng: selectedProposal.current_longitude,
                          radiusKm: 0.1,
                          color: '#64748b',
                        },
                      ]
                    : []),
                  {
                    id: 'proposed-circle',
                    centerLat: selectedProposal.proposed_latitude,
                    centerLng: selectedProposal.proposed_longitude,
                    radiusKm: 0.1,
                    color: '#059669',
                  },
                ]}
              />
            </div>

            {/* Submitter details & notes */}
            <div className="p-3 bg-surface-container rounded-lg space-y-1 text-xs text-on-surface">
              <p><strong>Submitted By:</strong> {selectedProposal.submitter_name || 'Employee'} ({new Date(selectedProposal.submitted_at).toLocaleString()})</p>
              {selectedProposal.notes && (
                <p><strong>Notes from Field:</strong> {selectedProposal.notes}</p>
              )}
            </div>

            {/* Action Buttons in Review Modal */}
            <div className="flex justify-end gap-2 pt-2 border-t border-outline-variant">
              <Button variant="outline" onClick={() => setSelectedProposal(null)}>
                Close
              </Button>
              {selectedProposal.status === 'PENDING' && (
                <>
                  <Button
                    variant="danger"
                    onClick={() => {
                      const p = selectedProposal;
                      setSelectedProposal(null);
                      handleOpenReject(p);
                    }}
                    disabled={isProcessing}
                  >
                    Reject Proposal
                  </Button>
                  <Button
                    variant="primary"
                    onClick={() => {
                      const p = selectedProposal;
                      setSelectedProposal(null);
                      handleOpenApprove(p);
                    }}
                    disabled={isProcessing}
                    className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold"
                  >
                    Approve Location
                  </Button>
                </>
              )}
            </div>
          </div>
        </Modal>
      )}

      {/* Approve Modal */}
      {approvingProposal && (
        <Modal
          isOpen={true}
          onClose={() => setApprovingProposal(null)}
          title={`Approve Location for ${approvingProposal.customer_name || 'Customer'}`}
        >
          <div className="space-y-4">
            <div className="p-3 bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/40 rounded-xl space-y-2">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                <span className="font-headline-sm text-sm font-bold text-emerald-800 dark:text-emerald-300">
                  Update Official Customer Geofence
                </span>
              </div>
              <p className="text-xs text-emerald-700 dark:text-emerald-400 leading-relaxed">
                Approving this proposal will immediately update the official GPS coordinates in the database and mark the customer location status as <strong>VERIFIED</strong>.
              </p>
            </div>

            <div className="space-y-2 bg-surface-container p-3 rounded-xl border border-outline-variant text-xs">
              <div className="flex justify-between">
                <span className="text-on-surface-variant font-medium">Customer:</span>
                <span className="font-bold text-primary">{approvingProposal.customer_name || '—'}</span>
              </div>
              {approvingProposal.customer_outlet_code && (
                <div className="flex justify-between">
                  <span className="text-on-surface-variant font-medium">Outlet Code:</span>
                  <span className="font-mono font-bold text-on-primary-container bg-primary-container px-1.5 py-0.5 rounded text-[11px]">
                    {approvingProposal.customer_outlet_code}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-on-surface-variant font-medium">Proposed GPS:</span>
                <span className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                  {approvingProposal.proposed_latitude.toFixed(6)}, {approvingProposal.proposed_longitude.toFixed(6)}
                </span>
              </div>
              {approvingProposal.gps_accuracy_meters != null && (
                <div className="flex justify-between">
                  <span className="text-on-surface-variant font-medium">Accuracy:</span>
                  <span className="font-mono">±{Math.round(approvingProposal.gps_accuracy_meters)}m</span>
                </div>
              )}
              {approvingProposal.distance_meters != null && (
                <div className="flex justify-between">
                  <span className="text-on-surface-variant font-medium">Location Shift:</span>
                  <span className="font-mono text-amber-600 font-bold">
                    {(approvingProposal.distance_meters / 1000).toFixed(2)} km shift
                  </span>
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
              <Button variant="outline" onClick={() => setApprovingProposal(null)} disabled={isProcessing}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleConfirmApprove}
                isLoading={isProcessing}
                className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold"
              >
                Confirm &amp; Update Location
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Reject Modal */}
      {rejectingProposal && (
        <Modal
          isOpen={true}
          onClose={() => setRejectingProposal(null)}
          title={`Reject Location Proposal for ${rejectingProposal.customer_name || 'Customer'}`}
        >
          <form onSubmit={handleConfirmReject} className="space-y-4">
            <p className="text-xs text-on-surface-variant">
              Please enter a reason for rejecting this proposed location ({rejectingProposal.proposed_latitude.toFixed(6)}, {rejectingProposal.proposed_longitude.toFixed(6)}). The official coordinates will remain unchanged.
            </p>

            <div>
              <label className="block text-xs font-bold text-on-surface mb-1">
                Rejection Reason <span className="text-rose-600">*</span>
              </label>
              <textarea
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="e.g. Coordinates mismatch outlet address; please recapture in front of the store entrance."
                rows={3}
                className="w-full text-xs p-2 rounded border border-outline bg-surface text-on-surface focus:outline-hidden focus:ring-1 focus:ring-primary"
                required
              />
            </div>

            {rejectError && <ErrorBanner message={rejectError} />}

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setRejectingProposal(null)} disabled={isProcessing}>
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
