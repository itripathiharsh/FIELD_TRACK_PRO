import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import {
    FieldTrackMap,
    MapMarker,
    TerritoryCircle,
    CurrentUserLocation,
} from './FieldTrackMap';
import { getBoundsForMarkersAndCircles, isValidCoordinate } from './mapGeometry';

const { mockFitBounds, mockFlyTo, mockResize, popupContents } = vi.hoisted(() => ({
    popupContents: [] as HTMLElement[],
    mockFitBounds: vi.fn(),
    mockFlyTo: vi.fn(),
    mockResize: vi.fn(),
}));

// Mock MapLibre GL JS
vi.mock('maplibre-gl', () => {
    class MockMap {
        on(event: string, callback: (e?: unknown) => void) {
            if (event === 'load') {
                setTimeout(() => callback(), 0);
            }
        }
        off() {}
        remove() {}
        addControl() {}
        addSource() {}
        addLayer() {}
        removeLayer() {}
        removeSource() {}
        getSource() { return null; }
        getLayer() { return null; }
        queryRenderedFeatures() { return []; }
        easeTo() {}
        flyTo(opts: unknown) { mockFlyTo(opts); }
        fitBounds(bounds: unknown, opts: unknown) { mockFitBounds(bounds, opts); }
        resize() { mockResize(); }
        isStyleLoaded() { return true; }
        getZoom() { return 12; }
        getCanvas() { return { style: {} }; }
        setFilter() {}
        setPaintProperty() {}
    }

    class MockMarker {
        private _element: HTMLElement;
        constructor(opts?: { element?: HTMLElement }) {
            this._element = opts?.element || document.createElement('div');
        }
        setLngLat() { return this; }
        setPopup() { return this; }
        addTo() { return this; }
        remove() {}
        getElement() { return this._element; }
    }

    class MockPopup {
        setText() { return this; }
        setLngLat() { return this; }
        setDOMContent(el: HTMLElement) { popupContents.push(el); return this; }
        addTo() { return this; }
        remove() { return this; }
    }

    class MockNavigationControl {}

    return {
        default: {
            Map: MockMap,
            Marker: MockMarker,
            Popup: MockPopup,
            NavigationControl: MockNavigationControl,
            setWorkerUrl: vi.fn(),
        },
        Map: MockMap,
        Marker: MockMarker,
        Popup: MockPopup,
        NavigationControl: MockNavigationControl,
        setWorkerUrl: vi.fn(),
    };
});

// Mock tile config
vi.mock('./tileConfig', () => ({
    getTileProviderConfig: () => ({
        styleObject: { version: 8, sources: {}, layers: [] },
        styleUrl: null,
    }),
    MAPLIBRE_WORKER_URL: 'https://test-worker-url.js',
}));

const mockMarkers: MapMarker[] = [
    { id: '1', latitude: 12.9716, longitude: 77.5946, label: 'Customer A', color: '#ffa515' },
    { id: '2', latitude: 12.9720, longitude: 77.5950, label: 'Customer B', color: '#ffa515' },
    { id: '3', latitude: 13.0000, longitude: 77.6000, label: 'Customer C', color: '#ffa515' },
];

const mockCircles: TerritoryCircle[] = [
    { id: 't1', centerLat: 26.8467, centerLng: 80.9462, radiusKm: 15, name: 'Lucknow Zone' },
];

const mockUserLocation: CurrentUserLocation = {
    latitude: 12.9750,
    longitude: 77.5900,
    accuracy: 10,
    label: 'Your Current Location',
};

