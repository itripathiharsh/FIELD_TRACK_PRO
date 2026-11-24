import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { OutletProof, OutletProofKind, OutletProofStatus } from '../../types';
import {
  ACCURACY_TONE_CLASS,
  accuracyHelp,
  accuracyTone,
  KIND_CLASS,
  KIND_HELP,
  KIND_LABEL,
  proofWarnings,
  STATUS_CLASS,
  STATUS_HELP,
} from '../../utils/outletProof';

export const ProofKindBadge: React.FC<{ kind: OutletProofKind }> = ({ kind }) => (
  <span
    title={KIND_HELP[kind]}
    className={`inline-flex px-2 py-0.5 text-[10px] font-bold rounded border ${KIND_CLASS[kind] ?? KIND_CLASS.INITIAL}`}
  >
    {KIND_LABEL[kind] ?? kind}
  </span>
);

export const ProofStatusBadge: React.FC<{ status: OutletProofStatus }> = ({ status }) => (
  <span
    title={STATUS_HELP[status]}
    className={`inline-flex px-2 py-0.5 text-[10px] font-bold rounded border ${STATUS_CLASS[status] ?? STATUS_CLASS.UNATTACHED}`}
  >
    {status}
  </span>
);

export const AccuracyChip: React.FC<{ accuracyM: number }> = ({ accuracyM }) => (
  <span
    data-testid="accuracy-chip"
    title={accuracyHelp(accuracyM)}
    className={`inline-flex px-2 py-0.5 text-[11px] font-bold rounded border ${ACCURACY_TONE_CLASS[accuracyTone(accuracyM)]}`}
  >
    ±{Math.round(accuracyM)} m
  </span>
);

export const ProofWarningChips: React.FC<{
  proof: Pick<OutletProof, 'is_mock_location' | 'distance_from_verified_m'>;
}> = ({ proof }) => {
  const warnings = proofWarnings(proof);
  if (warnings.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {warnings.map((w) => (
        <span
          key={w}
          role="alert"
          className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-bold rounded border bg-rose-100 text-rose-900 border-rose-400"
        >
          <AlertTriangle className="w-3 h-3" /> {w}
        </span>
      ))}
    </div>
  );
};
