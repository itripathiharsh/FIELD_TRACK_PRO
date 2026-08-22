import React, { useState, useEffect, useMemo } from 'react';
import { Search, Check } from 'lucide-react';
import { Modal } from './Modal';
import { Button } from './Button';
import { FieldTrackMap, MapMarker, TerritoryCircle } from '../maps/FieldTrackMap';

interface MapPickerProps {
  isOpen: boolean;
  onClose: () => void;
  initialLat?: number | null;
  initialLng?: number | null;
  initialRadius?: number;
  outletName?: string;
  outletAddress?: string;
  onConfirm: (lat: number, lng: number, radiusMeters: number) => void;
}

const DEFAULT_LAT = 26.8467; // Lucknow / Kanpur default center
const DEFAULT_LNG = 80.9462;

export const MapPicker: React.FC<MapPickerProps> = ({
  isOpen,
  onClose,
  initialLat,
  initialLng,
  initialRadius = 75,
  outletName = 'Outlet Location',
  outletAddress = '',
  onConfirm,
}) => {
  const [lat, setLat] = useState<number>(initialLat && !isNaN(initialLat) ? initialLat : DEFAULT_LAT);
  const [lng, setLng] = useState<number>(initialLng && !isNaN(initialLng) ? initialLng : DEFAULT_LNG);
  const [radius, setRadius] = useState<number>(initialRadius || 75);
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      if (initialLat && initialLng && !isNaN(initialLat) && !isNaN(initialLng)) {
        setLat(initialLat);
        setLng(initialLng);
      } else {
        setLat(DEFAULT_LAT);
        setLng(DEFAULT_LNG);
      }
      setRadius(initialRadius || 75);
      setSearchQuery(outletAddress || '');
    }
  }, [isOpen, initialLat, initialLng, initialRadius, outletAddress]);

  const markers: MapMarker[] = useMemo(() => {
    return [
      {
        id: 'selected-pin',
        latitude: lat,
        longitude: lng,
        label: outletName,
        address: outletAddress,
        color: '#ffa515',
      },
    ];
  }, [lat, lng, outletName, outletAddress]);

  const territoryCircles: TerritoryCircle[] = useMemo(() => {
    return [
      {
        id: 'geofence-circle',
        centerLat: lat,
        centerLng: lng,
        radiusKm: radius / 1000,
        name: `Geofence (${radius}m)`,
        color: '#3B82F6',
      },
    ];
  }, [lat, lng, radius]);

  const handleMapClick = (clickLat: number, clickLng: number) => {
    setLat(parseFloat(clickLat.toFixed(6)));
    setLng(parseFloat(clickLng.toFixed(6)));
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setIsSearching(true);
    setSearchError(null);
    try {
      // Free OpenStreetMap Nominatim geocoding
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(
          searchQuery
        )}&limit=1`
      );
      const data = await res.json();
      if (data && data.length > 0) {
        const newLat = parseFloat(parseFloat(data[0].lat).toFixed(6));
        const newLng = parseFloat(parseFloat(data[0].lon).toFixed(6));
        setLat(newLat);
        setLng(newLng);
      } else {
        setSearchError('Address not found. Click directly on the map to place the pin.');
      }
    } catch {
      setSearchError('Geocoding service unavailable. Click directly on the map to place the pin.');
    } finally {
      setIsSearching(false);
    }
  };

  const handleConfirm = () => {
    onConfirm(lat, lng, radius);
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Map Location Picker & Geofence">
      <div className="space-y-4">
        {/* Search Bar */}
        <form onSubmit={handleSearch} className="flex gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-on-surface-variant absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search area, landmark or address in Kanpur/UP..."
              className="w-full pl-9 pr-3 py-2 text-sm bg-surface border border-outline-variant rounded-md text-on-surface focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>
          <Button type="submit" variant="secondary" disabled={isSearching}>
            {isSearching ? 'Searching...' : 'Locate'}
          </Button>
        </form>

        {searchError && (
          <p className="text-xs text-amber-500 bg-amber-500/10 border border-amber-500/20 px-3 py-1.5 rounded">
            {searchError}
          </p>
        )}

        {/* Map View */}
        <div className="relative h-[340px] rounded-lg overflow-hidden border border-outline-variant bg-surface-container">
          <FieldTrackMap
            centerLat={lat}
            centerLng={lng}
            zoom={15}
            markers={markers}
            territoryCircles={territoryCircles}
            onMapClick={handleMapClick}
            height="100%"
            autoFitBounds={false}
          />
          <div className="absolute top-2 left-2 bg-surface/90 backdrop-blur-sm border border-outline-variant px-2.5 py-1 rounded text-xs text-on-surface font-mono shadow-sm">
            Click map to move pin
          </div>
        </div>

        {/* Coordinates & Radius Controls */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 bg-surface-container/50 p-3 rounded-lg border border-outline-variant">
          <div>
            <label className="block text-xs font-semibold text-on-surface-variant mb-1">
              Latitude
            </label>
            <input
              type="number"
              step="0.000001"
              value={lat}
              onChange={(e) => setLat(parseFloat(e.target.value) || 0)}
              className="w-full px-2.5 py-1.5 text-xs font-mono bg-surface border border-outline-variant rounded text-on-surface"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-on-surface-variant mb-1">
              Longitude
            </label>
            <input
              type="number"
              step="0.000001"
              value={lng}
              onChange={(e) => setLng(parseFloat(e.target.value) || 0)}
              className="w-full px-2.5 py-1.5 text-xs font-mono bg-surface border border-outline-variant rounded text-on-surface"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-on-surface-variant mb-1">
              Geofence Radius: <span className="text-primary font-bold">{radius}m</span>
            </label>
            <input
              type="range"
              min="25"
              max="500"
              step="5"
              value={radius}
              onChange={(e) => setRadius(parseInt(e.target.value, 10))}
              className="w-full accent-primary"
            />
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-2 border-t border-outline-variant">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleConfirm}>
            <Check className="w-4 h-4 mr-1.5" /> Confirm Location
          </Button>
        </div>
      </div>
    </Modal>
  );
};
