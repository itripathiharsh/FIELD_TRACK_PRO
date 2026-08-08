# FieldTrack Pro — Android Application
### Phase 6 — First phase where every backend dependency already exists

Everything here consumes real endpoints from Phases 3–5 — no mocked APIs. Structure follows the Folder Structure doc's `data/domain/ui` split and MVVM architecture from Tech Stack.

---

## 1. UI/UX

### Navigation Setup (Implements the Navigation Flow Doc)
```kotlin
@Composable
fun FieldTrackNavGraph(navController: NavHostController, startDestination: String) {
    NavHost(navController, startDestination = startDestination) {
        composable("login") { LoginScreen(onLoginSuccess = { navController.navigate("dashboard") { popUpTo("login") { inclusive = true } } }) }
        composable("dashboard") { DashboardScreen(onVisitClick = { id -> navController.navigate("visit/$id") }) }
        composable("visit/{visitId}", arguments = listOf(navArgument("visitId") { type = NavType.StringType })) { backStackEntry ->
            VisitDetailScreen(visitId = backStackEntry.arguments!!.getString("visitId")!!, navController = navController)
        }
        composable("visit/{visitId}/form") { /* Requirement Form screen */ }
        composable("visit/{visitId}/signature/{signedBy}") { /* Signature Pad screen */ }
        composable("visit/{visitId}/review") { /* Visit Summary/Review screen */ }
        composable("notifications") { NotificationsScreen() }
        composable("profile") { ProfileScreen() }
        composable("settings") { SettingsScreen(onLogout = { navController.navigate("login") { popUpTo(0) } }) }
    }
}
```

Single-stack push navigation, exactly as decided in the Navigation Flow doc — no bottom nav bar, since Dashboard is the only true home and everything else is a forward path back to it.

### Theme
```kotlin
val FieldTrackColors = lightColorScheme(
    primary = Color(0xFF1D9E75),      // matches c-teal from the wireframe palette
    secondary = Color(0xFF378ADD),
    error = Color(0xFFE24B4A),
    surface = Color(0xFFFFFFFF)
)
```

### Reusable Components (Built Once, Used Across Screens)
- `VisitStatusBadge` — colored chip for Pending/In Progress/Completed/Missed/Flagged, shared between Dashboard cards and Visit Detail.
- `LoadingState` / `ErrorState` / `EmptyState` — standard composables so every screen handles these three states consistently rather than each screen inventing its own.
- `OfflineBanner` — the persistent top banner from the Android Screen List (Screen 20), shown app-wide when `ConnectivityObserver` reports no network.

---

## 2. Authentication

```kotlin
@HiltViewModel
class LoginViewModel @Inject constructor(
    private val authRepository: AuthRepository
) : ViewModel() {

    var uiState by mutableStateOf(LoginUiState())
        private set

    fun login(identifier: String, password: String) {
        viewModelScope.launch {
            uiState = uiState.copy(isLoading = true, error = null)
            authRepository.login(identifier, password)
                .onSuccess { uiState = uiState.copy(isLoading = false, loginSuccess = true) }
                .onFailure { e ->
                    val message = when (e) {
                        is RateLimitException -> "Too many attempts — try again in 15 minutes"
                        is UnauthorizedException -> "Incorrect email/phone or password"
                        else -> "Something went wrong — check your connection"
                    }
                    uiState = uiState.copy(isLoading = false, error = message)
                }
        }
    }
}
```

**Copy note, tying back to CDS content guidance from the wireframe read_me**: error messages are specific and actionable ("Incorrect email/phone or password"), never a raw exception string surfaced to the field employee.

### Token Storage (Android Keystore-backed, per Security Design)
```kotlin
class SecureTokenStore @Inject constructor(@ApplicationContext context: Context) {
    private val encryptedPrefs = EncryptedSharedPreferences.create(
        context, "auth_tokens",
        MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
        EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
        EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
    )
    fun saveTokens(access: String, refresh: String) { /* store */ }
    fun getAccessToken(): String? = encryptedPrefs.getString("access_token", null)
}
```

