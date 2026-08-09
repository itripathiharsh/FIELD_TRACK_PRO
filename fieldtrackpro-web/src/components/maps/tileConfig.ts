/**
 * Map tile provider configuration.
 *
 * Environment-driven tile URL configuration.
 * Default: OpenStreetMap raster tiles via MapLibre demo.
 * Production: Set VITE_MAPLIBRE_TILE_URL to a commercial provider or self-hosted tiles.
 *
 * IMPORTANT: Public/community tile services must not be abused for production traffic.
 * For production use, configure a commercial provider or self-hosted tile server.
 */

export interface TileProviderConfig {
    styleUrl: string;
    attribution: string;
}

/**
 * Default tile provider configuration.
 * Uses MapLibre demo tiles (suitable for development only).
 */
const DEFAULT_TILE_CONFIG: TileProviderConfig = {
    styleUrl: 'https://demotiles.maplibre.org/style.json',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
};

/**
 * Get tile provider configuration from environment or use defaults.
 */
export function getTileProviderConfig(): TileProviderConfig {
    const envUrl = import.meta.env.VITE_MAPLIBRE_TILE_URL;

    if (envUrl) {
        return {
            styleUrl: envUrl,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        };
    }

    return DEFAULT_TILE_CONFIG;
}

/**
 * Validate that a tile URL is properly configured.
 */
export function isTileConfigured(): Boolean {
    const config = getTileProviderConfig();
    return config.styleUrl.length > 0;
}
