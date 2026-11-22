package com.fieldtrackpro.android.performance

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.performance.EmployeeDashboardCalculator.AgeBucket
import com.fieldtrackpro.android.performance.EmployeeDashboardCalculator.CollectionSummary
import com.fieldtrackpro.android.performance.EmployeeDashboardCalculator.FieldPerformance
import com.fieldtrackpro.android.performance.EmployeeDashboardCalculator.OutletRow
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.InlineErrorCard
import com.fieldtrackpro.android.ui.components.SectionHeader
import com.fieldtrackpro.android.ui.components.SkeletonBlock
import com.fieldtrackpro.android.ui.components.StatusChip
import com.fieldtrackpro.android.ui.components.customerSubtitle
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandGoldDark
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.KpiNumber
import com.fieldtrackpro.android.ui.theme.LabelCaps
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.Navy100
import com.fieldtrackpro.android.ui.theme.Navy50
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SuccessGreenText
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.SystemBarIcons
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.theme.TextSubtle
import com.fieldtrackpro.android.utils.MoneyFormat
import java.math.BigDecimal
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

private val DATE = DateTimeFormatter.ofPattern("d MMM yyyy", Locale.getDefault())
private val MONTH = DateTimeFormatter.ofPattern("MMMM yyyy", Locale.getDefault())
private fun money(v: BigDecimal?) = if (v == null) "—" else MoneyFormat.inr(v)

@Composable
fun EmployeeDashboardScreen(viewModel: EmployeeDashboardViewModel, onNavigateBack: () -> Unit) {
    val state by viewModel.state.collectAsState()
    LaunchedEffect(Unit) { viewModel.onOpened() }
    var outlet by remember { mutableStateOf<OutletRow?>(null) }
    EmployeeDashboardContent(state, onBack = onNavigateBack, onRefresh = viewModel::refresh, onOutlet = { outlet = it })
    outlet?.let { OutletDetailSheet(it) { outlet = null } }
}

/** Stateless dashboard (rendered by the screenshot test). */
@Composable
fun EmployeeDashboardContent(
    state: EmployeeDashboardState,
    onBack: () -> Unit = {},
    onRefresh: () -> Unit = {},
    onOutlet: (OutletRow) -> Unit = {},
    initialQuery: String = ""
) {
    SystemBarIcons(darkIcons = true)
    var query by rememberSaveable { mutableStateOf(initialQuery) }
    var area by rememberSaveable { mutableStateOf<String?>(null) }
    Scaffold(
        topBar = {
            FieldTrackTopAppBar(title = "My performance", onBackClick = onBack, actions = {
                IconButton(onClick = onRefresh) { Icon(Icons.Default.Refresh, contentDescription = "Refresh", tint = BrandNavy) }
            })
        },
        containerColor = SurfaceSecondary
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState())
                .padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            if (state.notForThisRole) {
                InfoNote("This dashboard shows a field employee's own collections, outlets and visits. Admin and accountant accounts use the reports in the web console.")
                return@Column
            }
            Text(state.month.format(MONTH), fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 22.sp, color = BrandNavy)

            // A. Collections (employee-linked, verified)
            SectionHeader("My collections")
            when (val c = state.collections) {
                is Section.Ready -> CollectionsCard(c.value)
                is Section.Failed -> InlineErrorCard(message = "Collections couldn't load: ${c.message}", onRetry = onRefresh)
                else -> SkeletonBlock(height = 170.dp)
            }
            InfoNote("Counts only payments recorded by you in the app (linked to you). Tally receipts without a field collection are never counted as yours. Collection history by outlet needs a server report that is not available yet.")

            // B. Field performance
            SectionHeader("Field performance")
            when (val p = state.performance) {
                is Section.Ready -> PerformanceCard(p.value)
                is Section.Failed -> InlineErrorCard(message = p.message, onRetry = onRefresh)
                else -> SkeletonBlock(height = 120.dp)
            }

            // C. Portfolio outstanding (customer-level)
            SectionHeader("Outlet portfolio outstanding")
            when (val pf = state.portfolio) {
                is Section.Ready -> {
                    PortfolioCard(pf.value.summary)
                    AgeingCard(pf.value.summary.ageing)
                }
                is Section.Progress -> ProgressCard(pf.done, pf.total)
                is Section.Failed -> InlineErrorCard(message = "Outlets couldn't load: ${pf.message}", onRetry = onRefresh)
                else -> SkeletonBlock(height = 150.dp)
            }
            InfoNote("What your current outlets owe the company, from their accounts and bills. This is not money you collected, and it reflects today's assignments, not past ownership.")

            // D. My outlets
            val ready = state.portfolio as? Section.Ready
            if (ready != null) {
                SectionHeader("My outlets · ${ready.value.rows.size}")
                OutletFilters(query, { query = it }, area, { area = it }, ready.value.rows)
                val list = EmployeeDashboardCalculator.filterOutlets(ready.value.rows, query, area)
                if (list.isEmpty()) {
                    Text(if (ready.value.rows.isEmpty()) "No outlets are assigned to you yet." else "No outlets match your search.", fontSize = 14.sp, color = TextSecondary)
                } else {
                    OutletList(list.take(60), onOutlet)
                    if (list.size > 60) Text("Showing 60 of ${list.size}. Search to find a specific outlet.", fontSize = 12.sp, color = TextSubtle)
                }
            }
        }
    }
}

