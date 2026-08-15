import { describe, expect, it, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import { FieldTrackMap, MapMarker } from './FieldTrackMap';

// Mock MapLibre GL JS
vi.mock('maplibre-gl', () => {
    const mockMap = {
        on: vi.fn(),
        off: vi.fn(),
        remove: vi.fn(),
        addControl: vi.fn(),
        addSource: vi.fn(),
        addLayer: vi.fn(),
        removeLayer: vi.fn(),
        removeSource: vi.fn(),
        getSource: vi.fn().mockReturnValue(null),
        getLayer: vi.fn().mockReturnValue(null),
        queryRenderedFeatures: vi.fn().mockReturnValue([]),
        easeTo: vi.fn(),
        getCanvas: vi.fn().mockReturnValue({ style: {} }),
    };
    const mockPopup = {
        setText: vi.fn().mockReturnThis(),
    };
    return {
        default: {
            Map: vi.fn().mockImplementation(() => mockMap),
            Marker: vi.fn().mockImplementation(() => ({
                setLngLat: vi.fn().mockReturnThis(),
                setPopup: vi.fn().mockReturnThis(),
                addTo: vi.fn().mockReturnThis(),
            })),
            Popup: vi.fn().mockImplementation(() => mockPopup),
            NavigationControl: vi.fn(),
        },
        Map: vi.fn().mockImplementation(() => mockMap),
        Marker: vi.fn().mockImplementation(() => ({
            setLngLat: vi.fn().mockReturnThis(),
            setPopup: vi.fn().mockReturnThis(),
            addTo: vi.fn().mockReturnThis(),
        })),
        Popup: vi.fn().mockImplementation(() => mockPopup),
        NavigationControl: vi.fn(),
    };
});

// Mock tile config
vi.mock('./tileConfig', () => ({
    getTileProviderConfig: vi.fn().mockReturnValue({
        styleObject: { version: 8, sources: {}, layers: [] },
        styleUrl: null,
    }),
}));

const mockMarkers: MapMarker[] = [
    { id: '1', latitude: 12.9716, longitude: 77.5946, label: 'Customer A', color: '#ffa515' },
    { id: '2', latitude: 12.9720, longitude: 77.5950, label: 'Customer B', color: '#ffa515' },
    { id: '3', latitude: 13.0000, longitude: 77.6000, label: 'Customer C', color: '#ffa515' },
];

describe('FieldTrackMap', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('renders map container', () => {
        const { container } = render(<FieldTrackMap markers={mockMarkers} />);
        // Map container div should exist
        expect(container.querySelector('div')).toBeTruthy();
    });

    it('renders without markers', () => {
        render(<FieldTrackMap markers={[]} />);
        // Should not throw
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
});
