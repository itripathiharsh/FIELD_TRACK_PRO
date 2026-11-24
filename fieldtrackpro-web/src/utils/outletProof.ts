import { ApiError } from '../api/client';
import { OutletProof, OutletProofKind, OutletProofStatus } from '../types';

/** Distance (metres) from the verified pin above which a proof is flagged for extra care. */
export const FAR_FROM_VERIFIED_M = 50;

export const PROOF_COLORS = { proposed: '#f97316', verified: '#059669', other: '#6b7280' } as const;

export type AccuracyTone = 'good' | 'ok' | 'poor';

/** <= 20 m green, <= 30 m amber, otherwise red. */
export function accuracyTone(accuracyM: number): AccuracyTone {
  if (accuracyM <= 20) return 'good';
  if (accuracyM <= 30) return 'ok';
  return 'poor';
}

export const ACCURACY_TONE_CLASS: Record<AccuracyTone, string> = {
  good: 'bg-emerald-100 text-emerald-900 border-emerald-300',
  ok: 'bg-amber-100 text-amber-900 border-amber-300',
  poor: 'bg-rose-100 text-rose-900 border-rose-300',
};

export const KIND_LABEL: Record<OutletProofKind, string> = {
  INITIAL: 'INITIAL',
  CONFIRMATION: 'CONFIRMATION',
  CHANGE_REQUEST: 'CHANGE REQUEST',
};

/** What each proof kind means, in plain words (tooltips + the line under the badges). */
export const KIND_HELP: Record<OutletProofKind, string> = {
  INITIAL: 'First photo and GPS point for this outlet: it has no approved location yet.',
  CONFIRMATION: 'Taken at the approved location (within the confirm radius): it confirms it. No action needed.',
  CHANGE_REQUEST: "Taken away from the approved location: approving it moves the outlet's official pin here.",
};

export const STATUS_HELP: Record<OutletProofStatus, string> = {
  UNATTACHED: 'Captured on the phone but not yet attached to an outlet or a new-outlet request.',
  PENDING: 'Waiting for an admin to approve or reject it.',
  CONFIRMED: 'Agrees with the approved location; counted as a confirmation.',
  APPROVED: "Approved: this photo and GPS point are the outlet's official ones.",
  REJECTED: 'Rejected by an admin; the outlet location did not change.',
  SUPERSEDED: 'Replaced by a newer approved location.',
};

/** '±18 m' explained: how sure the phone was of its position, with the colour bands used on the chip. */
export function accuracyHelp(accuracyM: number): string {
  const m = Math.round(accuracyM);
  const band = accuracyM <= 20 ? 'good (20 m or better)' : accuracyM <= 30 ? 'fair (21-30 m)' : 'poor (more than 30 m)';
  return `GPS accuracy: the phone placed itself within about ${m} m of the true spot when the photo was taken - ${band}.`;
}

export const KIND_CLASS: Record<OutletProofKind, string> = {
  INITIAL: 'bg-sky-100 text-sky-900 border-sky-300',
  CONFIRMATION: 'bg-emerald-100 text-emerald-900 border-emerald-300',
  CHANGE_REQUEST: 'bg-orange-100 text-orange-900 border-orange-300',
};

export const STATUS_CLASS: Record<OutletProofStatus, string> = {
  UNATTACHED: 'bg-slate-100 text-slate-700 border-slate-300',
  PENDING: 'bg-amber-100 text-amber-900 border-amber-300',
  CONFIRMED: 'bg-emerald-100 text-emerald-900 border-emerald-300',
  APPROVED: 'bg-emerald-100 text-emerald-900 border-emerald-300',
  REJECTED: 'bg-rose-100 text-rose-900 border-rose-300',
  SUPERSEDED: 'bg-slate-100 text-slate-700 border-slate-300',
};

/** Warning chips for a proof: mock GPS and/or far from the verified pin. */
export function proofWarnings(p: Pick<OutletProof, 'is_mock_location' | 'distance_from_verified_m'>): string[] {
  const out: string[] = [];
  if (p.is_mock_location) out.push('Mock location detected');
  if (p.distance_from_verified_m != null && p.distance_from_verified_m > FAR_FROM_VERIFIED_M) {
    out.push(`${Math.round(p.distance_from_verified_m)} m from verified location`);
  }
  return out;
}

export function formatDistance(m: number): string {
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`;
}

/** Friendly message for approve/reject failures; falls back to the server message. */
export function outletProofErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.code) {
      case 'OUTLET_PROOF_NOT_PENDING':
        return 'This proof was already reviewed by someone else. The list has been refreshed.';
      case 'OUTLET_PROOF_PROSPECT_PENDING':
        return 'This photo belongs to a new-outlet request. Approve or reject the request in Customers > New Outlet Approvals; its location and photo follow that decision.';
      case 'OUTLET_PROOF_NOT_FOUND':
        return 'This proof no longer exists. The list has been refreshed.';
      default:
        if (err.status === 404) return 'This proof no longer exists. The list has been refreshed.';
        return err.message;
    }
  }
  return err instanceof Error ? err.message : 'Something went wrong. Please try again.';
}

/** True when the error means the row is stale and the list should be reloaded. */
export function isStaleProofError(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 404 || err.code === 'OUTLET_PROOF_NOT_PENDING');
}

/** GeoJSON ring approximating a circle of `radiusM` metres around lng/lat. */
export function circleRing(lng: number, lat: number, radiusM: number, steps = 48): [number, number][] {
  const R = 6371008.8;
  const d = radiusM / R;
  const latR = (lat * Math.PI) / 180;
  const lngR = (lng * Math.PI) / 180;
  const ring: [number, number][] = [];
  for (let i = 0; i < steps; i++) {
    const th = (i * 2 * Math.PI) / steps;
    const pLat = Math.asin(Math.sin(latR) * Math.cos(d) + Math.cos(latR) * Math.sin(d) * Math.cos(th));
    const pLng =
      lngR + Math.atan2(Math.sin(th) * Math.sin(d) * Math.cos(latR), Math.cos(d) - Math.sin(latR) * Math.sin(pLat));
    ring.push([(pLng * 180) / Math.PI, (pLat * 180) / Math.PI]);
  }
  ring.push(ring[0]);
  return ring;
}
