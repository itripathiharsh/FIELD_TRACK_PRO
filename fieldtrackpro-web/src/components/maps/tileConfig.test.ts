import { describe, expect, it } from 'vitest';
import {
    getTileProviderConfig,
    isDemoOrInsecureTileUrl,
    isValidUrl,
    CARTO_VOYAGER_STYLE_OBJECT,
    OSM_ATTRIBUTION,
} from './tileConfig';

describe('tileConfig Configuration & Fallback', () => {
    describe('isDemoOrInsecureTileUrl', () => {
        it('detects demo maplibre URLs as demo/insecure', () => {
            expect(isDemoOrInsecureTileUrl('https://demotiles.maplibre.org/style.json')).toBe(true);
            expect(isDemoOrInsecureTileUrl('http://demotiles.maplibre.org')).toBe(true);
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

    describe('getTileProviderConfig Resolution', () => {
        it('falls back to default Carto Voyager style when no URL is configured', () => {
            const config = getTileProviderConfig('', false);
            expect(config.styleUrl).toBeNull();
            expect(config.styleObject).toEqual(CARTO_VOYAGER_STYLE_OBJECT);
            expect(config.attribution).toBe(OSM_ATTRIBUTION);
        });

        it('uses custom valid URL if provided', () => {
            const customUrl = 'https://custom-tiles.org/style.json';
            const config = getTileProviderConfig(customUrl, false);
            expect(config.styleUrl).toBe(customUrl);
            expect(config.styleObject).toBeNull();
        });

        it('gracefully falls back in production when no custom tile URL is set', () => {
            const config = getTileProviderConfig('', true);
            expect(config.styleUrl).toBeNull();
            expect(config.styleObject).toEqual(CARTO_VOYAGER_STYLE_OBJECT);
        });
    });
});
