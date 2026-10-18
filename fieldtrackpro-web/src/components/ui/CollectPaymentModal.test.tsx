import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { CollectPaymentModal } from './CollectPaymentModal';
import { apiClient } from '../../api/client';
import type { BrandSummary } from '../../types';

vi.mock('../../api/client', () => ({
  apiClient: {
    getBrands: vi.fn(),
    createPayment: vi.fn(),
    uploadPaymentProof: vi.fn(),
  },
}));

const BRANDS = [
  { brand: 'Alpha', total_outstanding: '1000.00' },
  { brand: 'Beta', total_outstanding: '500.00' },
] as unknown as BrandSummary[];

function setup() {
  vi.mocked(apiClient.getBrands).mockResolvedValue([]);
  vi.mocked(apiClient.createPayment).mockResolvedValue({ id: 'p1' } as never);
  const onCollected = vi.fn();
  render(
    <CollectPaymentModal
      isOpen
      onClose={() => {}}
      visitId="visit-1"
      brandSummaries={BRANDS}
      onCollected={onCollected}
    />,
  );
  const inputs = screen.getAllByPlaceholderText('₹ 0.00') as HTMLInputElement[];
  return { inputs, onCollected };
}

describe('CollectPaymentModal money handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('0.1 + 0.2 totals exactly 0.30 and is sent as exact decimal strings', async () => {
    const { inputs } = setup();
    fireEvent.change(inputs[0], { target: { value: '0.1' } });
    fireEvent.change(inputs[1], { target: { value: '0.2' } });
    expect(screen.getByText('₹0.30')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Submit Payment/ }));
    await waitFor(() => expect(apiClient.createPayment).toHaveBeenCalledTimes(1));
    const payload = vi.mocked(apiClient.createPayment).mock.calls[0][0];
    expect(payload.amount).toBe('0.30');
    expect(payload.allocations).toEqual([
      { brand: 'Alpha', amount: '0.10' },
      { brand: 'Beta', amount: '0.20' },
    ]);
    // allocation sum equals the total exactly
    const sumPaise = payload.allocations!.reduce((s, a) => s + Math.round(Number(a.amount) * 100), 0);
    expect(sumPaise).toBe(30);
  });

  it('clamps input to 2 decimals as the user types', () => {
    const { inputs } = setup();
    fireEvent.change(inputs[0], { target: { value: '12.3456' } });
    expect(inputs[0].value).toBe('12.34');
    expect(screen.getByText('₹12.34')).toBeInTheDocument();
  });

  it('sums awkward amounts without float drift', async () => {
    const { inputs } = setup();
    fireEvent.change(inputs[0], { target: { value: '1234567.89' } });
    fireEvent.change(inputs[1], { target: { value: '0.11' } });
    fireEvent.click(screen.getByRole('button', { name: /Submit Payment/ }));
    await waitFor(() => expect(apiClient.createPayment).toHaveBeenCalled());
    expect(vi.mocked(apiClient.createPayment).mock.calls[0][0].amount).toBe('1234568.00');
  });

  it('disables submit when nothing is allocated', () => {
    setup();
    expect(screen.getByRole('button', { name: /Submit Payment/ })).toBeDisabled();
  });
});