@Composable
private fun Card(content: @Composable () -> Unit) {
    Surface(shape = RoundedCornerShape(16.dp), color = BrandWhite, modifier = Modifier.fillMaxWidth().border(1.dp, BrandLightGray, RoundedCornerShape(16.dp))) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) { content() }
    }
}

@Composable
private fun Metric(label: String, value: String, modifier: Modifier = Modifier, color: Color = BrandNavy, sub: String? = null) {
    Column(modifier) {
        Text(label.uppercase(), style = LabelCaps.copy(fontSize = 11.sp), color = TextSubtle, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(value, style = KpiNumber.copy(fontSize = if (value.length > 11) 18.sp else 22.sp), color = color, maxLines = 1)
        sub?.let { Text(it, fontSize = 12.sp, color = TextSecondary) }
    }
}

@Composable
private fun CollectionsCard(c: CollectionSummary) = Card {
    Row {
        Metric("Verified this month", money(c.monthVerified), Modifier.weight(1f), SuccessGreenText)
        Metric("Verified today", money(c.todayVerified), Modifier.weight(1f))
    }
    Row {
        Metric("Recorded this month", money(c.monthRecorded), Modifier.weight(1f))
        Metric("Not yet verified", money(c.monthNotVerified), Modifier.weight(1f), if (c.monthNotVerified.signum() > 0) BrandGoldDark else BrandNavy)
    }
    if (c.dailyVerified.any { it.second.signum() > 0 }) {
        Text("DAILY VERIFIED", style = LabelCaps.copy(fontSize = 11.sp), color = TextSubtle)
        DailyBars(c.dailyVerified)
    } else {
        Text("No verified collections yet this month.", fontSize = 14.sp, color = TextSecondary)
    }
    if (!c.isComplete) Text("${c.missingDays} day(s) could not be loaded, so totals may be lower than actual.", fontSize = 12.sp, color = ErrorRed)
}

@Composable
private fun DailyBars(days: List<Pair<LocalDate, BigDecimal>>) {
    val max = days.maxOf { it.second }.takeIf { it.signum() > 0 } ?: BigDecimal.ONE
    Row(Modifier.fillMaxWidth().height(64.dp), horizontalArrangement = Arrangement.spacedBy(3.dp), verticalAlignment = Alignment.Bottom) {
        days.forEach { (_, v) ->
            val f = (v.toDouble() / max.toDouble()).toFloat().coerceIn(0f, 1f)
            Box(Modifier.weight(1f).fillMaxHeight(if (v.signum() > 0) f.coerceAtLeast(0.06f) else 0.03f)
                .clip(RoundedCornerShape(topStart = 3.dp, topEnd = 3.dp)).background(if (v.signum() > 0) SuccessGreen else Navy100))
        }
    }
}

@Composable
private fun PerformanceCard(p: FieldPerformance) = Card {
    Row {
        Metric("Planned", p.planned?.toString() ?: "—", Modifier.weight(1f))
        Metric("Completed", p.completed?.toString() ?: "—", Modifier.weight(1f))
        Metric("Completion", p.completionRatePercent?.let { "$it%" } ?: "—", Modifier.weight(1f))
    }
    p.completionRatePercent?.let {
        LinearProgressIndicator(progress = { it / 100f }, color = BrandGold, trackColor = Navy100,
            modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)))
    }
    Row {
        Metric("Workdays", p.workdays.toString(), Modifier.weight(1f))
        Metric("Visits done", p.visitsCompleted.toString(), Modifier.weight(1f))
        Metric("Missed", p.missed?.toString() ?: "—", Modifier.weight(1f))
    }
    if (p.planned == null) Text("Plan figures are unavailable right now; workday figures are from your daily records.", fontSize = 12.sp, color = TextSubtle)
}

