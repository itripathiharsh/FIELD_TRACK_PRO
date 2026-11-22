# Android premium UI (app 1.3.0, versionCode 6)

Branch `feature/android-premium-ui`. Android-only changes; no backend, API contract, RBAC, Tally or business-scope change.

## Screenshots (`screens/`)
Rendered on the JVM (Robolectric) with **demo data only**, at 360×640, 393×852 and 412×915 dp, plus the dashboard at
1.3× font scale on 360×640. Regenerate with:

    ./gradlew testDebugUnitTest -PcaptureScreens=true --tests "*Screenshot*"

| File prefix | Screen |
|---|---|
| 01_splash | Splash (continues the system launch window: one splash) |
| 02_login | Sign in (navy header, white sheet) |
| 03_dashboard_on_duty | Dashboard while on duty (+ `_font1.3`) |
| 04_dashboard_not_started | Dashboard before Start Day, empty beat |
| 05_dashboard_errors | GPS rejection, server unreachable, offline queue: actions stay available |
| 06_profile | Profile & settings |

## Design system
- Tokens in `ui/theme/Color.kt` (navy scale, gold-ink for gold text on light, navy-tinted neutrals, AA-contrast status colours), `Type.kt` (League Spartan for brand/numbers, device sans for body), `Theme.kt` (shapes, `SystemBarIcons`).
- Components in `ui/components/DesignSystem.kt`: `BrandMark`, `PrimaryButton`, `SignalButton`, `OutlineButton`, `DangerButton`, `SectionHeader`, `StatTile`, `ActionTile`, `InlineErrorCard`, `SkeletonBlock`, `StatusChip`, `ListGroup`.
- New mark (gold shield with a map-pin cut-out): `res/drawable/ic_brand_mark.xml`; adaptive launcher icon with a monochrome layer; notification icon `ic_stat_mark`.

## Bug fixes (with tests in `app/src/test/.../premiumui/`)
| Fix | Where | Test |
|---|---|---|
| Start/End Day request location permission (with disclosure) and open location settings when off | `DashboardScreen.kt` | manual (permission UI) |
| Workday errors and successes are shown | `DashboardScreen.kt`, `WorkdayViewModel.kt` | DashboardUiMapperTest |
| End/Start Day never sends 0,0, mock or too-vague fixes | `WorkdayLocationPolicy.kt`, `WorkdayRepository.kt` | WorkdayLocationPolicyTest, WorkdayRepositoryGpsGuardTest |
| Dashboard actions stay usable while visits load or fail | `DashboardScreen.kt` | DashboardUiMapperTest |
| Today's Beat isolated from the visits screen's tab/filter/search; tab switch during a load no longer dropped | `VisitsViewModel.kt` | DashboardIsolationTest |
| Double-tap back no longer pops two screens | `ui/navigation/BackNavigation.kt`, `NavGraph.kt` | BackNavigationGuardTest |
| Add Customer form survives rotation/process death; no duplicate submit | `AddCustomerScreen.kt`, `AddCustomerSubmitViewModel.kt` | AddCustomerSubmitViewModelTest |
| Indian currency grouping, paise kept | `utils/MoneyFormat.kt` (dashboard, collections, requirements) | MoneyFormatTest |
| Status-bar icons legible; single splash; login IME Next/Done | `MainActivity.kt`, `Theme.kt`, `themes.xml`, `LoginScreen.kt` | screenshots |
| Timeouts 10 s connect / 20 s read; no retry on read timeout or no network; no unused `/dashboard/summary` or duplicate `/workday/today` | `ApiClient.kt`, `TransientRetryInterceptor.kt` | RetryPolicyTest |
| Profile refreshed from existing `GET /auth/me` (never ends the session) | `AuthRepository.kt` | ProfileRefreshTest |
| Release `BASE_URL` = production by default, `RELEASE_BASE_URL` override, Render/local hosts refused | `app/build.gradle.kts` | ReleaseConfigGuardTest + Gradle dry run |

Employee performance dashboard: see `EMPLOYEE_PERFORMANCE_PROPOSAL.md` (proposal only).
