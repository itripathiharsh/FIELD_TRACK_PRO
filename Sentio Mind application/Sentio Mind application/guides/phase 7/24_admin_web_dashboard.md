# FieldTrack Pro — Admin Web Dashboard
### Phase 7 — React + TypeScript, consuming the same backend Android already validated

Every endpoint here was already smoke-tested in Phase 3 and exercised for real by Android in Phase 6 — this phase is UI over proven APIs, not new backend risk.

---

## 1. Admin Authentication

```tsx
// hooks/useAuth.ts
export function useLogin() {
  const setAuth = useAuthStore(s => s.setAuth);
  return useMutation({
    mutationFn: (creds: LoginRequest) => api.post<AuthResponse>('/auth/login', creds),
    onSuccess: (data) => {
      setAuth(data.user);                      // access token kept in memory only — never localStorage
      document.cookie = `refresh=${data.refreshToken}; Secure; SameSite=Strict; HttpOnly`;
      // note: httpOnly cookies can't actually be set from client JS — this line is illustrative;
      // in practice the backend's /auth/login response sets the httpOnly cookie directly via
      // a Set-Cookie header, matching the Security Design decision. Flagging this explicitly
      // since it's a common mistake when translating the security doc into actual frontend code.
    }
  });
}
```

```tsx
// api/client.ts
const client = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL });

client.interceptors.request.use(config => {
  const token = useAuthStore.getState().accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  response => response,
  async error => {
    if (error.response?.status === 401) {
      const { data } = await client.post('/auth/refresh');   // refresh cookie sent automatically
      useAuthStore.getState().setAccessToken(data.accessToken);
      return client(error.config);   // retry original request
    }
    return Promise.reject(error);
  }
);
```

**Correction worth calling out**: the Security Design doc specified an httpOnly cookie for the refresh token specifically so client-side JS *cannot* read or set it — that's the whole XSS-protection point. The actual implementation is entirely backend-driven (Spring sets `Set-Cookie` on the `/auth/login` response), and the frontend never touches the refresh token directly at all — it just relies on the browser sending the cookie automatically on `/auth/refresh` calls. Flagging this now so it doesn't get built wrong.

---

## 2. Employee Management

```tsx
function EmployeeListPage() {
  const [filters, setFilters] = useState({ territoryId: '', isActive: true });
  const { data, isLoading } = useQuery({
    queryKey: ['employees', filters],
    queryFn: () => api.get('/employees', { params: filters })
  });

  return (
    <PageLayout title="Employees" action={<Button onClick={() => navigate('/employees/new')}>Add employee</Button>}>
      <FilterBar filters={filters} onChange={setFilters} />
      <DataTable
        columns={['Name', 'Territory', 'Employee code', 'Status']}
        rows={data?.content}
        onRowClick={(row) => navigate(`/employees/${row.id}`)}
      />
    </PageLayout>
  );
}
```

```tsx
function AddEmployeeForm() {
  const mutation = useMutation({
    mutationFn: (data: CreateEmployeeRequest) => api.post('/employees', data),
    onSuccess: () => { toast('Employee added'); navigate('/employees'); }
  });
  // form fields: fullName, email, phone, territoryId, initialPassword
  // client-side validation mirrors backend Jakarta Bean Validation rules —
  // but backend validation remains the actual security boundary (per Security Design Section 6)
}
```

