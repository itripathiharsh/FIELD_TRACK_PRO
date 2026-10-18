import React from 'react';
import { StatusBadge } from './StatusBadge';
import { TallyStatus } from '../../types';
import { TALLY_STATUS_LABELS } from './tallyStatusLabels';

interface TallyStatusBadgeProps {
  status: TallyStatus | undefined | null;
  size?: 'sm' | 'md';
}

/** Tally write-back lifecycle badge (colours come from StatusBadge: posted=green, awaiting=amber, failed=red). */
export const TallyStatusBadge: React.FC<TallyStatusBadgeProps> = ({ status, size = 'sm' }) => {
  const s: TallyStatus = status ?? 'NOT_APPLICABLE';
  return <StatusBadge status={s} size={size} label={TALLY_STATUS_LABELS[s]} />;
};
