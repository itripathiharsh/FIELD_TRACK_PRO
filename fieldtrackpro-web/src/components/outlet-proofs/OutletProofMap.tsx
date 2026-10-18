import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { getTileProviderConfig, MAPLIBRE_WORKER_URL } from '../maps/tileConfig';
import { circleRing, PROOF_COLORS } from '../../utils/outletProof';

try {
  if (typeof maplibregl.setWorkerUrl === 'function') maplibregl.setWorkerUrl(MAPLIBRE_WORKER_URL);
} catch {
  // not available in this environment
}

export interface ProofMapPoint {
  id: string;
  latitude: number;
  longitude: number;
}

export interface OutletProofMapProps {
  /** The point being reviewed (orange) with its GPS accuracy circle. */
  proposed: ProofMapPoint & { accuracyM?: number };
  /** Current verified outlet location (green), joined to the proposed point by a line. */
  verified?: { latitude: number; longitude: number } | null;
  /** Other pending candidates for the same outlet (grey). */
  others?: ProofMapPoint[];
  height?: string;
}

type Pt = [number, number];

/**
 * Small review map: proposed point (orange) + accuracy circle, verified pin (green) with a
 * dashed distance line, other pending candidates (grey). Built on the shared MapLibre tile config.
 */
export function OutletProofMap({ proposed, verified = null, others = [], height = '240px' }: OutletProofMapProps) {
  const othersKey = others.map((o) => `${o.latitude},${o.longitude}`).join('|');
  const container = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!container.current) return;
    let map: maplibregl.Map | null = null;
    try {
      const cfg = getTileProviderConfig() || { styleUrl: null, styleObject: { version: 8, sources: {}, layers: [] } };
      map = new maplibregl.Map({
        container: container.current,
        style: cfg.styleUrl ? cfg.styleUrl : (cfg.styleObject as maplibregl.StyleSpecification),
        center: [proposed.longitude, proposed.latitude],
        zoom: 16,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
      const m = map;
      m.on('error', (e: { error?: { message?: string } }) => {
        const msg = e.error?.message || '';
        if (/401|403|unauthor|forbidden/i.test(msg)) setError('Basemap unavailable');
      });
      m.on('load', () => {
        const points = [
          { p: [proposed.longitude, proposed.latitude] as Pt, color: PROOF_COLORS.proposed, r: 9 },
          ...(verified
            ? [{ p: [verified.longitude, verified.latitude] as Pt, color: PROOF_COLORS.verified, r: 8 }]
            : []),
          ...others.map((o) => ({ p: [o.longitude, o.latitude] as Pt, color: PROOF_COLORS.other, r: 6 })),
        ];
        m.addSource('proof-accuracy', {
          type: 'geojson',
          data: {
            type: 'Feature',
            properties: {},
            geometry: {
              type: 'Polygon',
              coordinates: [circleRing(proposed.longitude, proposed.latitude, Math.max(proposed.accuracyM ?? 0, 1))],
            },
          },
        });
        m.addLayer({ id: 'proof-accuracy-fill', type: 'fill', source: 'proof-accuracy', paint: { 'fill-color': PROOF_COLORS.proposed, 'fill-opacity': 0.15 } });
        m.addLayer({ id: 'proof-accuracy-line', type: 'line', source: 'proof-accuracy', paint: { 'line-color': PROOF_COLORS.proposed, 'line-width': 1.5 } });
        if (verified) {
          m.addSource('proof-line', {
            type: 'geojson',
            data: {
              type: 'Feature',
              properties: {},
              geometry: {
                type: 'LineString',
                coordinates: [[verified.longitude, verified.latitude], [proposed.longitude, proposed.latitude]],
              },
            },
          });
          m.addLayer({ id: 'proof-line', type: 'line', source: 'proof-line', paint: { 'line-color': '#111827', 'line-width': 2, 'line-dasharray': [2, 2] } });
        }
        m.addSource('proof-points', {
          type: 'geojson',
          data: {
            type: 'FeatureCollection',
            features: points.map((pt) => ({
              type: 'Feature' as const,
              properties: { color: pt.color, r: pt.r },
              geometry: { type: 'Point' as const, coordinates: pt.p },
            })),
          },
        });
        m.addLayer({
          id: 'proof-points',
          type: 'circle',
          source: 'proof-points',
          paint: {
            'circle-color': ['get', 'color'],
            'circle-radius': ['get', 'r'],
            'circle-stroke-color': '#ffffff',
            'circle-stroke-width': 2,
          },
        });
        const lngs = points.map((x) => x.p[0]);
        const lats = points.map((x) => x.p[1]);
        const sw: Pt = [Math.min(...lngs), Math.min(...lats)];
        const ne: Pt = [Math.max(...lngs), Math.max(...lats)];
        if (points.length > 1 && (sw[0] !== ne[0] || sw[1] !== ne[1])) {
          m.fitBounds([sw, ne], { padding: 50, maxZoom: 18, duration: 0 });
        }
        m.resize();
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Map unavailable');
    }
    return () => {
      map?.remove();
    };
    // The map is rebuilt when the reviewed coordinates change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    proposed.latitude,
    proposed.longitude,
    proposed.accuracyM,
    verified?.latitude,
    verified?.longitude,
    othersKey,
  ]);

  return (
    <div className="relative rounded-lg overflow-hidden border border-outline-variant" style={{ height }}>
      <div ref={container} data-testid="outlet-proof-map" className="w-full h-full" />
      {error && (
        <div className="absolute inset-0 flex items-center justify-center bg-surface-container text-xs text-on-surface-variant">
          {error}. Proposed point: {proposed.latitude.toFixed(6)}, {proposed.longitude.toFixed(6)}
        </div>
      )}
    </div>
  );
}
