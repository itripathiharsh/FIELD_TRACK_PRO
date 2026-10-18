import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { OutletVerificationPage } from './OutletVerificationPage';
import { apiClient, ApiError } from '../api/client';
import { makeProof, stubObjectUrls } from '../test/outletProofFixtures';

vi.mock('../components/outlet-proofs/OutletProofMap', () => ({
  OutletProofMap: (p: { others?: unknown[]; verified?: unknown }) => (
    <div data-testid="map-stub" data-others={p.others?.length ?? 0} data-verified={p.verified ? 'yes' : 'no'} />
  ),
}));

const APPROVE_BTN = /approve location (&|&amp;) photo/i;
const PROOF_ID = 'aaaaaaaa-0000-0000-0000-000000000001';

function renderPage() {
  return render(
    <MemoryRouter>
      <OutletVerificationPage />
    </MemoryRouter>,
  );
}

describe('OutletVerificationPage', () => {
  let revoked: string[];
  beforeEach(() => {
    revoked = stubObjectUrls().revoked;
    vi.spyOn(apiClient, 'getOutletProofImageUrl').mockResolvedValue('blob:test/img');
  });

  it('lists pending proofs by default with facts, IST time, warnings and the photo', async () => {
    const list = vi.spyOn(apiClient, 'getOutletProofs').mockResolvedValue({
      items: [makeProof({ is_mock_location: true, accuracy_m: 25 })],
      total: 1,
    });
    renderPage();
    expect(await screen.findByText('Acme Industrial')).toBeInTheDocument();
    expect(list).toHaveBeenCalledWith(expect.objectContaining({ status: 'PENDING', skip: 0 }));
    expect(screen.getByText('OUT-001')).toBeInTheDocument();
    expect(screen.getByText('CHANGE REQUEST')).toBeInTheDocument();
    expect(screen.getByTestId('captured-at')).toHaveTextContent('10/10/2026 10:00 IST');
    expect(screen.getByTestId('accuracy-chip')).toHaveClass('bg-amber-100');
    expect(screen.getByText('Mock location detected')).toBeInTheDocument();
    expect(screen.getByText('120 m from verified location')).toBeInTheDocument();
    expect(screen.getByText('Test Field Rep')).toBeInTheDocument();
    expect(screen.getByText('Pixel 7 / Android 14')).toBeInTheDocument();
    expect(await screen.findByAltText('Live photo of Acme Industrial')).toHaveAttribute('src', 'blob:test/img');
    expect(screen.getByTestId('map-stub')).toHaveAttribute('data-verified', 'yes');
  });

  it('shows no warning chip for a clean, close proof and green accuracy', async () => {
    vi.spyOn(apiClient, 'getOutletProofs').mockResolvedValue({
      items: [makeProof({ distance_from_verified_m: 10, accuracy_m: 8 })],
      total: 1,
    });
    renderPage();
    await screen.findByText('Acme Industrial');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByTestId('accuracy-chip')).toHaveClass('bg-emerald-100');
  });

  it('passes other pending proofs of the same outlet to the map as grey candidates', async () => {
    vi.spyOn(apiClient, 'getOutletProofs').mockResolvedValue({
      items: [makeProof(), makeProof({ id: 'bbbbbbbb-0000-0000-0000-000000000002', latitude: 26.4501 })],
      total: 2,
    });
    renderPage();
    await screen.findAllByTestId('outlet-proof-card');
    expect(screen.getAllByTestId('map-stub')[0]).toHaveAttribute('data-others', '1');
  });

  it('opens the photo in a lightbox and closes it, revoking object URLs', async () => {
    vi.spyOn(apiClient, 'getOutletProofs').mockResolvedValue({ items: [makeProof()], total: 1 });
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /open photo/i }));
    const dialog = await screen.findByRole('dialog', { name: /photo/i });
    await userEvent.click(within(dialog).getByRole('button', { name: /close/i }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: /photo/i })).not.toBeInTheDocument());
    await waitFor(() => expect(revoked).toContain('blob:test/img'));
  });

  it('approves after confirmation, refreshes and toasts', async () => {
    const list = vi
      .spyOn(apiClient, 'getOutletProofs')
      .mockResolvedValueOnce({ items: [makeProof()], total: 1 })
      .mockResolvedValue({ items: [], total: 0 });
    const approve = vi.spyOn(apiClient, 'approveOutletProof').mockResolvedValue(makeProof({ status: 'APPROVED' }));
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: APPROVE_BTN }));
    expect(approve).not.toHaveBeenCalled();
    await userEvent.click(await screen.findByRole('button', { name: /confirm approval/i }));
    await waitFor(() => expect(approve).toHaveBeenCalledWith(PROOF_ID));
    expect(await screen.findByText(/approved for Acme Industrial/i)).toBeInTheDocument();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Nothing to review')).toBeInTheDocument();
  });

  it('requires a reject reason, then rejects and refreshes', async () => {
    vi.spyOn(apiClient, 'getOutletProofs')
      .mockResolvedValueOnce({ items: [makeProof()], total: 1 })
      .mockResolvedValue({ items: [], total: 0 });
    const reject = vi.spyOn(apiClient, 'rejectOutletProof').mockResolvedValue(makeProof({ status: 'REJECTED' }));
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /^reject$/i }));
    await userEvent.click(screen.getByRole('button', { name: /confirm rejection/i }));
    expect(await screen.findByText(/minimum 3 characters/i)).toBeInTheDocument();
    expect(reject).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText(/rejection reason/i), 'Photo is blurry');
    await userEvent.click(screen.getByRole('button', { name: /confirm rejection/i }));
    await waitFor(() => expect(reject).toHaveBeenCalledWith(PROOF_ID, 'Photo is blurry'));
    expect(await screen.findByText(/Proof rejected for Acme Industrial/i)).toBeInTheDocument();
  });

  it('shows a friendly message for 409 OUTLET_PROOF_NOT_PENDING and reloads the list', async () => {
    const list = vi.spyOn(apiClient, 'getOutletProofs').mockResolvedValue({ items: [makeProof()], total: 1 });
    vi.spyOn(apiClient, 'approveOutletProof').mockRejectedValue(
      new ApiError('already approved', 409, 'OUTLET_PROOF_NOT_PENDING'),
    );
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: APPROVE_BTN }));
    await userEvent.click(await screen.findByRole('button', { name: /confirm approval/i }));
    expect(await screen.findByText(/already reviewed by someone else/i)).toBeInTheDocument();
    await waitFor(() => expect(list.mock.calls.length).toBeGreaterThanOrEqual(2));
  });

  it('shows "Approve the new outlet first" for OUTLET_PROOF_PROSPECT_PENDING', async () => {
    vi.spyOn(apiClient, 'getOutletProofs').mockResolvedValue({ items: [makeProof()], total: 1 });
    vi.spyOn(apiClient, 'approveOutletProof').mockRejectedValue(new ApiError('x', 409, 'OUTLET_PROOF_PROSPECT_PENDING'));
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: APPROVE_BTN }));
    await userEvent.click(await screen.findByRole('button', { name: /confirm approval/i }));
    expect(await screen.findByText(/Approve the new outlet first/i)).toBeInTheDocument();
  });

  it('shows a friendly message on 404', async () => {
    vi.spyOn(apiClient, 'getOutletProofs').mockResolvedValue({ items: [makeProof()], total: 1 });
    vi.spyOn(apiClient, 'rejectOutletProof').mockRejectedValue(new ApiError('nf', 404, 'OUTLET_PROOF_NOT_FOUND'));
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /^reject$/i }));
    await userEvent.type(screen.getByLabelText(/rejection reason/i), 'Not the shop');
    await userEvent.click(screen.getByRole('button', { name: /confirm rejection/i }));
    expect(await screen.findByText(/no longer exists/i)).toBeInTheDocument();
  });

  it('disables approve for a not-yet-approved new outlet proof', async () => {
    vi.spyOn(apiClient, 'getOutletProofs').mockResolvedValue({
      items: [
        makeProof({
          customer_id: null,
          prospect_id: 'pp',
          customer_name: null,
          prospect_name: 'New Shop',
          kind: 'INITIAL',
          customer_latitude: null,
          customer_longitude: null,
          distance_from_verified_m: null,
        }),
      ],
      total: 1,
    });
    renderPage();
    expect(await screen.findByText('New Shop')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: APPROVE_BTN })).toBeDisabled();
  });

  it('changes filters, resets to page 1 and paginates', async () => {
    const list = vi.spyOn(apiClient, 'getOutletProofs').mockResolvedValue({ items: [makeProof()], total: 25 });
    renderPage();
    await screen.findByText('Acme Industrial');
    expect(screen.getByText(/Page 1 of 3/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /next/i }));
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ skip: 10, status: 'PENDING' })));
    await userEvent.click(screen.getByRole('button', { name: 'Rejected' }));
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ skip: 0, status: 'REJECTED' })));
    fireEvent.change(screen.getByLabelText('Kind filter'), { target: { value: 'INITIAL' } });
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ kind: 'INITIAL' })));
  });

  it('filters by outlet name on the loaded page', async () => {
    vi.spyOn(apiClient, 'getOutletProofs').mockResolvedValue({
      items: [
        makeProof(),
        makeProof({
          id: 'bbbbbbbb-0000-0000-0000-000000000002',
          customer_id: 'c2',
          customer_name: 'Zeta Traders',
          customer_outlet_code: 'Z-9',
        }),
      ],
      total: 2,
    });
    renderPage();
    await screen.findByText('Zeta Traders');
    await userEvent.type(screen.getByLabelText('Search outlet'), 'zeta');
    expect(screen.queryByText('Acme Industrial')).not.toBeInTheDocument();
    expect(screen.getByText('Zeta Traders')).toBeInTheDocument();
  });

  it('shows the empty state', async () => {
    vi.spyOn(apiClient, 'getOutletProofs').mockResolvedValue({ items: [], total: 0 });
    renderPage();
    expect(await screen.findByText('Nothing to review')).toBeInTheDocument();
  });

  it('shows an error banner with retry', async () => {
    const list = vi
      .spyOn(apiClient, 'getOutletProofs')
      .mockRejectedValueOnce(new Error('Server exploded'))
      .mockResolvedValue({ items: [makeProof()], total: 1 });
    renderPage();
    expect(await screen.findByText('Server exploded')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(await screen.findByText('Acme Industrial')).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
  });
});
