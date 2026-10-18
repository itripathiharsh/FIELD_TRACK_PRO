import { PositionFields } from '../../types';

export { formatMoney } from '../../utils/money';

/** True when the backend sent the new position fields (older backends omit them). */
export const hasPosition = (p: PositionFields | null | undefined): boolean =>
  !!p && p.opening_balance !== undefined && p.opening_balance !== null;

export const RECONCILE_WARNING = 'Totals do not reconcile — contact support';
