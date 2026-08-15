import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { getTileProviderConfig } from './tileConfig';

/** GeoJSON types defined inline to avoid an external dependency. */
interface GeoJSONPoint {
  type: 'Point';
  coordinates: [number, number];
}

interface GeoJSONPolygon {
  type: 'Polygon';
  coordinates: [number, number][][];
}

interface GeoJSONFeature {
  type: 'Feature';
  geometry: GeoJSONPoint | GeoJSONPolygon;
  properties: Record<string, unknown> | null;
}

interface GeoJSONFeatureCollection {
  type: 'FeatureCollection';
  features: GeoJSONFeature[];
}

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

export interface TerritoryCircle {
  id: string;
  centerLat: number;
  centerLng: number;
  radiusKm: number;
  name?: string;
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
  territoryCircles?: TerritoryCircle[];
  height?: string;
  onMarkerClick?: (marker: MapMarker) => void;
  onMapClick?: (lat: number, lng: number) => void;
  onError?: (error: string) => void;
  enableClustering?: boolean;
}

const LOADING_TIMEOUT_MS = 15000;

function createGeoJSONCircle(
  center: [number, number],
  radiusKm: number,
  points = 64,
): GeoJSONFeature {
  const [lng, lat] = center;
  const coords: [number, number][] = [];
  const R = 6371.0088; // Earth radius in km
  const d = radiusKm / R;
  const latRad = (lat * Math.PI) / 180;
  const lngRad = (lng * Math.PI) / 180;

  for (let i = 0; i < points; i++) {
    const bearing = (i * 360) / points;
    const theta = (bearing * Math.PI) / 180;

    const ptLatRad = Math.asin(
      Math.sin(latRad) * Math.cos(d) +
        Math.cos(latRad) * Math.sin(d) * Math.cos(theta),
    );
    const ptLngRad =
      lngRad +
      Math.atan2(
        Math.sin(theta) * Math.sin(d) * Math.cos(latRad),
        Math.cos(d) - Math.sin(latRad) * Math.sin(ptLatRad),
      );

    coords.push([(ptLngRad * 180) / Math.PI, (ptLatRad * 180) / Math.PI]);
  }
  coords.push(coords[0]);

  return {
    type: 'Feature',
    geometry: {
      type: 'Polygon',
      coordinates: [coords],
    },
    properties: null,
  };
}

/**
 * FieldTrack Pro Map component using MapLibre GL JS.
 * Supports interactive markers, territory coverage circles, and map click picker.
 */
