import { OutletProof } from '../types';

export function makeProof(over: Partial<OutletProof> = {}): OutletProof {
  return {
    id: 'aaaaaaaa-0000-0000-0000-000000000001',
    customer_id: '55555555-5555-5555-5555-555555555555',
    prospect_id: null,
    kind: 'CHANGE_REQUEST',
    status: 'PENDING',
    is_primary: false,
    latitude: 26.4499,
    longitude: 80.3319,
    accuracy_m: 12,
    captured_at: '2026-10-10T04:30:00Z', // 10:00 IST
    received_at: '2026-10-10T04:31:00Z',
    is_mock_location: false,
    device_info: 'Pixel 7 / Android 14',
    submitted_by: '22222222-2222-2222-2222-222222222222',
    submitted_by_name: 'Test Field Rep',
    distance_from_verified_m: 120,
    image_url: null,
    created_at: '2026-10-10T04:31:00Z',
    customer_name: 'Acme Industrial',
    customer_outlet_code: 'OUT-001',
    territory_name: 'North Region',
    area_name: 'Civil Lines',
    customer_latitude: 26.45,
    customer_longitude: 80.33,
    nearby_pending_proofs: 0,
    ...over,
  };
}

/** jsdom has no object-URL support; install deterministic stubs. */
export function stubObjectUrls() {
  const created: string[] = [];
  const revoked: string[] = [];
  let n = 0;
  URL.createObjectURL = (() => {
    const u = `blob:test/${++n}`;
    created.push(u);
    return u;
  }) as typeof URL.createObjectURL;
  URL.revokeObjectURL = ((u: string) => {
    revoked.push(u);
  }) as typeof URL.revokeObjectURL;
  return { created, revoked };
}
