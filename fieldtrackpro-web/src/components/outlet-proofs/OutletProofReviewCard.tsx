import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, XCircle, Smartphone, User as UserIcon, Clock, MapPin } from 'lucide-react';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { ErrorBanner } from '../ui/ErrorBanner';
import { OutletProof } from '../../types';
import { formatIstDateTime } from '../../utils/ist';
import { formatDistance, PROOF_COLORS } from '../../utils/outletProof';
import { OutletProofImage } from './OutletProofImage';
import { OutletProofMap } from './OutletProofMap';
import { AccuracyChip, ProofKindBadge, ProofStatusBadge, ProofWarningChips } from './OutletProofBadges';

interface OutletProofReviewCardProps {
  proof: OutletProof;
  /** Other pending proofs of the same outlet that are currently loaded (shown grey on the map). */
  candidates?: OutletProof[];
  onOpenPhoto: (proof: OutletProof) => void;
  /** Resolve with an error message to keep the dialog open, or null on success. */
  onApprove: (proof: OutletProof) => Promise<string | null>;
  onReject: (proof: OutletProof, reason: string) => Promise<string | null>;
}

/** One review card: LEFT live photo, RIGHT map + facts, actions underneath. */
export const OutletProofReviewCard: React.FC<OutletProofReviewCardProps> = ({
  proof,
  candidates = [],
  onOpenPhoto,
  onApprove,
  onReject,
}) => {
  const [confirming, setConfirming] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);

  const name = proof.customer_name || proof.prospect_name || 'Unknown outlet';
  const code = proof.customer_outlet_code;
  const isPending = proof.status === 'PENDING';
  // A proof of a not-yet-approved new outlet is approved together with the outlet itself.
  const isProspectProof = !proof.customer_id && !!proof.prospect_id;
  const hasVerified = proof.customer_latitude != null && proof.customer_longitude != null;

  const approve = async () => {
    setBusy(true);
    setDialogError(null);
    const err = await onApprove(proof);
    setBusy(false);
    if (err) setDialogError(err);
    else setConfirming(false);
  };

  const reject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (reason.trim().length < 3) {
      setDialogError('Please provide a rejection reason (minimum 3 characters).');
      return;
    }
    setBusy(true);
    setDialogError(null);
    const err = await onReject(proof, reason.trim());
    setBusy(false);
    if (err) setDialogError(err);
    else {
      setRejecting(false);
      setReason('');
    }
  };

  return (
    <article
      data-testid="outlet-proof-card"
      className="bg-surface border border-outline-variant rounded-xl shadow-xs overflow-hidden"
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 p-4">
        {/* LEFT: live photo */}
        <div>
          <OutletProofImage
            proofId={proof.id}
            alt={`Live photo of ${name}`}
            className="w-full h-64 rounded-lg"
            emptyLabel="Photo unavailable"
            onClick={() => onOpenPhoto(proof)}
          />
          <p className="mt-1 text-[11px] text-on-surface-variant">Click the photo to enlarge.</p>
        </div>

        {/* RIGHT: map + facts */}
        <div className="space-y-3 min-w-0">
          <OutletProofMap
            proposed={{ id: proof.id, latitude: proof.latitude, longitude: proof.longitude, accuracyM: proof.accuracy_m }}
            verified={hasVerified ? { latitude: proof.customer_latitude!, longitude: proof.customer_longitude! } : null}
            others={candidates.map((c) => ({ id: c.id, latitude: c.latitude, longitude: c.longitude }))}
            height="200px"
          />
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-on-surface-variant" data-testid="map-legend">
            <span className="inline-flex items-center gap-1">
              <i className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: PROOF_COLORS.proposed }} /> Proposed
            </span>
            {hasVerified && (
              <span className="inline-flex items-center gap-1">
                <i className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: PROOF_COLORS.verified }} /> Verified
                {proof.distance_from_verified_m != null && (
                  <strong className="text-on-surface">{formatDistance(proof.distance_from_verified_m)} apart</strong>
                )}
              </span>
            )}
            {candidates.length > 0 && (
              <span className="inline-flex items-center gap-1">
                <i className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: PROOF_COLORS.other }} /> Other pending ({candidates.length})
              </span>
            )}
            {!hasVerified && <span>No verified location yet</span>}
          </div>
          {(proof.nearby_pending_proofs ?? 0) > 0 && (
            <p className="text-[11px] text-amber-800">
              {proof.nearby_pending_proofs} other pending proof(s) for this outlet within the confirm radius.
            </p>
          )}
        </div>
      </div>

      <div className="px-4 pb-4 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-headline-sm text-sm font-bold text-primary">{name}</h3>
          {code && (
            <span className="font-mono text-[11px] font-bold text-on-primary-container bg-primary-container px-2 py-0.5 rounded">
              {code}
            </span>
          )}
          <ProofKindBadge kind={proof.kind} />
          <ProofStatusBadge status={proof.status} />
          <AccuracyChip accuracyM={proof.accuracy_m} />
        </div>
        <ProofWarningChips proof={proof} />
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-xs text-on-surface">
          <div className="flex items-center gap-1.5">
            <MapPin className="w-3.5 h-3.5 text-on-surface-variant" />
            <dt className="sr-only">Zone / Area</dt>
            <dd>{proof.territory_name || '-'} / {proof.area_name || '-'}</dd>
          </div>
          <div className="flex items-center gap-1.5">
            <UserIcon className="w-3.5 h-3.5 text-on-surface-variant" />
            <dt className="sr-only">Submitted by</dt>
            <dd>{proof.submitted_by_name || 'Field employee'}</dd>
          </div>
          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-on-surface-variant" />
            <dt className="sr-only">Captured at</dt>
            <dd data-testid="captured-at">{formatIstDateTime(proof.captured_at)} IST</dd>
          </div>
          <div className="flex items-center gap-1.5">
            <Smartphone className="w-3.5 h-3.5 text-on-surface-variant" />
            <dt className="sr-only">Device</dt>
            <dd className="truncate">{proof.device_info || 'Unknown device'}</dd>
          </div>
          <div className="font-mono text-[11px] text-on-surface-variant sm:col-span-2">
            {proof.latitude.toFixed(6)}, {proof.longitude.toFixed(6)}
          </div>
        </dl>
        {proof.status === 'REJECTED' && proof.rejection_reason && (
          <p className="text-xs text-rose-800">Rejected: {proof.rejection_reason}</p>
        )}

        {isPending && (
          <div className="flex flex-wrap items-center justify-end gap-2 pt-2 border-t border-outline-variant">
            {isProspectProof && (
              <span className="mr-auto text-[11px] text-on-surface-variant">
                New outlet: approve it in{' '}
                <Link to="/customers" className="text-primary underline">Customers &rarr; New Outlets</Link>; its location
                and photo are approved together.
              </span>
            )}
            <Button
              variant="danger"
              size="sm"
              icon={XCircle}
              onClick={() => {
                setDialogError(null);
                setRejecting(true);
              }}
            >
              Reject
            </Button>
            <Button
              variant="primary"
              size="sm"
              icon={CheckCircle2}
              disabled={isProspectProof}
              title={isProspectProof ? 'Approve the new outlet first' : undefined}
              onClick={() => {
                setDialogError(null);
                setConfirming(true);
              }}
              className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold"
            >
              Approve location &amp; photo
            </Button>
          </div>
        )}
      </div>

      {confirming && (
        <Modal isOpen onClose={() => !busy && setConfirming(false)} title="Approve location & photo?">
          <div className="space-y-4">
            <p className="text-sm text-on-surface">
              This sets the official location of <strong>{name}</strong> to the proposed point
              ({proof.latitude.toFixed(6)}, {proof.longitude.toFixed(6)}) and uses this live photo as the outlet photo.
            </p>
            <ProofWarningChips proof={proof} />
            {dialogError && <ErrorBanner message={dialogError} />}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setConfirming(false)} disabled={busy}>
                Cancel
              </Button>
              <Button
                variant="primary"
                isLoading={busy}
                onClick={approve}
                className="bg-emerald-600 hover:bg-emerald-700 text-white font-bold"
              >
                Confirm approval
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {rejecting && (
        <Modal isOpen onClose={() => !busy && setRejecting(false)} title={`Reject proof for ${name}`}>
          <form onSubmit={reject} className="space-y-4">
            <p className="text-xs text-on-surface-variant">The employee is notified with this reason.</p>
            <div>
              <label htmlFor={`reject-${proof.id}`} className="block text-xs font-bold text-on-surface mb-1">
                Rejection reason <span className="text-rose-600">*</span>
              </label>
              <textarea
                id={`reject-${proof.id}`}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={3}
                maxLength={255}
                placeholder="e.g. Photo does not show the shop front."
                className="w-full text-xs p-2 rounded border border-outline bg-surface text-on-surface"
              />
            </div>
            {dialogError && <ErrorBanner message={dialogError} />}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setRejecting(false)} disabled={busy}>
                Cancel
              </Button>
              <Button type="submit" variant="danger" isLoading={busy}>
                Confirm rejection
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </article>
  );
};
