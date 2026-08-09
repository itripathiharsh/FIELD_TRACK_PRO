import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { getTileProviderConfig } from './tileConfig';

/**
 * Map marker data.
 */
export interface MapMarker {
    id: string;
    latitude: number;
    longitude: number;
    label?: string;
    color?: string;
}

/**
 * Map component props.
 */
export interface FieldTrackMapProps {
    centerLat?: number;
    centerLng?: number;
    zoom?: number;
    markers?: MapMarker[];
    height?: string;
    onMarkerClick?: (marker: MapMarker) => void;
    onError?: (error: string) => void;
}

/**
 * FieldTrack Pro Map component using MapLibre GL JS.
 *
 * Displays an interactive map with markers from real backend data.
 * No fake/demo geographic data is used.
 */
export function FieldTrackMap({
    centerLat,
    centerLng,
    zoom = 12,
    markers = [],
    height = '400px',
    onMarkerClick,
    onError,
}: FieldTrackMapProps) {
    const mapContainer = useRef<HTMLDivElement>(null);
    const map = useRef<maplibregl.Map | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Validate coordinates
    const hasValidCenter = centerLat != null && centerLng != null &&
        centerLat >= -90 && centerLat <= 90 &&
        centerLng >= -180 && centerLng <= 180 &&
        !(centerLat === 0 && centerLng === 0);

    useEffect(() => {
        if (!mapContainer.current || map.current) return;

        const tileConfig = getTileProviderConfig();

        try {
            map.current = new maplibregl.Map({
                container: mapContainer.current,
                style: tileConfig.styleUrl,
                center: hasValidCenter ? [centerLng!, centerLat!] : [77.5946, 12.9716],
                zoom: hasValidCenter ? zoom : 4,
            });

            map.current.addControl(new maplibregl.NavigationControl(), 'top-right');

            map.current.on('load', () => {
                setIsLoading(false);
            });

            map.current.on('error', (e: { error?: { message?: string } }) => {
                const msg = e.error?.message || 'Failed to load map tiles';
                setError(msg);
                setIsLoading(false);
                onError?.(msg);
            });
        } catch (e) {
            const msg = e instanceof Error ? e.message : 'Failed to initialize map';
            setError(msg);
            setIsLoading(false);
            onError?.(msg);
        }

        return () => {
            map.current?.remove();
            map.current = null;
        };
    }, []);

    // Update markers when they change
    useEffect(() => {
        if (!map.current) return;

        // Remove existing markers
        const existingMarkers = document.querySelectorAll('.maplibre-marker');
        existingMarkers.forEach((m) => m.remove());

        // Add new markers
        markers.forEach((marker) => {
            if (!marker.latitude || !marker.longitude) return;
            if (marker.latitude === 0 && marker.longitude === 0) return;

            const el = document.createElement('div');
            el.className = 'maplibre-marker';
            el.style.width = '24px';
            el.style.height = '24px';
            el.style.borderRadius = '50%';
            el.style.backgroundColor = marker.color || '#ffa515';
            el.style.border = '3px solid white';
            el.style.boxShadow = '0 2px 4px rgba(0,0,0,0.3)';
            el.style.cursor = 'pointer';

            el.addEventListener('click', () => {
                onMarkerClick?.(marker);
            });

            new maplibregl.Marker({ element: el })
                .setLngLat([marker.longitude, marker.latitude])
                .setPopup(
                    new maplibregl.Popup({ offset: 25 }).setText(
                        marker.label || `Location (${marker.latitude.toFixed(4)}, ${marker.longitude.toFixed(4)})`
                    )
                )
                .addTo(map.current!);
        });
    }, [markers, onMarkerClick]);

    if (error) {
        return (
            <div
                style={{ height }}
                className="flex items-center justify-center bg-surface-container-low rounded-lg"
            >
                <div className="text-center p-space-5">
                    <p className="font-headline-sm text-sm text-on-surface-variant font-semibold">Map unavailable</p>
                    <p className="font-caption text-xs text-outline mt-1">{error}</p>
                </div>
            </div>
        );
    }

    return (
        <div style={{ position: 'relative', height }}>
            {isLoading && (
                <div
                    style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 10 }}
                    className="flex items-center justify-center bg-surface-container-low"
                >
                    <div className="text-center">
                        <div className="w-10 h-10 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin mx-auto mb-space-2.5" />
                        <p className="font-caption text-xs text-on-surface-variant">Loading map...</p>
                    </div>
                </div>
            )}
            <div ref={mapContainer} style={{ width: '100%', height: '100%', borderRadius: '8px', overflow: 'hidden' }} />
        </div>
    );
}