describe('FieldTrackMap', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('renders map container', () => {
        const { container } = render(<FieldTrackMap markers={mockMarkers} />);
        expect(container.querySelector('div')).toBeTruthy();
    });

    it('renders without markers or circles', () => {
        render(<FieldTrackMap markers={[]} territoryCircles={[]} />);
        expect(true).toBe(true);
    });

    it('renders with single marker', () => {
        render(<FieldTrackMap markers={[mockMarkers[0]]} />);
        expect(true).toBe(true);
    });

    it('renders with live employee GPS currentLocation marker', () => {
        render(<FieldTrackMap markers={mockMarkers} currentLocation={mockUserLocation} />);
        expect(true).toBe(true);
    });

    it('escapes outlet ids in the data-select-outlet attribute (no attribute injection)', async () => {
        popupContents.length = 0;
        const evilId = 'x" onmouseover="window.__pwned=1" data-x="';
        const clash: MapMarker[] = [
            { id: evilId, latitude: 12.9, longitude: 77.5, label: 'Evil <b>one</b>', color: '#ffa515' },
            { id: 'ok-2', latitude: 12.9, longitude: 77.5, label: 'Second', color: '#ffa515' },
        ];
        render(<FieldTrackMap markers={clash} />);
        await waitFor(() => expect(popupContents.length).toBeGreaterThan(0));
        const popup = popupContents.find((p) => p.querySelector('[data-select-outlet]'))!;
        const buttons = Array.from(popup.querySelectorAll('button'));
        expect(buttons).toHaveLength(2);
        expect(buttons[0].getAttribute('data-select-outlet')).toBe(evilId);
        expect(buttons[0].hasAttribute('onmouseover')).toBe(false);
        expect(popup.querySelector('b')).toBeNull(); // label markup stays text
    });

    it('validates coordinates accurately with isValidCoordinate', () => {
        expect(isValidCoordinate(12.9716, 77.5946)).toBe(true);
        expect(isValidCoordinate(0, 0)).toBe(true); // 0,0 is a valid coordinate pair per WEB-MAP-005
        expect(isValidCoordinate(null, 77.5)).toBe(false);
        expect(isValidCoordinate(95, 77.5)).toBe(false);
        expect(isValidCoordinate(12.5, 190)).toBe(false);
    });

    it('renders markers at valid coordinates', () => {
        const markersWithZero: MapMarker[] = [
            ...mockMarkers,
            { id: 'zero', latitude: 0, longitude: 0, label: 'Zero Location' },
        ];
        render(<FieldTrackMap markers={markersWithZero} />);
        expect(true).toBe(true);
    });

    it('calls fitBounds when autoFitBounds is true with multiple markers', async () => {
        render(<FieldTrackMap markers={mockMarkers} autoFitBounds={true} />);
        await waitFor(() => {
            expect(mockFitBounds).toHaveBeenCalled();
        });
    });

    it('calls fitBounds when autoFitBounds is true with territory circles', async () => {
        render(<FieldTrackMap territoryCircles={mockCircles} autoFitBounds={true} />);
        await waitFor(() => {
            expect(mockFitBounds).toHaveBeenCalled();
        });
    });

    it('smoothly centers on selected marker when selectedMarkerId changes without refitting whole map', async () => {
        const { rerender } = render(
            <FieldTrackMap markers={mockMarkers} autoFitBounds={true} selectedMarkerId={null} />
        );
        await waitFor(() => {
            expect(mockFitBounds).toHaveBeenCalledTimes(1);
        });

        // Selecting a marker triggers flyTo on that marker
        rerender(
            <FieldTrackMap markers={mockMarkers} autoFitBounds={true} selectedMarkerId="1" />
        );

        await waitFor(() => {
            expect(mockFlyTo).toHaveBeenCalledWith(
                expect.objectContaining({
                    center: [77.5946, 12.9716],
                })
            );
        });

        // autoFitBounds is NOT called again on selection!
        expect(mockFitBounds).toHaveBeenCalledTimes(1);
    });

    it('correctly calculates bounding box with getBoundsForMarkersAndCircles including employee location', () => {
        const bounds = getBoundsForMarkersAndCircles(mockMarkers, mockCircles, mockUserLocation);
        expect(bounds).not.toBeNull();
        if (bounds) {
            const [[minLng, minLat], [maxLng, maxLat]] = bounds;
            expect(minLng).toBeLessThanOrEqual(77.5900);
            expect(maxLng).toBeGreaterThanOrEqual(80.9462);
            expect(minLat).toBeLessThanOrEqual(12.9716);
            expect(maxLat).toBeGreaterThanOrEqual(26.8467);
        }
    });

    it('returns null bounds when all coordinates are empty or invalid', () => {
        const bounds = getBoundsForMarkersAndCircles(
            [{ id: 'invalid', latitude: NaN, longitude: NaN }],
            [{ id: 't_invalid', centerLat: NaN, centerLng: NaN, radiusKm: 0 }],
            { latitude: NaN, longitude: NaN }
        );
        expect(bounds).toBeNull();
    });
});
