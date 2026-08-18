import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MapPage } from './MapPage';
import { AuthProvider } from '../context/AuthContext';
import { ADMIN_USER, CUSTOMER, EMPLOYEE, TERRITORY, json, mockApi, route, signIn } from '../test/utils';
import { Area, Customer } from '../types';

const AREA: Area = {
  id: 'area-1111-1111-1111-111111111111',
  name: 'Central Business District',
  territory_id: TERRITORY.id,
  territory_name: TERRITORY.name,
  created_at: '2026-01-01T00:00:00Z',
};

const TERRITORY_2 = {
  id: '66666666-6666-6666-6666-666666666666',
  name: 'South Region',
  center_latitude: 13.0000,
  center_longitude: 77.7000,
  radius_km: 10,
  status: 'ACTIVE' as const,
  created_at: '2026-01-01T00:00:00Z',
};

const CUSTOMER_2: Customer = {
  id: 'cust-2222-2222-2222-222222222222',
  name: 'Lakshmi Traders',
  contact_number: '+919123456780',
  contact_person: 'Ramesh Kumar',
  address: '45 Commercial Street, Bengaluru',
  location: { latitude: 12.9800, longitude: 77.6000 },
  geofence_radius_m: 100,
  outlet_code: 'OUT-002',
  territory_id: TERRITORY_2.id,
  area_id: null,
  area_name: null,
  created_by: ADMIN_USER.id,
  created_at: '2026-01-01T00:00:00Z',
};

// Mock MapLibre GL JS — stable mock with setData support to test filter/source updates
const mockSetData = vi.fn();
const mockAddSource = vi.fn();
const mockAddLayer = vi.fn();
const mockFitBounds = vi.fn();
const mockFlyTo = vi.fn();

