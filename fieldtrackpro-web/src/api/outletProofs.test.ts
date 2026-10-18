import { describe, expect, it, vi, beforeEach } from 'vitest';
import { ApiClient } from './client';
import { makeProof, stubObjectUrls } from '../test/outletProofFixtures';

function res(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
}

describe('ApiClient outlet proofs', () => {
  let client: ApiClient;
  beforeEach(() => {
    localStorage.clear();
    client = new ApiClient();
  });

  it('lists proofs with filters and reads X-Total-Count', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(res([makeProof()], 200, { 'X-Total-Count': '42' }));
    const out = await client.getOutletProofs({ status: 'PENDING', kind: 'CHANGE_REQUEST', skip: 10, limit: 5 });
    expect(out.total).toBe(42);
    expect(out.items).toHaveLength(1);
    const url = String(spy.mock.calls[0][0]);
    expect(url).toContain('/api/v1/customers/outlet-proofs?');
    expect(url).toContain('status=PENDING');
    expect(url).toContain('kind=CHANGE_REQUEST');
    expect(url).toContain('skip=10');
    expect(url).toContain('limit=5');
  });

  it('fetches a customer proofs list', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(res([makeProof()]));
    await client.getCustomerOutletProofs('abc');
    expect(String(spy.mock.calls[0][0])).toContain('/api/v1/customers/abc/outlet-proofs');
  });

  it('approves with POST and rejects with a JSON reason', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => res(makeProof({ status: 'APPROVED' })));
    await client.approveOutletProof('p1');
    expect(String(spy.mock.calls[0][0])).toContain('/api/v1/customers/outlet-proofs/p1/approve');
    expect((spy.mock.calls[0][1] as RequestInit).method).toBe('POST');
    await client.rejectOutletProof('p1', 'blurry photo');
    expect(String(spy.mock.calls[1][0])).toContain('/outlet-proofs/p1/reject');
    expect(JSON.parse((spy.mock.calls[1][1] as RequestInit).body as string)).toEqual({ reason: 'blurry photo' });
  });

  it('fetches image bytes with the Authorization header and returns an object URL', async () => {
    stubObjectUrls();
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      res({ access_token: 'tok', refresh_token: 'r', token_type: 'bearer' }),
    );
    await client.login('a@b.c', 'pw');
    spy.mockImplementation(async () => new Response(new Blob(['x'], { type: 'image/jpeg' }), { status: 200 }));
    const u = await client.getOutletProofImageUrl('p1');
    expect(u).toMatch(/^blob:/);
    const call = spy.mock.calls[spy.mock.calls.length - 1];
    expect(String(call[0])).toContain('/outlet-proofs/p1/image');
    expect((call[1] as RequestInit).headers).toMatchObject({ Authorization: 'Bearer tok' });
    await client.getCustomerOutletImageUrl('c1');
    expect(String(spy.mock.calls[spy.mock.calls.length - 1][0])).toContain('/customers/c1/outlet-image');
  });
});
