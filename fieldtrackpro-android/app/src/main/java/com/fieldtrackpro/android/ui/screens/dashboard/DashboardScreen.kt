package com.fieldtrackpro.android.ui.screens.dashboard

import android.Manifest
import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.AddBusiness
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.EventNote
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material.icons.filled.NearMe
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.services.LocationCaptureService
import com.fieldtrackpro.android.services.LocationPermissionDeniedException
import com.fieldtrackpro.android.ui.components.ActionTile
import com.fieldtrackpro.android.ui.components.BrandMark
import com.fieldtrackpro.android.ui.components.InlineErrorCard
import com.fieldtrackpro.android.ui.components.OfflineSyncBanner
import com.fieldtrackpro.android.ui.components.PermissionDisclosureKind
import com.fieldtrackpro.android.ui.components.PrimaryButton
import com.fieldtrackpro.android.ui.components.SectionHeader
import com.fieldtrackpro.android.ui.components.SignalButton
import com.fieldtrackpro.android.ui.components.SkeletonBlock
import com.fieldtrackpro.android.ui.components.StatTile
import com.fieldtrackpro.android.ui.components.StatusBadge
import com.fieldtrackpro.android.ui.components.StatusChip
import com.fieldtrackpro.android.ui.components.rememberPermissionDeniedHandler
import com.fieldtrackpro.android.ui.components.rememberWithDisclosure
import com.fieldtrackpro.android.ui.screens.visits.AdHocVisitDialog
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandGoldDark
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.GoldOnNavyText
import com.fieldtrackpro.android.ui.theme.LabelCaps
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.Navy100
import com.fieldtrackpro.android.ui.theme.Navy50
import com.fieldtrackpro.android.ui.theme.Navy950
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SuccessGreenText
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.SystemBarIcons
import com.fieldtrackpro.android.ui.theme.TextOnNavyMuted
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.theme.TextSubtle
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel
import com.fieldtrackpro.android.ui.viewmodel.WorkdayViewModel
import com.fieldtrackpro.android.utils.LocationSettingsHelper
import com.fieldtrackpro.android.utils.MoneyFormat
import com.fieldtrackpro.android.utils.WorkdayLocationPolicy
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

private enum class WorkdayAction { START, END }

/**
 * Employee dashboard (design v2).
 *
 * Fixes folded in here: Start/End Day go through the location permission + disclosure flow and a GPS validity policy
 * ([WorkdayLocationPolicy]: never 0,0, never mock, accuracy bounded); workday errors and successes are shown; the
 * quick actions stay usable while visits load or fail; Today's Beat no longer inherits the visits screen's filters;
 * the unused /dashboard/summary request and the duplicate /workday/today request are gone; money keeps paise and
 * uses Indian grouping.
 */
