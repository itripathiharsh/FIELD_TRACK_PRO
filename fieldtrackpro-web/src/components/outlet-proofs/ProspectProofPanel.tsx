import React from 'react';
import { Camera } from 'lucide-react';
import { OutletProof } from '../../types';
import { formatIstDateTime } from '../../utils/ist';
import { OutletProofImage } from './OutletProofImage';
import { AccuracyChip, ProofWarningChips } from './OutletProofBadges';

interface ProspectProofPanelProps {
  proof: OutletProof | null | undefined;
  onOpenPhoto: (proof: OutletProof) => void;
  /** Compact = thumbnail + accuracy + time only (for table cells). */
  compact?: boolean;
}

/** Live photo proof linked to a new-outlet submission (found by prospect_id). */
export const ProspectProofPanel: React.FC<ProspectProofPanelProps> = ({ proof, onOpenPhoto, compact = false }) => {
  if (!proof) {
    return (
      <span className="text-[11px] text-on-surface-variant italic" data-testid="no-proof">
        No live photo proof
      </span>
    );
  }
  if (compact) {
    return (
      <div className="flex items-center gap-2" data-testid="prospect-proof-compact">
        <OutletProofImage
          proofId={proof.id}
          alt="Live outlet photo"
          className="w-14 h-14 rounded"
          emptyLabel=""
          onClick={() => onOpenPhoto(proof)}
        />
        <div className="space-y-1">
          <AccuracyChip accuracyM={proof.accuracy_m} />
          <p className="text-[11px] text-on-surface-variant">{formatIstDateTime(proof.captured_at)}</p>
        </div>
      </div>
    );
  }
  return (
    <div className="p-3 bg-surface-container rounded-lg space-y-2" data-testid="prospect-proof-panel">
      <p className="text-xs font-bold text-on-surface flex items-center gap-1.5">
        <Camera className="w-3.5 h-3.5" /> Live photo proof
      </p>
      <div className="flex items-start gap-3">
        <OutletProofImage
          proofId={proof.id}
          alt="Live outlet photo"
          className="w-28 h-28 rounded-lg"
          emptyLabel="Photo unavailable"
          onClick={() => onOpenPhoto(proof)}
        />
        <div className="space-y-1.5 text-xs text-on-surface">
          <div className="flex items-center gap-2">
            <span className="text-on-surface-variant">GPS accuracy</span>
            <AccuracyChip accuracyM={proof.accuracy_m} />
          </div>
          <p>
            <span className="text-on-surface-variant">Captured </span>
            {formatIstDateTime(proof.captured_at)} IST
          </p>
          <ProofWarningChips proof={proof} />
        </div>
      </div>
      <p className="text-[11px] text-on-surface-variant">Location comes from the live photo proof.</p>
    </div>
  );
};
