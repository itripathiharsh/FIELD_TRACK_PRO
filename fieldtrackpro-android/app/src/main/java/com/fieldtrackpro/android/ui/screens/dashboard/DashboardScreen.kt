package com.fieldtrackpro.android.ui.screens.dashboard

import android.widget.Toast
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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountBalanceWallet
import androidx.compose.material.icons.filled.AddBusiness
import androidx.compose.material.icons.filled.CalendarToday
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.NearMe
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Divider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.services.LocationCaptureService
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.LoadingScreen
import com.fieldtrackpro.android.ui.components.OfflineSyncBanner
import com.fieldtrackpro.android.ui.components.StatusBadge
import com.fieldtrackpro.android.ui.screens.visits.AdHocVisitDialog
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandGoldDark
import com.fieldtrackpro.android.ui.theme.BrandGoldLight
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.theme.TextSubtle
import com.fieldtrackpro.android.ui.viewmodel.DashboardState
import com.fieldtrackpro.android.ui.viewmodel.VisitsState
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel
import com.fieldtrackpro.android.ui.viewmodel.WorkdayViewModel
import com.fieldtrackpro.android.utils.DateTimeUtils
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

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
    onNavigateToAddCustomer: () -> Unit = {}
) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()
    val locationService = remember { LocationCaptureService(context) }

    val visitsState by visitsViewModel.visitsState.collectAsState()
    val dashboardState by visitsViewModel.dashboardState.collectAsState()
    val pendingOfflineCount by visitsViewModel.pendingOfflineCount.collectAsState()
    val workdayUiState by workdayViewModel.uiState.collectAsState()

    var isCapturingLocation by remember { mutableStateOf(false) }
    var showEndDayConfirmDialog by remember { mutableStateOf(false) }
    var showAdHocVisitDialog by remember { mutableStateOf(false) }
    var endDayLocationFix by remember { mutableStateOf<Pair<Double, Double>?>(null) }
    var endDayAccuracy by remember { mutableStateOf<Double?>(null) }
    var endDayNotes by remember { mutableStateOf("") }

    val greeting = remember {
        val hour = Calendar.getInstance().get(Calendar.HOUR_OF_DAY)
        when {
            hour < 12 -> "Good Morning"
            hour < 17 -> "Good Afternoon"
            else -> "Good Evening"
        }
    }
    val currentDateStr = remember {
        SimpleDateFormat("EEEE, dd MMM", Locale.getDefault()).format(Date())
    }

    fun refreshAll() {
        visitsViewModel.loadVisits(refresh = true)
        visitsViewModel.loadDashboardSummary()
        workdayViewModel.loadTodayWorkday()
    }

    LaunchedEffect(Unit) {
        refreshAll()
    }

    val workday = workdayUiState.workday?.session
    val workdaySummary = workdayUiState.workday?.summary

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "FieldTrack Pro",
                actions = {
                    IconButton(onClick = { refreshAll() }) {
                        Icon(
                            imageVector = Icons.Default.Refresh,
                            contentDescription = "Refresh",
                            tint = BrandNavy
                        )
                    }
                    IconButton(onClick = onNavigateToProfile) {
                        Icon(
                            imageVector = Icons.Default.Person,
                            contentDescription = "Profile",
                            tint = BrandNavy
                        )
                    }
                }
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(SurfaceSecondary)
                .padding(innerPadding)
                .padding(horizontal = 16.dp, vertical = 12.dp)
                .verticalScroll(rememberScrollState())
        ) {
            // ----------------------------------------------------
            // 1. HEADER CARD: Greeting, Date & Workday Status
            // ----------------------------------------------------
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, BrandLightGray, RoundedCornerShape(16.dp)),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = BrandWhite),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    // Greeting & Date Row
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.Top
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = "$greeting,",
                                fontFamily = LibreBaskervilleFamily,
                                fontSize = 14.sp,
                                color = TextSecondary
                            )
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = tokenManager.getUserName() ?: "Field Representative",
                                fontFamily = LeagueSpartanFamily,
                                fontSize = 22.sp,
                                fontWeight = FontWeight.Bold,
                                color = BrandNavy
                            )
                        }

                        // Formatted Date Badge
                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(8.dp))
                                .background(SurfaceSecondary)
                                .border(1.dp, BrandLightGray, RoundedCornerShape(8.dp))
                                .padding(horizontal = 10.dp, vertical = 6.dp)
                        ) {
                            Text(
                                text = currentDateStr,
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                fontSize = 12.sp,
                                color = BrandNavy
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    // Workday Status & Action Section
                    when (workday?.status) {
                        "STARTED" -> {
                            // Active Shift
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(12.dp))
                                    .background(SuccessGreen.copy(alpha = 0.08f))
                                    .border(1.dp, SuccessGreen.copy(alpha = 0.3f), RoundedCornerShape(12.dp))
                                    .padding(12.dp),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Box(
                                        modifier = Modifier
                                            .size(10.dp)
                                            .clip(CircleShape)
                                            .background(SuccessGreen)
                                    )
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Column {
                                        Text(
                                            text = "Workday Started",
                                            fontFamily = LeagueSpartanFamily,
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 14.sp,
                                            color = BrandNavy
                                        )
                                        Text(
                                            text = "Clocked in at ${DateTimeUtils.formatDisplayTime(workday.startTime)}",
                                            fontFamily = LeagueSpartanFamily,
                                            fontSize = 12.sp,
                                            color = TextSecondary
                                        )
                                    }
                                }

                                Button(
                                    onClick = {
                                        workdayViewModel.loadTodayWorkday()
                                        coroutineScope.launch {
                                            isCapturingLocation = true
                                            try {
                                                val loc = locationService.getCurrentLocation(8000)
                                                endDayLocationFix = Pair(loc.latitude, loc.longitude)
                                                endDayAccuracy = loc.accuracy.toDouble()
                                                showEndDayConfirmDialog = true
                                            } catch (e: Exception) {
                                                Toast.makeText(context, e.message ?: "Location error", Toast.LENGTH_SHORT).show()
                                                endDayLocationFix = Pair(0.0, 0.0)
                                                showEndDayConfirmDialog = true
                                            } finally {
                                                isCapturingLocation = false
                                            }
                                        }
                                    },
                                    shape = RoundedCornerShape(8.dp),
                                    colors = ButtonDefaults.buttonColors(containerColor = ErrorRed),
                                    enabled = !isCapturingLocation && !workdayUiState.isSubmitting
                                ) {
                                    if (isCapturingLocation) {
                                        CircularProgressIndicator(
                                            modifier = Modifier.size(14.dp),
                                            color = BrandWhite,
                                            strokeWidth = 2.dp
                                        )
                                    } else {
                                        Icon(
                                            imageVector = Icons.Default.Stop,
                                            contentDescription = null,
                                            tint = BrandWhite,
                                            modifier = Modifier.size(14.dp)
                                        )
                                        Spacer(modifier = Modifier.width(4.dp))
                                        Text(
                                            text = "END DAY",
                                            fontFamily = LeagueSpartanFamily,
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 12.sp,
                                            letterSpacing = 0.6.sp,
                                            color = BrandWhite
                                        )
                                    }
                                }
                            }
                        }

                        "COMPLETED" -> {
                            // Completed Shift
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(12.dp))
                                    .background(BrandNavy.copy(alpha = 0.06f))
                                    .border(1.dp, BrandNavy.copy(alpha = 0.2f), RoundedCornerShape(12.dp))
                                    .padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(
                                    imageVector = Icons.Default.CheckCircle,
                                    contentDescription = null,
                                    tint = SuccessGreen,
                                    modifier = Modifier.size(18.dp)
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Column {
                                    Text(
                                        text = "Workday Completed",
                                        fontFamily = LeagueSpartanFamily,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 14.sp,
                                        color = BrandNavy
                                    )
                                    Text(
                                        text = "${DateTimeUtils.formatDisplayTime(workday.startTime)} — ${DateTimeUtils.formatDisplayTime(workday.endTime)}",
                                        fontFamily = LeagueSpartanFamily,
                                        fontSize = 12.sp,
                                        color = TextSecondary
                                    )
                                }
                            }
                        }

                        else -> {
                            // Not Started Shift
                            Column(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(12.dp))
                                    .background(BrandGold.copy(alpha = 0.1f))
                                    .border(1.dp, BrandGold.copy(alpha = 0.4f), RoundedCornerShape(12.dp))
                                    .padding(14.dp)
                            ) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column {
                                        Text(
                                            text = "Workday not started",
                                            fontFamily = LeagueSpartanFamily,
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 14.sp,
                                            color = BrandNavy
                                        )
                                        Text(
                                            text = "Clock in with GPS to begin visits",
                                            fontFamily = LeagueSpartanFamily,
                                            fontSize = 12.sp,
                                            color = TextSecondary
                                        )
                                    }

                                    Button(
                                        onClick = {
                                            coroutineScope.launch {
                                                isCapturingLocation = true
                                                try {
                                                    val loc = locationService.getCurrentLocation(8000)
                                                    workdayViewModel.startDay(
                                                        latitude = loc.latitude,
                                                        longitude = loc.longitude,
                                                        accuracyM = loc.accuracy.toDouble(),
                                                        notes = "Mobile check-in",
                                                        onSuccess = { refreshAll() }
                                                    )
                                                } catch (e: Exception) {
                                                    Toast.makeText(context, e.message ?: "Failed to capture GPS", Toast.LENGTH_SHORT).show()
                                                } finally {
                                                    isCapturingLocation = false
                                                }
                                            }
                                        },
                                        shape = RoundedCornerShape(8.dp),
                                        colors = ButtonDefaults.buttonColors(containerColor = SuccessGreen),
                                        enabled = !isCapturingLocation && !workdayUiState.isSubmitting
                                    ) {
                                        if (isCapturingLocation || workdayUiState.isSubmitting) {
                                            CircularProgressIndicator(
                                                modifier = Modifier.size(14.dp),
                                                color = BrandWhite,
                                                strokeWidth = 2.dp
                                            )
                                        } else {
                                            Icon(
                                                imageVector = Icons.Default.PlayArrow,
                                                contentDescription = null,
                                                tint = BrandWhite,
                                                modifier = Modifier.size(16.dp)
                                            )
                                            Spacer(modifier = Modifier.width(4.dp))
                                            Text(
                                                text = "START DAY",
                                                fontFamily = LeagueSpartanFamily,
                                                fontWeight = FontWeight.Bold,
                                                fontSize = 12.sp,
                                                letterSpacing = 0.8.sp,
                                                color = BrandWhite
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(14.dp))

            // Offline Sync Banner
            OfflineSyncBanner(
                pendingCount = pendingOfflineCount,
                onSyncClick = onNavigateToSync
            )

            Spacer(modifier = Modifier.height(14.dp))

            when (val state = visitsState) {
                is VisitsState.Loading -> LoadingScreen(message = "Loading daily beat and performance...")
                is VisitsState.Error -> {
                    Text(
                        text = "Notice: ${state.message}",
                        fontFamily = LeagueSpartanFamily,
                        color = ErrorRed,
                        fontSize = 13.sp
                    )
                }
                is VisitsState.Success -> {
                    val allVisits = state.visits
                    val plannedVisits = allVisits.filter { !it.isAdHoc }
                    val adhocVisits = allVisits.filter { it.isAdHoc }

                    val totalVisitsCount = workdaySummary?.totalVisits ?: allVisits.size
                    val plannedCount = workdaySummary?.plannedVisits ?: plannedVisits.size
                    val adhocCount = workdaySummary?.adhocVisits ?: adhocVisits.size
                    val totalCollection = workdaySummary?.collectionsTotalAmount ?: 0.0

                    // ----------------------------------------------------
                    // 2. TODAY'S PERFORMANCE (4 KPI Cards)
                    // ----------------------------------------------------
                    Text(
                        text = "TODAY'S PERFORMANCE",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 1.sp,
                        color = BrandNavy
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        MetricCard(
                            title = "TODAY'S VISITS",
                            value = totalVisitsCount.toString(),
                            accentColor = BrandNavy,
                            modifier = Modifier.weight(1f)
                        )
                        MetricCard(
                            title = "PLANNED",
                            value = plannedCount.toString(),
                            accentColor = BrandGoldDark,
                            modifier = Modifier.weight(1f)
                        )
                        MetricCard(
                            title = "AD-HOC",
                            value = adhocCount.toString(),
                            accentColor = if (adhocCount > 0) SuccessGreen else TextSecondary,
                            modifier = Modifier.weight(1f)
                        )
                        MetricCard(
                            title = "COLLECTION",
                            value = "₹${totalCollection.toInt()}",
                            accentColor = SuccessGreen,
                            modifier = Modifier.weight(1.2f)
                        )
                    }

                    Spacer(modifier = Modifier.height(18.dp))

                    // ----------------------------------------------------
                    // 3. QUICK ACTIONS GRID (4 Action Buttons)
                    // ----------------------------------------------------
                    Text(
                        text = "QUICK ACTIONS",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 1.sp,
                        color = BrandNavy
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        QuickActionButton(
                            title = "Today's Beat",
                            icon = Icons.Default.CalendarToday,
                            onClick = onNavigateToVisits,
                            modifier = Modifier.weight(1f)
                        )
                        QuickActionButton(
                            title = "Off-Beat Visit",
                            icon = Icons.Default.NearMe,
                            onClick = { showAdHocVisitDialog = true },
                            modifier = Modifier.weight(1f)
                        )
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        QuickActionButton(
                            title = "+ Add Customer",
                            icon = Icons.Default.AddBusiness,
                            onClick = onNavigateToAddCustomer,
                            modifier = Modifier.weight(1f)
                        )
                        QuickActionButton(
                            title = "Collect Payment",
                            icon = Icons.Default.AccountBalanceWallet,
                            onClick = onNavigateToVisits,
                            modifier = Modifier.weight(1f)
                        )
                    }

                    Spacer(modifier = Modifier.height(18.dp))

                    // ----------------------------------------------------
                    // 4. TODAY'S BEAT (Planned Customer Visits Preview)
                    // ----------------------------------------------------
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "TODAY'S BEAT (${plannedVisits.size} CUSTOMERS)",
                            fontFamily = LeagueSpartanFamily,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 1.sp,
                            color = BrandNavy
                        )
                        Text(
                            text = "View All Visits →",
                            fontFamily = LeagueSpartanFamily,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            color = BrandGoldDark,
                            modifier = Modifier.clickable { onNavigateToVisits() }
                        )
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    if (plannedVisits.isEmpty()) {
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
                            shape = RoundedCornerShape(12.dp),
                            colors = CardDefaults.cardColors(containerColor = BrandWhite)
                        ) {
                            Column(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(18.dp),
                                horizontalAlignment = Alignment.CenterHorizontally
                            ) {
                                Text(
                                    text = "No planned beat visits for today.",
                                    fontFamily = LeagueSpartanFamily,
                                    fontSize = 13.sp,
                                    color = TextSecondary
                                )
                                Spacer(modifier = Modifier.height(6.dp))
                                Text(
                                    text = "Use [Off-Beat Visit] to start an ad-hoc visit.",
                                    fontFamily = LeagueSpartanFamily,
                                    fontSize = 12.sp,
                                    color = BrandGoldDark,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.clickable { showAdHocVisitDialog = true }
                                )
                            }
                        }
                    } else {
                        plannedVisits.take(5).forEach { visit ->
                            Card(
                                onClick = { onNavigateToVisitDetails(visit.id) },
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 3.dp)
                                    .border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
                                shape = RoundedCornerShape(12.dp),
                                colors = CardDefaults.cardColors(containerColor = BrandWhite),
                                elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                            ) {
                                Row(
                                    modifier = Modifier
                                        .padding(12.dp)
                                        .fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(
                                            text = visit.customerName ?: "Customer #${visit.customerId.take(8)}",
                                            fontFamily = LeagueSpartanFamily,
                                            fontSize = 14.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = BrandNavy
                                        )
                                        Spacer(modifier = Modifier.height(2.dp))
                                        Text(
                                            text = "Scheduled: ${DateTimeUtils.formatDisplayDateTime(visit.scheduledAt)}",
                                            fontFamily = LibreBaskervilleFamily,
                                            fontSize = 12.sp,
                                            color = TextSecondary
                                        )
                                    }

                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        StatusBadge(status = visit.status)
                                        Spacer(modifier = Modifier.width(6.dp))
                                        Icon(
                                            imageVector = Icons.Default.ChevronRight,
                                            contentDescription = null,
                                            tint = TextSecondary,
                                            modifier = Modifier.size(16.dp)
                                        )
                                    }
                                }
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(18.dp))

                    // ----------------------------------------------------
                    // 5. COLLECTION SUMMARY CARD
                    // ----------------------------------------------------
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .border(1.dp, BrandLightGray, RoundedCornerShape(14.dp)),
                        shape = RoundedCornerShape(14.dp),
                        colors = CardDefaults.cardColors(containerColor = BrandWhite),
                        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(
                                        imageVector = Icons.Default.AccountBalanceWallet,
                                        contentDescription = null,
                                        tint = SuccessGreen,
                                        modifier = Modifier.size(18.dp)
                                    )
                                    Spacer(modifier = Modifier.width(6.dp))
                                    Text(
                                        text = "Today's Collection Summary",
                                        fontFamily = LeagueSpartanFamily,
                                        fontSize = 14.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = BrandNavy
                                    )
                                }
                                Text(
                                    text = "₹${totalCollection.toInt()}",
                                    fontFamily = LeagueSpartanFamily,
                                    fontSize = 16.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = SuccessGreen
                                )
                            }

                            Spacer(modifier = Modifier.height(10.dp))

                            val verifiedAmt = workdaySummary?.collectionsVerifiedAmount ?: 0.0
                            val pendingAmt = (workdaySummary?.collectionsTotalAmount ?: 0.0) - verifiedAmt

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                Box(
                                    modifier = Modifier
                                        .weight(1f)
                                        .clip(RoundedCornerShape(8.dp))
                                        .background(SurfaceSecondary)
                                        .padding(10.dp)
                                ) {
                                    Column {
                                        Text(
                                            text = "PENDING VERIFICATION",
                                            fontFamily = LeagueSpartanFamily,
                                            fontSize = 9.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = TextSecondary
                                        )
                                        Text(
                                            text = "₹${pendingAmt.toInt()}",
                                            fontFamily = LeagueSpartanFamily,
                                            fontSize = 14.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = if (pendingAmt > 0) BrandGoldDark else TextSecondary
                                        )
                                    }
                                }

                                Box(
                                    modifier = Modifier
                                        .weight(1f)
                                        .clip(RoundedCornerShape(8.dp))
                                        .background(SurfaceSecondary)
                                        .padding(10.dp)
                                ) {
                                    Column {
                                        Text(
                                            text = "VERIFIED",
                                            fontFamily = LeagueSpartanFamily,
                                            fontSize = 9.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = TextSecondary
                                        )
                                        Text(
                                            text = "₹${verifiedAmt.toInt()}",
                                            fontFamily = LeagueSpartanFamily,
                                            fontSize = 14.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = SuccessGreen
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ----------------------------------------------------
    // END DAY CONFIRMATION DIALOG
    // ----------------------------------------------------
    if (showEndDayConfirmDialog) {
        val currentVisits = (visitsState as? VisitsState.Success)?.visits ?: emptyList()
        val localCompleted = currentVisits.count { it.status.equals("COMPLETED", ignoreCase = true) }
        val localAdhoc = currentVisits.count { it.visitType.equals("AD_HOC", ignoreCase = true) }
        val displayCompletedVisits = maxOf(workdaySummary?.completedVisits ?: 0, localCompleted)
        val displayTotalVisits = maxOf(workdaySummary?.totalVisits ?: 0, currentVisits.size, displayCompletedVisits)
        val displayAdhocVisits = maxOf(workdaySummary?.adhocVisits ?: 0, localAdhoc)
        val displayCollections = workdaySummary?.collectionsTotalAmount ?: 0.0

        AlertDialog(
            onDismissRequest = { if (!workdayUiState.isSubmitting) showEndDayConfirmDialog = false },
            containerColor = BrandWhite,
            shape = RoundedCornerShape(16.dp),
            title = {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Box(
                        modifier = Modifier
                            .size(36.dp)
                            .background(BrandGoldLight, CircleShape),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = Icons.Default.Stop,
                            contentDescription = null,
                            tint = BrandNavy,
                            modifier = Modifier.size(20.dp)
                        )
                    }
                    Column {
                        Text(
                            text = "End Your Workday?",
                            fontFamily = LibreBaskervilleFamily,
                            fontWeight = FontWeight.Bold,
                            fontSize = 18.sp,
                            color = BrandNavy
                        )
                        Text(
                            text = "Shift wrap-up & activity verification",
                            fontFamily = LeagueSpartanFamily,
                            fontSize = 12.sp,
                            color = TextSubtle
                        )
                    }
                }
            },
            text = {
                Column(modifier = Modifier.fillMaxWidth()) {
                    Spacer(modifier = Modifier.height(4.dp))

                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(containerColor = Color(0xFFF6F8FA)),
                        shape = RoundedCornerShape(12.dp),
                        border = BorderStroke(1.dp, BrandLightGray)
                    ) {
                        Column(
                            modifier = Modifier.padding(14.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text("Shift Started:", fontSize = 12.sp, color = TextSubtle, fontFamily = LeagueSpartanFamily)
                                Text(
                                    DateTimeUtils.formatDisplayTime(workday?.startTime),
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = BrandNavy,
                                    fontFamily = LeagueSpartanFamily
                                )
                            }
                            Divider(color = BrandLightGray.copy(alpha = 0.7f), thickness = 0.5.dp)
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text("Visits Completed:", fontSize = 12.sp, color = TextSubtle, fontFamily = LeagueSpartanFamily)
                                Text(
                                    "$displayCompletedVisits / $displayTotalVisits",
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = BrandNavy,
                                    fontFamily = LeagueSpartanFamily
                                )
                            }
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text("Ad-hoc Visits:", fontSize = 12.sp, color = TextSubtle, fontFamily = LeagueSpartanFamily)
                                Text(
                                    "$displayAdhocVisits",
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = BrandNavy,
                                    fontFamily = LeagueSpartanFamily
                                )
                            }
                            Divider(color = BrandLightGray.copy(alpha = 0.7f), thickness = 0.5.dp)
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text("Collections Total:", fontSize = 12.sp, color = TextSubtle, fontFamily = LeagueSpartanFamily)
                                Text(
                                    "₹${displayCollections.toInt()}",
                                    fontSize = 14.sp,
                                    fontWeight = FontWeight.Black,
                                    color = SuccessGreen,
                                    fontFamily = LeagueSpartanFamily
                                )
                            }
                            if (endDayAccuracy != null) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Text("GPS Fix:", fontSize = 12.sp, color = TextSubtle, fontFamily = LeagueSpartanFamily)
                                    Text(
                                        "Captured (±${endDayAccuracy?.toInt()}m)",
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = BrandNavy,
                                        fontFamily = LeagueSpartanFamily
                                    )
                                }
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    OutlinedTextField(
                        value = endDayNotes,
                        onValueChange = { endDayNotes = it },
                        label = { Text("Shift summary notes (optional)", fontSize = 12.sp, color = TextSubtle) },
                        modifier = Modifier.fillMaxWidth(),
                        maxLines = 2,
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = BrandNavy,
                            unfocusedBorderColor = BrandLightGray,
                            focusedLabelColor = BrandNavy,
                            cursorColor = BrandNavy
                        ),
                        shape = RoundedCornerShape(10.dp),
                        textStyle = androidx.compose.ui.text.TextStyle(
                            fontSize = 13.sp,
                            fontFamily = LeagueSpartanFamily,
                            color = BrandNavy
                        )
                    )
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        val fix = endDayLocationFix ?: Pair(0.0, 0.0)
                        workdayViewModel.endDay(
                            latitude = fix.first,
                            longitude = fix.second,
                            accuracyM = endDayAccuracy,
                            notes = endDayNotes.ifBlank { "Completed shift" },
                            onSuccess = {
                                showEndDayConfirmDialog = false
                                refreshAll()
                            }
                        )
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = BrandNavy),
                    shape = RoundedCornerShape(10.dp),
                    enabled = !workdayUiState.isSubmitting
                ) {
                    if (workdayUiState.isSubmitting) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            color = BrandWhite,
                            strokeWidth = 2.dp
                        )
                    } else {
                        Text(
                            "Confirm & End Day",
                            color = BrandWhite,
                            fontWeight = FontWeight.Bold,
                            fontFamily = LeagueSpartanFamily,
                            fontSize = 13.sp
                        )
                    }
                }
            },
            dismissButton = {
                OutlinedButton(
                    onClick = { showEndDayConfirmDialog = false },
                    shape = RoundedCornerShape(10.dp),
                    border = BorderStroke(1.dp, BrandLightGray),
                    enabled = !workdayUiState.isSubmitting
                ) {
                    Text(
                        "Cancel",
                        color = TextSecondary,
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 13.sp
                    )
                }
            }
        )
    }

    // ----------------------------------------------------
    // AD-HOC / OFF-BEAT VISIT DIALOG
    // ----------------------------------------------------
    if (showAdHocVisitDialog) {
        AdHocVisitDialog(
            viewModel = visitsViewModel,
            onDismiss = { showAdHocVisitDialog = false },
            onVisitCreated = { visit ->
                showAdHocVisitDialog = false
                refreshAll()
                onNavigateToVisitDetails(visit.id)
            },
            onError = { err ->
                Toast.makeText(context, err, Toast.LENGTH_LONG).show()
            }
        )
    }
}

@Composable
fun MetricCard(title: String, value: String, accentColor: Color, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier.border(1.dp, BrandLightGray, RoundedCornerShape(10.dp)),
        shape = RoundedCornerShape(10.dp),
        colors = CardDefaults.cardColors(containerColor = BrandWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(modifier = Modifier.padding(10.dp)) {
            Text(
                text = title,
                fontFamily = LeagueSpartanFamily,
                fontSize = 9.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 0.5.sp,
                color = TextSecondary,
                maxLines = 1
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = value,
                fontFamily = LeagueSpartanFamily,
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
                color = accentColor,
                maxLines = 1
            )
        }
    }
}

@Composable
fun QuickActionButton(title: String, icon: ImageVector, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Card(
        onClick = onClick,
        modifier = modifier.border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = BrandWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(34.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(BrandNavy)
                    .border(1.dp, BrandGold, RoundedCornerShape(8.dp)),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = BrandGold,
                    modifier = Modifier.size(18.dp)
                )
            }
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text = title,
                fontFamily = LeagueSpartanFamily,
                fontSize = 13.sp,
                fontWeight = FontWeight.Bold,
                color = BrandNavy
            )
        }
    }
}
