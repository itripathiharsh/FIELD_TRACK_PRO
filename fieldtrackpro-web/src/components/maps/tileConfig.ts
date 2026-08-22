/**
 * Map tile provider configuration.
 *
 * Environment-driven tile provider configuration with production hardening:
 * - Development: OpenStreetMap raster tiles (no API key required) fallback.
 * - Production: Requires an explicit, secure commercial provider or self-hosted tile URL via VITE_MAPLIBRE_TILE_URL.
 * - Production Hardening: Rejects demo, placeholder, and public development tile endpoints in production.
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
                'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
                'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
                'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png',
            ],
            tileSize: 256,
            attribution: '© OpenStreetMap contributors',
        },
    },
    layers: [
        {
            id: 'osm',
            type: 'raster',
            source: 'osm',
        },
    ],
};

export const OSM_ATTRIBUTION =
    '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const REJECTED_DEMO_PATTERNS = [
    'demotiles.maplibre.org',
    'tile.openstreetmap.org',
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

export function isProductionEnvironment(): boolean {
    const mode = (typeof import.meta !== 'undefined' && import.meta.env?.MODE) || '';
    const isProdFlag = (typeof import.meta !== 'undefined' && import.meta.env?.PROD) || false;
    const appEnv = (ENV?.APP_ENV || (typeof import.meta !== 'undefined' && import.meta.env?.VITE_APP_ENV) || '').toLowerCase();
    return isProdFlag || mode === 'production' || appEnv === 'production';
}

function getDefaultConfig(): TileProviderConfig {
    return {
        styleUrl: null,
        styleObject: OSM_STYLE_OBJECT,
        attribution: OSM_ATTRIBUTION,
    };
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

/**
 * Resolve the tile provider configuration.
 *
 * In production:
 * - Throws an explicit error if VITE_MAPLIBRE_TILE_URL is missing or uses demo/insecure tiles.
 * In development/test:
 * - Returns custom style URL if valid, or falls back to development OSM raster style.
 */
export function getTileProviderConfig(overrideUrl?: string, overrideIsProd?: boolean): TileProviderConfig {
    const isProd = overrideIsProd !== undefined ? overrideIsProd : isProductionEnvironment();
    const envUrl = (overrideUrl !== undefined ? overrideUrl : (typeof import.meta !== 'undefined' ? import.meta.env?.VITE_MAPLIBRE_TILE_URL : '')) || '';
    const cleanUrl = envUrl.trim();

    if (isProd) {
        if (!cleanUrl) {
            throw new Error(
                'Production configuration error: VITE_MAPLIBRE_TILE_URL must be explicitly configured with a commercial or self-hosted tile provider URL in production. Development fallback tiles are not permitted.'
            );
        }
        if (!isValidUrl(cleanUrl)) {
            throw new Error(
                `Production configuration error: VITE_MAPLIBRE_TILE_URL is not a valid URL: '${cleanUrl}'`
            );
        }
        if (isDemoOrInsecureTileUrl(cleanUrl)) {
            throw new Error(
                `Production configuration error: VITE_MAPLIBRE_TILE_URL cannot use demo or development tile provider ('${cleanUrl}'). A dedicated production tile service is required.`
            );
        }
        return {
            styleUrl: cleanUrl,
            styleObject: null,
            attribution: OSM_ATTRIBUTION,
        };
    }

    // Development / Test fallback
    if (cleanUrl && isValidUrl(cleanUrl) && !cleanUrl.toLowerCase().includes('your_')) {
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
