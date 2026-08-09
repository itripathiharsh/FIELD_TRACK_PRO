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
            el.style.backgroundColor = marker.color || '#1976D2';
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
            <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f5f5f5', borderRadius: '8px' }}>
                <div style={{ textAlign: 'center', padding: '20px' }}>
                    <p style={{ color: '#666', fontSize: '14px' }}>Map unavailable</p>
                    <p style={{ color: '#999', fontSize: '12px' }}>{error}</p>
                </div>
            </div>
        );
    }

    return (
        <div style={{ position: 'relative', height }}>
            {isLoading && (
                <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f5f5f5', zIndex: 10 }}>
                    <div style={{ textAlign: 'center' }}>
                        <div style={{ width: '40px', height: '40px', border: '4px solid #e0e0e0', borderTopColor: '#1976D2', borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 10px' }} />
                        <p style={{ color: '#666', fontSize: '14px' }}>Loading map...</p>
                    </div>
                </div>
            )}
            <div ref={mapContainer} style={{ width: '100%', height: '100%', borderRadius: '8px', overflow: 'hidden' }} />
        </div>
    );
}