export function FieldTrackMap({
  centerLat,
  centerLng,
  zoom = 12,
  markers = [],
  territoryCircles = [],
  height = '400px',
  onMarkerClick,
  onMapClick,
  onError,
  enableClustering = true,
}: FieldTrackMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const loadTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onMapClickRef = useRef(onMapClick);
  onMapClickRef.current = onMapClick;

  const [isLoading, setIsLoading] = useState(true);
  const [isStyleLoaded, setIsStyleLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!mapContainer.current || map.current) return;

    const tileConfig = getTileProviderConfig();

    const hasValidCenter =
      centerLat != null &&
      centerLng != null &&
      centerLat >= -90 &&
      centerLat <= 90 &&
      centerLng >= -180 &&
      centerLng <= 180 &&
      !(centerLat === 0 && centerLng === 0);

    const handleMapError = (msg: string) => {
      setError(msg);
      setIsLoading(false);
      if (loadTimeoutRef.current) {
        clearTimeout(loadTimeoutRef.current);
        loadTimeoutRef.current = null;
      }
      onError?.(msg);
    };

    try {
      const styleConfig = tileConfig.styleUrl
        ? { style: tileConfig.styleUrl }
        : { style: tileConfig.styleObject as maplibregl.StyleSpecification };

      map.current = new maplibregl.Map({
        container: mapContainer.current,
        ...styleConfig,
        center: hasValidCenter ? [centerLng!, centerLat!] : [77.5946, 12.9716],
        zoom: hasValidCenter ? zoom : 4,
      });

      map.current.addControl(new maplibregl.NavigationControl(), 'top-right');

      loadTimeoutRef.current = setTimeout(() => {
        handleMapError(
          'Map loading timed out. Please check your network connection and try again.',
        );
      }, LOADING_TIMEOUT_MS);

      map.current.on('load', () => {
        if (loadTimeoutRef.current) {
          clearTimeout(loadTimeoutRef.current);
          loadTimeoutRef.current = null;
        }
        setIsLoading(false);
        setIsStyleLoaded(true);
      });

      map.current.on('click', (e) => {
        if (onMapClickRef.current) {
          onMapClickRef.current(e.lngLat.lat, e.lngLat.lng);
        }
      });

      map.current.on('error', (e: { error?: { message?: string } }) => {
        const msg = e.error?.message || 'Failed to load map tiles';
        handleMapError(`Map loading failed: ${msg}`);
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to initialize map';
      handleMapError(msg);
    }

    return () => {
      if (loadTimeoutRef.current) {
        clearTimeout(loadTimeoutRef.current);
        loadTimeoutRef.current = null;
      }
      map.current?.remove();
      map.current = null;
    };
  }, [centerLat, centerLng, zoom, onError]);

  // Update map center/zoom if centerLat/centerLng prop changes
  useEffect(() => {
    if (!map.current || !isStyleLoaded) return;
    if (
      centerLat != null &&
      centerLng != null &&
      centerLat >= -90 &&
      centerLat <= 90 &&
      centerLng >= -180 &&
      centerLng <= 180 &&
      !(centerLat === 0 && centerLng === 0)
    ) {
      map.current.flyTo({
        center: [centerLng, centerLat],
        zoom,
        essential: true,
      });
    }
  }, [centerLat, centerLng, zoom, isStyleLoaded]);

  // Render Territory Circles
  useEffect(() => {
    if (!map.current || !isStyleLoaded) return;

    try {
      if (
        map.current.isStyleLoaded() &&
        map.current.getSource('territory-circles-source')
      ) {
        if (map.current.getLayer('territory-circles-fill')) {
          map.current.removeLayer('territory-circles-fill');
        }
        if (map.current.getLayer('territory-circles-outline')) {
          map.current.removeLayer('territory-circles-outline');
        }
        map.current.removeSource('territory-circles-source');
      }

      if (territoryCircles.length > 0) {
        const features = territoryCircles
          .filter(
            (c) =>
              c.centerLat != null &&
              c.centerLng != null &&
              c.radiusKm != null &&
              c.radiusKm > 0,
          )
          .map((c) => {
            const feat = createGeoJSONCircle(
              [c.centerLng, c.centerLat],
              c.radiusKm,
            );
            feat.properties = {
              id: c.id,
              name: c.name || 'Territory Coverage',
              color: c.color || '#14213D',
            };
            return feat;
          });

        if (features.length > 0) {
          const geojson: GeoJSONFeatureCollection = {
            type: 'FeatureCollection',
            features,
          };

          map.current.addSource('territory-circles-source', {
            type: 'geojson',
            data: geojson,
          });

          map.current.addLayer({
            id: 'territory-circles-fill',
            type: 'fill',
            source: 'territory-circles-source',
            paint: {
              'fill-color': ['get', 'color'],
              'fill-opacity': 0.18,
            },
          });

          map.current.addLayer({
            id: 'territory-circles-outline',
            type: 'line',
            source: 'territory-circles-source',
            paint: {
              'line-color': ['get', 'color'],
              'line-width': 2,
              'line-opacity': 0.85,
            },
          });
        }
      }
    } catch (e) {
      console.error('Error rendering territory circles:', e);
    }
  }, [territoryCircles, isStyleLoaded]);

  // Update markers when they change and map style is ready
  useEffect(() => {
    if (!map.current || !isStyleLoaded) return;

    try {
      // Remove existing DOM markers
      const existingMarkers = document.querySelectorAll('.maplibre-marker');
      existingMarkers.forEach((m) => m.remove());

      // Remove existing sources/layers (clustering mode)
      if (
        map.current.isStyleLoaded() &&
        map.current.getSource('markers-source')
      ) {
        if (map.current.getLayer('clusters'))
          map.current.removeLayer('clusters');
        if (map.current.getLayer('cluster-count'))
          map.current.removeLayer('cluster-count');
        if (map.current.getLayer('unclustered-point'))
          map.current.removeLayer('unclustered-point');
        map.current.removeSource('markers-source');
      }

      if (enableClustering) {
        const geojson: GeoJSONFeatureCollection = {
          type: 'FeatureCollection',
          features: markers
            .filter(
              (m) =>
                m.latitude &&
                m.longitude &&
                !(m.latitude === 0 && m.longitude === 0),
            )
            .map(
              (m): GeoJSONFeature => ({
                type: 'Feature',
                geometry: {
                  type: 'Point',
                  coordinates: [m.longitude, m.latitude],
                },
                properties: {
                  id: m.id,
                  label: m.label || '',
                  color: m.color || '#ffa515',
                },
              }),
            ),
        };

        map.current.addSource('markers-source', {
          type: 'geojson',
          data: geojson,
          cluster: true,
          clusterMaxZoom: 14,
          clusterRadius: 50,
        });

        // Cluster circles
        map.current.addLayer({
          id: 'clusters',
          type: 'circle',
          source: 'markers-source',
          filter: ['has', 'point_count'],
          paint: {
            'circle-color': [
              'step',
              ['get', 'point_count'],
              '#14213D',
              100,
              '#fca311',
              750,
              '#e63946',
            ],
            'circle-radius': [
              'step',
              ['get', 'point_count'],
              20,
              100,
              30,
              750,
              40,
            ],
            'circle-opacity': 0.85,
            'circle-stroke-width': 2,
            'circle-stroke-color': '#fff',
          },
        });

        // Cluster count labels
        map.current.addLayer({
          id: 'cluster-count',
          type: 'symbol',
          source: 'markers-source',
          filter: ['has', 'point_count'],
          layout: {
            'text-field': ['get', 'point_count_abbreviated'],
            'text-size': 12,
          },
          paint: {
            'text-color': '#fff',
          },
        });

        // Unclustered points
        map.current.addLayer({
          id: 'unclustered-point',
          type: 'circle',
          source: 'markers-source',
          filter: ['!', ['has', 'point_count']],
          paint: {
            'circle-color': ['get', 'color'],
            'circle-radius': 8,
            'circle-stroke-width': 2,
            'circle-stroke-color': '#fff',
          },
        });

        // Click on cluster to zoom in
        map.current.on('click', 'clusters', async (e) => {
          if (!map.current) return;
          const features = map.current.queryRenderedFeatures(e.point, {
            layers: ['clusters'],
          });
          const clusterId = features[0]?.properties?.cluster_id;
          if (clusterId && features[0]) {
            const source = map.current.getSource(
              'markers-source',
            ) as maplibregl.GeoJSONSource;
            try {
              const zoomLevel =
                await source.getClusterExpansionZoom(clusterId);
              const coords = (features[0].geometry as GeoJSONPoint).coordinates;
              map.current?.easeTo({
                center: coords as [number, number],
                zoom: zoomLevel,
              });
            } catch {
              // Cluster expansion failed, ignore
            }
          }
        });

        // Click on unclustered point
        map.current.on('click', 'unclustered-point', (e) => {
          const features = e.features;
          if (!features || features.length === 0) return;
          const props = features[0].properties;
          if (!props) return;
          const marker = markers.find((m) => m.id === props.id);
          if (marker) {
            onMarkerClick?.(marker);
          }
        });

        map.current.on('mouseenter', 'clusters', () => {
          if (map.current) map.current.getCanvas().style.cursor = 'pointer';
        });
        map.current.on('mouseleave', 'clusters', () => {
          if (map.current) map.current.getCanvas().style.cursor = '';
        });
        map.current.on('mouseenter', 'unclustered-point', () => {
          if (map.current) map.current.getCanvas().style.cursor = 'pointer';
        });
        map.current.on('mouseleave', 'unclustered-point', () => {
          if (map.current) map.current.getCanvas().style.cursor = '';
        });
      } else {
        // Legacy DOM-based markers
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
                marker.label ||
                  `Location (${marker.latitude.toFixed(4)}, ${marker.longitude.toFixed(4)})`,
              ),
            )
            .addTo(map.current!);
        });
      }
    } catch (e) {
      console.error('Error updating map markers:', e);
    }
  }, [markers, onMarkerClick, enableClustering, isStyleLoaded]);

  if (error) {
    return (
      <div
        style={{ height }}
        className="flex items-center justify-center bg-surface-container-low rounded-lg"
        role="alert"
        aria-live="polite"
      >
        <div className="text-center p-space-5">
          <p className="font-headline-sm text-sm text-on-surface-variant font-semibold">
            Map unavailable
          </p>
          <p className="font-caption text-xs text-outline mt-1">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ position: 'relative', height }}>
      {isLoading && (
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            zIndex: 10,
          }}
          className="flex items-center justify-center bg-surface-container-low"
          aria-live="polite"
          aria-busy="true"
        >
          <div className="text-center">
            <div className="w-10 h-10 border-4 border-primary-container border-t-secondary-container rounded-full animate-spin mx-auto mb-space-2.5" />
            <p className="font-caption text-xs text-on-surface-variant">
              Loading map...
            </p>
          </div>
        </div>
      )}
      <div
        ref={mapContainer}
        style={{
          width: '100%',
          height: '100%',
          borderRadius: '8px',
          overflow: 'hidden',
          cursor: onMapClick ? 'crosshair' : 'grab',
        }}
      />
    </div>
  );
}
