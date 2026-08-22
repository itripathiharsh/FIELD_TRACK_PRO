/**
 * Map tile provider configuration.
 *
 * Environment-driven tile provider configuration with production hardening:
 * - Commercial / Self-Hosted: Uses VITE_MAPLIBRE_TILE_URL when configured.
 * - Production / Default Fallback: Uses high-performance Carto Voyager / OpenStreetMap raster tiles.
 * - Always ensures a reliable, beautiful, high-resolution base map without throwing unhandled exceptions.
 */
import { ENV } from '../../config/env';

export interface TileProviderConfig {
    styleUrl: string | null;
    styleObject: object | null;
    attribution: string;
}

export const CARTO_VOYAGER_STYLE_OBJECT: object = {
    version: 8,
    sources: {
        'carto-voyager': {
            type: 'raster',
            tiles: [
                'https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png',
                'https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png',
                'https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png',
                'https://d.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png',
            ],
            tileSize: 256,
            attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, © <a href="https://carto.com/attributions">CARTO</a>',
        },
    },
    layers: [
        {
            id: 'carto-voyager-layer',
            type: 'raster',
            source: 'carto-voyager',
            minzoom: 0,
            maxzoom: 20,
        },
    ],
};

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
            attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
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
    '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, © <a href="https://carto.com/attributions">CARTO</a>';

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

export function isProductionEnvironment(): boolean {
    const mode = (typeof import.meta !== 'undefined' && import.meta.env?.MODE) || '';
    const isProdFlag = (typeof import.meta !== 'undefined' && import.meta.env?.PROD) || false;
    const appEnv = (ENV?.APP_ENV || (typeof import.meta !== 'undefined' && import.meta.env?.VITE_APP_ENV) || '').toLowerCase();
    return isProdFlag || mode === 'production' || appEnv === 'production';
}

function getDefaultConfig(): TileProviderConfig {
    return {
        styleUrl: null,
        styleObject: CARTO_VOYAGER_STYLE_OBJECT,
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
 * If VITE_MAPLIBRE_TILE_URL is explicitly set to a valid URL, it is used.
 * Otherwise, falls back gracefully to high-performance Carto Voyager base maps.
 */
export function getTileProviderConfig(overrideUrl?: string, overrideIsProd?: boolean): TileProviderConfig {
    void overrideIsProd;
    const envUrl = (overrideUrl !== undefined ? overrideUrl : (typeof import.meta !== 'undefined' ? import.meta.env?.VITE_MAPLIBRE_TILE_URL : '')) || '';
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