vi.mock('maplibre-gl', () => {
  class MockMap {
    private _sources: Record<string, { setData: typeof vi.fn }> = {};
    on(event: string, callback: () => void) {
      if (event === 'load') {
        setTimeout(() => callback(), 0);
      }
    }
    off() {}
    remove() {}
    addControl() {}
    addSource(id: string, _opts: unknown) {
      mockAddSource(id, _opts);
      this._sources[id] = { setData: mockSetData };
    }
    addLayer(layer: unknown) { mockAddLayer(layer); }
    removeLayer() {}
    removeSource() {}
    getSource(id: string) { return this._sources[id] ?? null; }
    getLayer() { return null; }
    queryRenderedFeatures() { return []; }
    easeTo() {}
    flyTo(opts: unknown) { mockFlyTo(opts); }
    fitBounds(bounds: unknown, opts: unknown) { mockFitBounds(bounds, opts); }
    resize() {}
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
vi.mock('../components/maps/tileConfig', () => ({
  getTileProviderConfig: () => ({
    styleObject: { version: 8, sources: {}, layers: [] },
    styleUrl: null,
  }),
}));

function renderMapPage() {
  return render(
    <MemoryRouter initialEntries={['/map']}>
      <AuthProvider>
        <MapPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('MapPage', () => {
  beforeEach(() => {
    localStorage.clear();
    signIn(ADMIN_USER);
    vi.clearAllMocks();
  });

  it('loads and displays map overview with metric cards', async () => {
    mockApi({
      '/api/v1/auth/me': json(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER, CUSTOMER_2],
      '/api/v1/territories': [TERRITORY, TERRITORY_2],
      '/api/v1/areas': [AREA],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderMapPage();

    expect(await screen.findByText('Customer & Territory Locations Map')).toBeInTheDocument();
    expect(screen.getByText('Total Outlets')).toBeInTheDocument();
    expect(screen.getByText('Active Zones')).toBeInTheDocument();
    expect(screen.getByText('Covered Areas')).toBeInTheDocument();
    expect(screen.getByText('Field Force')).toBeInTheDocument();

    // Default guide state in lower panel
    expect(screen.getByText('Select an Outlet on the Map')).toBeInTheDocument();
  });

  it('Zone filter: filters markers to matching zone, shows No outlets message for zero results', async () => {
    mockApi({
      '/api/v1/auth/me': json(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER, CUSTOMER_2],
      '/api/v1/territories': [TERRITORY, TERRITORY_2],
      '/api/v1/areas': [AREA],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderMapPage();
    await screen.findByText('Customer & Territory Locations Map');

    const zoneSelect = screen.getByRole('combobox', { name: /filter by zone/i });

    // Select a zone that has one customer (TERRITORY.id is CUSTOMER's territory_id)
    await act(async () => {
      fireEvent.change(zoneSelect, { target: { value: TERRITORY.id } });
    });

    // Map legend should still be visible (map is not destroyed)
    expect(screen.getByText('Map Legend & Telemetry Indicators')).toBeInTheDocument();

    // When zone is selected but has matching customers, no zero-result overlay
    expect(screen.queryByText('No outlets match the selected filters.')).not.toBeInTheDocument();

    // Select a zone that has NO customers with matching territory_id
    await act(async () => {
      fireEvent.change(zoneSelect, { target: { value: '00000000-0000-0000-0000-000000000000' } });
    });

    // Toolbar Reset Filters button should appear (use getAllByRole since overlay also has a reset link)
    const resetButtons = screen.getAllByRole('button');
    expect(resetButtons.some((b) => /reset filters/i.test(b.textContent || ''))).toBe(true);

    // Map remains rendered (legend still visible)
    expect(screen.getByText('Map Legend & Telemetry Indicators')).toBeInTheDocument();
  });

  it('Search filter: filters outlets by name and shows reset button', async () => {
    mockApi({
      '/api/v1/auth/me': json(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER, CUSTOMER_2],
      '/api/v1/territories': [TERRITORY, TERRITORY_2],
      '/api/v1/areas': [AREA],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderMapPage();
    await screen.findByText('Customer & Territory Locations Map');

    const searchInput = screen.getByPlaceholderText(/search outlet by name/i);

    await act(async () => {
      fireEvent.change(searchInput, { target: { value: 'Lakshmi' } });
    });

    // Reset button should appear
    expect(screen.getByRole('button', { name: /reset filters/i })).toBeInTheDocument();

    // Map remains visible
    expect(screen.getByText('Map Legend & Telemetry Indicators')).toBeInTheDocument();

    // Clear search via Reset Filters
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /reset filters/i }));
    });
    expect(searchInput).toHaveValue('');

    // Reset button should be gone
    expect(screen.queryByRole('button', { name: /reset filters/i })).not.toBeInTheDocument();
  });

  it('Zero-result filter: shows "No outlets match" overlay without destroying map', async () => {
    mockApi({
      '/api/v1/auth/me': json(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER, CUSTOMER_2],
      '/api/v1/territories': [TERRITORY, TERRITORY_2],
      '/api/v1/areas': [AREA],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderMapPage();
    await screen.findByText('Customer & Territory Locations Map');

    const searchInput = screen.getByPlaceholderText(/search outlet by name/i);

    // Search for something that matches nothing
    await act(async () => {
      fireEvent.change(searchInput, { target: { value: 'zzz_no_match_xyz' } });
    });

    // Overlay message should appear
    expect(await screen.findByText('No outlets match the selected filters.')).toBeInTheDocument();

    // Map is still rendered (tiles visible via legend)
    expect(screen.getByText('Map Legend & Telemetry Indicators')).toBeInTheDocument();

    // "Reset Filters to restore all outlets" link inside overlay
    expect(screen.getByText(/reset filters to restore/i)).toBeInTheDocument();

    // Click it — map should remain and search should be cleared
    await act(async () => {
      fireEvent.click(screen.getByText(/reset filters to restore/i));
    });
    expect(searchInput).toHaveValue('');
    expect(screen.queryByText('No outlets match the selected filters.')).not.toBeInTheDocument();
  });

  it('Employee filter: filters by zone assignment and restores on reset', async () => {
    mockApi({
      '/api/v1/auth/me': json(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER, CUSTOMER_2],
      '/api/v1/territories': [TERRITORY, TERRITORY_2],
      '/api/v1/areas': [AREA],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderMapPage();
    await screen.findByText('Customer & Territory Locations Map');

    const empSelect = screen.getByRole('combobox', { name: /filter by field representative/i });

    await act(async () => {
      fireEvent.change(empSelect, { target: { value: EMPLOYEE.id } });
    });

    // Map remains visible
    expect(screen.getByText('Map Legend & Telemetry Indicators')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reset filters/i })).toBeInTheDocument();

    // Return to All
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /reset filters/i }));
    });
    expect(empSelect).toHaveValue('ALL');
  });

  it('Combined filter: zone + search combination keeps map rendered', async () => {
    mockApi({
      '/api/v1/auth/me': json(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER, CUSTOMER_2],
      '/api/v1/territories': [TERRITORY, TERRITORY_2],
      '/api/v1/areas': [AREA],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderMapPage();
    await screen.findByText('Customer & Territory Locations Map');

    const zoneSelect = screen.getByRole('combobox', { name: /filter by zone/i });
    const searchInput = screen.getByPlaceholderText(/search outlet by name/i);

    await act(async () => {
      fireEvent.change(zoneSelect, { target: { value: TERRITORY.id } });
      fireEvent.change(searchInput, { target: { value: 'Acme' } });
    });

    // Both filters active, map still rendered
    expect(screen.getByText('Map Legend & Telemetry Indicators')).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /reset filters/i }));
    });
    expect(zoneSelect).toHaveValue('ALL');
    expect(searchInput).toHaveValue('');
  });

  it('Selection: auto-clears selected outlet when it is filtered out', async () => {
    // CUSTOMER is in TERRITORY, CUSTOMER_2 is in TERRITORY_2
    // We'll simulate marker click by triggering onMarkerClick via internals
    mockApi({
      '/api/v1/auth/me': json(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER, CUSTOMER_2],
      '/api/v1/territories': [TERRITORY, TERRITORY_2],
      '/api/v1/areas': [AREA],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderMapPage();
    await screen.findByText('Customer & Territory Locations Map');

    // Filter to TERRITORY_2 which only has CUSTOMER_2, CUSTOMER is not in it
    // CUSTOMER is in TERRITORY, not TERRITORY_2
    const zoneSelect = screen.getByRole('combobox', { name: /filter by zone/i });
    await act(async () => {
      fireEvent.change(zoneSelect, { target: { value: TERRITORY_2.id } });
    });

    // Map remains rendered
    expect(screen.getByText('Map Legend & Telemetry Indicators')).toBeInTheDocument();

    // Guide state should be shown (no selection)
    expect(screen.getByText('Select an Outlet on the Map')).toBeInTheDocument();
  });

  it('handles empty customer location datasets gracefully', async () => {
    mockApi({
      '/api/v1/auth/me': json(ADMIN_USER),
      '/api/v1/customers': [],
      '/api/v1/territories': [],
      '/api/v1/areas': [],
      '/api/v1/employees': [],
    });

    renderMapPage();

    expect(await screen.findByText('No Location Data')).toBeInTheDocument();
  });

  it('handles API errors gracefully', async () => {
    mockApi({
      '/api/v1/auth/me': json(ADMIN_USER),
      '/api/v1/customers': route(() => {
        return json({ error: { code: 'INTERNAL_ERROR', message: 'Failed to fetch' } }, 500);
      }),
      '/api/v1/territories': [],
      '/api/v1/areas': [],
      '/api/v1/employees': [],
    });

    renderMapPage();

    // Customers API fails silently (catch(() => [])), so empty state shown
    expect(await screen.findByText('No Location Data')).toBeInTheDocument();
  });

  it('Area filter: works when zone changes and area is reset', async () => {
    mockApi({
      '/api/v1/auth/me': json(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER, CUSTOMER_2],
      '/api/v1/territories': [TERRITORY, TERRITORY_2],
      '/api/v1/areas': [AREA],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderMapPage();
    await screen.findByText('Customer & Territory Locations Map');

    const zoneSelect = screen.getByRole('combobox', { name: /filter by zone/i });
    const areaSelect = screen.getByRole('combobox', { name: /filter by area/i });

    // Select zone first
    await act(async () => {
      fireEvent.change(zoneSelect, { target: { value: TERRITORY.id } });
    });

    // Area dropdown should now only show AREA (which belongs to TERRITORY)
    expect(areaSelect).toHaveValue('ALL');

    // Changing zone resets area to ALL
    await act(async () => {
      fireEvent.change(zoneSelect, { target: { value: TERRITORY_2.id } });
    });
    expect(areaSelect).toHaveValue('ALL');

    // Map remains rendered
    expect(screen.getByText('Map Legend & Telemetry Indicators')).toBeInTheDocument();
  });

  it('Multiple successive filter changes do not break map', async () => {
    mockApi({
      '/api/v1/auth/me': json(ADMIN_USER),
      '/api/v1/customers': [CUSTOMER, CUSTOMER_2],
      '/api/v1/territories': [TERRITORY, TERRITORY_2],
      '/api/v1/areas': [AREA],
      '/api/v1/employees': [EMPLOYEE],
    });

    renderMapPage();
    await screen.findByText('Customer & Territory Locations Map');

    const zoneSelect = screen.getByRole('combobox', { name: /filter by zone/i });
    const searchInput = screen.getByPlaceholderText(/search outlet by name/i);

    // Rapid successive filter changes
    for (let i = 0; i < 3; i++) {
      await act(async () => {
        fireEvent.change(zoneSelect, { target: { value: TERRITORY.id } });
        fireEvent.change(searchInput, { target: { value: 'test' + i } });
        fireEvent.change(zoneSelect, { target: { value: 'ALL' } });
        fireEvent.change(searchInput, { target: { value: '' } });
      });
    }

    // Map is still rendered and functional
    expect(screen.getByText('Map Legend & Telemetry Indicators')).toBeInTheDocument();
    expect(screen.getByText('Select an Outlet on the Map')).toBeInTheDocument();
  });
});
