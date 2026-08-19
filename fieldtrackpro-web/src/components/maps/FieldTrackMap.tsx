import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { getTileProviderConfig, MAPLIBRE_WORKER_URL } from './tileConfig';

// Initialize MapLibre worker URL if supported
try {
  if (typeof maplibregl.setWorkerUrl === 'function') {
    maplibregl.setWorkerUrl(MAPLIBRE_WORKER_URL);
  }
} catch {
  // Ignore in environments where setWorkerUrl is not available
}

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
 * Current user / employee GPS telemetry coordinates.
 */
export interface CurrentUserLocation {
  latitude: number;
  longitude: number;
  accuracy?: number;
  label?: string;
}

/**
 * Customer / Outlet map marker data.
 */
export interface MapMarker {
  id: string;
  latitude: number;
  longitude: number;
  label?: string;
  color?: string;
  outletCode?: string;
  address?: string;
  territoryName?: string;
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
  currentLocation?: CurrentUserLocation | null;
  height?: string;
  onMarkerClick?: (marker: MapMarker) => void;
  onMapClick?: (lat: number, lng: number) => void;
  onError?: (error: string) => void;
  enableClustering?: boolean;
  autoFitBounds?: boolean;
}

const LOADING_TIMEOUT_MS = 15000;

export function isValidCoordinate(lat?: number | null, lng?: number | null): boolean {
  return (
    lat != null &&
    lng != null &&
    !isNaN(lat) &&
    !isNaN(lng) &&
    lat >= -90 &&
    lat <= 90 &&
    lng >= -180 &&
    lng <= 180 &&
    !(lat === 0 && lng === 0)
  );
}

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
 * Extract a bounding box for all valid markers, employee location, and territory circles.
 */
