package com.fieldtrackpro.android.ui.screens.planning

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ViewList
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.CalendarToday
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.EventBusy
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.WifiOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SelectableDates
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.PlannedVisitDto
import com.fieldtrackpro.android.search.CustomerSearchState
import com.fieldtrackpro.android.ui.components.CustomerPicker
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.InlineErrorCard
import com.fieldtrackpro.android.ui.components.OutlineButton
import com.fieldtrackpro.android.ui.components.PrimaryButton
import com.fieldtrackpro.android.ui.components.SectionHeader
import com.fieldtrackpro.android.ui.components.SkeletonBlock
import com.fieldtrackpro.android.ui.components.StatusChip
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandGoldDark
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.ErrorRedBg
import com.fieldtrackpro.android.ui.theme.KpiNumber
import com.fieldtrackpro.android.ui.theme.LabelCaps
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.Navy100
import com.fieldtrackpro.android.ui.theme.Navy50
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SuccessGreenBg
import com.fieldtrackpro.android.ui.theme.SuccessGreenText
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.SystemBarIcons
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.theme.TextSubtle
import com.fieldtrackpro.android.ui.theme.WarningGold
import com.fieldtrackpro.android.ui.theme.WarningGoldBg
import com.fieldtrackpro.android.ui.viewmodel.MonthlyPlanUiState
import com.fieldtrackpro.android.ui.viewmodel.MonthlyPlanningViewModel
import com.fieldtrackpro.android.ui.viewmodel.PlanLoadError
import com.fieldtrackpro.android.ui.viewmodel.summarize
import com.fieldtrackpro.android.utils.SessionManager
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Locale
import java.util.TimeZone

private val MONTHS = listOf("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")

internal fun formatDateStr(y: Int, m: Int, d: Int) = String.format(Locale.US, "%04d-%02d-%02d", y, m, d)

internal fun formatDisplayDate(iso: String): String = try {
    val p = SimpleDateFormat("yyyy-MM-dd", Locale.US)
    SimpleDateFormat("EEE, d MMM yyyy", Locale.getDefault()).format(p.parse(iso)!!)
} catch (e: Exception) {
    iso
}

internal fun todayIso(): String {
    val c = Calendar.getInstance()
    return formatDateStr(c.get(Calendar.YEAR), c.get(Calendar.MONTH) + 1, c.get(Calendar.DAY_OF_MONTH))
}

/** Business rule (backend): employees cannot plan visits in the past. */
internal fun isPlannableDate(iso: String, today: String = todayIso()): Boolean = iso >= today

@Composable
fun MonthlyPlanningScreen(
    viewModel: MonthlyPlanningViewModel,
    onNavigateBack: () -> Unit
) {
    val ui by viewModel.uiState.collectAsState()
    val search by viewModel.customerSearch.state.collectAsState()
    var showAdd by rememberSaveable { mutableStateOf(false) }
    var addDate by rememberSaveable { mutableStateOf<String?>(null) }
    var actionVisit by remember { mutableStateOf<PlannedVisitDto?>(null) }
    val snackbar = remember { SnackbarHostState() }

    LaunchedEffect(Unit) { viewModel.onScreenOpened() }
    LaunchedEffect(ui.successMessage, ui.errorMessage) {
        val msg = ui.successMessage ?: ui.errorMessage
        if (msg != null && !showAdd) {
            snackbar.showSnackbar(msg)
            viewModel.clearMessages()
        }
    }

    MonthlyPlanContent(
        ui = ui,
        snackbar = snackbar,
        onBack = onNavigateBack,
        onRefresh = viewModel::refresh,
        onPrevMonth = viewModel::previousMonth,
        onNextMonth = viewModel::nextMonth,
        onToday = {
            val c = Calendar.getInstance()
            viewModel.selectMonth(c.get(Calendar.YEAR), c.get(Calendar.MONTH) + 1)
        },
        onFilter = viewModel::setFilter,
        onToggleCalendar = { viewModel.setCalendarView(!ui.calendarView) },
        onSelectDate = viewModel::selectDate,
        onRetry = viewModel::loadMonthlyPlan,
        onSignInAgain = { SessionManager.notifySessionExpired() },
        onAdd = { date ->
            addDate = date
            showAdd = true
        },
        onVisitClick = { actionVisit = it }
    )

    if (showAdd) {
        AddVisitSheet(
            year = ui.year,
            month = ui.month,
            initialDate = addDate,
            search = search,
            isSaving = ui.isSaving,
            serverError = ui.errorMessage,
            onQueryChange = viewModel.customerSearch::onQueryChange,
            onDismiss = {
                showAdd = false
                viewModel.clearMessages()
                viewModel.customerSearch.clear()
            },
            onSubmit = { customer, date, priority, notes ->
                viewModel.createPlannedVisit(customer.id, date, priority, "PLANNED", notes) { ok, _ ->
                    if (ok) {
                        showAdd = false
                        viewModel.customerSearch.clear()
                    }
                }
            }
        )
    }

    actionVisit?.let { visit ->
        VisitActionsSheet(
            visit = visit,
            isSaving = ui.isSaving,
            onDismiss = { actionVisit = null },
            onReschedule = { date -> viewModel.reschedulePlannedVisit(visit.id, date) { ok, _ -> if (ok) actionVisit = null } },
            onUpdate = { priority, notes -> viewModel.updatePlannedVisit(visit.id, priority, null, notes) { ok, _ -> if (ok) actionVisit = null } },
            onCancelVisit = { viewModel.cancelPlannedVisit(visit.id) { ok, _ -> if (ok) actionVisit = null } }
        )
    }
}

