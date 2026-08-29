/**
 * Shared Geographic Utilities and Haversine Distance Calculations.
 *
 * Canonical Earth Radius:
 * - 6,371,000 meters (6,371 km)
 *
 * Note: Backend PostGIS calculations remain authoritative for official geo-verification.
 */

export const EARTH_RADIUS_METERS = 6371000;
export const EARTH_RADIUS_KM = 6371;

/**
 * Calculates Haversine distance in meters between two lat/lng points.
 */
export function calculateHaversineDistanceMeters(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number {
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return EARTH_RADIUS_METERS * c;
}

/**
 * Calculates Haversine distance in kilometers between two lat/lng points.
 */
export function calculateHaversineDistanceKm(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number {
  return calculateHaversineDistanceMeters(lat1, lon1, lat2, lon2) / 1000;
}
