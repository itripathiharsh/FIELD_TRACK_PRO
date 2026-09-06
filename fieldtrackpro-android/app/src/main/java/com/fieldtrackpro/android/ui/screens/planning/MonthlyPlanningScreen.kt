package com.fieldtrackpro.android.ui.screens.planning

import android.app.DatePickerDialog
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.CalendarToday
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Event
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Store
import androidx.compose.material.icons.filled.Today
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.PlannedVisitDto
import com.fieldtrackpro.android.ui.components.EmptyState
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.theme.BrandBlack
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandGoldDark
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandNavyLight
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.ErrorRedBg
import com.fieldtrackpro.android.ui.theme.ErrorRedText
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SuccessGreenBg
import com.fieldtrackpro.android.ui.theme.SuccessGreenText
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.theme.TextSubtle
import com.fieldtrackpro.android.ui.theme.WarningGold
import com.fieldtrackpro.android.ui.viewmodel.MonthlyPlanningViewModel
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale

private val MONTH_NAMES = listOf(
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
)

@Composable
fun MonthlyPlanningScreen(
    viewModel: MonthlyPlanningViewModel,
    onNavigateBack: () -> Unit
) {
    val context = LocalContext.current
    val uiState by viewModel.uiState.collectAsState()

    var showAddDialog by remember { mutableStateOf(false) }
    var initialDateForAdd by remember { mutableStateOf<String?>(null) }
    var visitToEdit by remember { mutableStateOf<PlannedVisitDto?>(null) }
    var visitToReschedule by remember { mutableStateOf<PlannedVisitDto?>(null) }
    var visitToCancel by remember { mutableStateOf<PlannedVisitDto?>(null) }

    val monthName = remember(uiState.month) {
        if (uiState.month in 1..12) MONTH_NAMES[uiState.month - 1] else "Month ${uiState.month}"
    }

    LaunchedEffect(uiState.successMessage) {
        uiState.successMessage?.let {
            Toast.makeText(context, it, Toast.LENGTH_SHORT).show()
            viewModel.clearMessages()
        }
    }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "My Monthly Plan",
                onBackClick = onNavigateBack,
                actions = {
                    IconButton(onClick = { viewModel.loadMonthlyPlan() }) {
                        Icon(
                            imageVector = Icons.Default.Refresh,
                            contentDescription = "Refresh",
                            tint = BrandNavy
                        )
                    }
                }
            )
        },
        floatingActionButton = {
            Button(
                onClick = {
                    initialDateForAdd = if (uiState.selectedFilter == "CALENDAR") uiState.selectedDate else null
                    showAddDialog = true
                },
                colors = ButtonDefaults.buttonColors(containerColor = BrandNavy),
                shape = RoundedCornerShape(24.dp),
                elevation = ButtonDefaults.buttonElevation(defaultElevation = 4.dp),
                modifier = Modifier.height(48.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.Add,
                    contentDescription = null,
                    tint = BrandWhite,
                    modifier = Modifier.size(18.dp)
                )
                Spacer(modifier = Modifier.width(6.dp))
                Text(
                    text = "PLAN VISIT",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 13.sp,
                    letterSpacing = 0.5.sp,
                    color = BrandWhite
                )
            }
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(SurfaceSecondary)
                .padding(padding)
        ) {
            // Month Navigation Bar
            MonthNavigationBar(
                year = uiState.year,
                monthName = monthName,
                onPreviousMonth = { viewModel.previousMonth() },
                onNextMonth = { viewModel.nextMonth() },
                onJumpToToday = {
                    val cal = Calendar.getInstance()
                    viewModel.selectMonth(cal.get(Calendar.YEAR), cal.get(Calendar.MONTH) + 1)
                }
            )

            if (uiState.errorMessage != null) {
                ErrorBanner(
                    message = uiState.errorMessage!!,
                    modifier = Modifier
                        .padding(horizontal = 16.dp, vertical = 6.dp)
                        .clickable { viewModel.clearMessages() }
                )
            }

            LazyColumn(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // 1. Monthly Progress KPI Card
                item {
                    MonthlyProgressCard(
                        analytics = uiState.analytics,
                        totalVisitsCount = uiState.plan?.plannedVisits?.count { it.status != "CANCELLED" } ?: 0,
                        activeDaysCount = uiState.plan?.activeDaysCount ?: 0
                    )
                }

                // 2. Filter Tabs (All / Pending / Completed / Calendar View)
                item {
                    FilterTabsSection(
                        selectedFilter = uiState.selectedFilter,
                        totalCount = uiState.plan?.plannedVisits?.count { it.status != "CANCELLED" } ?: 0,
                        plannedCount = uiState.plan?.plannedVisits?.count { it.status == "PLANNED" } ?: 0,
                        completedCount = uiState.plan?.plannedVisits?.count { it.status == "COMPLETED" } ?: 0,
                        onFilterSelected = { viewModel.setFilter(it) }
                    )
                }

                // 3. View Content: Calendar View vs List View
                if (uiState.selectedFilter == "CALENDAR") {
                    // CALENDAR VIEW: 7-Column Monthly Calendar Grid
                    item {
                        val visitsByDate = remember(uiState.plan?.plannedVisits) {
                            uiState.plan?.plannedVisits
                                ?.filter { it.status != "CANCELLED" }
                                ?.groupBy { it.plannedDate }
                                ?: emptyMap()
                        }

                        MonthlyCalendarCard(
                            year = uiState.year,
                            month = uiState.month,
                            selectedDate = uiState.selectedDate,
                            visitsByDate = visitsByDate,
                            onDateSelected = { dateStr ->
                                viewModel.selectDate(dateStr)
                            }
                        )
                    }

                    // Selected Day Details Inspector
                    item {
                        val visitsByDate = remember(uiState.plan?.plannedVisits) {
                            uiState.plan?.plannedVisits
                                ?.filter { it.status != "CANCELLED" }
                                ?.groupBy { it.plannedDate }
                                ?: emptyMap()
                        }
                        val selectedDateStr = uiState.selectedDate ?: remember(uiState.year, uiState.month) {
                            val todayCal = Calendar.getInstance()
                            if (uiState.year == todayCal.get(Calendar.YEAR) && uiState.month == todayCal.get(Calendar.MONTH) + 1) {
                                formatDateStr(uiState.year, uiState.month, todayCal.get(Calendar.DAY_OF_MONTH))
                            } else {
                                formatDateStr(uiState.year, uiState.month, 1)
                            }
                        }
                        val dayVisits = visitsByDate[selectedDateStr] ?: emptyList()

                        SelectedDayInspectorCard(
                            dateStr = selectedDateStr,
                            visits = dayVisits,
                            onAddVisit = {
                                initialDateForAdd = selectedDateStr
                                showAddDialog = true
                            },
                            onEdit = { visitToEdit = it },
                            onReschedule = { visitToReschedule = it },
                            onCancel = { visitToCancel = it }
                        )
                    }
                } else {
                    // LIST VIEW (ALL, PENDING, COMPLETED)
                    if (uiState.isLoading && uiState.plan == null) {
                        item {
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(200.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                CircularProgressIndicator(color = BrandNavy)
                            }
                        }
                    } else if (uiState.filteredVisits.isEmpty()) {
                        item {
                            Card(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 12.dp)
                                    .border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
                                shape = RoundedCornerShape(12.dp),
                                colors = CardDefaults.cardColors(containerColor = BrandWhite)
                            ) {
                                Column(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(24.dp),
                                    horizontalAlignment = Alignment.CenterHorizontally
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.CalendarToday,
                                        contentDescription = null,
                                        tint = TextSubtle,
                                        modifier = Modifier.size(40.dp)
                                    )
                                    Spacer(modifier = Modifier.height(10.dp))
                                    Text(
                                        text = if (uiState.selectedFilter == "ALL")
                                            "No visits planned for $monthName ${uiState.year}"
                                        else
                                            "No ${uiState.selectedFilter.lowercase()} visits for $monthName",
                                        fontFamily = LeagueSpartanFamily,
                                        fontWeight = FontWeight.SemiBold,
                                        fontSize = 14.sp,
                                        color = TextSecondary
                                    )
                                    Spacer(modifier = Modifier.height(6.dp))
                                    Text(
                                        text = "Tap [+ PLAN VISIT] below to schedule customer beats for this month.",
                                        fontFamily = LeagueSpartanFamily,
                                        fontSize = 12.sp,
                                        color = TextSubtle
                                    )
                                }
                            }
                        }
                    } else {
                        items(
                            items = uiState.filteredVisits,
                            key = { it.id }
                        ) { visit ->
                            PlannedVisitItemCard(
                                visit = visit,
                                onEdit = { visitToEdit = visit },
                                onReschedule = { visitToReschedule = visit },
                                onCancel = { visitToCancel = visit }
                            )
                        }
                    }
                }

                // Bottom padding for FAB
                item {
                    Spacer(modifier = Modifier.height(80.dp))
                }
            }
        }
    }

    // Add Planned Visit Dialog
    if (showAddDialog) {
        AddPlannedVisitDialog(
            selectedYear = uiState.year,
            selectedMonth = uiState.month,
            initialPlannedDate = initialDateForAdd,
            isSaving = uiState.isSaving,
            searchResults = uiState.customerSearchResults,
            isSearching = uiState.isSearchingCustomers,
            onSearchCustomers = { viewModel.searchCustomers(it) },
            onDismiss = {
                showAddDialog = false
                initialDateForAdd = null
            },
            onConfirm = { custId, date, priority, visitType, notes ->
                viewModel.createPlannedVisit(custId, date, priority, visitType, notes) { success, _ ->
                    if (success) {
                        showAddDialog = false
                        initialDateForAdd = null
                    }
                }
            }
        )
    }

    // Edit Planned Visit Dialog
    visitToEdit?.let { visit ->
        EditPlannedVisitDialog(
            visit = visit,
            isSaving = uiState.isSaving,
            onDismiss = { visitToEdit = null },
            onConfirm = { priority, visitType, notes ->
                viewModel.updatePlannedVisit(visit.id, priority, visitType, notes) { success, _ ->
                    if (success) visitToEdit = null
                }
            }
        )
    }

    // Reschedule Planned Visit Dialog
    visitToReschedule?.let { visit ->
        ReschedulePlannedVisitDialog(
            visit = visit,
            isSaving = uiState.isSaving,
            onDismiss = { visitToReschedule = null },
            onConfirm = { newDate ->
                viewModel.reschedulePlannedVisit(visit.id, newDate) { success, _ ->
                    if (success) visitToReschedule = null
                }
            }
        )
    }

    // Cancel Planned Visit Confirmation Dialog
    visitToCancel?.let { visit ->
        AlertDialog(
            onDismissRequest = { visitToCancel = null },
            title = {
                Text(
                    text = "Cancel Planned Visit?",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    color = BrandNavy
                )
            },
            text = {
                Text(
                    text = "Are you sure you want to cancel the planned visit for ${visit.customerName ?: "Customer"} scheduled on ${formatDisplayDate(visit.plannedDate)}?",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 13.sp,
                    color = TextSecondary
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        viewModel.cancelPlannedVisit(visit.id) { success, _ ->
                            if (success) visitToCancel = null
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = ErrorRed),
                    enabled = !uiState.isSaving
                ) {
                    if (uiState.isSaving) {
                        CircularProgressIndicator(modifier = Modifier.size(14.dp), color = BrandWhite, strokeWidth = 2.dp)
                    } else {
                        Text("CANCEL VISIT", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold)
                    }
                }
            },
            dismissButton = {
                TextButton(onClick = { visitToCancel = null }) {
                    Text("KEEP VISIT", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = TextSubtle)
                }
            }
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Month Navigation Bar
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun MonthNavigationBar(
    year: Int,
    monthName: String,
    onPreviousMonth: () -> Unit,
    onNextMonth: () -> Unit,
    onJumpToToday: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(16.dp, 8.dp, 16.dp, 4.dp),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = BrandWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onPreviousMonth) {
                Icon(
                    imageVector = Icons.Default.ChevronLeft,
                    contentDescription = "Previous Month",
                    tint = BrandNavy
                )
            }

            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.clickable { onJumpToToday() }
            ) {
                Icon(
                    imageVector = Icons.Default.CalendarMonth,
                    contentDescription = null,
                    tint = BrandGoldDark,
                    modifier = Modifier.size(18.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "$monthName $year",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 17.sp,
                    color = BrandNavy
                )
            }

            IconButton(onClick = onNextMonth) {
                Icon(
                    imageVector = Icons.Default.ChevronRight,
                    contentDescription = "Next Month",
                    tint = BrandNavy
                )
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Monthly Progress KPI Card
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun MonthlyProgressCard(
    analytics: com.fieldtrackpro.android.data.model.EmployeeMonthlyAnalyticsDto?,
    totalVisitsCount: Int,
    activeDaysCount: Int
) {
    val totalPlanned = analytics?.totalPlanned ?: totalVisitsCount
    val completed = analytics?.completed ?: 0
    val pending = (totalPlanned - completed).coerceAtLeast(0)
    val completionRate = analytics?.completionRate ?: if (totalPlanned > 0) (completed.toDouble() / totalPlanned * 100) else 0.0

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = BrandWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "MONTHLY PLAN PROGRESS",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 0.8.sp,
                    color = BrandNavy
                )

                if (analytics?.behindSchedule == true) {
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(6.dp))
                            .background(WarningGold.copy(alpha = 0.15f))
                            .padding(horizontal = 8.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = "BEHIND SCHEDULE",
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.Bold,
                            fontSize = 10.sp,
                            color = WarningGold
                        )
                    }
                } else if (totalPlanned > 0 && completed >= totalPlanned) {
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(6.dp))
                            .background(SuccessGreenBg)
                            .padding(horizontal = 8.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = "GOAL REACHED",
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.Bold,
                            fontSize = 10.sp,
                            color = SuccessGreenText
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                PlanKpiItem(
                    label = "PLANNED",
                    value = totalPlanned.toString(),
                    color = BrandNavy,
                    modifier = Modifier.weight(1f)
                )
                PlanKpiItem(
                    label = "COMPLETED",
                    value = completed.toString(),
                    color = SuccessGreen,
                    modifier = Modifier.weight(1f)
                )
                PlanKpiItem(
                    label = "REMAINING",
                    value = pending.toString(),
                    color = BrandGoldDark,
                    modifier = Modifier.weight(1f)
                )
                PlanKpiItem(
                    label = "ACTIVE DAYS",
                    value = (analytics?.activePlannedDays ?: activeDaysCount).toString(),
                    color = BrandNavyLight,
                    modifier = Modifier.weight(1f)
                )
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Completion Progress Bar
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Completion Coverage",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 12.sp,
                    color = TextSubtle
                )
                Text(
                    text = "${completionRate.toInt()}%",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 12.sp,
                    color = if (completionRate >= 80) SuccessGreen else BrandNavy
                )
            }
            Spacer(modifier = Modifier.height(6.dp))
            LinearProgressIndicator(
                progress = { (completionRate / 100.0).toFloat().coerceIn(0f, 1f) },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(6.dp)
                    .clip(RoundedCornerShape(3.dp)),
                color = if (completionRate >= 80) SuccessGreen else BrandGold,
                trackColor = BrandLightGray
            )
        }
    }
}

