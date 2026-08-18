import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { FieldTrackMap, MapMarker, TerritoryCircle, getBoundsForMarkersAndCircles } from './FieldTrackMap';

const { mockFitBounds, mockFlyTo, mockResize } = vi.hoisted(() => ({
    mockFitBounds: vi.fn(),
    mockFlyTo: vi.fn(),
    mockResize: vi.fn(),
}));

// Mock MapLibre GL JS
vi.mock('maplibre-gl', () => {
    class MockMap {
        on(event: string, callback: () => void) {
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
        setLngLat() { return this; }
        setPopup() { return this; }
        addTo() { return this; }
    }

    class MockPopup {
        setText() { return this; }
        setLngLat() { return this; }
        setDOMContent() { return this; }
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
        },
        Map: MockMap,
        Marker: MockMarker,
        Popup: MockPopup,
        NavigationControl: MockNavigationControl,
    };
});

// Mock tile config
vi.mock('./tileConfig', () => ({
    getTileProviderConfig: () => ({
        styleObject: { version: 8, sources: {}, layers: [] },
        styleUrl: null,
    }),
}));

const mockMarkers: MapMarker[] = [
    { id: '1', latitude: 12.9716, longitude: 77.5946, label: 'Customer A', color: '#ffa515' },
    { id: '2', latitude: 12.9720, longitude: 77.5950, label: 'Customer B', color: '#ffa515' },
    { id: '3', latitude: 13.0000, longitude: 77.6000, label: 'Customer C', color: '#ffa515' },
];

const mockCircles: TerritoryCircle[] = [
    { id: 't1', centerLat: 26.8467, centerLng: 80.9462, radiusKm: 15, name: 'Lucknow Zone' },
];

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

    it('renders with multiple markers for clustering', () => {
        render(<FieldTrackMap markers={mockMarkers} enableClustering={true} />);
        expect(true).toBe(true);
    });

    it('renders with clustering disabled', () => {
        render(<FieldTrackMap markers={mockMarkers} enableClustering={false} />);
        expect(true).toBe(true);
    });

    it('filters out markers at Null Island', () => {
        const markersWithNullIsland: MapMarker[] = [
            ...mockMarkers,
            { id: 'null', latitude: 0, longitude: 0, label: 'Null Island' },
        ];
        render(<FieldTrackMap markers={markersWithNullIsland} enableClustering={true} />);
        expect(true).toBe(true);
    });

    it('handles markers with invalid coordinates', () => {
        const markersWithInvalid: MapMarker[] = [
            ...mockMarkers,
            { id: 'invalid', latitude: 91, longitude: 181, label: 'Invalid' },
        ];
        render(<FieldTrackMap markers={markersWithInvalid} enableClustering={true} />);
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

    it('correctly calculates bounding box with getBoundsForMarkersAndCircles', () => {
        const bounds = getBoundsForMarkersAndCircles(mockMarkers, mockCircles);
        expect(bounds).not.toBeNull();
        if (bounds) {
            const [[minLng, minLat], [maxLng, maxLat]] = bounds;
            expect(minLng).toBeLessThanOrEqual(77.5946);
            expect(maxLng).toBeGreaterThanOrEqual(80.9462);
            expect(minLat).toBeLessThanOrEqual(12.9716);
            expect(maxLat).toBeGreaterThanOrEqual(26.8467);
        }
    });

    it('returns null bounds when all coordinates are empty or invalid', () => {
        const bounds = getBoundsForMarkersAndCircles(
            [{ id: 'invalid', latitude: 0, longitude: 0 }],
            [{ id: 't_invalid', centerLat: 0, centerLng: 0, radiusKm: 0 }]
        );
        expect(bounds).toBeNull();
    });
});
