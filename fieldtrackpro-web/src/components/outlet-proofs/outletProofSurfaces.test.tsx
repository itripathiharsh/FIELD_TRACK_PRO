import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { NewOutletApprovalsQueue } from '../customers/NewOutletApprovalsQueue';
import { CustomerOutletProofSection } from './CustomerOutletProofSection';
import { OutletPhotoChip } from './OutletPhotoChip';
import { apiClient } from '../../api/client';
import { CUSTOMER } from '../../test/utils';
import { makeProof, stubObjectUrls } from '../../test/outletProofFixtures';
import { CustomerProspect } from '../../types';

vi.mock('../maps/FieldTrackMap', () => ({ FieldTrackMap: () => <div data-testid="ftmap" /> }));

const PROSPECT: CustomerProspect = {
  id: 'pppppppp-0000-0000-0000-000000000001',
  status: 'PENDING',
  name: 'Brand New Traders',
  contact_number: '+919800000000',
  contact_person: 'Ravi',
  gst_number: null,
  address: 'Market Road',
  outlet_code: null,
  territory_id: null,
  area_id: null,
  brands: [],
  requirement: null,
  location: { latitude: 26.4499, longitude: 80.3319 },
  gps_accuracy_meters: 12,
  submitted_by: 'u',
  submitted_by_name: 'Test Field Rep',
  submitted_at: '2026-10-10T04:00:00Z',
};

describe('NewOutletApprovalsQueue live proof', () => {
  beforeEach(() => {
    stubObjectUrls();
    vi.spyOn(apiClient, 'getOutletProofImageUrl').mockResolvedValue('blob:test/img');
  });

  it('matches the proof by prospect_id and shows thumbnail, accuracy and captured time', async () => {
    vi.spyOn(apiClient, 'getCustomerProspects').mockResolvedValue([PROSPECT]);
    const proofs = vi.spyOn(apiClient, 'getOutletProofs').mockResolvedValue({
      items: [
        makeProof({ id: 'other', prospect_id: 'someone-else', customer_id: null, accuracy_m: 99 }),
        makeProof({ prospect_id: PROSPECT.id, customer_id: null, kind: 'INITIAL', accuracy_m: 14 }),
      ],
      total: 2,
    });
    render(<NewOutletApprovalsQueue />);
    await screen.findByText('Brand New Traders');
    expect(proofs).toHaveBeenCalledWith(expect.objectContaining({ status: 'PENDING' }));
    const compact = await screen.findByTestId('prospect-proof-compact');
    expect(compact).toHaveTextContent('±14 m');
    expect(compact).toHaveTextContent('10/10/2026 10:00');
    expect(await screen.findByAltText('Live outlet photo')).toHaveAttribute('src', 'blob:test/img');
  });

  it('shows the "location comes from the live photo proof" note in the review modal', async () => {
    vi.spyOn(apiClient, 'getCustomerProspects').mockResolvedValue([PROSPECT]);
    vi.spyOn(apiClient, 'getOutletProofs').mockResolvedValue({
      items: [makeProof({ prospect_id: PROSPECT.id, customer_id: null, kind: 'INITIAL' })],
      total: 1,
    });
    render(<NewOutletApprovalsQueue />);
    await userEvent.click(await screen.findByRole('button', { name: /review/i }));
    expect(await screen.findByText('Location comes from the live photo proof.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save (&|&amp;) approve/i })).toBeInTheDocument();
  });

  it('degrades gracefully when proofs cannot be loaded', async () => {
    vi.spyOn(apiClient, 'getCustomerProspects').mockResolvedValue([PROSPECT]);
    vi.spyOn(apiClient, 'getOutletProofs').mockRejectedValue(new Error('nope'));
    render(<NewOutletApprovalsQueue />);
    expect(await screen.findByText('Brand New Traders')).toBeInTheDocument();
    expect(screen.getByTestId('no-proof')).toBeInTheDocument();
  });
});

describe('CustomerOutletProofSection', () => {
  beforeEach(() => {
    stubObjectUrls();
    vi.spyOn(apiClient, 'getOutletProofImageUrl').mockResolvedValue('blob:test/proof');
    vi.spyOn(apiClient, 'getCustomerOutletImageUrl').mockResolvedValue('blob:test/primary');
  });

  it('shows the primary photo, verified badge, confirmation count and history', async () => {
    vi.spyOn(apiClient, 'getCustomerOutletProofs').mockResolvedValue([
      makeProof({ status: 'APPROVED', kind: 'INITIAL', is_primary: true }),
      makeProof({ id: 'p2', status: 'CONFIRMED', kind: 'CONFIRMATION', submitted_by_name: 'Second Rep' }),
    ]);
    render(
      <CustomerOutletProofSection
        customer={{
          ...CUSTOMER,
          location_status: 'VERIFIED',
          primary_outlet_image_available: true,
          primary_outlet_proof_id: 'aaaaaaaa-0000-0000-0000-000000000001',
          outlet_proof_count: 2,
          outlet_location_confirmations: 3,
        }}
      />,
    );
    expect(await screen.findByAltText(`Outlet photo of ${CUSTOMER.name}`)).toHaveAttribute('src', 'blob:test/primary');
    expect(screen.getByText('Location verified')).toBeInTheDocument();
    expect(screen.getByTestId('confirmations')).toHaveTextContent('Confirmed by 3 employees');
    const history = await screen.findByTestId('proof-history');
    expect(history).toHaveTextContent('Second Rep');
    expect(history).toHaveTextContent('CONFIRMATION');
    expect(history).toHaveTextContent('PRIMARY');
    await userEvent.click(screen.getAllByRole('button', { name: /open photo$/i })[0]);
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('shows the placeholder when there is no primary photo', async () => {
    vi.spyOn(apiClient, 'getCustomerOutletProofs').mockResolvedValue([]);
    render(<CustomerOutletProofSection customer={{ ...CUSTOMER, primary_outlet_image_available: false }} />);
    expect(screen.getByText('No outlet photo yet')).toBeInTheDocument();
    expect(apiClient.getCustomerOutletImageUrl).not.toHaveBeenCalled();
    expect(await screen.findByText(/No proofs submitted/i)).toBeInTheDocument();
    expect(screen.getByTestId('confirmations')).toHaveTextContent('Not yet confirmed');
  });

  it('survives a history load failure', async () => {
    vi.spyOn(apiClient, 'getCustomerOutletProofs').mockRejectedValue(new Error('x'));
    render(<CustomerOutletProofSection customer={CUSTOMER} />);
    await waitFor(() => expect(screen.getByText(/could not load the proof history/i)).toBeInTheDocument());
  });
});

describe('OutletPhotoChip', () => {
  it('renders Photo check vs No photo', () => {
    const { rerender } = render(<MemoryRouter><OutletPhotoChip customer={{ primary_outlet_image_available: true, outlet_location_confirmations: 2 }} /></MemoryRouter>);
    expect(screen.getByText(/Photo ✓/)).toBeInTheDocument();
    expect(screen.getByText('Confirmed by 2')).toBeInTheDocument();
    rerender(<MemoryRouter><OutletPhotoChip customer={{}} /></MemoryRouter>);
    expect(screen.getByText('No photo')).toBeInTheDocument();
  });
});