@Composable
private fun PlanKpiItem(
    label: String,
    value: String,
    color: Color,
    modifier: Modifier = Modifier
) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(SurfaceSecondary)
            .padding(vertical = 8.dp, horizontal = 4.dp),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(
                text = value,
                fontFamily = LeagueSpartanFamily,
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp,
                color = color
            )
            Text(
                text = label,
                fontFamily = LeagueSpartanFamily,
                fontWeight = FontWeight.SemiBold,
                fontSize = 9.sp,
                letterSpacing = 0.5.sp,
                color = TextSubtle
            )
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Filter Tabs Section
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun FilterTabsSection(
    selectedFilter: String,
    totalCount: Int,
    plannedCount: Int,
    completedCount: Int,
    onFilterSelected: (String) -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        FilterChip(
            selected = selectedFilter == "ALL",
            onClick = { onFilterSelected("ALL") },
            label = {
                Text(
                    text = "All ($totalCount)",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 12.sp
                )
            },
            colors = FilterChipDefaults.filterChipColors(
                selectedContainerColor = BrandNavy,
                selectedLabelColor = BrandWhite,
                containerColor = BrandWhite,
                labelColor = BrandNavy
            ),
            border = FilterChipDefaults.filterChipBorder(
                borderColor = BrandLightGray,
                selectedBorderColor = BrandNavy,
                enabled = true,
                selected = selectedFilter == "ALL"
            )
        )

        FilterChip(
            selected = selectedFilter == "PLANNED",
            onClick = { onFilterSelected("PLANNED") },
            label = {
                Text(
                    text = "Pending ($plannedCount)",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 12.sp
                )
            },
            colors = FilterChipDefaults.filterChipColors(
                selectedContainerColor = BrandGoldDark,
                selectedLabelColor = BrandWhite,
                containerColor = BrandWhite,
                labelColor = BrandGoldDark
            ),
            border = FilterChipDefaults.filterChipBorder(
                borderColor = BrandLightGray,
                selectedBorderColor = BrandGoldDark,
                enabled = true,
                selected = selectedFilter == "PLANNED"
            )
        )

        FilterChip(
            selected = selectedFilter == "COMPLETED",
            onClick = { onFilterSelected("COMPLETED") },
            label = {
                Text(
                    text = "Completed ($completedCount)",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 12.sp
                )
            },
            colors = FilterChipDefaults.filterChipColors(
                selectedContainerColor = SuccessGreen,
                selectedLabelColor = BrandWhite,
                containerColor = BrandWhite,
                labelColor = SuccessGreen
            ),
            border = FilterChipDefaults.filterChipBorder(
                borderColor = BrandLightGray,
                selectedBorderColor = SuccessGreen,
                enabled = true,
                selected = selectedFilter == "COMPLETED"
            )
        )

        FilterChip(
            selected = selectedFilter == "CALENDAR",
            onClick = { onFilterSelected("CALENDAR") },
            leadingIcon = {
                Icon(
                    imageVector = Icons.Default.CalendarMonth,
                    contentDescription = null,
                    modifier = Modifier.size(16.dp),
                    tint = if (selectedFilter == "CALENDAR") BrandWhite else BrandNavy
                )
            },
            label = {
                Text(
                    text = "Calendar View",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 12.sp
                )
            },
            colors = FilterChipDefaults.filterChipColors(
                selectedContainerColor = BrandNavy,
                selectedLabelColor = BrandWhite,
                containerColor = BrandWhite,
                labelColor = BrandNavy
            ),
            border = FilterChipDefaults.filterChipBorder(
                borderColor = BrandLightGray,
                selectedBorderColor = BrandNavy,
                enabled = true,
                selected = selectedFilter == "CALENDAR"
            )
        )
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Monthly Calendar Grid Card (Parity with Admin Monthly Calendar)
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun MonthlyCalendarCard(
    year: Int,
    month: Int,
    selectedDate: String?,
    visitsByDate: Map<String, List<PlannedVisitDto>>,
    onDateSelected: (String) -> Unit
) {
    val todayCal = Calendar.getInstance()
    val todayStr = remember {
        formatDateStr(
            todayCal.get(Calendar.YEAR),
            todayCal.get(Calendar.MONTH) + 1,
            todayCal.get(Calendar.DAY_OF_MONTH)
        )
    }

    val cal = remember(year, month) {
        Calendar.getInstance().apply {
            set(Calendar.YEAR, year)
            set(Calendar.MONTH, month - 1)
            set(Calendar.DAY_OF_MONTH, 1)
        }
    }
    val daysInMonth = remember(year, month) { cal.getActualMaximum(Calendar.DAY_OF_MONTH) }
    val firstDayOfWeek = remember(year, month) { cal.get(Calendar.DAY_OF_WEEK) }
    val leadingEmptyDays = firstDayOfWeek - 1

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = BrandWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp)
        ) {
            // Header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.CalendarMonth,
                        contentDescription = null,
                        tint = BrandNavy,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = "Schedule Overview",
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp,
                        color = BrandNavy
                    )
                }
                Text(
                    text = "Tap any day to view beats",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 11.sp,
                    color = TextSubtle
                )
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Weekday Column Header (Sun -> Sat)
            val weekdays = listOf("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                weekdays.forEachIndexed { idx, day ->
                    Text(
                        text = day,
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = FontWeight.Bold,
                        fontSize = 10.sp,
                        letterSpacing = 0.5.sp,
                        color = if (idx == 0 || idx == 6) TextSubtle.copy(alpha = 0.7f) else BrandNavy,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.weight(1f)
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Calendar Grid Days
            val totalCells = leadingEmptyDays + daysInMonth
            val totalRows = (totalCells + 6) / 7

            for (rowIndex in 0 until totalRows) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    for (colIndex in 0 until 7) {
                        val cellIndex = rowIndex * 7 + colIndex
                        if (cellIndex < leadingEmptyDays || cellIndex >= totalCells) {
                            Spacer(
                                modifier = Modifier
                                    .weight(1f)
                                    .height(50.dp)
                            )
                        } else {
                            val dayNum = cellIndex - leadingEmptyDays + 1
                            val dateStr = formatDateStr(year, month, dayNum)
                            val isToday = (dateStr == todayStr)
                            val isSelected = (dateStr == selectedDate)
                            val dayVisits = visitsByDate[dateStr] ?: emptyList()
                            val visitCount = dayVisits.size
                            val hasCompleted = dayVisits.any { it.status == "COMPLETED" }
                            val hasHighPriority = dayVisits.any { it.priority.uppercase() == "HIGH" }

                            Box(
                                modifier = Modifier
                                    .weight(1f)
                                    .height(50.dp)
                                    .padding(2.dp)
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(
                                        when {
                                            isSelected -> BrandNavy.copy(alpha = 0.08f)
                                            isToday -> BrandGold.copy(alpha = 0.12f)
                                            visitCount > 0 -> SurfaceSecondary
                                            else -> Color.Transparent
                                        }
                                    )
                                    .border(
                                        width = if (isSelected) 1.5.dp else if (isToday) 1.dp else 0.5.dp,
                                        color = when {
                                            isSelected -> BrandNavy
                                            isToday -> BrandGoldDark
                                            visitCount > 0 -> BrandLightGray
                                            else -> BrandLightGray.copy(alpha = 0.4f)
                                        },
                                        shape = RoundedCornerShape(8.dp)
                                    )
                                    .clickable { onDateSelected(dateStr) },
                                contentAlignment = Alignment.Center
                            ) {
                                Column(
                                    horizontalAlignment = Alignment.CenterHorizontally,
                                    verticalArrangement = Arrangement.Center
                                ) {
                                    // Day Number Circle
                                    Box(
                                        modifier = Modifier
                                            .size(22.dp)
                                            .clip(CircleShape)
                                            .background(
                                                when {
                                                    isSelected -> BrandNavy
                                                    isToday -> BrandGold
                                                    else -> Color.Transparent
                                                }
                                            ),
                                        contentAlignment = Alignment.Center
                                    ) {
                                        Text(
                                            text = dayNum.toString(),
                                            fontFamily = LeagueSpartanFamily,
                                            fontWeight = if (isSelected || isToday || visitCount > 0) FontWeight.Bold else FontWeight.Medium,
                                            fontSize = 11.sp,
                                            color = when {
                                                isSelected -> BrandWhite
                                                isToday -> BrandBlack
                                                else -> BrandNavy
                                            }
                                        )
                                    }

                                    // Status indicators & count badge
                                    if (visitCount > 0) {
                                        Row(
                                            horizontalArrangement = Arrangement.spacedBy(2.dp),
                                            verticalAlignment = Alignment.CenterVertically,
                                            modifier = Modifier.padding(top = 2.dp)
                                        ) {
                                            if (hasCompleted) {
                                                Box(
                                                    modifier = Modifier
                                                        .size(4.dp)
                                                        .clip(CircleShape)
                                                        .background(SuccessGreen)
                                                )
                                            }
                                            if (hasHighPriority) {
                                                Box(
                                                    modifier = Modifier
                                                        .size(4.dp)
                                                        .clip(CircleShape)
                                                        .background(ErrorRed)
                                                )
                                            }
                                            Box(
                                                modifier = Modifier
                                                    .clip(RoundedCornerShape(3.dp))
                                                    .background(if (isSelected) BrandNavy else BrandGoldDark)
                                                    .padding(horizontal = 3.dp, vertical = 0.5.dp)
                                            ) {
                                                Text(
                                                    text = visitCount.toString(),
                                                    fontFamily = LeagueSpartanFamily,
                                                    fontWeight = FontWeight.Bold,
                                                    fontSize = 8.sp,
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
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Selected Day Inspector Card (Parity with Admin Day Details Inspector)
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun SelectedDayInspectorCard(
    dateStr: String,
    visits: List<PlannedVisitDto>,
    onAddVisit: () -> Unit,
    onEdit: (PlannedVisitDto) -> Unit,
    onReschedule: (PlannedVisitDto) -> Unit,
    onCancel: (PlannedVisitDto) -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = BrandWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp)
        ) {
            // Header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "SELECTED DAY",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 0.8.sp,
                        color = TextSubtle
                    )
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = formatDisplayDate(dateStr),
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold,
                        color = BrandNavy
                    )
                    Text(
                        text = if (visits.isEmpty()) "No customer visits scheduled" else "${visits.size} visit${if (visits.size > 1) "s" else ""} scheduled",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 11.sp,
                        color = if (visits.isEmpty()) TextSubtle else BrandGoldDark,
                        fontWeight = FontWeight.SemiBold
                    )
                }

                Button(
                    onClick = onAddVisit,
                    colors = ButtonDefaults.buttonColors(containerColor = BrandNavy),
                    shape = RoundedCornerShape(16.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 12.dp, vertical = 6.dp),
                    modifier = Modifier.height(34.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Add,
                        contentDescription = null,
                        tint = BrandWhite,
                        modifier = Modifier.size(14.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = "ADD VISIT",
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = FontWeight.Bold,
                        fontSize = 11.sp,
                        color = BrandWhite
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            if (visits.isEmpty()) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(8.dp))
                        .background(SurfaceSecondary)
                        .border(1.dp, BrandLightGray, RoundedCornerShape(8.dp))
                        .padding(20.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(
                            imageVector = Icons.Default.CalendarToday,
                            contentDescription = null,
                            tint = TextSubtle,
                            modifier = Modifier.size(32.dp)
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "No visits scheduled for this date",
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 13.sp,
                            color = TextSecondary
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Tap [+ ADD VISIT] above to schedule beats for ${formatDisplayDate(dateStr)}.",
                            fontFamily = LeagueSpartanFamily,
                            fontSize = 11.sp,
                            color = TextSubtle
                        )
                    }
                }
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    visits.forEach { visit ->
                        PlannedVisitItemCard(
                            visit = visit,
                            onEdit = { onEdit(visit) },
                            onReschedule = { onReschedule(visit) },
                            onCancel = { onCancel(visit) }
                        )
                    }
                }
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Planned Visit Item Card
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun PlannedVisitItemCard(
    visit: PlannedVisitDto,
    onEdit: () -> Unit,
    onReschedule: () -> Unit,
    onCancel: () -> Unit
) {
    var menuExpanded by remember { mutableStateOf(false) }

    val priorityColor = when (visit.priority.uppercase()) {
        "HIGH" -> ErrorRed
        "LOW" -> SuccessGreen
        else -> BrandGoldDark
    }

    val statusBg = when (visit.status) {
        "COMPLETED" -> SuccessGreenBg
        "CANCELLED" -> ErrorRedBg
        else -> BrandNavy.copy(alpha = 0.08f)
    }
    val statusColor = when (visit.status) {
        "COMPLETED" -> SuccessGreenText
        "CANCELLED" -> ErrorRedText
        else -> BrandNavy
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = BrandWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                // Customer Name & Outlet Code
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = visit.customerName ?: "Unnamed Customer",
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = FontWeight.Bold,
                        fontSize = 15.sp,
                        color = BrandNavy,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    if (!visit.customerOutletCode.isNullOrBlank()) {
                        Text(
                            text = "Code: ${visit.customerOutletCode}",
                            fontFamily = LeagueSpartanFamily,
                            fontSize = 12.sp,
                            color = TextSubtle
                        )
                    }
                }

                // Status Badge & Menu
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(6.dp))
                            .background(statusBg)
                            .padding(horizontal = 8.dp, vertical = 3.dp)
                    ) {
                        Text(
                            text = visit.status,
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.Bold,
                            fontSize = 10.sp,
                            letterSpacing = 0.5.sp,
                            color = statusColor
                        )
                    }

                    if (visit.status != "CANCELLED" && visit.status != "COMPLETED") {
                        Box {
                            IconButton(
                                onClick = { menuExpanded = true },
                                modifier = Modifier.size(28.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.MoreVert,
                                    contentDescription = "Actions",
                                    tint = TextSubtle
                                )
                            }
                            DropdownMenu(
                                expanded = menuExpanded,
                                onDismissRequest = { menuExpanded = false }
                            ) {
                                DropdownMenuItem(
                                    text = { Text("Reschedule Date", fontFamily = LeagueSpartanFamily) },
                                    leadingIcon = { Icon(Icons.Default.Event, null, modifier = Modifier.size(16.dp)) },
                                    onClick = {
                                        menuExpanded = false
                                        onReschedule()
                                    }
                                )
                                DropdownMenuItem(
                                    text = { Text("Edit Details", fontFamily = LeagueSpartanFamily) },
                                    leadingIcon = { Icon(Icons.Default.Edit, null, modifier = Modifier.size(16.dp)) },
                                    onClick = {
                                        menuExpanded = false
                                        onEdit()
                                    }
                                )
                                DropdownMenuItem(
                                    text = { Text("Cancel Visit", fontFamily = LeagueSpartanFamily, color = ErrorRed) },
                                    leadingIcon = { Icon(Icons.Default.DeleteOutline, null, tint = ErrorRed, modifier = Modifier.size(16.dp)) },
                                    onClick = {
                                        menuExpanded = false
                                        onCancel()
                                    }
                                )
                            }
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Date & Priority Badges Row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.CalendarToday,
                        contentDescription = null,
                        tint = BrandGoldDark,
                        modifier = Modifier.size(13.dp)
                    )
                    Spacer(modifier = Modifier.width(5.dp))
                    Text(
                        text = formatDisplayDate(visit.plannedDate),
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 12.sp,
                        color = BrandNavy
                    )
                }

                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    // Priority chip
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(4.dp))
                            .background(priorityColor.copy(alpha = 0.12f))
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = "${visit.priority} PRIORITY",
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.Bold,
                            fontSize = 9.sp,
                            color = priorityColor
                        )
                    }

                    // Visit type chip
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(4.dp))
                            .background(BrandLightGray.copy(alpha = 0.6f))
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = visit.visitType,
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 9.sp,
                            color = TextSubtle
                        )
                    }
                }
            }

            // Area / Address
            if (!visit.customerAddress.isNullOrBlank() || !visit.areaName.isNullOrBlank()) {
                Spacer(modifier = Modifier.height(6.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.LocationOn,
                        contentDescription = null,
                        tint = TextSubtle,
                        modifier = Modifier.size(12.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = listOfNotNull(visit.areaName, visit.customerAddress).joinToString(" • "),
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 11.sp,
                        color = TextSubtle,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }

            // Notes
            if (!visit.notes.isNullOrBlank()) {
                Spacer(modifier = Modifier.height(6.dp))
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(6.dp))
                        .background(SurfaceSecondary)
                        .padding(horizontal = 8.dp, vertical = 4.dp)
                ) {
                    Text(
                        text = "Notes: ${visit.notes}",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 11.sp,
                        color = TextSecondary,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Add Planned Visit Dialog
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun AddPlannedVisitDialog(
    selectedYear: Int,
    selectedMonth: Int,
    initialPlannedDate: String? = null,
    isSaving: Boolean,
    searchResults: List<CustomerDto>,
    isSearching: Boolean,
    onSearchCustomers: (String) -> Unit,
    onDismiss: () -> Unit,
    onConfirm: (customerId: String, plannedDate: String, priority: String, visitType: String, notes: String?) -> Unit
) {
    val context = LocalContext.current

    var searchQuery by remember { mutableStateOf("") }
    var selectedCustomer by remember { mutableStateOf<CustomerDto?>(null) }
    var priority by remember { mutableStateOf("MEDIUM") }
    var visitType by remember { mutableStateOf("PLANNED") }
    var notes by remember { mutableStateOf("") }

    // Initial default planned date: initialPlannedDate if provided, else today if current month, or 1st day of target month
    val todayCal = Calendar.getInstance()
    val defaultDateStr = remember(selectedYear, selectedMonth, initialPlannedDate) {
        if (!initialPlannedDate.isNullOrBlank()) {
            initialPlannedDate
        } else {
            val currentYear = todayCal.get(Calendar.YEAR)
            val currentMonth = todayCal.get(Calendar.MONTH) + 1
            val currentDay = todayCal.get(Calendar.DAY_OF_MONTH)
            if (selectedYear == currentYear && selectedMonth == currentMonth) {
                formatDateStr(selectedYear, selectedMonth, currentDay)
            } else {
                formatDateStr(selectedYear, selectedMonth, 1)
            }
        }
    }
    var plannedDate by remember { mutableStateOf(defaultDateStr) }

    AlertDialog(
        onDismissRequest = { if (!isSaving) onDismiss() },
        title = {
            Text(
                text = "Plan a Customer Visit",
                fontFamily = LeagueSpartanFamily,
                fontWeight = FontWeight.Bold,
                color = BrandNavy
            )
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 480.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                // 1. Customer Selection
                Text(
                    text = "CUSTOMER / OUTLET *",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = BrandNavy
                )

                if (selectedCustomer != null) {
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .border(1.dp, BrandGoldDark, RoundedCornerShape(8.dp)),
                        shape = RoundedCornerShape(8.dp),
                        colors = CardDefaults.cardColors(containerColor = BrandGold.copy(alpha = 0.08f))
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(10.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = selectedCustomer!!.name,
                                    fontFamily = LeagueSpartanFamily,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 14.sp,
                                    color = BrandNavy
                                )
                                Text(
                                    text = selectedCustomer!!.outletCode ?: selectedCustomer!!.address ?: "",
                                    fontFamily = LeagueSpartanFamily,
                                    fontSize = 11.sp,
                                    color = TextSubtle
                                )
                            }
                            IconButton(
                                onClick = { selectedCustomer = null },
                                modifier = Modifier.size(24.dp)
                            ) {
                                Icon(Icons.Default.Clear, "Remove", tint = TextSubtle)
                            }
                        }
                    }
                } else {
                    OutlinedTextField(
                        value = searchQuery,
                        onValueChange = {
                            searchQuery = it
                            onSearchCustomers(it)
                        },
                        placeholder = { Text("Search customer name or code...", fontSize = 12.sp) },
                        leadingIcon = { Icon(Icons.Default.Search, null, modifier = Modifier.size(18.dp)) },
                        trailingIcon = {
                            if (isSearching) {
                                CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp)
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        shape = RoundedCornerShape(8.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = BrandNavy,
                            unfocusedBorderColor = BrandLightGray
                        )
                    )

                    LazyColumn(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(max = 140.dp)
                            .border(1.dp, BrandLightGray, RoundedCornerShape(8.dp))
                    ) {
                        if (searchResults.isEmpty()) {
                            item {
                                Text(
                                    text = if (isSearching) "Searching..." else "No matching customers found",
                                    fontFamily = LeagueSpartanFamily,
                                    fontSize = 12.sp,
                                    color = TextSubtle,
                                    modifier = Modifier.padding(12.dp)
                                )
                            }
                        } else {
                            items(searchResults) { cust ->
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable { selectedCustomer = cust }
                                        .padding(horizontal = 10.dp, vertical = 8.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Icon(Icons.Default.Store, null, tint = BrandNavyLight, modifier = Modifier.size(16.dp))
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Column {
                                        Text(
                                            text = cust.name,
                                            fontFamily = LeagueSpartanFamily,
                                            fontWeight = FontWeight.SemiBold,
                                            fontSize = 13.sp,
                                            color = BrandNavy
                                        )
                                        Text(
                                            text = cust.outletCode ?: cust.address ?: "",
                                            fontFamily = LeagueSpartanFamily,
                                            fontSize = 11.sp,
                                            color = TextSubtle
                                        )
                                    }
                                }
                            }
                        }
                    }
                }

                // 2. Date Picker
                Text(
                    text = "PLANNED DATE *",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = BrandNavy
                )
                OutlinedButton(
                    onClick = {
                        val parts = plannedDate.split("-").mapNotNull { it.toIntOrNull() }
                        val initY = parts.getOrNull(0) ?: selectedYear
                        val initM = (parts.getOrNull(1) ?: selectedMonth) - 1
                        val initD = parts.getOrNull(2) ?: 1
                        DatePickerDialog(context, { _, y, m, d ->
                            plannedDate = formatDateStr(y, m + 1, d)
                        }, initY, initM, initD).show()
                    },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Icon(Icons.Default.CalendarToday, null, tint = BrandGoldDark, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = formatDisplayDate(plannedDate),
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = FontWeight.SemiBold,
                        color = BrandNavy
                    )
                }

                // 3. Priority Row
                Text(
                    text = "PRIORITY",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = BrandNavy
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    listOf("LOW", "MEDIUM", "HIGH").forEach { p ->
                        FilterChip(
                            selected = priority == p,
                            onClick = { priority = p },
                            label = { Text(p, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 11.sp) },
                            modifier = Modifier.weight(1f),
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = if (p == "HIGH") ErrorRed else if (p == "LOW") SuccessGreen else BrandGoldDark,
                                selectedLabelColor = BrandWhite,
                                containerColor = BrandWhite,
                                labelColor = BrandNavy
                            )
                        )
                    }
                }

                // 4. Notes
                Text(
                    text = "VISIT OBJECTIVE / REMARKS",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = BrandNavy
                )
                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it },
                    placeholder = { Text("Enter purpose (e.g. payment follow-up, stock audit)", fontSize = 12.sp) },
                    modifier = Modifier.fillMaxWidth(),
                    maxLines = 3,
                    shape = RoundedCornerShape(8.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = BrandNavy,
                        unfocusedBorderColor = BrandLightGray
                    )
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    if (selectedCustomer == null) {
                        Toast.makeText(context, "Please select a customer first", Toast.LENGTH_SHORT).show()
                        return@Button
                    }
                    onConfirm(selectedCustomer!!.id, plannedDate, priority, visitType, notes)
                },
                colors = ButtonDefaults.buttonColors(containerColor = BrandNavy),
                enabled = !isSaving && selectedCustomer != null
            ) {
                if (isSaving) {
                    CircularProgressIndicator(modifier = Modifier.size(14.dp), color = BrandWhite, strokeWidth = 2.dp)
                } else {
                    Text("ADD TO PLAN", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold)
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !isSaving) {
                Text("CANCEL", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = TextSubtle)
            }
        }
    )
}