@Composable
fun DashboardScreen(
    visitsViewModel: VisitsViewModel,
    tokenManager: TokenManager,
    workdayViewModel: WorkdayViewModel = viewModel(),
    onNavigateToVisits: () -> Unit,
    onNavigateToVisitDetails: (String) -> Unit,
    onNavigateToProfile: () -> Unit,
    onNavigateToSync: () -> Unit,
    onNavigateToNotifications: () -> Unit,
    onNavigateToAddCustomer: () -> Unit = {},
    onNavigateToMonthlyPlanning: () -> Unit = {},
    onNavigateToPerformance: () -> Unit = {}
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val locationService = remember { LocationCaptureService(context) }

    val beatState by visitsViewModel.dashboardVisitsState.collectAsState()
    val pendingOfflineCount by visitsViewModel.pendingOfflineCount.collectAsState()
    val workdayUi by workdayViewModel.uiState.collectAsState()

    var isCapturing by remember { mutableStateOf(false) }
    var pendingAction by rememberSaveable { mutableStateOf<WorkdayAction?>(null) }
    var showAdHocDialog by rememberSaveable { mutableStateOf(false) }
    // End Day can only be confirmed with an ACCEPTED fix; there is no (0,0) fallback any more.
    var endDayFix by remember { mutableStateOf<WorkdayLocationPolicy.Decision.Accept?>(null) }
    var endDayNotes by rememberSaveable { mutableStateOf("") }

    fun refreshAll() {
        visitsViewModel.loadDashboardVisits()
        visitsViewModel.updateOfflineCount()
        workdayViewModel.loadTodayWorkday()
    }

    LaunchedEffect(Unit) { refreshAll() }

    LaunchedEffect(workdayUi.actionSuccessMessage) {
        workdayUi.actionSuccessMessage?.let {
            Toast.makeText(context, it, Toast.LENGTH_SHORT).show()
            workdayViewModel.clearMessages()
        }
    }

    fun captureAndRun(action: WorkdayAction) {
        if (isCapturing || workdayUi.isSubmitting) return
        scope.launch {
            isCapturing = true
            workdayViewModel.clearMessages()
            try {
                val loc = locationService.getCurrentLocation(15_000)
                when (val decision = WorkdayLocationPolicy.evaluate(loc.latitude, loc.longitude, loc.accuracy.toDouble(), loc.isMockLocation)) {
                    is WorkdayLocationPolicy.Decision.Reject -> workdayViewModel.showError(decision.message)
                    is WorkdayLocationPolicy.Decision.Accept -> when (action) {
                        WorkdayAction.START -> workdayViewModel.startDay(
                            latitude = decision.latitude,
                            longitude = decision.longitude,
                            accuracyM = decision.accuracyM,
                            notes = "Mobile check-in",
                            onSuccess = { refreshAll() }
                        )
                        WorkdayAction.END -> endDayFix = decision
                    }
                }
            } catch (e: LocationPermissionDeniedException) {
                workdayViewModel.showError("Location permission is needed to ${if (action == WorkdayAction.START) "start" else "end"} your day.")
            } catch (e: Exception) {
                workdayViewModel.showError(e.message ?: "Couldn't get your location. Try again.")
            } finally {
                isCapturing = false
            }
        }
    }

    val onLocationDenied = rememberPermissionDeniedHandler(PermissionDisclosureKind.LOCATION, Manifest.permission.ACCESS_FINE_LOCATION)
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        val action = pendingAction
        pendingAction = null
        val granted = grants[Manifest.permission.ACCESS_FINE_LOCATION] == true || grants[Manifest.permission.ACCESS_COARSE_LOCATION] == true
        if (granted && action != null) {
            captureAndRun(action)
        } else if (!granted) {
            workdayViewModel.showError("Location permission is needed to start or end your day. Allow it and try again.")
            onLocationDenied()
        }
    }
    val requestLocationPermission = rememberWithDisclosure(PermissionDisclosureKind.LOCATION) {
        permissionLauncher.launch(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION))
    }

    fun beginWorkdayAction(action: WorkdayAction) {
        when {
            !locationService.isLocationEnabled() -> {
                workdayViewModel.showError("Location is turned off. Turn it on, then try again.")
                LocationSettingsHelper.openLocationSettings(context)
            }
            !locationService.hasLocationPermission() -> {
                pendingAction = action
                requestLocationPermission()
            }
            else -> captureAndRun(action)
        }
    }

    val ui = DashboardUiMapper.build(
        greeting = DashboardUiMapper.greetingFor(Calendar.getInstance().get(Calendar.HOUR_OF_DAY)),
        userName = tokenManager.getUserName() ?: "Field representative",
        dateLabel = SimpleDateFormat("EEE, d MMM", Locale.getDefault()).format(Date()),
        workday = workdayUi.workday,
        workdayLoadedOnce = workdayUi.loadedOnce,
        isWorkdayLoading = workdayUi.isLoading,
        isCapturingLocation = isCapturing,
        isSubmitting = workdayUi.isSubmitting,
        workdayError = workdayUi.errorMessage,
        visitsState = beatState,
        pendingOffline = pendingOfflineCount
    )

    DashboardContent(
        ui = ui,
        onRefresh = { refreshAll() },
        onStartDay = { beginWorkdayAction(WorkdayAction.START) },
        onEndDay = { beginWorkdayAction(WorkdayAction.END) },
        onDismissError = { workdayViewModel.clearMessages() },
        onOpenProfile = onNavigateToProfile,
        onOpenVisits = onNavigateToVisits,
        onOpenVisit = onNavigateToVisitDetails,
        onOffBeat = { showAdHocDialog = true },
        onAddCustomer = onNavigateToAddCustomer,
        onMonthlyPlan = onNavigateToMonthlyPlanning,
        onSync = onNavigateToSync,
        onPerformance = onNavigateToPerformance
    )

    endDayFix?.let { fix ->
        EndDayDialog(
            ui = ui,
            accuracyM = fix.accuracyM,
            notes = endDayNotes,
            onNotesChange = { endDayNotes = it.take(500) },
            isSubmitting = workdayUi.isSubmitting,
            error = workdayUi.errorMessage,
            onConfirm = {
                workdayViewModel.endDay(
                    latitude = fix.latitude,
                    longitude = fix.longitude,
                    accuracyM = fix.accuracyM,
                    notes = endDayNotes.ifBlank { "Completed shift" },
                    onSuccess = {
                        endDayFix = null
                        endDayNotes = ""
                        refreshAll()
                    }
                )
            },
            onDismiss = { if (!workdayUi.isSubmitting) endDayFix = null }
        )
    }

    if (showAdHocDialog) {
        AdHocVisitDialog(
            viewModel = visitsViewModel,
            onDismiss = { showAdHocDialog = false },
            onVisitCreated = { visit ->
                showAdHocDialog = false
                refreshAll()
                onNavigateToVisitDetails(visit.id)
            },
            onError = { err -> Toast.makeText(context, err, Toast.LENGTH_LONG).show() }
        )
    }
}

