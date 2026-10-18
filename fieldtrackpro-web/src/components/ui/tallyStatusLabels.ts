import { TallyStatus } from '../../types';

export const TALLY_STATUS_LABELS: Record<TallyStatus, string> = {
  NOT_APPLICABLE: 'Not applicable',
  AWAITING_TALLY: 'Verified, awaiting Tally',
  POSTED: 'Posted to Tally',
  FAILED: 'Tally post failed',
};
