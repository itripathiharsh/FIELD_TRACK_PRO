import React, { useEffect, useState } from 'react';
import { Camera, ShieldCheck, Clock, AlertTriangle, Users } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardSubtitle } from '../ui/Card';
import { apiClient } from '../../api/client';
import { Customer, OutletProof } from '../../types';
import { formatIstDateTime } from '../../utils/ist';
import { OutletPhotoLightbox, OutletProofImage } from './OutletProofImage';
import { AccuracyChip, ProofKindBadge, ProofStatusBadge, ProofWarningChips } from './OutletProofBadges';

interface CustomerOutletProofSectionProps {
  customer: Customer;
}

/** Customer detail: primary outlet photo, location status, confirmations and proof history. */
export const CustomerOutletProofSection: React.FC<CustomerOutletProofSectionProps> = ({ customer }) => {
  const [proofs, setProofs] = useState<OutletProof[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [lightbox, setLightbox] = useState<OutletProof | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadError(false);
    apiClient
      .getCustomerOutletProofs(customer.id)
      .then((list) => {
        if (!cancelled) setProofs(Array.isArray(list) ? list : []);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [customer.id]);

  const status = customer.location_status || 'MISSING';
  const confirmations = customer.outlet_location_confirmations ?? 0;
  const hasPhoto = customer.primary_outlet_image_available === true;

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle className="flex items-center gap-2">
            <Camera className="w-5 h-5 text-primary" />
            Outlet Photo &amp; Location Proof
          </CardTitle>
          <CardSubtitle>Live photo with GPS captured at the same click by field employees</CardSubtitle>
        </div>
      </CardHeader>
      <div className="grid grid-cols-1 md:grid-cols-[260px_1fr] gap-5 p-5">
        <div>
          {hasPhoto ? (
            <OutletProofImage
              customerId={customer.id}
              alt={`Outlet photo of ${customer.name}`}
              className="w-full h-52 rounded-lg"
              onClick={
                customer.primary_outlet_proof_id
                  ? () =>
                      setLightbox(
                        proofs.find((p) => p.id === customer.primary_outlet_proof_id) ??
                          ({ id: customer.primary_outlet_proof_id } as OutletProof),
                      )
                  : undefined
              }
            />
          ) : (
            <div
              data-testid="no-outlet-photo"
              className="w-full h-52 rounded-lg bg-surface-container flex flex-col items-center justify-center gap-2 text-on-surface-variant border border-dashed border-outline-variant"
            >
              <Camera className="w-8 h-8" />
              <span className="text-sm">No outlet photo yet</span>
            </div>
          )}
        </div>
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            {status === 'VERIFIED' && (
              <span className="inline-flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-900 border border-emerald-300">
                <ShieldCheck className="w-3.5 h-3.5" /> Location verified
              </span>
            )}
            {status === 'PENDING_APPROVAL' && (
              <span className="inline-flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-full bg-amber-100 text-amber-900 border border-amber-300">
                <Clock className="w-3.5 h-3.5" /> Location pending approval
              </span>
            )}
            {status === 'NEEDS_REVIEW' && (
              <span className="inline-flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-full bg-orange-100 text-orange-900 border border-orange-300">
                <AlertTriangle className="w-3.5 h-3.5" /> Location needs review
              </span>
            )}
            {status === 'MISSING' && (
              <span className="inline-flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-full bg-slate-100 text-slate-700 border border-slate-300">
                No location yet
              </span>
            )}
            <span
              data-testid="confirmations"
              className="inline-flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-full bg-sky-50 text-sky-900 border border-sky-200"
            >
              <Users className="w-3.5 h-3.5" />
              {confirmations === 0
                ? 'Not yet confirmed by employees'
                : `Confirmed by ${confirmations} ${confirmations === 1 ? 'employee' : 'employees'}`}
            </span>
          </div>

          <h4 className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">Location &amp; photo history</h4>
          {loadError ? (
            <p className="text-xs text-rose-700">Could not load the proof history.</p>
          ) : proofs.length === 0 ? (
            <p className="text-xs text-on-surface-variant italic">No proofs submitted for this outlet yet.</p>
          ) : (
            <ul className="divide-y divide-outline-variant border border-outline-variant rounded-lg" data-testid="proof-history">
              {proofs.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 p-2.5 text-xs">
                  <OutletProofImage
                    proofId={p.id}
                    alt="Proof photo"
                    className="w-12 h-12 rounded"
                    emptyLabel=""
                    onClick={() => setLightbox(p)}
                  />
                  <ProofKindBadge kind={p.kind} />
                  <ProofStatusBadge status={p.status} />
                  {p.is_primary && <span className="text-[10px] font-bold text-emerald-800">PRIMARY</span>}
                  <AccuracyChip accuracyM={p.accuracy_m} />
                  <span className="text-on-surface">{p.submitted_by_name || 'Field employee'}</span>
                  <span className="text-on-surface-variant">{formatIstDateTime(p.captured_at)}</span>
                  <ProofWarningChips proof={p} />
                  <button
                    type="button"
                    onClick={() => setLightbox(p)}
                    className="ml-auto text-primary font-bold underline cursor-pointer"
                  >
                    Open photo
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <OutletPhotoLightbox
        proofId={lightbox?.id ?? null}
        title={customer.name}
        onClose={() => setLightbox(null)}
      />
    </Card>
  );
};