// ─────────────────────────────────────────────────────────────────────────────
// Edit Planned Visit Dialog
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun EditPlannedVisitDialog(
    visit: PlannedVisitDto,
    isSaving: Boolean,
    onDismiss: () -> Unit,
    onConfirm: (priority: String, visitType: String, notes: String?) -> Unit
) {
    var priority by remember { mutableStateOf(visit.priority) }
    var visitType by remember { mutableStateOf(visit.visitType) }
    var notes by remember { mutableStateOf(visit.notes ?: "") }

    AlertDialog(
        onDismissRequest = { if (!isSaving) onDismiss() },
        title = {
            Text(
                text = "Edit Planned Visit",
                fontFamily = LeagueSpartanFamily,
                fontWeight = FontWeight.Bold,
                color = BrandNavy
            )
        },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text(
                    text = visit.customerName ?: "Customer",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 15.sp,
                    color = BrandNavy
                )
                Text(
                    text = "Scheduled for ${formatDisplayDate(visit.plannedDate)}",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 12.sp,
                    color = TextSubtle
                )

                Spacer(modifier = Modifier.height(4.dp))

                Text(
                    text = "PRIORITY",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = BrandNavy
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    listOf("LOW", "MEDIUM", "HIGH").forEach { p ->
                        FilterChip(
                            selected = priority.equals(p, ignoreCase = true),
                            onClick = { priority = p },
                            label = { Text(p, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 11.sp) },
                            modifier = Modifier.weight(1f),
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = if (p == "HIGH") ErrorRed else if (p == "LOW") SuccessGreen else BrandGoldDark,
                                selectedLabelColor = BrandWhite,
                                containerColor = BrandWhite,
                                labelColor = BrandNavy
                            )
                        )
                    }
                }

                Text(
                    text = "VISIT OBJECTIVE / NOTES",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = BrandNavy
                )
                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it },
                    placeholder = { Text("Update notes or remarks", fontSize = 12.sp) },
                    modifier = Modifier.fillMaxWidth(),
                    maxLines = 3,
                    shape = RoundedCornerShape(8.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = BrandNavy,
                        unfocusedBorderColor = BrandLightGray
                    )
                )
            }
        },
        confirmButton = {
            Button(
                onClick = { onConfirm(priority, visitType, notes) },
                colors = ButtonDefaults.buttonColors(containerColor = BrandNavy),
                enabled = !isSaving
            ) {
                if (isSaving) {
                    CircularProgressIndicator(modifier = Modifier.size(14.dp), color = BrandWhite, strokeWidth = 2.dp)
                } else {
                    Text("SAVE CHANGES", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold)
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !isSaving) {
                Text("CANCEL", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = TextSubtle)
            }
        }
    )
}

