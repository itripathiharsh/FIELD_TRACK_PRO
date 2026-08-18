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
  selectedMarkerId?: string | null;
  height?: string;
  onMarkerClick?: (marker: MapMarker) => void;
  onMapClick?: (lat: number, lng: number) => void;
  onError?: (error: string) => void;
  enableClustering?: boolean;
  autoFitBounds?: boolean;
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
 * Extract a bounding box for all valid markers and territory circles.
 */
export function getBoundsForMarkersAndCircles(
  markers: MapMarker[] = [],
  territoryCircles: TerritoryCircle[] = [],
): [[number, number], [number, number]] | null {
  const points: [number, number][] = [];

  for (const m of markers) {
    if (
      m.latitude != null &&
      m.longitude != null &&
      !isNaN(m.latitude) &&
      !isNaN(m.longitude) &&
      m.latitude >= -90 &&
      m.latitude <= 90 &&
      m.longitude >= -180 &&
      m.longitude <= 180 &&
      !(m.latitude === 0 && m.longitude === 0)
    ) {
      points.push([m.longitude, m.latitude]);
    }
  }

  for (const c of territoryCircles) {
    if (
      c.centerLat != null &&
      c.centerLng != null &&
      !isNaN(c.centerLat) &&
      !isNaN(c.centerLng) &&
      c.centerLat >= -90 &&
      c.centerLat <= 90 &&
      c.centerLng >= -180 &&
      c.centerLng <= 180 &&
      !(c.centerLat === 0 && c.centerLng === 0)
    ) {
      const radiusKm = c.radiusKm || 10;
      const latDelta = radiusKm / 110.574;
      const cosLat = Math.cos((c.centerLat * Math.PI) / 180);
      const lngDelta = radiusKm / (111.32 * (Math.abs(cosLat) > 0.001 ? Math.abs(cosLat) : 1));
      points.push([c.centerLng - lngDelta, c.centerLat - latDelta]);
      points.push([c.centerLng + lngDelta, c.centerLat + latDelta]);
    }
  }

  if (points.length === 0) return null;

  let minLng = points[0][0];
  let maxLng = points[0][0];
  let minLat = points[0][1];
  let maxLat = points[0][1];

  for (const [lng, lat] of points) {
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }

  return [
    [minLng, minLat],
    [maxLng, maxLat],
  ];
}

function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * FieldTrack Pro Map component using MapLibre GL JS.
 * Supports interactive markers, selection highlights, popups, territory coverage circles,
 * auto-fit bounds, and container resize observation.
 */