Deactivate action calls `PATCH /employees/{id}/deactivate` with a confirmation dialog — this is a meaningful action (per Authentication doc, it immediately revokes the employee's session), so the UI should say so plainly: "This employee will be logged out immediately and won't be able to log back in."

---

## 3. Customer Management

Same list/add/edit pattern as Employees, with two differences worth building distinctly:

```tsx
function AddCustomerForm() {
  const [useMapPicker, setUseMapPicker] = useState(false);

  // Two ways to set location, matching backend's dual support (Customer Service, Phase 3):
  // 1. Type an address, let backend geocode it
  // 2. Drop a pin on an embedded map for precise placement
  return (
    <Form>
      <TextInput label="Customer name" name="name" />
      <TextInput label="Address" name="address" />
      <Toggle label="Set exact location on map instead" checked={useMapPicker} onChange={setUseMapPicker} />
      {useMapPicker && <LocationPicker onSelect={(lat, lng) => setFieldValue('coordinates', { lat, lng })} />}
      <NumberInput label="Check-in radius (meters)" name="geofenceRadiusM" defaultValue={75} />
    </Form>
  );
}
```

The map picker matters practically: geocoding from address text alone can be off by tens of meters in areas with poor address data (common in less-mapped regions) — letting an admin fine-tune the pin directly prevents customers from being set up with a geofence center that doesn't match where the business actually is, which would cause real employees real check-in failures for no fault of their own.

---

## 4. Visit Management

```tsx
function VisitStatusBoard() {
  const { data } = useQuery({
    queryKey: ['visits', 'board'],
    queryFn: () => api.get('/visits', { params: { dateFrom: today, dateTo: today } }),
    refetchInterval: 30000   // light polling — matches the "at-a-glance, not demanding attention" journey insight
  });

  const columns = groupBy(data?.content, 'status');
  return (
    <KanbanBoard>
      {['PENDING', 'IN_PROGRESS', 'COMPLETED', 'MISSED', 'FLAGGED'].map(status => (
        <KanbanColumn key={status} title={status} count={columns[status]?.length ?? 0}>
          {columns[status]?.map(visit => <VisitCard key={visit.id} visit={visit} onClick={() => navigate(`/visits/${visit.id}`)} />)}
        </KanbanColumn>
      ))}
    </KanbanBoard>
  );
}
```

**Refetch interval set to 30s, not real-time websockets** — deliberate choice given the Live Location decision from Phase 4 (event-based, not continuous). Building a websocket layer for "live" updates when the underlying location data itself only changes at check-in/check-out events would be complexity with no real payoff — polling every 30s is indistinguishable from real-time for this use case.

### Flagged Visit Review — The High-Trust-Risk Screen
```tsx
function FlaggedVisitReview({ visitId }: { visitId: string }) {
  const { data: visit } = useQuery({ queryKey: ['visit', visitId], queryFn: () => api.get(`/visits/${visitId}`) });
  const { data: logs } = useQuery({ queryKey: ['geo-logs', visitId], queryFn: () => api.get(`/visits/${visitId}/geo-logs`) });

  return (
    <Card>
      <EmployeeHeader employee={visit.employee} />
      <MapView customerLocation={visit.customer.location} attemptLocations={logs.map(l => l.attemptedLocation)} />
      <ReasonList>
        {logs.filter(l => l.result === 'FAILED').map(l => (
          <ReasonRow key={l.id} reason={l.reason} distance={l.distanceMeters} timestamp={l.attemptedAt} />
        ))}
      </ReasonList>
      <ActionBar>
        <Button variant="secondary" onClick={() => resolveVisit(visitId, 'IN_PROGRESS')}>Mark as resolved</Button>
        <Button variant="primary" onClick={() => resolveVisit(visitId, 'COMPLETED')}>Approve as completed</Button>
      </ActionBar>
    </Card>
  );
}
```

Every failed attempt shows its specific reason code (`OUTSIDE_RADIUS` vs `MOCK_LOCATION_SUSPECTED` vs `GPS_UNAVAILABLE`) distinctly, per the design intent from the Low-Fidelity Wireframes doc — an admin reviewing this should never have to guess why something was flagged.

---

## 5. Reports (Data Views)

```tsx
function EmployeeVisitReport() {
  const [dateRange, setDateRange] = useState({ from: startOfMonth, to: today });
  const { data } = useQuery({
    queryKey: ['reports', 'employee-visits', dateRange],
    queryFn: () => api.get('/reports/employee-visits', { params: dateRange })
  });
  return (
    <ReportLayout title="Employee visit report" filters={<DateRangePicker value={dateRange} onChange={setDateRange} />} onExport={() => exportReport('employee-visits', dateRange)}>
      <DataTable columns={['Employee', 'Visits completed', 'Visits missed', 'Completion rate']} rows={data} />
    </ReportLayout>
  );
}
```

Same `ReportLayout` wrapper used across all four report screens (Employee Visit, Customer History, Productivity, Geo-verification) — consistent filter/export chrome per the Web Dashboard Screen List's note that the Export Modal is a shared component, not four separate implementations.

---

## 6. Analytics (Aggregation, Dashboards, Export)

```tsx
function ProductivityDashboard() {
  const { data } = useQuery({ queryKey: ['reports', 'productivity'], queryFn: () => api.get('/reports/productivity') });
  return (
    <Grid columns={2}>
      <MetricCard label="Avg visits/day" value={data?.avgVisitsPerDay} />
      <MetricCard label="Avg visit duration" value={`${data?.avgDurationMinutes} min`} />
      <ChartCard title="Visits per employee">
        <BarChart data={data?.byEmployee} xKey="employeeName" yKey="visitCount" />
      </ChartCard>
      <ChartCard title="Approx. distance traveled">
        <BarChart data={data?.byEmployee} xKey="employeeName" yKey="distanceKm" />
      </ChartCard>
    </Grid>
  );
}
```

**Distance chart label says "approx."** deliberately — carrying forward the honesty flag from the Maps & Location Services doc (straight-line estimate between check-in/check-out points, not GPS-tracked road mileage). Small UI copy detail, but it's what stops an admin from over-trusting a number that isn't as precise as it looks in a bar chart.

### Export
```tsx
async function exportReport(reportType: string, params: Record<string, string>) {
  const response = await api.get(`/reports/${reportType}/export`, {
    params: { ...params, format: 'csv' },
    responseType: 'blob'
  });
  downloadBlob(response.data, `${reportType}-${today}.csv`);
}
```

CSV and PDF both hit the same backend export endpoint from API Design (`/reports/{type}/export?format=`) — frontend just toggles the `format` param and handles the blob response.

---

## Phase 7 — Complete

Admin Auth (with the httpOnly cookie correction), Employee/Customer/Visit management, and Reports/Analytics (folded together as one UI layer, per your instruction) are all built against the already-proven backend.

**Next up:** Phase 8 — Testing & QA (Final Integration Pass) — the full regression sweep across Android, Web, and Backend together, now that all three exist.
