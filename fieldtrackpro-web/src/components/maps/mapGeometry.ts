import type { CurrentUserLocation, MapMarker, TerritoryCircle } from './FieldTrackMap';

export function isValidCoordinate(lat?: number | null, lng?: number | null): boolean {
  return (
    lat != null &&
    lng != null &&
    !isNaN(lat) &&
    !isNaN(lng) &&
    lat >= -90 &&
    lat <= 90 &&
    lng >= -180 &&
    lng <= 180
  );
}

/**
 * Extract a bounding box for all valid markers, employee location, and territory circles.
 */
export function getBoundsForMarkersAndCircles(
  markers: MapMarker[] = [],
  territoryCircles: TerritoryCircle[] = [],
  currentLocation?: CurrentUserLocation | null,
): [[number, number], [number, number]] | null {
  const points: [number, number][] = [];

  for (const m of markers) {
    if (isValidCoordinate(m.latitude, m.longitude)) {
      points.push([m.longitude, m.latitude]);
    }
  }

  if (currentLocation && isValidCoordinate(currentLocation.latitude, currentLocation.longitude)) {
    points.push([currentLocation.longitude, currentLocation.latitude]);
  }

  for (const c of territoryCircles) {
    if (isValidCoordinate(c.centerLat, c.centerLng)) {
      const radiusKm = c.radiusKm || 10;
      const latDelta = radiusKm / 110.574;
      const cosLat = Math.cos((c.centerLat * Math.PI) / 180);
      const lngDelta = radiusKm / (111.32 * (Math.abs(cosLat) > 0.001 ? Math.abs(cosLat) : 1));
      points.push([c.centerLng - lngDelta, c.centerLat - latDelta]);
      points.push([c.centerLng + lngDelta, c.centerLat + latDelta]);
    }
  }

  if (points.length === 0) return null;

  let minLng = points[0][0];
  let maxLng = points[0][0];
  let minLat = points[0][1];
  let maxLat = points[0][1];

  for (const [lng, lat] of points) {
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }

  return [
    [minLng, minLat],
    [maxLng, maxLat],
  ];
}
