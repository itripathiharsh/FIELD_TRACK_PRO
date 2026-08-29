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
import androidx.compose.foundation.lazy.itemsIndexed
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
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.ui.components.EmptyState
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.LoadingScreen
import com.fieldtrackpro.android.ui.components.StatusBadge
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

    val filterOptions = listOf("ALL", "PENDING", "IN_PROGRESS", "COMPLETED", "FLAGGED", "MISSED")

    LaunchedEffect(Unit) {
        viewModel.loadVisits(refresh = true)
    }

    val pullRefreshState = rememberPullRefreshState(
        refreshing = isRefreshing,
        onRefresh = {
            isRefreshing = true
            viewModel.setTab(selectedTab)
            isRefreshing = false
        }
    )

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "Field Visit Telemetry",
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
            // Tab Row
            TabRow(
                selectedTabIndex = if (selectedTab == VisitTab.TODAY) 0 else 1,
                containerColor = BrandWhite,
                contentColor = BrandNavy,
                indicator = { tabPositions ->
                    TabRowDefaults.SecondaryIndicator(
                        modifier = Modifier.tabIndicatorOffset(tabPositions[if (selectedTab == VisitTab.TODAY) 0 else 1]),
                        color = BrandGold,
                        height = 3.dp
                    )
                }
            ) {
                Tab(
                    selected = selectedTab == VisitTab.TODAY,
                    onClick = { viewModel.setTab(VisitTab.TODAY) },
                    text = {
                        Text(
                            text = "TODAY'S SCHEDULE",
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.Bold,
                            fontSize = 13.sp,
                            letterSpacing = 0.5.sp,
                            color = if (selectedTab == VisitTab.TODAY) BrandNavy else TextSecondary
                        )
                    }
                )
                Tab(
                    selected = selectedTab == VisitTab.ALL,
                    onClick = { viewModel.setTab(VisitTab.ALL) },
                    text = {
                        Text(
                            text = "ALL ASSIGNED VISITS",
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.Bold,
                            fontSize = 13.sp,
                            letterSpacing = 0.5.sp,
                            color = if (selectedTab == VisitTab.ALL) BrandNavy else TextSecondary
                        )
                    }
                )
            }

            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = 16.dp, vertical = 12.dp)
            ) {
                // Search Field
                OutlinedTextField(
                    value = searchQuery,
                    onValueChange = { viewModel.setSearchQuery(it) },
                    placeholder = {
                        Text(
                            "Search customer, outlet or code...",
                            fontFamily = LibreBaskervilleFamily,
                            fontSize = 13.sp,
                            color = TextSubtle
                        )
                    },
                    leadingIcon = {
                        Icon(
                            imageVector = Icons.Default.Search,
                            contentDescription = "Search",
                            tint = TextSecondary,
                            modifier = Modifier.size(18.dp)
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
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(50.dp),
                    shape = RoundedCornerShape(10.dp),
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = TextPrimary,
                        unfocusedTextColor = TextPrimary,
                        focusedBorderColor = BrandGold,
                        unfocusedBorderColor = BrandLightGray,
                        focusedContainerColor = BrandWhite,
                        unfocusedContainerColor = BrandWhite
                    )
                )

                Spacer(modifier = Modifier.height(10.dp))

                // Status Filter Chips
                LazyRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    items(filterOptions.size) { index ->
                        val status = filterOptions[index]
                        val isSelected = (selectedStatus == null && status == "ALL") || selectedStatus == status
                        FilterChip(
                            selected = isSelected,
                            onClick = { viewModel.setStatusFilter(status) },
                            label = {
                                Text(
                                    text = status.replace("_", " "),
                                    fontFamily = LeagueSpartanFamily,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    letterSpacing = 0.5.sp
                                )
                            },
                            shape = RoundedCornerShape(8.dp),
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
                        val count = s.totalCount
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
                                    itemsIndexed(visits) { index, visit ->
                                        CompactVisitCard(
                                            visit = visit,
                                            onClick = { onNavigateToVisitDetails(visit.id) }
                                        )

                                        if (s.hasMore && index == visits.size - 1) {
                                            LaunchedEffect(visits.size) {
                                                viewModel.loadNextPage()
                                            }
                                        }
                                    }

                                    if (s.hasMore) {
                                        item {
                                            Box(
                                                modifier = Modifier
                                                    .fillMaxWidth()
                                                    .padding(8.dp),
                                                contentAlignment = Alignment.Center
                                            ) {
                                                CircularProgressIndicator(
                                                    color = BrandGold,
                                                    modifier = Modifier.size(20.dp),
                                                    strokeWidth = 2.dp
                                                )
                                            }
                                        }
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
        Row(
            modifier = Modifier
                .padding(14.dp)
                .fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = visit.customerName ?: "Customer #${visit.customerId.take(8)}",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Bold,
                    color = BrandNavy
                )
                val address = visit.customerAddress
                if (!address.isNullOrBlank()) {
                    Spacer(modifier = Modifier.height(2.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.Default.LocationOn,
                            contentDescription = null,
                            tint = BrandGoldDark,
                            modifier = Modifier.size(13.dp)
                        )
                        Spacer(modifier = Modifier.width(3.dp))
                        Text(
                            text = address,
                            fontFamily = LibreBaskervilleFamily,
                            fontSize = 12.sp,
                            color = TextSecondary,
                            maxLines = 1
                        )
                    }
                }
                Spacer(modifier = Modifier.height(4.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.Schedule,
                        contentDescription = null,
                        tint = TextSecondary,
                        modifier = Modifier.size(13.dp)
                    )
                    Spacer(modifier = Modifier.width(3.dp))
                    Text(
                        text = "Scheduled: ${com.fieldtrackpro.android.utils.DateTimeUtils.formatDisplayDateTime(visit.scheduledAt)}",
                        fontFamily = LibreBaskervilleFamily,
                        fontSize = 12.sp,
                        color = TextSecondary
                    )
                }
            }
            Spacer(modifier = Modifier.width(10.dp))
            StatusBadge(status = visit.status)
        }
    }
}

private fun String?.isNull_or_empty(): Boolean = this == null || this.trim().isEmpty()
