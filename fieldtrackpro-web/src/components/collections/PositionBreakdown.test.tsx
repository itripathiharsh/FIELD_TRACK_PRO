import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';

import { PositionBreakdown, AgeingTable, PositionData } from './PositionBreakdown';
import { formatMoney } from './positionFormat';
import { StatusBadge } from '../ui/StatusBadge';

const POSITION: PositionData = {
  opening_balance: '5000.00',
  total_invoiced: '10000.00',
  paid_in_tally: '4000.00',
  total_outstanding: '11000.00',
  verified_awaiting_tally_amount: '1500.50',
  advance_credit: '0.00',
  reconciles: true,
  ageing: { normal: '2000.00', warning: '1000.00', overdue: '3000.00', baseline_current: '2500.00', baseline_overdue: '2500.00' },
};

describe('PositionBreakdown', () => {
  it('renders the equation with the exact backend values', () => {
    render(<PositionBreakdown position={POSITION} />);
    expect(screen.getByTestId('pos-opening')).toHaveTextContent(formatMoney('5000.00'));
    expect(screen.getByTestId('pos-opening')).toHaveTextContent('₹5,000.00');
    expect(screen.getByTestId('pos-invoiced')).toHaveTextContent('₹10,000.00');
    expect(screen.getByTestId('pos-paid')).toHaveTextContent('₹4,000.00');
    expect(screen.getByTestId('pos-outstanding')).toHaveTextContent('₹11,000.00');
    expect(screen.getByText(/Opening balance \(Tally\)/)).toBeInTheDocument();
    expect(screen.getAllByRole('img').length).toBe(4); // one info tooltip per term
    expect(screen.queryByTestId('reconcile-warning')).toBeNull();
  });

  it('shows the awaiting line only when > 0', () => {
    const { rerender } = render(<PositionBreakdown position={POSITION} />);
    expect(screen.getByTestId('pos-awaiting')).toHaveTextContent('Verified, awaiting Tally ₹1,500.50 (not yet deducted)');
    rerender(<PositionBreakdown position={{ ...POSITION, verified_awaiting_tally_amount: '0.00' }} />);
    expect(screen.queryByTestId('pos-awaiting')).toBeNull();
  });

  it('shows a warning badge when reconciles is false but still shows values', () => {
    render(<PositionBreakdown position={{ ...POSITION, reconciles: false }} />);
    expect(screen.getByTestId('reconcile-warning')).toHaveTextContent('Totals do not reconcile — contact support');
    expect(screen.getByTestId('pos-outstanding')).toHaveTextContent('₹11,000.00');
  });

  it('shows advance credit only when > 0 and renders nothing for an old backend', () => {
    const { rerender, container } = render(<PositionBreakdown position={{ ...POSITION, advance_credit: '250.00' }} />);
    expect(screen.getByTestId('pos-advance')).toHaveTextContent('₹250.00');
    rerender(<PositionBreakdown position={POSITION} />);
    expect(screen.queryByTestId('pos-advance')).toBeNull();
    rerender(<PositionBreakdown position={{ total_invoiced: '1', total_outstanding: '1' }} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('AgeingTable', () => {
  it('lists all five backend buckets and they sum to the Outstanding total row', () => {
    render(<AgeingTable ageing={POSITION.ageing} totalOutstanding={POSITION.total_outstanding} />);
    const keys = ['normal', 'warning', 'overdue', 'baseline_current', 'baseline_overdue'] as const;
    let sum = 0;
    for (const k of keys) {
      const row = screen.getByTestId(`ageing-${k}`);
      sum += Number(POSITION.ageing![k]);
      expect(within(row).getByText(formatMoney(POSITION.ageing![k]))).toBeInTheDocument();
    }
    expect(sum).toBe(Number(POSITION.total_outstanding));
    expect(within(screen.getByTestId('ageing-total')).getByText('₹11,000.00')).toBeInTheDocument();
    expect(screen.getByText('Warning (21–25 days)')).toBeInTheDocument();
    expect(screen.getByText('Overdue (26+ days)')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('flags buckets that do not add up to Outstanding', () => {
    render(<AgeingTable ageing={POSITION.ageing} totalOutstanding="12000.00" />);
    expect(screen.getByRole('alert')).toHaveTextContent(/differs from Outstanding/);
  });

  it('renders nothing when the backend sends no ageing object', () => {
    const { container } = render(<AgeingTable ageing={undefined} totalOutstanding="0" />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('StatusBadge WARNING', () => {
  it('uses the yellow/amber style', () => {
    render(<StatusBadge status="WARNING" />);
    expect(screen.getByText('WARNING').closest('span[class*="amber"]')).not.toBeNull();
  });
});