export function getBoundsForMarkersAndCircles(
  markers: MapMarker[] = [],
  territoryCircles: TerritoryCircle[] = [],
  currentLocation?: CurrentUserLocation | null,
): [[number, number], [number, number]] | null {
  const points: [number, number][] = [];

  for (const m of markers) {
    if (isValidCoordinate(m.latitude, m.longitude)) {
      points.push([m.longitude, m.latitude]);
    }
  }

  if (currentLocation && isValidCoordinate(currentLocation.latitude, currentLocation.longitude)) {
    points.push([currentLocation.longitude, currentLocation.latitude]);
  }

  for (const c of territoryCircles) {
    if (isValidCoordinate(c.centerLat, c.centerLng)) {
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

// Injected CSS for marker animations and radar wave
const MARKER_STYLES_ID = 'fieldtrack-map-styles';
function ensureMarkerStylesInjected() {
  if (typeof document === 'undefined') return;
  if (document.getElementById(MARKER_STYLES_ID)) return;

  const style = document.createElement('style');
  style.id = MARKER_STYLES_ID;
  style.textContent = `
    @keyframes ft-radar-ping {
      0% { transform: scale(0.9); opacity: 0.8; }
      70% { transform: scale(2.4); opacity: 0; }
      100% { transform: scale(2.4); opacity: 0; }
    }
    @keyframes ft-pulse-ring {
      0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.7); }
      70% { transform: scale(1.05); box-shadow: 0 0 0 8px rgba(245, 158, 11, 0); }
      100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(245, 158, 11, 0); }
    }
    .ft-customer-pin {
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      border-radius: 50% 50% 50% 0;
      transform: rotate(-45deg);
      cursor: pointer;
      box-shadow: 0 3px 8px rgba(0,0,0,0.3);
      transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
      background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
      border: 2px solid #ffffff;
    }
    .ft-customer-pin.is-selected {
      background: linear-gradient(135deg, #ffa515 0%, #ea580c 100%);
      border: 3px solid #14213D;
      animation: ft-pulse-ring 2s infinite;
      z-index: 100;
      transform: rotate(-45deg) scale(1.2);
    }
    .ft-customer-pin svg {
      transform: rotate(45deg);
      width: 16px;
      height: 16px;
      color: #ffffff;
      fill: none;
      stroke: currentColor;
      stroke-width: 2;
    }
    .ft-employee-marker-container {
      position: relative;
      width: 44px;
      height: 44px;
      display: flex;
      align-items: center;
      justify-content: center;
      pointer-events: auto;
      cursor: pointer;
    }
    .ft-employee-radar-wave {
      position: absolute;
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background-color: rgba(14, 165, 233, 0.4);
      animation: ft-radar-ping 2s cubic-bezier(0, 0, 0.2, 1) infinite;
      pointer-events: none;
    }
    .ft-employee-beacon {
      position: relative;
      width: 22px;
      height: 22px;
      border-radius: 50%;
      background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
      border: 3px solid #ffffff;
      box-shadow: 0 2px 6px rgba(2, 132, 199, 0.5), 0 0 0 2px #0284c7;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.2s ease;
    }
    .ft-employee-beacon:hover {
      transform: scale(1.15);
    }
    .ft-employee-beacon-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background-color: #ffffff;
    }
    .maplibregl-popup-content {
      padding: 10px 12px !important;
      border-radius: 8px !important;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2), 0 8px 10px -6px rgba(0, 0, 0, 0.1) !important;
    }
  `;
  document.head.appendChild(style);
}

/**
 * FieldTrack Pro Map component using MapLibre GL JS.
 * Supports interactive markers, selection highlights, popups, territory coverage circles,
 * live employee GPS tracking, auto-fit bounds, and container resize observation.
 */
export function FieldTrackMap({
  centerLat,
  centerLng,
  zoom = 12,
  markers = [],
  territoryCircles = [],
  selectedMarkerId = null,
  currentLocation = null,
  height = '400px',
  onMarkerClick,
  onMapClick,
  onError,
  enableClustering = true,
  autoFitBounds = false,
}: FieldTrackMapProps) {
  void enableClustering;
  const mapContainer = useRef<HTMLDivElement>(null);

  const map = useRef<maplibregl.Map | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const loadTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Markers ref to track active DOM marker instances
  const activeMarkersRef = useRef<Map<string, maplibregl.Marker>>(new Map());
  const employeeMarkerRef = useRef<maplibregl.Marker | null>(null);

  // Keep all callback props in refs so changing them never triggers a map reinit
  const onMapClickRef = useRef(onMapClick);
  onMapClickRef.current = onMapClick;

  const onMarkerClickRef = useRef(onMarkerClick);
  onMarkerClickRef.current = onMarkerClick;

  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const markersRef = useRef(markers);
  markersRef.current = markers;

  // Track the signature of marker IDs + location to avoid re-triggering autoFitBounds unnecessarily
  const lastFittedSignatureRef = useRef<string | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isStyleLoaded, setIsStyleLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Inject CSS animations
  useEffect(() => {
    ensureMarkerStylesInjected();
  }, []);

  // Initialize Map
  useEffect(() => {
    if (!mapContainer.current || map.current) return;

    const tileConfig = getTileProviderConfig() || {
      styleUrl: null,
      styleObject: { version: 8, sources: {}, layers: [] },
    };

    const hasValidCenter = isValidCoordinate(centerLat, centerLng);

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
        zoom: hasValidCenter ? zoom : 5,
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
        // Ignore non-fatal worker or tile 404 errors so map stays usable
        if (msg.includes('worker') || msg.includes('404')) {
          console.warn('MapLibre notice:', msg);
          return;
        }
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
      // Remove all active DOM markers
      activeMarkersRef.current.forEach((marker) => marker.remove());
      activeMarkersRef.current.clear();
      if (employeeMarkerRef.current) {
        employeeMarkerRef.current.remove();
        employeeMarkerRef.current = null;
      }
      map.current?.remove();
      map.current = null;
      setIsStyleLoaded(false);
    };
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
  const currentMarkersSignature = [
    markers.map((m) => m.id).sort().join(','),
    currentLocation ? `${currentLocation.latitude.toFixed(3)},${currentLocation.longitude.toFixed(3)}` : 'noloc',
  ].join('|');

  // Auto-fit bounding box on style load or when dataset/filters change, NOT on selection!
  useEffect(() => {
    if (!map.current || !isStyleLoaded || !autoFitBounds) return;

    if (lastFittedSignatureRef.current === currentMarkersSignature) {
      return; // Skip re-fitting bounds if markers and location have not changed
    }

    const bounds = getBoundsForMarkersAndCircles(markers, territoryCircles, currentLocation);
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
          padding: 60,
          maxZoom: 14,
          duration: 600,
        });
      }
    }
  }, [currentMarkersSignature, territoryCircles, autoFitBounds, isStyleLoaded, markers, currentLocation]);

  // Render Territory Circles
  useEffect(() => {
    if (!map.current || !isStyleLoaded) return;

    try {
      const validCircles = territoryCircles.filter(
        (c) =>
          isValidCoordinate(c.centerLat, c.centerLng) &&
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
            'fill-opacity': 0.16,
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
      console.warn('Notice rendering territory circles:', e);
    }
  }, [territoryCircles, isStyleLoaded]);

  // Render Customer Markers using high-performance, worker-independent DOM Markers
  useEffect(() => {
    if (!map.current || !isStyleLoaded) return;

    try {
      const validMarkers = markers.filter((m) => isValidCoordinate(m.latitude, m.longitude));
      const currentMarkerIds = new Set(validMarkers.map((m) => m.id));

      // 1. Remove markers that are no longer in the dataset
      activeMarkersRef.current.forEach((markerInstance, id) => {
        if (!currentMarkerIds.has(id)) {
          markerInstance.remove();
          activeMarkersRef.current.delete(id);
        }
      });

      // 2. Create or update markers
      validMarkers.forEach((marker) => {
        const isSelected = marker.id === selectedMarkerId;
        let markerInstance = activeMarkersRef.current.get(marker.id);

        if (!markerInstance) {
          // Build custom SVG Pin DOM Element
          const el = document.createElement('div');
          el.className = `ft-customer-pin ${isSelected ? 'is-selected' : ''}`;
          el.setAttribute('data-testid', `marker-${marker.id}`);
          el.setAttribute('title', marker.label || 'Customer Outlet');
          el.setAttribute('tabindex', '0');
          el.setAttribute('role', 'button');
          el.setAttribute('aria-label', `Outlet: ${marker.label || marker.id}`);

          // Shop / Building Icon SVG
          el.innerHTML = `
            <svg viewBox="0 0 24 24" stroke="currentColor" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
              <polyline points="9 22 9 12 15 12 15 22"></polyline>
            </svg>
          `;

          const popupContent = document.createElement('div');
          popupContent.className = 'font-sans text-xs';
          popupContent.innerHTML = `
            <div style="font-weight: 700; color: #0f172a; font-size: 13px; margin-bottom: 2px;">${escapeHtml(marker.label || 'Customer Outlet')}</div>
            ${marker.outletCode ? `<div style="font-size: 11px; color: #64748b; margin-bottom: 2px;">Code: <strong>${escapeHtml(marker.outletCode)}</strong></div>` : ''}
            <div style="font-size: 10px; color: #94a3b8;">${marker.latitude.toFixed(4)}°, ${marker.longitude.toFixed(4)}°</div>
            <div style="margin-top: 6px; font-size: 10px; font-weight: 600; color: #d97706; text-transform: uppercase; letter-spacing: 0.5px;">Click to inspect outlet</div>
          `;

          const popup = new maplibregl.Popup({
            offset: 16,
            closeButton: false,
            className: 'fieldtrack-outlet-hover-popup',
          }).setDOMContent(popupContent);

          const handleClick = (e: Event) => {
            e.stopPropagation();
            onMarkerClickRef.current?.(marker);
          };

          el.addEventListener('click', handleClick);
          el.addEventListener('keydown', (e: KeyboardEvent) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onMarkerClickRef.current?.(marker);
            }
          });

          markerInstance = new maplibregl.Marker({
            element: el,
            anchor: 'bottom',
          })
            .setLngLat([marker.longitude, marker.latitude])
            .setPopup(popup)
            .addTo(map.current!);

          activeMarkersRef.current.set(marker.id, markerInstance);
        } else {
          // Update position and selected state of existing marker
          markerInstance.setLngLat([marker.longitude, marker.latitude]);
          const el = markerInstance.getElement();
          if (isSelected) {
            el.classList.add('is-selected');
          } else {
            el.classList.remove('is-selected');
          }
        }
      });
    } catch (e) {
      console.error('Error rendering customer markers:', e);
    }
  }, [markers, isStyleLoaded, selectedMarkerId]);

  // Render Employee Live GPS Current Location Marker
  useEffect(() => {
    if (!map.current || !isStyleLoaded) return;

    try {
      if (currentLocation && isValidCoordinate(currentLocation.latitude, currentLocation.longitude)) {
        if (!employeeMarkerRef.current) {
          // Create custom GPS radar marker DOM element
          const el = document.createElement('div');
          el.className = 'ft-employee-marker-container';
          el.setAttribute('data-testid', 'marker-employee-location');
          el.setAttribute('title', 'Your Current Location');
          el.setAttribute('aria-label', 'Employee Current GPS Location');

          el.innerHTML = `
            <div class="ft-employee-radar-wave"></div>
            <div class="ft-employee-beacon">
              <div class="ft-employee-beacon-dot"></div>
            </div>
          `;

          const popupContent = document.createElement('div');
          popupContent.className = 'font-sans text-xs';
          popupContent.innerHTML = `
            <div style="display: flex; align-items: center; gap: 4px; margin-bottom: 2px;">
              <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background-color: #0ea5e9;"></span>
              <strong style="color: #0284c7; font-size: 12px;">Your Current Location</strong>
            </div>
            <div style="font-size: 11px; color: #334155; font-weight: 500;">Field Representative GPS</div>
            <div style="font-size: 10px; color: #64748b; margin-top: 2px;">${currentLocation.latitude.toFixed(5)}°, ${currentLocation.longitude.toFixed(5)}°</div>
            ${currentLocation.accuracy ? `<div style="font-size: 9px; color: #94a3b8; margin-top: 2px;">Accuracy: ±${Math.round(currentLocation.accuracy)}m</div>` : ''}
          `;

          const popup = new maplibregl.Popup({
            offset: 14,
            closeButton: false,
          }).setDOMContent(popupContent);

          employeeMarkerRef.current = new maplibregl.Marker({
            element: el,
            anchor: 'center',
          })
            .setLngLat([currentLocation.longitude, currentLocation.latitude])
            .setPopup(popup)
            .addTo(map.current!);
        } else {
          // Update location smoothly
          employeeMarkerRef.current.setLngLat([currentLocation.longitude, currentLocation.latitude]);
        }
      } else {
        if (employeeMarkerRef.current) {
          employeeMarkerRef.current.remove();
          employeeMarkerRef.current = null;
        }
      }
    } catch (e) {
      console.error('Error rendering employee location marker:', e);
    }
  }, [currentLocation, isStyleLoaded]);

  // Handle selected marker camera centering & active popup synchronization
  useEffect(() => {
    if (!map.current || !isStyleLoaded) return;

    try {
      if (selectedMarkerId) {
        const marker = markersRef.current.find((m) => m.id === selectedMarkerId);
        if (marker && isValidCoordinate(marker.latitude, marker.longitude)) {
          // Smoothly center the map on the selected customer without jarring zoom
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
          popupContainer.className = 'font-sans p-1 min-w-[180px]';
          popupContainer.innerHTML = `
            <div style="font-weight: 700; color: #14213D; font-size: 13px; margin-bottom: 2px;">${escapeHtml(marker.label || 'Selected Outlet')}</div>
            ${marker.outletCode ? `<div style="font-size: 11px; color: #475569; margin-bottom: 2px;">Code: <span style="font-family: monospace; font-weight: 600;">${escapeHtml(marker.outletCode)}</span></div>` : ''}
            <div style="font-size: 11px; color: #64748B; margin-bottom: 4px;">Coordinates: ${marker.latitude.toFixed(4)}°, ${marker.longitude.toFixed(4)}°</div>
            <div style="display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; background: #fef3c7; color: #92400e;">Active Outlet</div>
          `;

          popupRef.current = new maplibregl.Popup({
            offset: 24,
            closeButton: true,
            closeOnClick: false,
            className: 'fieldtrack-map-selected-popup',
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
