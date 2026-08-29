/**
 * Map tile provider configuration.
 *
 * Environment-driven tile provider configuration:
 * - Commercial / Self-Hosted: Uses VITE_MAPLIBRE_TILE_URL when configured.
 * - Default Fallback: Uses OpenStreetMap raster tiles (no API key required).
 * - Always ensures a reliable, standard base map without throwing unhandled exceptions.
 */
import { ENV } from '../../config/env';

export interface TileProviderConfig {
  styleUrl: string | null;
  styleObject: object | null;
  attribution: string;
}

export const OSM_STYLE_OBJECT: object = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: [
        'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
        'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
        'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png',
      ],
      tileSize: 256,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    },
  },
  layers: [
    {
      id: 'osm',
      type: 'raster',
      source: 'osm',
      minzoom: 0,
      maxzoom: 19,
    },
  ],
};

export const OSM_ATTRIBUTION =
  '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const REJECTED_DEMO_PATTERNS = [
  'demotiles.maplibre.org',
  'your_',
  'placeholder',
  'example.com',
  'localhost',
  '127.0.0.1',
];

export function isDemoOrInsecureTileUrl(url: string): boolean {
  const lower = url.toLowerCase();
  return REJECTED_DEMO_PATTERNS.some((pattern) => lower.includes(pattern));
}

export function isValidUrl(url: string): boolean {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
}

export const MAPLIBRE_WORKER_URL =
  'https://cdn.jsdelivr.net/npm/maplibre-gl@6.2.0/dist/maplibre-gl-worker.mjs';

function getDefaultConfig(): TileProviderConfig {
  return {
    styleUrl: null,
    styleObject: OSM_STYLE_OBJECT,
    attribution: OSM_ATTRIBUTION,
  };
}

/**
 * Resolve the tile provider configuration.
 *
 * If VITE_MAPLIBRE_TILE_URL is explicitly set to a valid URL, it is used.
 * Otherwise, defaults directly to OpenStreetMap raster tiles (no API key required).
 */
export function getTileProviderConfig(overrideUrl?: string): TileProviderConfig {
  const envUrl = (overrideUrl !== undefined ? overrideUrl : ENV.MAPLIBRE_TILE_URL) || '';
  const cleanUrl = envUrl.trim();

  if (cleanUrl && isValidUrl(cleanUrl) && !isDemoOrInsecureTileUrl(cleanUrl)) {
    return {
      styleUrl: cleanUrl,
      styleObject: null,
      attribution: OSM_ATTRIBUTION,
    };
  }

  return getDefaultConfig();
}

export function isTileConfigured(): boolean {
  try {
    getTileProviderConfig();
    return true;
  } catch {
    return false;
  }
}
