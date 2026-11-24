import { describe, expect, it } from 'vitest';
import { ApiError } from '../api/client';
import {
  accuracyTone,
  circleRing,
  formatDistance,
  isStaleProofError,
  outletProofErrorMessage,
  proofWarnings,
} from './outletProof';

describe('outletProof utils', () => {
  it('colour-codes accuracy: <=20 good, <=30 ok, else poor', () => {
    expect(accuracyTone(20)).toBe('good');
    expect(accuracyTone(20.1)).toBe('ok');
    expect(accuracyTone(30)).toBe('ok');
    expect(accuracyTone(30.1)).toBe('poor');
  });

  it('flags mock location and distance over 50 m', () => {
    expect(proofWarnings({ is_mock_location: false, distance_from_verified_m: 50 })).toEqual([]);
    expect(proofWarnings({ is_mock_location: false, distance_from_verified_m: null })).toEqual([]);
    expect(proofWarnings({ is_mock_location: true, distance_from_verified_m: 51 })).toEqual([
      'Mock location detected',
      '51 m from verified location',
    ]);
  });

  it('formats distances', () => {
    expect(formatDistance(120.4)).toBe('120 m');
    expect(formatDistance(1500)).toBe('1.50 km');
  });

  it('maps backend error codes to friendly messages', () => {
    expect(outletProofErrorMessage(new ApiError('x', 409, 'OUTLET_PROOF_PROSPECT_PENDING'))).toMatch(/New Outlet Approvals/);
    expect(outletProofErrorMessage(new ApiError('x', 409, 'OUTLET_PROOF_NOT_PENDING'))).toMatch(/already reviewed/);
    expect(outletProofErrorMessage(new ApiError('x', 404, 'OUTLET_PROOF_NOT_FOUND'))).toMatch(/no longer exists/);
    expect(outletProofErrorMessage(new ApiError('boom', 500))).toBe('boom');
    expect(isStaleProofError(new ApiError('x', 409, 'OUTLET_PROOF_NOT_PENDING'))).toBe(true);
    expect(isStaleProofError(new ApiError('x', 500))).toBe(false);
  });

  it('builds a closed circle ring', () => {
    const ring = circleRing(80, 26, 20, 8);
    expect(ring).toHaveLength(9);
    expect(ring[0]).toEqual(ring[8]);
  });
});