@Composable
private fun PortfolioCard(s: EmployeeDashboardCalculator.PortfolioSummary) = Card {
    Row {
        Metric("Total outstanding", money(s.totalOutstanding), Modifier.weight(1f))
        Metric("Past due date", money(s.pastDue), Modifier.weight(1f), if (s.pastDue.signum() > 0) ErrorRed else BrandNavy)
    }
    Text("${s.outletsWithBalance} of ${s.outlets} outlets have a balance.", fontSize = 13.sp, color = TextSecondary)
    if (s.unavailable > 0) Text("${s.unavailable} outlet(s) could not be loaded and are not included.", fontSize = 12.sp, color = ErrorRed)
}

@Composable
private fun AgeingCard(buckets: Map<AgeBucket, BigDecimal>) = Card {
    Text("AGEING BY BILL DUE DATE", style = LabelCaps.copy(fontSize = 11.sp), color = TextSubtle)
    val total = buckets.values.fold(BigDecimal.ZERO) { a, b -> a + b }
    if (total.signum() == 0) {
        Text("No open bills.", fontSize = 14.sp, color = TextSecondary)
        return@Card
    }
    AgeBucket.entries.filter { (buckets[it] ?: BigDecimal.ZERO).signum() > 0 }.forEach { b ->
        val v = buckets.getValue(b)
        val color = when (b) {
            AgeBucket.NOT_DUE -> SuccessGreen
            AgeBucket.D1_30 -> BrandGold
            AgeBucket.D31_60 -> BrandGoldDark
            AgeBucket.D61_90, AgeBucket.D90_PLUS -> ErrorRed
            AgeBucket.NO_DUE_DATE -> TextSubtle
        }
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row {
                Text(b.label, fontSize = 14.sp, color = BrandNavy, modifier = Modifier.weight(1f))
                Text(MoneyFormat.inr(v), fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, color = BrandNavy)
            }
            LinearProgressIndicator(progress = { (v.toDouble() / total.toDouble()).toFloat() }, color = color, trackColor = Navy50,
                modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)))
        }
    }
}

@Composable
private fun ProgressCard(done: Int, total: Int) = Card {
    Text("Loading outlet accounts… $done of $total", fontSize = 14.sp, color = TextSecondary)
    LinearProgressIndicator(progress = { if (total == 0) 0f else done.toFloat() / total }, color = BrandGold, trackColor = Navy100,
        modifier = Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(3.dp)))
}

@Composable
private fun InfoNote(text: String) {
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Navy50).padding(12.dp)) {
        Icon(Icons.Default.Info, contentDescription = null, tint = TextSecondary, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(10.dp))
        Text(text, fontSize = 12.sp, lineHeight = 17.sp, color = TextSecondary)
    }
}