/** Stateless dashboard. Everything stays reachable whatever the loading/error state of the visit list. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardContent(
    ui: DashboardUi,
    onRefresh: () -> Unit,
    onStartDay: () -> Unit,
    onEndDay: () -> Unit,
    onDismissError: () -> Unit,
    onOpenProfile: () -> Unit,
    onOpenVisits: () -> Unit,
    onOpenVisit: (String) -> Unit,
    onOffBeat: () -> Unit,
    onAddCustomer: () -> Unit,
    onMonthlyPlan: () -> Unit,
    onSync: () -> Unit,
    onPerformance: () -> Unit = {}
) {
    SystemBarIcons(darkIcons = false)
    Column(Modifier.fillMaxSize().background(SurfaceSecondary)) {
        // Fixed navy app bar: the status bar always sits on navy, so light icons are always legible.
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(BrandNavy)
                .statusBarsPadding()
                .padding(start = 16.dp, end = 4.dp, top = 6.dp, bottom = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            BrandMark(height = 26.dp)
            Spacer(Modifier.width(10.dp))
            Text("FieldTrack Pro", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 19.sp, color = BrandWhite, modifier = Modifier.weight(1f))
            IconButton(onClick = onRefresh) { Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = BrandWhite) }
            IconButton(onClick = onOpenProfile) { Icon(Icons.Default.Person, contentDescription = "Profile and settings", tint = BrandWhite) }
        }

        PullToRefreshBox(
            isRefreshing = ui.isWorkdayLoading && ui.beat is BeatUi.Loading,
            onRefresh = onRefresh,
            modifier = Modifier.fillMaxSize()
        ) {
            Column(
                Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .navigationBarsPadding()
                    .padding(bottom = 24.dp)
            ) {
                WorkdayHero(ui, onStartDay, onEndDay)

                // KPI grid floats over the hero's lower edge.
                Column(
                    Modifier.padding(horizontal = 16.dp).offset(y = (-34).dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        StatTile("Visits done", "${ui.visitsDone} / ${ui.visitsTotal}", Modifier.weight(1f))
                        StatTile("Ad-hoc visits", ui.adhocVisits.toString(), Modifier.weight(1f))
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        StatTile("Collected", MoneyFormat.inr(ui.collectedToday), Modifier.weight(1f), valueColor = SuccessGreenText)
                        StatTile(
                            "Not verified",
                            MoneyFormat.inr(ui.notVerified),
                            Modifier.weight(1f),
                            valueColor = if (ui.notVerified > 0) BrandGoldDark else BrandNavy
                        )
                    }
                }

                Column(
                    Modifier.padding(horizontal = 16.dp).offset(y = (-18).dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp)
                ) {
                    if (ui.workdayError != null) {
                        InlineErrorCard(message = ui.workdayError, onRetry = onDismissError, actionLabel = "Dismiss")
                    }
                    OfflineSyncBanner(pendingCount = ui.pendingOffline, onSyncClick = onSync)

                    Surface(shape = RoundedCornerShape(16.dp), color = BrandWhite, modifier = Modifier.fillMaxWidth().border(1.dp, BrandLightGray, RoundedCornerShape(16.dp))) {
                        Row(Modifier.padding(horizontal = 6.dp, vertical = 8.dp)) {
                            ActionTile("Today's beat", Icons.Default.EventNote, onOpenVisits, Modifier.weight(1f), emphasized = true)
                            ActionTile("Off-beat visit", Icons.Default.NearMe, onOffBeat, Modifier.weight(1f))
                            ActionTile("Add customer", Icons.Default.AddBusiness, onAddCustomer, Modifier.weight(1f))
                            ActionTile("Monthly plan", Icons.Default.CalendarMonth, onMonthlyPlan, Modifier.weight(1f))
                        }
                    }

                    PerformanceEntry(onPerformance)

                    BeatSection(ui.beat, onOpenVisits, onOpenVisit, onOffBeat, onRefresh)

                    CollectionCard(ui, onCollect = onOpenVisits)
                }
            }
        }
    }
}

@Composable
private fun PerformanceEntry(onClick: () -> Unit) {
    Surface(shape = RoundedCornerShape(16.dp), color = BrandWhite, modifier = Modifier.fillMaxWidth().border(1.dp, BrandLightGray, RoundedCornerShape(16.dp))) {
        Row(
            Modifier.fillMaxWidth().clickable(onClick = onClick).heightIn(min = 64.dp).padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).background(Navy100), contentAlignment = Alignment.Center) {
                Icon(Icons.Default.Insights, contentDescription = null, tint = BrandNavy)
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text("My performance", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = BrandNavy)
                Text("Collections, outlet outstanding and visit progress", fontSize = 13.sp, color = TextSecondary)
            }
            Icon(Icons.Default.ChevronRight, contentDescription = null, tint = TextSubtle)
        }
    }
}

@Composable
private fun WorkdayHero(ui: DashboardUi, onStartDay: () -> Unit, onEndDay: () -> Unit) {
    val busy = ui.isCapturingLocation || ui.isSubmitting
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(bottomStart = 28.dp, bottomEnd = 28.dp))
            .background(androidx.compose.ui.graphics.Brush.verticalGradient(listOf(BrandNavy, Navy950)))
            .padding(start = 20.dp, end = 20.dp, top = 14.dp, bottom = 54.dp)
    ) {
        Text(ui.greeting, fontSize = 15.sp, color = TextOnNavyMuted)
        Text(ui.userName, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 28.sp, color = BrandWhite, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Spacer(Modifier.height(10.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            val (chipText, dot) = when (ui.workdayStatus) {
                WorkdayStatus.STARTED -> "On duty" to Color(0xFF34D399)
                WorkdayStatus.COMPLETED -> "Day completed" to Color(0xFF34D399)
                WorkdayStatus.NOT_STARTED -> "Not started" to BrandGold
                WorkdayStatus.UNKNOWN -> "Status unavailable" to TextOnNavyMuted
            }
            StatusChip(chipText, container = BrandWhite.copy(alpha = 0.10f), content = BrandWhite, dot = dot)
            Spacer(Modifier.width(8.dp))
            StatusChip(ui.dateLabel, container = BrandGold.copy(alpha = 0.16f), content = GoldOnNavyText)
        }
        ui.workdayDetail?.let {
            Spacer(Modifier.height(10.dp))
            Text(it, fontSize = 14.sp, color = TextOnNavyMuted)
        }
        Spacer(Modifier.height(16.dp))
        when (ui.workdayStatus) {
            WorkdayStatus.NOT_STARTED, WorkdayStatus.UNKNOWN -> SignalButton(
                text = if (ui.isCapturingLocation) "Getting GPS…" else "Start day",
                onClick = onStartDay,
                loading = busy,
                icon = Icons.Default.PlayArrow,
                modifier = Modifier.fillMaxWidth()
            )
            WorkdayStatus.STARTED -> OutlinedButton(
                onClick = onEndDay,
                enabled = !busy,
                shape = RoundedCornerShape(12.dp),
                border = BorderStroke(1.5.dp, BrandWhite.copy(alpha = 0.7f)),
                modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)
            ) {
                if (busy) {
                    CircularProgressIndicator(color = BrandWhite, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
                } else {
                    Icon(Icons.Default.Stop, contentDescription = null, tint = BrandWhite, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(8.dp))
                    Text("End day", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 15.sp, color = BrandWhite)
                }
            }
            WorkdayStatus.COMPLETED -> Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.CheckCircle, contentDescription = null, tint = Color(0xFF34D399), modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(8.dp))
                Text("Workday completed. See you tomorrow.", fontSize = 14.sp, color = BrandWhite)
            }
        }
    }
}

@Composable
private fun BeatSection(beat: BeatUi, onOpenVisits: () -> Unit, onOpenVisit: (String) -> Unit, onOffBeat: () -> Unit, onRetry: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        val count = (beat as? BeatUi.Loaded)?.plannedTotal
        SectionHeader(
            title = if (count != null) "Today's beat · $count" else "Today's beat",
            actionLabel = "View all",
            onAction = onOpenVisits
        )
        when (beat) {
            is BeatUi.Loading -> repeat(3) { SkeletonBlock(height = 64.dp) }
            is BeatUi.Error -> InlineErrorCard(message = beat.message, onRetry = onRetry)
            is BeatUi.Loaded -> if (beat.planned.isEmpty()) {
                Surface(shape = RoundedCornerShape(16.dp), color = BrandWhite, modifier = Modifier.fillMaxWidth().border(1.dp, BrandLightGray, RoundedCornerShape(16.dp))) {
                    Column(Modifier.padding(18.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Box(Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(Navy100), contentAlignment = Alignment.Center) {
                            Icon(Icons.Default.EventNote, contentDescription = null, tint = BrandNavy)
                        }
                        Spacer(Modifier.height(10.dp))
                        Text("No beat visits today", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = BrandNavy)
                        Text("Visiting a customer anyway? Start an off-beat visit.", fontSize = 14.sp, color = TextSecondary)
                        TextButton(onClick = onOffBeat) {
                            Text("Start an off-beat visit", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = BrandNavy)
                            Spacer(Modifier.width(4.dp))
                            Icon(Icons.AutoMirrored.Filled.ArrowForward, contentDescription = null, tint = BrandNavy, modifier = Modifier.size(16.dp))
                        }
                    }
                }
            } else {
                Surface(shape = RoundedCornerShape(16.dp), color = BrandWhite, modifier = Modifier.fillMaxWidth().border(1.dp, BrandLightGray, RoundedCornerShape(16.dp))) {
                    Column {
                        beat.planned.forEachIndexed { i, item ->
                            if (i > 0) HorizontalDivider(color = BrandLightGray, modifier = Modifier.padding(horizontal = 14.dp))
                            Row(
                                Modifier
                                    .fillMaxWidth()
                                    .clickable { onOpenVisit(item.id) }
                                    .heightIn(min = 60.dp)
                                    .padding(horizontal = 14.dp, vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(Modifier.weight(1f)) {
                                    Text(item.name, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = BrandNavy, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    Text(item.timeLabel, fontSize = 13.sp, color = TextSubtle)
                                }
                                StatusBadge(status = item.status)
                                Icon(Icons.Default.ChevronRight, contentDescription = null, tint = TextSubtle, modifier = Modifier.size(20.dp))
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CollectionCard(ui: DashboardUi, onCollect: () -> Unit) {
    Surface(shape = RoundedCornerShape(16.dp), color = BrandWhite, modifier = Modifier.fillMaxWidth().border(1.dp, BrandLightGray, RoundedCornerShape(16.dp))) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("TODAY'S COLLECTIONS", style = LabelCaps, color = TextSecondary, modifier = Modifier.weight(1f))
                Text(MoneyFormat.inr(ui.collectedToday), fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 20.sp, color = SuccessGreenText)
            }
            Spacer(Modifier.height(12.dp))
            // Verified share of today's total.
            val share = if (ui.collectedToday > 0) (ui.verified / ui.collectedToday).toFloat().coerceIn(0f, 1f) else 0f
            Box(Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)).background(Navy50)) {
                Box(Modifier.fillMaxWidth(share).height(8.dp).clip(RoundedCornerShape(4.dp)).background(SuccessGreen))
            }
            Spacer(Modifier.height(10.dp))
            Row {
                Column(Modifier.weight(1f)) {
                    Text("Verified", fontSize = 13.sp, color = TextSubtle)
                    Text(MoneyFormat.inr(ui.verified), fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = BrandNavy)
                }
                Column(Modifier.weight(1f)) {
                    Text("Not verified yet", fontSize = 13.sp, color = TextSubtle)
                    Text(MoneyFormat.inr(ui.notVerified), fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = if (ui.notVerified > 0) BrandGoldDark else BrandNavy)
                }
            }
            Spacer(Modifier.height(12.dp))
            PrimaryButton(text = "Collect payment", onClick = onCollect, modifier = Modifier.fillMaxWidth())
            Text(
                "Pick the customer's visit to record a payment.",
                fontSize = 12.sp,
                color = TextSubtle,
                modifier = Modifier.padding(top = 6.dp).align(Alignment.CenterHorizontally)
            )
        }
    }
}

@Composable
private fun EndDayDialog(
    ui: DashboardUi,
    accuracyM: Double,
    notes: String,
    onNotesChange: (String) -> Unit,
    isSubmitting: Boolean,
    error: String?,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = BrandWhite,
        shape = RoundedCornerShape(20.dp),
        title = { Text("End your workday?", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 20.sp, color = BrandNavy) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                SummaryRow("Started", ui.workdayDetail?.removePrefix("Clocked in at ") ?: "—")
                SummaryRow("Visits done", "${ui.visitsDone} / ${ui.visitsTotal}")
                SummaryRow("Ad-hoc visits", ui.adhocVisits.toString())
                SummaryRow("Collected", MoneyFormat.inr(ui.collectedToday))
                SummaryRow("GPS", "Captured (±${accuracyM.toInt()} m)")
                OutlinedTextField(
                    value = notes,
                    onValueChange = onNotesChange,
                    label = { Text("Notes (optional)") },
                    maxLines = 3,
                    enabled = !isSubmitting,
                    shape = RoundedCornerShape(12.dp),
                    colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = BrandGold, unfocusedBorderColor = BrandLightGray, focusedLabelColor = BrandNavy),
                    modifier = Modifier.fillMaxWidth()
                )
                if (error != null) Text(error, fontSize = 13.sp, color = com.fieldtrackpro.android.ui.theme.ErrorRed)
            }
        },
        confirmButton = {
            PrimaryButton(text = "End day", onClick = onConfirm, loading = isSubmitting)
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !isSubmitting) {
                Text("Cancel", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = BrandNavy)
            }
        }
    )
}

@Composable
private fun SummaryRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth()) {
        Text(label, fontSize = 14.sp, color = TextSubtle, modifier = Modifier.weight(1f))
        Text(value, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, color = BrandNavy)
    }
}
