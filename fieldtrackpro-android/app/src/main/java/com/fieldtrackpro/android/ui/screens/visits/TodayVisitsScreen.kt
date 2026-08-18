package com.fieldtrackpro.android.ui.screens.visits

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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.ExperimentalMaterialApi
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.pullrefresh.PullRefreshIndicator
import androidx.compose.material.pullrefresh.pullRefresh
import androidx.compose.material.pullrefresh.rememberPullRefreshState
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.TabRowDefaults
import androidx.compose.material3.TabRowDefaults.tabIndicatorOffset
import androidx.compose.material3.Text
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
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.ui.components.EmptyState
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.LoadingScreen
import com.fieldtrackpro.android.ui.components.StatusBadge
import com.fieldtrackpro.android.ui.theme.BrandBlack
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandGoldDark
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.theme.TextSubtle
import com.fieldtrackpro.android.ui.viewmodel.VisitTab
import com.fieldtrackpro.android.ui.viewmodel.VisitsState
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel

@OptIn(ExperimentalMaterialApi::class)
@Composable
fun TodayVisitsScreen(
    viewModel: VisitsViewModel,
    onNavigateBack: () -> Unit,
    onNavigateToVisitDetails: (String) -> Unit
) {
    val state by viewModel.visitsState.collectAsState()
    val selectedTab by viewModel.selectedTab.collectAsState()
    val selectedStatus by viewModel.selectedStatus.collectAsState()
    val searchQuery by viewModel.searchQuery.collectAsState()
    var isRefreshing by remember { mutableStateOf(false) }

    val filterOptions = listOf("ALL", "PENDING", "IN_PROGRESS", "COMPLETED", "FLAGGED")

    LaunchedEffect(Unit) {
        viewModel.loadVisits()
    }

    val pullRefreshState = rememberPullRefreshState(
        refreshing = isRefreshing,
        onRefresh = {
            isRefreshing = true
            viewModel.loadVisits()
        }
    )

    LaunchedEffect(state) {
        if (state !is VisitsState.Loading) {
            isRefreshing = false
        }
    }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = if (selectedTab == VisitTab.TODAY) "Today's Schedule" else "All Assigned Visits",
                onBackClick = onNavigateBack
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(SurfaceSecondary)
                .padding(innerPadding)
        ) {
            // Tabs: [ Today's Visits ] [ All Visits ] with Gold Accent Indicator
            TabRow(
                selectedTabIndex = if (selectedTab == VisitTab.TODAY) 0 else 1,
                containerColor = BrandWhite,
                contentColor = BrandNavy,
                indicator = { tabPositions ->
                    TabRowDefaults.SecondaryIndicator(
                        modifier = Modifier.tabIndicatorOffset(tabPositions[if (selectedTab == VisitTab.TODAY) 0 else 1]),
                        height = 3.dp,
                        color = BrandGold
                    )
                },
                modifier = Modifier.border(1.dp, BrandLightGray)
            ) {
                Tab(
                    selected = selectedTab == VisitTab.TODAY,
                    onClick = { viewModel.setTab(VisitTab.TODAY) },
                    text = {
                        Text(
                            text = "TODAY'S VISITS",
                            fontFamily = LeagueSpartanFamily,
                            fontSize = 14.sp,
                            fontWeight = if (selectedTab == VisitTab.TODAY) FontWeight.Bold else FontWeight.SemiBold,
                            letterSpacing = 0.5.sp,
                            color = if (selectedTab == VisitTab.TODAY) BrandNavy else BrandNavy.copy(alpha = 0.65f)
                        )
                    }
                )
                Tab(
                    selected = selectedTab == VisitTab.ALL,
                    onClick = { viewModel.setTab(VisitTab.ALL) },
                    text = {
                        Text(
                            text = "ALL VISITS",
                            fontFamily = LeagueSpartanFamily,
                            fontSize = 14.sp,
                            fontWeight = if (selectedTab == VisitTab.ALL) FontWeight.Bold else FontWeight.SemiBold,
                            letterSpacing = 0.5.sp,
                            color = if (selectedTab == VisitTab.ALL) BrandNavy else BrandNavy.copy(alpha = 0.65f)
                        )
                    }
                )
            }

            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 16.dp, vertical = 12.dp)
            ) {
                // Search Bar with Gold Focus Border
                OutlinedTextField(
                    value = searchQuery,
                    onValueChange = { viewModel.setSearchQuery(it) },
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { 
                        Text(
                            "Search customer, code, or area...",
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.Medium,
                            fontSize = 14.sp,
                            color = TextSubtle
                        ) 
                    },
                    leadingIcon = {
                        Icon(
                            imageVector = Icons.Default.Search,
                            contentDescription = "Search",
                            tint = BrandNavy,
                            modifier = Modifier.size(20.dp)
                        )
                    },
                    trailingIcon = {
                        if (searchQuery.isNotEmpty()) {
                            IconButton(onClick = { viewModel.setSearchQuery("") }) {
                                Icon(
                                    imageVector = Icons.Default.Clear,
                                    contentDescription = "Clear",
                                    tint = TextSecondary,
                                    modifier = Modifier.size(18.dp)
                                )
                            }
                        }
                    },
                    singleLine = true,
                    shape = RoundedCornerShape(10.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedContainerColor = BrandWhite,
                        unfocusedContainerColor = BrandWhite,
                        focusedBorderColor = BrandGold,
                        unfocusedBorderColor = BrandLightGray,
                        focusedTextColor = TextPrimary,
                        unfocusedTextColor = TextPrimary
                    )
                )

                Spacer(modifier = Modifier.height(10.dp))

                // Status Filter Chips
                LazyRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    items(filterOptions) { filter ->
                        val isSelected = (selectedStatus == filter) || (selectedStatus == null && filter == "ALL")
                        FilterChip(
                            selected = isSelected,
                            onClick = { viewModel.setStatusFilter(filter) },
                            label = { 
                                Text(
                                    filter.replace("_", " "),
                                    fontFamily = LeagueSpartanFamily,
                                    fontWeight = if (isSelected) FontWeight.Bold else FontWeight.SemiBold,
                                    fontSize = 13.sp,
                                    letterSpacing = 0.4.sp
                                ) 
                            },
                            shape = RoundedCornerShape(8.dp),
                            border = FilterChipDefaults.filterChipBorder(
                                enabled = true,
                                selected = isSelected,
                                borderColor = if (isSelected) BrandGold else BrandLightGray,
                                selectedBorderColor = BrandGold
                            ),
                            colors = FilterChipDefaults.filterChipColors(
                                containerColor = BrandWhite,
                                selectedContainerColor = BrandNavy,
                                selectedLabelColor = BrandWhite,
                                labelColor = BrandNavy
                            )
                        )
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                // Count Header
                when (val s = state) {
                    is VisitsState.Success -> {
                        val count = s.visits.size
                        val label = if (s.isTodayTab) "TODAY'S SCHEDULE" else "ASSIGNED VISITS"
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 2.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "$label ($count)",
                                fontFamily = LeagueSpartanFamily,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold,
                                letterSpacing = 1.sp,
                                color = BrandNavy
                            )
                        }
                    }
                    else -> {}
                }

                Spacer(modifier = Modifier.height(6.dp))

                // Content List
                when (val s = state) {
                    is VisitsState.Loading -> LoadingScreen(message = "Loading visits telemetry...")
                    is VisitsState.Error -> EmptyState(title = "Notice", subtitle = s.message)
                    is VisitsState.Success -> {
                        val visits = s.visits
                        if (visits.isEmpty()) {
                            val emptyMsg = if (s.isTodayTab) {
                                "No visits scheduled for today."
                            } else {
                                "No assigned visits match the selected filter criteria."
                            }
                            EmptyState(
                                title = if (s.isTodayTab) "No Visits Scheduled Today" else "No Visits Found",
                                subtitle = emptyMsg
                            )
                        } else {
                            Box(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .pullRefresh(pullRefreshState)
                            ) {
                                LazyColumn(
                                    modifier = Modifier.fillMaxSize(),
                                    verticalArrangement = Arrangement.spacedBy(10.dp)
                                ) {
                                    items(visits) { visit ->
                                        CompactVisitCard(
                                            visit = visit,
                                            onClick = { onNavigateToVisitDetails(visit.id) }
                                        )
                                    }
                                }

                                PullRefreshIndicator(
                                    refreshing = isRefreshing,
                                    state = pullRefreshState,
                                    modifier = Modifier.align(Alignment.TopCenter),
                                    contentColor = BrandGold
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun CompactVisitCard(
    visit: VisitDto,
    onClick: () -> Unit
) {
    Card(
        onClick = onClick,
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = BrandWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = visit.customerName ?: "Outlet #${visit.customerId.take(8)}",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold,
                    color = BrandNavy,
                    modifier = Modifier.weight(1f)
                )
                StatusBadge(status = visit.status)
            }

            Spacer(modifier = Modifier.height(6.dp))

            val areaContext = listOfNotNull(visit.areaName, visit.territoryName).joinToString(", ")
            if (areaContext.isNotEmpty()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.LocationOn,
                        contentDescription = "Location",
                        tint = BrandGoldDark,
                        modifier = Modifier.size(15.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = areaContext,
                        fontFamily = LibreBaskervilleFamily,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Normal,
                        color = TextPrimary
                    )
                }
                Spacer(modifier = Modifier.height(4.dp))
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Default.Schedule,
                    contentDescription = "Scheduled Time",
                    tint = TextSecondary,
                    modifier = Modifier.size(14.dp)
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    text = "Scheduled: ${visit.scheduledAt}",
                    fontFamily = LibreBaskervilleFamily,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Normal,
                    color = TextSecondary
                )
            }
        }
    }
}