@Composable
private fun OutletFilters(query: String, onQuery: (String) -> Unit, area: String?, onArea: (String?) -> Unit, rows: List<OutletRow>) {
    OutlinedTextField(
        value = query, onValueChange = onQuery, singleLine = true,
        placeholder = { Text("Search outlet name or code") },
        leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = TextSecondary) },
        trailingIcon = { if (query.isNotEmpty()) IconButton(onClick = { onQuery("") }) { Icon(Icons.Default.Close, contentDescription = "Clear search") } },
        shape = RoundedCornerShape(14.dp),
        colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = BrandGold, unfocusedBorderColor = BrandLightGray, unfocusedContainerColor = BrandWhite, focusedContainerColor = BrandWhite),
        modifier = Modifier.fillMaxWidth()
    )
    val areas = rows.mapNotNull { it.customer.areaName ?: it.customer.territoryName }.distinct().sorted()
    if (areas.size > 1) {
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            (listOf<String?>(null) + areas).forEach { a ->
                val on = a == area
                Text(a ?: "All areas", fontSize = 13.sp, fontWeight = if (on) FontWeight.Bold else FontWeight.Medium,
                    color = if (on) BrandWhite else BrandNavy,
                    modifier = Modifier.clip(RoundedCornerShape(50)).background(if (on) BrandNavy else BrandWhite)
                        .border(1.dp, if (on) BrandNavy else BrandLightGray, RoundedCornerShape(50))
                        .clickable(role = Role.RadioButton) { onArea(a) }.heightIn(min = 36.dp).padding(horizontal = 12.dp, vertical = 8.dp))
            }
        }
    }
}

@Composable
private fun OutletList(rows: List<OutletRow>, onOutlet: (OutletRow) -> Unit) {
    Surface(shape = RoundedCornerShape(16.dp), color = BrandWhite, modifier = Modifier.fillMaxWidth().border(1.dp, BrandLightGray, RoundedCornerShape(16.dp))) {
        Column {
            rows.forEachIndexed { i, r ->
                if (i > 0) HorizontalDivider(color = BrandLightGray, modifier = Modifier.padding(start = 16.dp))
                Row(Modifier.fillMaxWidth().clickable { onOutlet(r) }.heightIn(min = 64.dp).padding(horizontal = 16.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(r.customer.name, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, color = BrandNavy, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(customerSubtitle(r.customer), fontSize = 12.sp, color = TextSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        val last = listOfNotNull(r.lastVisitDate?.let { "Visited ${it.format(DATE)}" }, r.lastPaymentDate?.let { "Paid ${it.format(DATE)}" }).joinToString(" · ")
                        if (last.isNotBlank()) Text(last, fontSize = 12.sp, color = TextSubtle, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                    Spacer(Modifier.width(8.dp))
                    Column(horizontalAlignment = Alignment.End) {
                        if (r.unavailableReason != null) StatusChip("Unavailable", container = Navy100, content = TextSecondary)
                        else Text(money(r.outstanding), fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 15.sp,
                            color = if ((r.overdue ?: BigDecimal.ZERO).signum() > 0) ErrorRed else BrandNavy)
                        if ((r.overdue ?: BigDecimal.ZERO).signum() > 0) Text("${money(r.overdue)} overdue", fontSize = 11.sp, color = ErrorRed)
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun OutletDetailSheet(r: OutletRow, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = BrandWhite) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).navigationBarsPadding().padding(horizontal = 20.dp).padding(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(r.customer.name, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 22.sp, color = BrandNavy)
            Text(customerSubtitle(r.customer), fontSize = 14.sp, color = TextSecondary)
            if (r.unavailableReason != null) {
                InlineErrorCard(message = r.unavailableReason)
                return@Column
            }
            Row {
                Metric("Outstanding", money(r.outstanding), Modifier.weight(1f))
                Metric("Overdue", money(r.overdue), Modifier.weight(1f), if ((r.overdue ?: BigDecimal.ZERO).signum() > 0) ErrorRed else BrandNavy)
            }
            Row {
                Metric("Last visit", r.lastVisitDate?.format(DATE) ?: "—", Modifier.weight(1f))
                Metric("Last payment", r.lastPaymentDate?.format(DATE) ?: "—", Modifier.weight(1f), sub = r.lastPaymentAmount?.let { MoneyFormat.inr(it) })
            }
            r.ageing?.let { if (it.values.any { v -> v.signum() > 0 }) AgeingCard(it) }
            InfoNote("Customer account figures. The last payment may have been collected by anyone or received directly in Tally.")
        }
    }
}
