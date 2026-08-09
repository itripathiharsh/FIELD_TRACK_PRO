/**
 * Map tile provider configuration.
 *
 * Environment-driven tile provider configuration.
 * Default: OpenStreetMap raster tiles (no API key required).
 * Production: Set VITE_MAPLIBRE_TILE_URL to a commercial provider or self-hosted tiles.
 *
 * IMPORTANT: OpenStreetMap tile usage policy applies for production traffic.
 * For production use, configure a commercial provider or self-hosted tile server.
 */

export interface TileProviderConfig {
    styleUrl: string | null;
    styleObject: object | null;
    attribution: string;
}

const OSM_STYLE_OBJECT: object = {
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
            attribution: '\u00a9 OpenStreetMap contributors',
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

const OSM_ATTRIBUTION =
    '\u00a9 <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

function getDefaultConfig(): TileProviderConfig {
    return {
        styleUrl: null,
        styleObject: OSM_STYLE_OBJECT,
        attribution: OSM_ATTRIBUTION,
    };
}

export function getTileProviderConfig(): TileProviderConfig {
    const envUrl = import.meta.env.VITE_MAPLIBRE_TILE_URL;

    if (envUrl) {
        return {
            styleUrl: envUrl,
            styleObject: null,
            attribution: OSM_ATTRIBUTION,
        };
    }

    return getDefaultConfig();
}

export function isTileConfigured(): boolean {
    return true;
}
