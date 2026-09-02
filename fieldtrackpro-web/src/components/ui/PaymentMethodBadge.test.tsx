import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PaymentMethodBadge } from './PaymentMethodBadge';

describe('PaymentMethodBadge', () => {
  it('renders CASH with green styling and label', () => {
    const { container } = render(<PaymentMethodBadge method="CASH" />);
    expect(screen.getByText('CASH')).toBeInTheDocument();
    const badge = container.querySelector('span');
    expect(badge).toHaveClass('bg-emerald-50');
    expect(badge).toHaveClass('text-emerald-800');
  });

  it('renders ONLINE with blue styling and label', () => {
    const { container } = render(<PaymentMethodBadge method="ONLINE" />);
    expect(screen.getByText('ONLINE')).toBeInTheDocument();
    const badge = container.querySelector('span');
    expect(badge).toHaveClass('bg-blue-50');
    expect(badge).toHaveClass('text-blue-800');
  });

  it('renders CHEQUE with purple styling, landmark icon, and label', () => {
    const { container } = render(<PaymentMethodBadge method="CHEQUE" chequeNumber="998877" />);
    expect(screen.getByText('CHEQUE')).toBeInTheDocument();
    expect(screen.getByText('#998877')).toBeInTheDocument();
    const badge = container.querySelector('span');
    expect(badge).toHaveClass('bg-purple-50');
    expect(badge).toHaveClass('text-purple-800');
  });

  it('normalizes CHECK to CHEQUE', () => {
    const { container } = render(<PaymentMethodBadge method="CHECK" />);
    expect(screen.getByText('CHEQUE')).toBeInTheDocument();
    const badge = container.querySelector('span');
    expect(badge).toHaveClass('bg-purple-50');
  });
});