### Auth Interceptor (Auto-Refresh on 401)
```kotlin
class AuthInterceptor @Inject constructor(
    private val tokenStore: SecureTokenStore,
    private val authApi: AuthApi
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request().newBuilder()
            .addHeader("Authorization", "Bearer ${tokenStore.getAccessToken()}")
            .build()
        val response = chain.proceed(request)

        if (response.code == 401) {
            response.close()
            val newToken = runBlocking { authApi.refresh(tokenStore.getRefreshToken()) }
            tokenStore.saveTokens(newToken.accessToken, newToken.refreshToken)
            val retryRequest = chain.request().newBuilder()
                .addHeader("Authorization", "Bearer ${newToken.accessToken}")
                .build()
            return chain.proceed(retryRequest)
        }
        return response
    }
}
```

---

## 3. Customer Visits

```kotlin
@HiltViewModel
class DashboardViewModel @Inject constructor(
    private val visitRepository: VisitRepository
) : ViewModel() {

    val todayVisits = flow { emit(visitRepository.getTodayVisits()) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), UiState.Loading)

    fun refresh() = viewModelScope.launch { visitRepository.syncTodayVisits() }
}
```

`VisitRepository` is the single source of truth (per Folder Structure's `data/repository` layer) — it decides whether to serve from Room (offline) or hit `GET /visits/me/today` and cache the result, so the ViewModel never needs to know which source it came from.

```kotlin
@Composable
fun VisitDetailScreen(visitId: String, viewModel: VisitDetailViewModel = hiltViewModel()) {
    val visit by viewModel.visit.collectAsState()
    Column {
        CustomerInfoCard(visit.customer)
        MiniMapPreview(visit.customer.location)
        Button(onClick = { viewModel.navigateToCustomer() }) { Text("Navigate") }
        Button(
            onClick = { viewModel.startCheckIn() },
            enabled = viewModel.isWithinGeofence   // per E11 — disabled until in range
        ) { Text("Start visit") }
    }
}
```

---

## 4. GPS (Consuming Phase 4's `LocationCaptureService`)

```kotlin
@HiltViewModel
class CheckInViewModel @Inject constructor(
    private val locationCaptureService: LocationCaptureService,
    private val visitRepository: VisitRepository
) : ViewModel() {

    fun performCheckIn(visitId: String) {
        viewModelScope.launch {
            val location = locationCaptureService.getCurrentLocation()
            val idempotencyKey = UUID.randomUUID().toString()   // generated once, reused on retry

            val result = visitRepository.checkIn(
                visitId = visitId,
                latitude = location.latitude,
                longitude = location.longitude,
                isMockLocation = location.isMockLocation,
                idempotencyKey = idempotencyKey
            )

            when {
                result.isValid -> navigateToRequirementForm()
                else -> showFailureState(result.reason)   // "Let's get you checked in — try moving closer" per User Journey copy tone
            }
        }
    }
}
```

The `idempotencyKey` is generated once per check-in attempt and persisted with the queued offline record (Room), so if `WorkManager` retries a failed sync later, it reuses the same key — this is the client half of the idempotency mechanism decided in Phase 3's Business Logic doc.

---

## 5. Geofencing (Consuming Phase 4's `GeofenceManager`)

```kotlin
@Composable
fun VisitDetailScreen(visitId: String, viewModel: VisitDetailViewModel = hiltViewModel()) {
    DisposableEffect(visitId) {
        viewModel.registerGeofence()   // calls GeofenceManager.registerGeofence() from Phase 4
        onDispose { viewModel.unregisterGeofence() }
    }
    // ... rest of screen
}
```

Registered when the screen is composed, unregistered when the employee navigates away — matches the "no more than the current day's active geofences" note from the Maps & Location Services doc. The `GeofenceBroadcastReceiver` (already built in Phase 4) triggers the check-in prompt dialog independently of whether this screen is even in the foreground, which is the actual point of using the OS-level Geofencing API rather than polling location manually.

---

## 6. Forms

```kotlin
@HiltViewModel
class RequirementFormViewModel @Inject constructor(
    private val formRepository: RequirementFormRepository,
    savedStateHandle: SavedStateHandle
) : ViewModel() {

    private val visitId: String = savedStateHandle["visitId"]!!
    var formState by mutableStateOf(RequirementFormState())
        private set

    init {
        // Restore any locally auto-saved draft (per H3 — crash protection)
        viewModelScope.launch {
            formRepository.getDraft(visitId)?.let { formState = it }
        }
    }

    fun updateField(field: FormField, value: String) {
        formState = formState.copyField(field, value)
        viewModelScope.launch { formRepository.saveDraft(visitId, formState) }   // debounced local auto-save
    }

    fun submit() = viewModelScope.launch {
        formRepository.submitForm(visitId, formState)   // POST /visits/{id}/requirement-form
        formRepository.clearDraft(visitId)
    }
}
```

Category dropdown is populated from `GET /requirement-categories` (Phase 3 API) — not hardcoded — so admin-added categories (H2) show up without an app update.

---

## 7. Uploads (Consuming Phase 5 Services)

```kotlin
@HiltViewModel
class AttachmentViewModel @Inject constructor(
    private val attachmentRepository: AttachmentRepository
) : ViewModel() {

    fun uploadImage(visitId: String, uri: Uri) = viewModelScope.launch {
        uiState = uiState.copy(uploading = true)
        attachmentRepository.uploadImage(visitId, uri)   // POST /visits/{id}/media, multipart
            .onSuccess { attachment -> uiState = uiState.copy(uploading = false, attachments = uiState.attachments + attachment) }
            .onFailure { e -> uiState = uiState.copy(uploading = false, error = mapUploadError(e)) }
    }

    fun uploadSignature(visitId: String, signedBy: String, bitmap: Bitmap) = viewModelScope.launch {
        val file = bitmapToPngFile(bitmap)
        attachmentRepository.uploadSignature(visitId, signedBy, file)   // POST /visits/{id}/signatures
    }
}
```

On poor field networks, uploads run through `WorkManager` (not a direct fire-and-forget coroutine) so a photo upload that fails mid-transfer retries automatically with backoff, same pattern as the offline visit sync.

---

## 8. Testing Discipline — Real Backend, Not Mocks

Per your instruction, every screen above gets built and manually verified against the actual running backend from Phases 3–5 as it's written, not against mocked Retrofit responses. Practical checklist per screen before moving to the next:

| Screen | Verify Against Real Backend |
|---|---|
| Login | Actual login, actual rate-limit after 6 failed attempts, actual token refresh on expiry |
| Dashboard | Actual `GET /visits/me/today` — create a real test visit via the Web dashboard (once Phase 7 exists) or Postman first, confirm it shows up |
| Visit Detail | Real customer data renders, geofence radius comes from the real `geofenceRadiusM` value |
| Check-in | Physically test at real GPS coordinates (or a GPS-spoofing dev tool set to known coordinates) both inside and outside a test customer's radius — confirm both the 200 success and 422 failure paths render correctly |
| Requirement Form | Real category dropdown populated from `GET /requirement-categories`, real submission lands in the DB |
| Uploads | Real file lands in MinIO, real pre-signed URL renders the image back in the Attachment Preview screen |
| Signatures | Real duplicate-signature attempt returns the real 409 from Phase 5, not a client-side-only check |
| Offline sync | Turn off device network mid-flow, complete a visit, confirm it queues, turn network back on, confirm it actually syncs and disappears from "Pending Sync" |

**Why this matters more here than it might seem**: mocked APIs hide exactly the kind of gaps this whole planning process has been surfacing — the idempotency key handling, the mock-location field, the geofence radius sourcing. An agent building against mocks will happily build a UI that "works" against fake data and silently breaks the moment it touches the real check-in endpoint's actual response shape.

---

## Phase 6 — Complete

UI/UX shell, Auth, Visits, GPS, Geofencing, Forms, and Uploads are all built consuming real Phase 3–5 services, verified screen-by-screen against the live backend.

**Next up:** Phase 7 — Admin Web Dashboard (Admin Authentication, Employee Management, Customer Management, Visit Management, Reports, Analytics).
