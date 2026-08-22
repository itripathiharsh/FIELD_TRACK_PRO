import { describe, expect, it } from 'vitest';
import {
    getTileProviderConfig,
    isDemoOrInsecureTileUrl,
    isValidUrl,
    OSM_STYLE_OBJECT,
    OSM_ATTRIBUTION,
} from './tileConfig';

describe('tileConfig Production Hardening', () => {
    describe('isDemoOrInsecureTileUrl', () => {
        it('detects demo maplibre URLs as demo/insecure', () => {
            expect(isDemoOrInsecureTileUrl('https://demotiles.maplibre.org/style.json')).toBe(true);
            expect(isDemoOrInsecureTileUrl('http://demotiles.maplibre.org')).toBe(true);
        });

        it('detects openstreetmap tile URLs as public/demo', () => {
            expect(isDemoOrInsecureTileUrl('https://tile.openstreetmap.org/0/0/0.png')).toBe(true);
            expect(isDemoOrInsecureTileUrl('https://a.tile.openstreetmap.org/style.json')).toBe(true);
        });

        it('detects placeholder and localhost URLs as insecure', () => {
            expect(isDemoOrInsecureTileUrl('https://api.maptiler.com/maps/basic/style.json?key=YOUR_API_KEY')).toBe(true);
            expect(isDemoOrInsecureTileUrl('http://localhost:8080/style.json')).toBe(true);
            expect(isDemoOrInsecureTileUrl('http://127.0.0.1:8000/tiles.json')).toBe(true);
            expect(isDemoOrInsecureTileUrl('https://example.com/tiles.json')).toBe(true);
        });

        it('accepts valid commercial / self-hosted tile URLs', () => {
            expect(isDemoOrInsecureTileUrl('https://api.maptiler.com/maps/streets-v2/style.json?key=prod_key_12345')).toBe(false);
            expect(isDemoOrInsecureTileUrl('https://tiles.fieldtrackpro.com/v1/style.json')).toBe(false);
            expect(isDemoOrInsecureTileUrl('https://api.mapbox.com/styles/v1/mapbox/streets-v12?access_token=pk.xxx')).toBe(false);
        });
    });

    describe('isValidUrl', () => {
        it('validates proper URLs', () => {
            expect(isValidUrl('https://tiles.example.org/style.json')).toBe(true);
            expect(isValidUrl('invalid-url-string')).toBe(false);
            expect(isValidUrl('')).toBe(false);
        });
    });

    describe('getTileProviderConfig in Development (isProd=false)', () => {
        it('falls back to default OSM raster style when no URL configured', () => {
            const config = getTileProviderConfig('', false);
            expect(config.styleUrl).toBeNull();
            expect(config.styleObject).toEqual(OSM_STYLE_OBJECT);
            expect(config.attribution).toBe(OSM_ATTRIBUTION);
        });

        it('uses custom valid URL if provided in development', () => {
            const customUrl = 'https://custom-tiles.org/style.json';
            const config = getTileProviderConfig(customUrl, false);
            expect(config.styleUrl).toBe(customUrl);
            expect(config.styleObject).toBeNull();
        });
    });

    describe('getTileProviderConfig in Production (isProd=true)', () => {
        it('throws error when VITE_MAPLIBRE_TILE_URL is missing in production', () => {
            expect(() => getTileProviderConfig('', true)).toThrowError(/VITE_MAPLIBRE_TILE_URL must be explicitly configured/);
        });

        it('throws error when VITE_MAPLIBRE_TILE_URL is invalid URL in production', () => {
            expect(() => getTileProviderConfig('not_a_url', true)).toThrowError(/not a valid URL/);
        });

        it('throws error when demo tiles (demotiles.maplibre.org) are used in production', () => {
            expect(() => getTileProviderConfig('https://demotiles.maplibre.org/style.json', true)).toThrowError(
                /cannot use demo or development tile provider/
            );
        });

        it('throws error when public openstreetmap tiles are used in production', () => {
            expect(() => getTileProviderConfig('https://a.tile.openstreetmap.org/style.json', true)).toThrowError(
                /cannot use demo or development tile provider/
            );
        });

        it('throws error when placeholder tokens are used in production', () => {
            expect(() => getTileProviderConfig('https://api.maptiler.com/style.json?key=YOUR_KEY', true)).toThrowError(
                /cannot use demo or development tile provider/
            );
        });

        it('succeeds and returns styleUrl when a valid production tile URL is provided', () => {
            const prodTileUrl = 'https://tiles.fieldtrackpro.com/production/style.json?key=prod_secret_token_99';
            const config = getTileProviderConfig(prodTileUrl, true);
            expect(config.styleUrl).toBe(prodTileUrl);
            expect(config.styleObject).toBeNull();
        });
    });
});