export function FieldTrackMap({
  centerLat,
  centerLng,
  zoom = 12,
  markers = [],
  territoryCircles = [],
  selectedMarkerId = null,
  height = '400px',
  onMarkerClick,
  onMapClick,
  onError,
  enableClustering = true,
  autoFitBounds = false,
}: FieldTrackMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const loadTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keep all callback props in refs so changing them never triggers a map reinit
  const onMapClickRef = useRef(onMapClick);
  onMapClickRef.current = onMapClick;

  const onMarkerClickRef = useRef(onMarkerClick);
  onMarkerClickRef.current = onMarkerClick;

  // onError is a ref so an inline lambda from the parent (e.g. MapPage) doesn't
  // cause the map initialisation effect to re-run and destroy the live instance
  // every time the parent re-renders (e.g. on every filter change).
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const markersRef = useRef(markers);
  markersRef.current = markers;

  // Track the signature of marker IDs to avoid re-triggering autoFitBounds on selection changes
  const lastFittedSignatureRef = useRef<string | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isStyleLoaded, setIsStyleLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Initialize Map
  useEffect(() => {
    if (!mapContainer.current || map.current) return;

    const tileConfig = getTileProviderConfig() || {
      styleUrl: null,
      styleObject: { version: 8, sources: {}, layers: [] },
    };

    const hasValidCenter =
      centerLat != null &&
      centerLng != null &&
      !isNaN(centerLat) &&
      !isNaN(centerLng) &&
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
      onErrorRef.current?.(msg);
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
        map.current?.resize();
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
      if (popupRef.current) {
        popupRef.current.remove();
        popupRef.current = null;
      }
      map.current?.remove();
      map.current = null;
      // Reset style-loaded flag so marker/territory effects correctly re-run
      // when a new map instance initialises after this cleanup.
      setIsStyleLoaded(false);
    };
  // onError is intentionally excluded: it is accessed via onErrorRef so
  // changing the callback never destroys and recreates the live map instance.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [centerLat, centerLng, zoom]);

  // Responsive resize observer to prevent broken layout on dimension changes
  useEffect(() => {
    if (!mapContainer.current || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => {
      map.current?.resize();
    });
    ro.observe(mapContainer.current);
    return () => ro.disconnect();
  }, []);

  // Compute marker signature for stable autoFitBounds triggering
  const currentMarkersSignature = markers.map((m) => m.id).sort().join(',');

  // Auto-fit bounding box ONLY on initial style load or when dataset/filters change, NOT on selection!
  useEffect(() => {
    if (!map.current || !isStyleLoaded || !autoFitBounds) return;

    if (lastFittedSignatureRef.current === currentMarkersSignature) {
      return; // Skip re-fitting bounds if markers have not changed
    }

    const bounds = getBoundsForMarkersAndCircles(markers, territoryCircles);
    if (bounds) {
      lastFittedSignatureRef.current = currentMarkersSignature;
      const [sw, ne] = bounds;
      if (Math.abs(sw[0] - ne[0]) < 0.0001 && Math.abs(sw[1] - ne[1]) < 0.0001) {
        map.current.flyTo({
          center: [sw[0], sw[1]],
          zoom: 13,
          essential: true,
        });
      } else {
        map.current.fitBounds(bounds, {
          padding: 50,
          maxZoom: 14,
          duration: 600,
        });
      }
    }
  }, [currentMarkersSignature, territoryCircles, autoFitBounds, isStyleLoaded, markers]);

  // Render Territory Circles
  useEffect(() => {
    if (!map.current || !isStyleLoaded) return;

    try {
      const validCircles = territoryCircles.filter(
        (c) =>
          c.centerLat != null &&
          c.centerLng != null &&
          !isNaN(c.centerLat) &&
          !isNaN(c.centerLng) &&
          c.radiusKm != null &&
          c.radiusKm > 0,
      );

      const features = validCircles.map((c) => {
        const feat = createGeoJSONCircle([c.centerLng, c.centerLat], c.radiusKm);
        feat.properties = {
          id: c.id,
          name: c.name || 'Territory Coverage',
          color: c.color || '#14213D',
        };
        return feat;
      });

      const geojson: GeoJSONFeatureCollection = {
        type: 'FeatureCollection',
        features,
      };

      const existingSource = map.current.getSource(
        'territory-circles-source',
      ) as maplibregl.GeoJSONSource | undefined;

      if (existingSource) {
        existingSource.setData(geojson);
      } else {
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
    } catch (e) {
      console.error('Error rendering territory circles:', e);
    }
  }, [territoryCircles, isStyleLoaded]);

  // Update markers GeoJSON and layers
  useEffect(() => {
    if (!map.current || !isStyleLoaded) return;

    try {
      // Remove legacy DOM markers if present
      const existingMarkers = document.querySelectorAll('.maplibre-marker');
      existingMarkers.forEach((m) => m.remove());

      const validMarkers = markers.filter(
        (m) =>
          m.latitude != null &&
          m.longitude != null &&
          !isNaN(m.latitude) &&
          !isNaN(m.longitude) &&
          m.latitude >= -90 &&
          m.latitude <= 90 &&
          m.longitude >= -180 &&
          m.longitude <= 180 &&
          !(m.latitude === 0 && m.longitude === 0),
      );

      if (enableClustering) {
        const geojson: GeoJSONFeatureCollection = {
          type: 'FeatureCollection',
          features: validMarkers.map(
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

        const existingSource = map.current.getSource(
          'markers-source',
        ) as maplibregl.GeoJSONSource | undefined;

        if (existingSource) {
          existingSource.setData(geojson);
        } else {
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

          // Selected Marker Outer Halo Ring
          map.current.addLayer({
            id: 'selected-marker-halo',
            type: 'circle',
            source: 'markers-source',
            filter: ['==', ['get', 'id'], selectedMarkerId || ''],
            paint: {
              'circle-color': '#ffa515',
              'circle-radius': 18,
              'circle-opacity': 0.35,
              'circle-stroke-width': 2,
              'circle-stroke-color': '#fca311',
              'circle-stroke-opacity': 0.8,
            },
          });

          // Unclustered individual points
          map.current.addLayer({
            id: 'unclustered-point',
            type: 'circle',
            source: 'markers-source',
            filter: ['!', ['has', 'point_count']],
            paint: {
              'circle-color': [
                'case',
                ['==', ['get', 'id'], selectedMarkerId || ''],
                '#ffa515',
                ['get', 'color'],
              ],
              'circle-radius': [
                'case',
                ['==', ['get', 'id'], selectedMarkerId || ''],
                11,
                8,
              ],
              'circle-stroke-width': [
                'case',
                ['==', ['get', 'id'], selectedMarkerId || ''],
                3,
                2,
              ],
              'circle-stroke-color': [
                'case',
                ['==', ['get', 'id'], selectedMarkerId || ''],
                '#14213D',
                '#ffffff',
              ],
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
                const zoomLevel = await source.getClusterExpansionZoom(clusterId);
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
            const marker = markersRef.current.find((m) => m.id === props.id);
            if (marker) {
              onMarkerClickRef.current?.(marker);
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
        }
      } else {
        // Fallback DOM-based markers
        validMarkers.forEach((marker) => {
          const isSelected = marker.id === selectedMarkerId;
          const el = document.createElement('div');
          el.className = 'maplibre-marker';
          el.style.width = isSelected ? '32px' : '24px';
          el.style.height = isSelected ? '32px' : '24px';
          el.style.borderRadius = '50%';
          el.style.backgroundColor = marker.color || '#ffa515';
          el.style.border = isSelected ? '3px solid #14213D' : '3px solid white';
          el.style.boxShadow = isSelected
            ? '0 0 12px rgba(252, 163, 17, 0.8)'
            : '0 2px 4px rgba(0,0,0,0.3)';
          el.style.cursor = 'pointer';
          el.style.transition = 'all 0.2s ease-in-out';

          el.addEventListener('click', () => {
            onMarkerClickRef.current?.(marker);
          });

          new maplibregl.Marker({ element: el })
            .setLngLat([marker.longitude, marker.latitude])
            .setPopup(
              new maplibregl.Popup({ offset: 25 }).setText(
                marker.label ||
                  `Outlet (${marker.latitude.toFixed(4)}, ${marker.longitude.toFixed(4)})`,
              ),
            )
            .addTo(map.current!);
        });
      }
    } catch (e) {
      console.error('Error updating map markers:', e);
    }
  }, [markers, enableClustering, isStyleLoaded, selectedMarkerId]);

  // Handle selected marker visual highlight & popup synchronization
  useEffect(() => {
    if (!map.current || !isStyleLoaded) return;

    try {
      // Update selected-marker-halo layer filter if it exists
      if (map.current.getLayer('selected-marker-halo')) {
        map.current.setFilter('selected-marker-halo', [
          '==',
          ['get', 'id'],
          selectedMarkerId || '',
        ]);
      }

      // Update unclustered-point styling for selected state
      if (map.current.getLayer('unclustered-point')) {
        map.current.setPaintProperty('unclustered-point', 'circle-color', [
          'case',
          ['==', ['get', 'id'], selectedMarkerId || ''],
          '#ffa515',
          ['get', 'color'],
        ]);
        map.current.setPaintProperty('unclustered-point', 'circle-radius', [
          'case',
          ['==', ['get', 'id'], selectedMarkerId || ''],
          11,
          8,
        ]);
        map.current.setPaintProperty('unclustered-point', 'circle-stroke-width', [
          'case',
          ['==', ['get', 'id'], selectedMarkerId || ''],
          3,
          2,
        ]);
        map.current.setPaintProperty('unclustered-point', 'circle-stroke-color', [
          'case',
          ['==', ['get', 'id'], selectedMarkerId || ''],
          '#14213D',
          '#ffffff',
        ]);
      }

      if (selectedMarkerId) {
        const marker = markersRef.current.find((m) => m.id === selectedMarkerId);
        if (marker) {
          // Smoothly center the map on the selected customer without zooming out
          map.current.flyTo({
            center: [marker.longitude, marker.latitude],
            zoom: Math.max(map.current.getZoom(), 13),
            duration: 600,
            essential: true,
          });

          // Show interactive popup anchored at marker
          if (popupRef.current) {
            popupRef.current.remove();
          }

          const popupContainer = document.createElement('div');
          popupContainer.className = 'font-sans p-1 min-w-[160px]';
          popupContainer.innerHTML = `
            <div style="font-weight: 700; color: #14213D; font-size: 13px; margin-bottom: 2px;">${escapeHtml(marker.label || 'Selected Outlet')}</div>
            <div style="font-size: 11px; color: #64748B; margin-bottom: 2px;">Coordinates: ${marker.latitude.toFixed(4)}°, ${marker.longitude.toFixed(4)}°</div>
            <div style="display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; background: #f1f5f9; color: #334155; margin-top: 2px;">Active Outlet</div>
          `;

          popupRef.current = new maplibregl.Popup({
            offset: 16,
            closeButton: false,
            closeOnClick: false,
            className: 'fieldtrack-map-popup',
          })
            .setLngLat([marker.longitude, marker.latitude])
            .setDOMContent(popupContainer)
            .addTo(map.current);
        }
      } else {
        if (popupRef.current) {
          popupRef.current.remove();
          popupRef.current = null;
        }
      }
    } catch (e) {
      console.error('Error updating selected marker highlight:', e);
    }
  }, [selectedMarkerId, isStyleLoaded]);

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