// ─────────────────────────────────────────────────────────────────────────────
// Reschedule Planned Visit Dialog
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun ReschedulePlannedVisitDialog(
    visit: PlannedVisitDto,
    isSaving: Boolean,
    onDismiss: () -> Unit,
    onConfirm: (newDate: String) -> Unit
) {
    val context = LocalContext.current
    var newDate by remember { mutableStateOf(visit.plannedDate) }

    AlertDialog(
        onDismissRequest = { if (!isSaving) onDismiss() },
        title = {
            Text(
                text = "Reschedule Visit",
                fontFamily = LeagueSpartanFamily,
                fontWeight = FontWeight.Bold,
                color = BrandNavy
            )
        },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text(
                    text = visit.customerName ?: "Customer",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 15.sp,
                    color = BrandNavy
                )
                Text(
                    text = "Currently scheduled: ${formatDisplayDate(visit.plannedDate)}",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 12.sp,
                    color = TextSubtle
                )

                Spacer(modifier = Modifier.height(6.dp))

                Text(
                    text = "SELECT NEW TARGET DATE *",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = BrandNavy
                )

                OutlinedButton(
                    onClick = {
                        val parts = newDate.split("-").mapNotNull { it.toIntOrNull() }
                        val initY = parts.getOrNull(0) ?: 2026
                        val initM = (parts.getOrNull(1) ?: 9) - 1
                        val initD = parts.getOrNull(2) ?: 1
                        DatePickerDialog(context, { _, y, m, d ->
                            newDate = formatDateStr(y, m + 1, d)
                        }, initY, initM, initD).show()
                    },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Icon(Icons.Default.CalendarToday, null, tint = BrandGoldDark, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = formatDisplayDate(newDate),
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = FontWeight.SemiBold,
                        color = BrandNavy
                    )
                }
            }
        },
        confirmButton = {
            Button(
                onClick = { onConfirm(newDate) },
                colors = ButtonDefaults.buttonColors(containerColor = BrandNavy),
                enabled = !isSaving
            ) {
                if (isSaving) {
                    CircularProgressIndicator(modifier = Modifier.size(14.dp), color = BrandWhite, strokeWidth = 2.dp)
                } else {
                    Text("RESCHEDULE", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold)
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !isSaving) {
                Text("CANCEL", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = TextSubtle)
            }
        }
    )
}

// ─────────────────────────────────────────────────────────────────────────────
// Format Helpers
// ─────────────────────────────────────────────────────────────────────────────

private fun formatDateStr(year: Int, month: Int, day: Int): String {
    return String.format(Locale.US, "%04d-%02d-%02d", year, month, day)
}

private fun formatDisplayDate(dateStr: String): String {
    return try {
        val parts = dateStr.split("-").map { it.toInt() }
        val cal = Calendar.getInstance().apply {
            set(parts[0], parts[1] - 1, parts[2])
        }
        val sdf = SimpleDateFormat("EEE, dd MMM yyyy", Locale.getDefault())
        sdf.format(cal.time)
    } catch (_: Exception) {
        dateStr
    }
}