/** Stateless Monthly Plan screen (also rendered by the screenshot test). */
@Composable
fun MonthlyPlanContent(
    ui: MonthlyPlanUiState,
    snackbar: SnackbarHostState = remember { SnackbarHostState() },
    onBack: () -> Unit = {},
    onRefresh: () -> Unit = {},
    onPrevMonth: () -> Unit = {},
    onNextMonth: () -> Unit = {},
    onToday: () -> Unit = {},
    onFilter: (String) -> Unit = {},
    onToggleCalendar: () -> Unit = {},
    onSelectDate: (String?) -> Unit = {},
    onRetry: () -> Unit = {},
    onSignInAgain: () -> Unit = {},
    onAdd: (String?) -> Unit = {},
    onVisitClick: (PlannedVisitDto) -> Unit = {}
) {
    SystemBarIcons(darkIcons = true)
    Scaffold(
        topBar = {
            FieldTrackTopAppBar(title = "Monthly plan", onBackClick = onBack, actions = {
                IconButton(onClick = onRefresh) { Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = BrandNavy) }
            })
        },
        snackbarHost = { SnackbarHost(snackbar) },
        floatingActionButton = {
            if (ui.hasLoadedPlan) {
                ExtendedFloatingActionButton(
                    onClick = { onAdd(if (ui.calendarView) ui.selectedDate?.takeIf { isPlannableDate(it) } else null) },
                    containerColor = BrandGold,
                    contentColor = BrandNavy,
                    icon = { Icon(Icons.Default.Add, contentDescription = null) },
                    text = { Text("Add visit", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold) }
                )
            }
        },
        containerColor = SurfaceSecondary
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 96.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            MonthSelector(ui.year, ui.month, onPrevMonth, onNextMonth, onToday)
            when {
                ui.loadError != null -> LoadErrorState(ui.loadError, ui.loadErrorMessage ?: "", onRetry, onSignInAgain)
                !ui.hasLoadedPlan -> {
                    SkeletonBlock(height = 150.dp)
                    SkeletonBlock(height = 44.dp)
                    repeat(3) { SkeletonBlock(height = 72.dp) }
                }
                else -> {
                    SummaryCard(ui)
                    FilterRow(ui.selectedFilter, ui.calendarView, onFilter, onToggleCalendar)
                    if (ui.calendarView) {
                        CalendarGrid(ui, onSelectDate)
                        val day = ui.selectedDate
                        val dayVisits = ui.filteredVisits.filter { it.plannedDate == day }
                        if (day != null) {
                            SectionHeader(
                                title = formatDisplayDate(day),
                                actionLabel = if (isPlannableDate(day)) "Add on this day" else null,
                                onAction = { onAdd(day) }
                            )
                            if (dayVisits.isEmpty()) Text("No visits on this day.", fontSize = 14.sp, color = TextSecondary)
                            else VisitGroup(dayVisits, onVisitClick)
                        }
                    } else {
                        val visits = ui.filteredVisits.sortedWith(compareBy({ it.plannedDate }, { it.customerName ?: "" }))
                        if (visits.isEmpty()) {
                            EmptyPlan(ui, onAdd)
                        } else {
                            visits.groupBy { it.plannedDate }.forEach { (date, list) ->
                                SectionHeader(title = "${formatDisplayDate(date)} · ${list.size}")
                                VisitGroup(list, onVisitClick)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MonthSelector(year: Int, month: Int, onPrev: () -> Unit, onNext: () -> Unit, onToday: () -> Unit) {
    val c = Calendar.getInstance()
    val isCurrent = c.get(Calendar.YEAR) == year && c.get(Calendar.MONTH) + 1 == month
    Row(verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = onPrev) { Icon(Icons.Default.ChevronLeft, contentDescription = "Previous month", tint = BrandNavy) }
        Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally) {
            Text("${MONTHS[month - 1]} $year", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 22.sp, color = BrandNavy)
            if (!isCurrent) {
                Text("Back to this month", fontSize = 13.sp, color = BrandGoldDark, fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.clickable(role = Role.Button, onClick = onToday).padding(4.dp))
            }
        }
        IconButton(onClick = onNext) { Icon(Icons.Default.ChevronRight, contentDescription = "Next month", tint = BrandNavy) }
    }
}

@Composable
private fun SummaryCard(ui: MonthlyPlanUiState) {
    val s = summarize(ui.plan!!, ui.analytics)
    Surface(shape = RoundedCornerShape(18.dp), color = BrandNavy, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(verticalAlignment = Alignment.Bottom) {
                Column(Modifier.weight(1f)) {
                    Text("COMPLETION", style = LabelCaps, color = Color(0xFFB4BDD0))
                    Text("${s.completionPercent}%", style = KpiNumber.copy(fontSize = 34.sp), color = BrandWhite)
                }
                Text("${s.completed} of ${s.planned} visits done", fontSize = 14.sp, color = Color(0xFFB4BDD0))
            }
            LinearProgressIndicator(
                progress = { if (s.planned == 0) 0f else s.completed.toFloat() / s.planned },
                color = BrandGold, trackColor = Color.White.copy(alpha = 0.14f),
                modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp))
            )
            Row {
                SummaryStat("Planned", s.planned, Modifier.weight(1f))
                SummaryStat("Completed", s.completed, Modifier.weight(1f))
                SummaryStat("Remaining", s.remaining, Modifier.weight(1f))
                SummaryStat("Active days", s.activeDays, Modifier.weight(1f))
            }
            if (ui.analytics?.behindSchedule == true) {
                StatusChip("Behind schedule", container = BrandGold.copy(alpha = 0.18f), content = Color(0xFFFCC15A))
            }
        }
    }
}

@Composable
private fun SummaryStat(label: String, value: Int, modifier: Modifier) {
    Column(modifier) {
        Text(value.toString(), style = KpiNumber.copy(fontSize = 22.sp), color = BrandWhite)
        Text(label, fontSize = 12.sp, color = Color(0xFFB4BDD0), maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun FilterRow(selected: String, calendar: Boolean, onFilter: (String) -> Unit, onToggleCalendar: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Row(
            Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).background(Navy100).padding(4.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            listOf("ALL" to "All", "PLANNED" to "Pending", "COMPLETED" to "Completed").forEach { (key, label) ->
                val on = selected == key
                Box(
                    Modifier
                        .weight(1f)
                        .clip(RoundedCornerShape(9.dp))
                        .background(if (on) BrandWhite else Color.Transparent)
                        .clickable(role = Role.Tab) { onFilter(key) }
                        .heightIn(min = 40.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text(label, fontFamily = LeagueSpartanFamily, fontWeight = if (on) FontWeight.Bold else FontWeight.Medium,
                        fontSize = 14.sp, color = if (on) BrandNavy else TextSecondary)
                }
            }
        }
        Spacer(Modifier.width(8.dp))
        IconButton(onClick = onToggleCalendar) {
            Icon(if (calendar) Icons.AutoMirrored.Filled.ViewList else Icons.Default.CalendarMonth,
                contentDescription = if (calendar) "Show list" else "Show calendar", tint = BrandNavy)
        }
    }
}

@Composable
private fun VisitGroup(visits: List<PlannedVisitDto>, onClick: (PlannedVisitDto) -> Unit) {
    Surface(shape = RoundedCornerShape(16.dp), color = BrandWhite, modifier = Modifier.fillMaxWidth().border(1.dp, BrandLightGray, RoundedCornerShape(16.dp))) {
        Column {
            visits.forEachIndexed { i, v ->
                if (i > 0) HorizontalDivider(color = BrandLightGray, modifier = Modifier.padding(start = 16.dp))
                Row(
                    Modifier.fillMaxWidth().clickable { onClick(v) }.heightIn(min = 64.dp).padding(horizontal = 16.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(Modifier.size(8.dp).clip(CircleShape).background(priorityColor(v.priority)))
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(v.customerName ?: "Customer", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold, fontSize = 16.sp,
                            color = BrandNavy, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        val sub = listOfNotNull(v.customerOutletCode, v.areaName ?: v.territoryName).joinToString(" · ")
                        if (sub.isNotBlank()) Text(sub, fontSize = 13.sp, color = TextSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        v.notes?.takeIf { it.isNotBlank() }?.let { Text(it, fontSize = 13.sp, color = TextSubtle, maxLines = 1, overflow = TextOverflow.Ellipsis) }
                    }
                    Spacer(Modifier.width(8.dp))
                    VisitStatusChip(v.status)
                }
            }
        }
    }
}

private fun priorityColor(p: String) = when (p.uppercase()) {
    "HIGH" -> ErrorRed
    "LOW" -> SuccessGreen
    else -> BrandGold
}

@Composable
private fun VisitStatusChip(status: String) = when (status.uppercase()) {
    "COMPLETED" -> StatusChip("Done", container = SuccessGreenBg, content = SuccessGreenText)
    "MISSED" -> StatusChip("Missed", container = ErrorRedBg, content = ErrorRed)
    else -> StatusChip("Pending", container = WarningGoldBg, content = WarningGold)
}

@Composable
private fun CalendarGrid(ui: MonthlyPlanUiState, onSelect: (String?) -> Unit) {
    val cal = Calendar.getInstance().apply { set(ui.year, ui.month - 1, 1) }
    val firstDow = (cal.get(Calendar.DAY_OF_WEEK) + 5) % 7 // Monday = 0
    val days = cal.getActualMaximum(Calendar.DAY_OF_MONTH)
    val counts = ui.filteredVisits.groupingBy { it.plannedDate }.eachCount()
    val today = todayIso()
    Surface(shape = RoundedCornerShape(16.dp), color = BrandWhite, modifier = Modifier.fillMaxWidth().border(1.dp, BrandLightGray, RoundedCornerShape(16.dp))) {
        Column(Modifier.padding(10.dp)) {
            Row { listOf("M", "T", "W", "T", "F", "S", "S").forEach { Text(it, Modifier.weight(1f), textAlign = TextAlign.Center, fontSize = 12.sp, color = TextSubtle) } }
            Spacer(Modifier.height(6.dp))
            val cells = firstDow + days
            for (week in 0 until (cells + 6) / 7) {
                Row {
                    for (dow in 0 until 7) {
                        val dayNum = week * 7 + dow - firstDow + 1
                        Box(Modifier.weight(1f).aspectRatio(1f).padding(2.dp), contentAlignment = Alignment.Center) {
                            if (dayNum in 1..days) {
                                val iso = formatDateStr(ui.year, ui.month, dayNum)
                                val selected = iso == ui.selectedDate
                                val count = counts[iso] ?: 0
                                Column(
                                    Modifier.fillMaxSize().clip(RoundedCornerShape(10.dp))
                                        .background(if (selected) BrandNavy else if (iso == today) Navy100 else Color.Transparent)
                                        .clickable { onSelect(iso) },
                                    horizontalAlignment = Alignment.CenterHorizontally,
                                    verticalArrangement = Arrangement.Center
                                ) {
                                    Text(dayNum.toString(), fontSize = 14.sp, fontWeight = if (count > 0) FontWeight.Bold else FontWeight.Normal,
                                        color = if (selected) BrandWhite else TextPrimary)
                                    if (count > 0) Box(Modifier.padding(top = 2.dp).size(5.dp).clip(CircleShape).background(if (selected) BrandGold else BrandGoldDark))
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun EmptyPlan(ui: MonthlyPlanUiState, onAdd: (String?) -> Unit) {
    Surface(shape = RoundedCornerShape(16.dp), color = BrandWhite, modifier = Modifier.fillMaxWidth().border(1.dp, BrandLightGray, RoundedCornerShape(16.dp))) {
        Column(Modifier.padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.size(48.dp).clip(RoundedCornerShape(14.dp)).background(Navy100), contentAlignment = Alignment.Center) {
                Icon(Icons.Default.CalendarToday, contentDescription = null, tint = BrandNavy)
            }
            val text = when (ui.selectedFilter) {
                "PLANNED" -> "No pending visits in ${MONTHS[ui.month - 1]}"
                "COMPLETED" -> "No completed visits yet in ${MONTHS[ui.month - 1]}"
                else -> "No visits planned for ${MONTHS[ui.month - 1]}"
            }
            Text(text, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold, fontSize = 17.sp, color = BrandNavy, textAlign = TextAlign.Center)
            Text("Plan your outlet visits so your day is ready when you start it.", fontSize = 14.sp, color = TextSecondary, textAlign = TextAlign.Center)
            if (ui.selectedFilter == "ALL") TextButton(onClick = { onAdd(null) }) {
                Text("Plan a visit", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = BrandNavy)
            }
        }
    }
}

@Composable
private fun LoadErrorState(kind: PlanLoadError, message: String, onRetry: () -> Unit, onSignInAgain: () -> Unit) {
    val (icon, title) = when (kind) {
        PlanLoadError.UNAUTHORIZED -> Icons.Default.Lock to "Session ended"
        PlanLoadError.FORBIDDEN -> Icons.Default.Lock to "No access to monthly plans"
        PlanLoadError.NETWORK -> Icons.Default.WifiOff to "You're offline"
        PlanLoadError.SERVER -> Icons.Default.EventBusy to "Plan not available"
    }
    Surface(shape = RoundedCornerShape(16.dp), color = BrandWhite, modifier = Modifier.fillMaxWidth().border(1.dp, BrandLightGray, RoundedCornerShape(16.dp))) {
        Column(Modifier.padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.size(52.dp).clip(CircleShape).background(Navy100), contentAlignment = Alignment.Center) {
                Icon(icon, contentDescription = null, tint = BrandNavy)
            }
            Text(title, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 18.sp, color = BrandNavy)
            Text(message, fontSize = 14.sp, color = TextSecondary, textAlign = TextAlign.Center)
            Text("Visit counts are hidden until the plan loads.", fontSize = 12.sp, color = TextSubtle, textAlign = TextAlign.Center)
            if (kind == PlanLoadError.UNAUTHORIZED) PrimaryButton("Sign in again", onClick = onSignInAgain, modifier = Modifier.fillMaxWidth())
            else PrimaryButton("Try again", onClick = onRetry, icon = Icons.Default.Refresh, modifier = Modifier.fillMaxWidth())
        }
    }
}

// ---------------------------------------------------------------------------------------------------------------
// Add visit sheet
// ---------------------------------------------------------------------------------------------------------------

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddVisitSheet(
    year: Int,
    month: Int,
    initialDate: String?,
    search: CustomerSearchState,
    isSaving: Boolean,
    serverError: String?,
    onQueryChange: (String) -> Unit,
    onDismiss: () -> Unit,
    onSubmit: (CustomerDto, String, String, String?) -> Unit
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = { if (!isSaving) onDismiss() },
        sheetState = sheetState,
        containerColor = BrandWhite,
        shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp)
    ) {
        AddVisitForm(year, month, initialDate, search, isSaving, serverError, onQueryChange, onDismiss, onSubmit)
    }
}

/** Form body of the Add visit sheet (stateless apart from field state; rendered by the screenshot test). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddVisitForm(
    year: Int,
    month: Int,
    initialDate: String?,
    search: CustomerSearchState,
    isSaving: Boolean,
    serverError: String?,
    onQueryChange: (String) -> Unit,
    onDismiss: () -> Unit,
    onSubmit: (CustomerDto, String, String, String?) -> Unit,
    preselected: CustomerDto? = null
) {
    val today = todayIso()
    val defaultDate = initialDate?.takeIf { isPlannableDate(it, today) }
        ?: formatDateStr(year, month, 1).takeIf { isPlannableDate(it, today) }
        ?: today
    var selected by remember { mutableStateOf(preselected) }
    var date by rememberSaveable { mutableStateOf(defaultDate) }
    var priority by rememberSaveable { mutableStateOf("MEDIUM") }
    var notes by rememberSaveable { mutableStateOf("") }
    var showPicker by remember { mutableStateOf(false) }
    var triedSubmit by remember { mutableStateOf(false) }

    Column(
        Modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .imePadding()
            .navigationBarsPadding()
            .padding(horizontal = 20.dp)
            .padding(bottom = 20.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
    ) {
        SheetHeader("Plan a visit", "Add an outlet visit to your monthly plan.")

        CustomerPicker(
            state = search,
            selected = selected,
            onQueryChange = onQueryChange,
            onSelect = { selected = it },
            onClearSelection = { selected = null }
        )
        if (triedSubmit && selected == null) Text("Choose an outlet to continue.", fontSize = 13.sp, color = ErrorRed)

        FieldBlock("Planned date") {
            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(14.dp))
                    .border(1.dp, BrandLightGray, RoundedCornerShape(14.dp))
                    .background(Navy50)
                    .clickable(role = Role.Button) { showPicker = true }
                    .heightIn(min = 56.dp)
                    .padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(Icons.Default.CalendarToday, contentDescription = null, tint = BrandNavy, modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(12.dp))
                Text(formatDisplayDate(date), fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, color = BrandNavy, modifier = Modifier.weight(1f))
                Text("Change", fontSize = 14.sp, color = BrandGoldDark, fontWeight = FontWeight.SemiBold)
            }
            Text("Visits can be planned for today or later.", fontSize = 12.sp, color = TextSubtle)
        }

        FieldBlock("Priority") {
            PrioritySelector(priority) { priority = it }
        }

        FieldBlock("Visit objective (optional)") {
            OutlinedTextField(
                value = notes,
                onValueChange = { notes = it.take(500) },
                placeholder = { Text("e.g. Payment follow-up, new scheme, stock check") },
                minLines = 3,
                maxLines = 6,
                shape = RoundedCornerShape(14.dp),
                colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = BrandGold, unfocusedBorderColor = BrandLightGray),
                modifier = Modifier.fillMaxWidth()
            )
            Text("${notes.length}/500", fontSize = 12.sp, color = TextSubtle, modifier = Modifier.align(Alignment.End))
        }

        serverError?.let { InlineErrorCard(message = it) }

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlineButton("Cancel", onClick = onDismiss, enabled = !isSaving, modifier = Modifier.weight(1f))
            PrimaryButton(
                text = "Add to plan",
                onClick = {
                    triedSubmit = true
                    val c = selected ?: return@PrimaryButton
                    if (!isPlannableDate(date)) return@PrimaryButton
                    onSubmit(c, date, priority, notes.ifBlank { null })
                },
                loading = isSaving,
                modifier = Modifier.weight(1.4f)
            )
        }
    }

    if (showPicker) {
        PlanDatePicker(date, onDismiss = { showPicker = false }) {
            date = it
            showPicker = false
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PlanDatePicker(current: String, onDismiss: () -> Unit, onPicked: (String) -> Unit) {
    val utc = TimeZone.getTimeZone("UTC")
    val fmt = SimpleDateFormat("yyyy-MM-dd", Locale.US).apply { timeZone = utc }
    val todayMillis = fmt.parse(todayIso())!!.time
    val state = rememberDatePickerState(
        initialSelectedDateMillis = runCatching { fmt.parse(current)!!.time }.getOrNull(),
        selectableDates = object : SelectableDates {
            override fun isSelectableDate(utcTimeMillis: Long) = utcTimeMillis >= todayMillis
        }
    )
    DatePickerDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            TextButton(onClick = { state.selectedDateMillis?.let { onPicked(fmt.format(java.util.Date(it))) } }) {
                Text("Select", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = BrandNavy)
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel", color = TextSecondary) } }
    ) { DatePicker(state = state) }
}

@Composable
internal fun SheetHeader(title: String, subtitle: String) {
    Column {
        Text(title, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 22.sp, color = BrandNavy)
        Text(subtitle, fontSize = 14.sp, color = TextSecondary)
    }
}

@Composable
internal fun FieldBlock(label: String, content: @Composable ColumnScope.() -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(label.uppercase(), style = LabelCaps, color = TextSecondary)
        content()
    }
}

@Composable
internal fun PrioritySelector(value: String, onChange: (String) -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        listOf("LOW" to "Low", "MEDIUM" to "Medium", "HIGH" to "High").forEach { (key, label) ->
            val on = value == key
            val accent = priorityColor(key)
            Row(
                Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(12.dp))
                    .background(if (on) BrandNavy else BrandWhite)
                    .border(1.dp, if (on) BrandNavy else BrandLightGray, RoundedCornerShape(12.dp))
                    .clickable(role = Role.RadioButton) { onChange(key) }
                    .heightIn(min = 48.dp),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(Modifier.size(8.dp).clip(CircleShape).background(accent))
                Spacer(Modifier.width(8.dp))
                Text(label, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, color = if (on) BrandWhite else BrandNavy)
            }
        }
    }
}

// ---------------------------------------------------------------------------------------------------------------
// Visit actions sheet (edit priority/objective, reschedule, cancel)
// ---------------------------------------------------------------------------------------------------------------

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun VisitActionsSheet(
    visit: PlannedVisitDto,
    isSaving: Boolean,
    onDismiss: () -> Unit,
    onReschedule: (String) -> Unit,
    onUpdate: (String, String?) -> Unit,
    onCancelVisit: () -> Unit
) {
    var priority by remember(visit.id) { mutableStateOf(visit.priority.uppercase()) }
    var notes by remember(visit.id) { mutableStateOf(visit.notes.orEmpty()) }
    var showPicker by remember { mutableStateOf(false) }
    var confirmCancel by remember { mutableStateOf(false) }
    val editable = visit.status == "PLANNED"
    ModalBottomSheet(
        onDismissRequest = { if (!isSaving) onDismiss() },
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = BrandWhite
    ) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).imePadding().navigationBarsPadding()
                .padding(horizontal = 20.dp).padding(bottom = 20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            SheetHeader(visit.customerName ?: "Planned visit", "${formatDisplayDate(visit.plannedDate)}${visit.customerOutletCode?.let { " · $it" } ?: ""}")
            if (!editable) {
                Text("This visit is ${visit.status.lowercase()} and can no longer be changed.", fontSize = 14.sp, color = TextSecondary)
            } else {
                FieldBlock("Priority") { PrioritySelector(priority) { priority = it } }
                FieldBlock("Visit objective") {
                    OutlinedTextField(value = notes, onValueChange = { notes = it.take(500) }, minLines = 2, maxLines = 5,
                        shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth(),
                        colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = BrandGold, unfocusedBorderColor = BrandLightGray))
                }
                PrimaryButton("Save changes", onClick = { onUpdate(priority, notes) }, loading = isSaving, modifier = Modifier.fillMaxWidth())
                OutlineButton("Move to another date", onClick = { showPicker = true }, enabled = !isSaving, icon = Icons.Default.CalendarToday, modifier = Modifier.fillMaxWidth())
                TextButton(onClick = { confirmCancel = true }, enabled = !isSaving, modifier = Modifier.align(Alignment.CenterHorizontally)) {
                    Text("Cancel this visit", color = ErrorRed, fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
    if (showPicker) PlanDatePicker(visit.plannedDate, onDismiss = { showPicker = false }) {
        showPicker = false
        onReschedule(it)
    }
    if (confirmCancel) AlertDialog(
        onDismissRequest = { confirmCancel = false },
        title = { Text("Cancel this visit?", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold) },
        text = { Text("It will be removed from your plan.") },
        confirmButton = { TextButton(onClick = { confirmCancel = false; onCancelVisit() }) { Text("Cancel visit", color = ErrorRed, fontWeight = FontWeight.Bold) } },
        dismissButton = { TextButton(onClick = { confirmCancel = false }) { Text("Keep") } }
    )
}
