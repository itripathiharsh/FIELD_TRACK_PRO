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
import androidx.compose.material.icons.filled.AddLocationAlt
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Storefront
import androidx.compose.material.pullrefresh.PullRefreshIndicator
import androidx.compose.material.pullrefresh.pullRefresh
import androidx.compose.material.pullrefresh.rememberPullRefreshState
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.fieldtrackpro.android.data.model.CustomerDto
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
import kotlinx.coroutines.launch

val AD_HOC_REASONS = listOf(
    "Payment Follow-up",
    "Cheque Bounce",
    "Customer Requested",
    "Urgent Collection",
    "New Business Opportunity",
    "Other"
)

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
    var showAdHocDialog by remember { mutableStateOf(false) }
    val snackbarHostState = remember { SnackbarHostState() }
    val coroutineScope = rememberCoroutineScope()

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
        snackbarHost = { SnackbarHost(snackbarHostState) },
        topBar = {
            FieldTrackTopAppBar(
                title = "Field Visit Telemetry",
                onBackClick = onNavigateBack
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { showAdHocDialog = true },
                containerColor = BrandNavy,
                contentColor = BrandGold,
                shape = RoundedCornerShape(12.dp),
                icon = {
                    Icon(
                        imageVector = Icons.Default.AddLocationAlt,
                        contentDescription = "Off-Beat Visit",
                        tint = BrandGold
                    )
                },
                text = {
                    Text(
                        text = "OFF-BEAT VISIT",
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = FontWeight.Bold,
                        fontSize = 12.sp,
                        letterSpacing = 0.5.sp
                    )
                }
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

        if (showAdHocDialog) {
            AdHocVisitDialog(
                viewModel = viewModel,
                onDismiss = {
                    showAdHocDialog = false
                    viewModel.clearCustomerSearch()
                },
                onVisitCreated = { visit ->
                    showAdHocDialog = false
                    viewModel.clearCustomerSearch()
                    onNavigateToVisitDetails(visit.id)
                },
                onError = { err ->
                    coroutineScope.launch {
                        snackbarHostState.showSnackbar(err)
                    }
                }
            )
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
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Text(
                        text = visit.customerName ?: "Customer #${visit.customerId.take(8)}",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold,
                        color = BrandNavy
                    )
                }

                if (visit.isAdHoc) {
                    Spacer(modifier = Modifier.height(3.dp))
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(4.dp))
                                .background(Color(0xFFFEF3C7))
                                .border(1.dp, Color(0xFFFCD34D), RoundedCornerShape(4.dp))
                                .padding(horizontal = 5.dp, vertical = 1.dp)
                        ) {
                            Text(
                                text = "AD-HOC",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                fontSize = 10.sp,
                                color = Color(0xFF92400E)
                            )
                        }
                        visit.adhocReason?.let { reason ->
                            Text(
                                text = "• $reason",
                                fontFamily = LibreBaskervilleFamily,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.SemiBold,
                                color = Color(0xFFB45309)
                            )
                        }
                    }
                }

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

@Composable
fun AdHocVisitDialog(
    viewModel: VisitsViewModel,
    onDismiss: () -> Unit,
    onVisitCreated: (VisitDto) -> Unit,
    onError: (String) -> Unit
) {
    var customerSearchText by remember { mutableStateOf("") }
    var selectedCustomer by remember { mutableStateOf<CustomerDto?>(null) }
    var selectedReason by remember { mutableStateOf(AD_HOC_REASONS[0]) }
    var notesText by remember { mutableStateOf("") }

    val searchResults by viewModel.customerSearchResults.collectAsState()
    val isSearching by viewModel.isSearchingCustomers.collectAsState()
    val isCreating by viewModel.isCreatingAdHocVisit.collectAsState()

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Card(
            modifier = Modifier
                .fillMaxWidth(0.92f)
                .clip(RoundedCornerShape(16.dp))
                .border(1.dp, BrandLightGray, RoundedCornerShape(16.dp)),
            colors = CardDefaults.cardColors(containerColor = BrandWhite),
            shape = RoundedCornerShape(16.dp)
        ) {
            Column(
                modifier = Modifier
                    .padding(20.dp)
                    .fillMaxWidth()
            ) {
                // Header
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column {
                        Text(
                            text = "START OFF-BEAT VISIT",
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.Bold,
                            fontSize = 16.sp,
                            color = BrandNavy
                        )
                        Text(
                            text = "Visit outside today's beat (GPS verified)",
                            fontFamily = LibreBaskervilleFamily,
                            fontSize = 12.sp,
                            color = TextSecondary
                        )
                    }
                    IconButton(onClick = onDismiss) {
                        Icon(
                            imageVector = Icons.Default.Close,
                            contentDescription = "Close",
                            tint = TextSecondary
                        )
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                // Step 1: Customer Selection
                Text(
                    text = "1. SELECT CUSTOMER / OUTLET",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 12.sp,
                    color = BrandNavy
                )
                Spacer(modifier = Modifier.height(6.dp))

                if (selectedCustomer == null) {
                    OutlinedTextField(
                        value = customerSearchText,
                        onValueChange = {
                            customerSearchText = it
                            viewModel.searchCustomersForAdHoc(it)
                        },
                        placeholder = {
                            Text("Type outlet name or code...", fontSize = 13.sp, color = TextSubtle)
                        },
                        leadingIcon = {
                            Icon(Icons.Default.Search, contentDescription = null, tint = TextSecondary, modifier = Modifier.size(18.dp))
                        },
                        trailingIcon = {
                            if (isSearching) {
                                CircularProgressIndicator(modifier = Modifier.size(16.dp), color = BrandGold, strokeWidth = 2.dp)
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp),
                        singleLine = true,
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = BrandGold,
                            unfocusedBorderColor = BrandLightGray,
                            focusedContainerColor = BrandWhite,
                            unfocusedContainerColor = BrandWhite
                        )
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    if (searchResults.isNotEmpty()) {
                        LazyColumn(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(140.dp)
                                .border(1.dp, BrandLightGray, RoundedCornerShape(8.dp))
                        ) {
                            items(searchResults.size) { i ->
                                val cust = searchResults[i]
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable { selectedCustomer = cust }
                                        .padding(horizontal = 12.dp, vertical = 8.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Icon(Icons.Default.Storefront, contentDescription = null, tint = BrandGoldDark, modifier = Modifier.size(18.dp))
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(
                                            text = cust.name,
                                            fontFamily = LeagueSpartanFamily,
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 13.sp,
                                            color = BrandNavy
                                        )
                                        Text(
                                            text = listOfNotNull(cust.outletCode, cust.address).joinToString(" • "),
                                            fontFamily = LibreBaskervilleFamily,
                                            fontSize = 11.sp,
                                            color = TextSecondary,
                                            maxLines = 1
                                        )
                                    }
                                }
                            }
                        }
                    } else if (customerSearchText.isNotBlank() && !isSearching) {
                        Text(
                            text = "No matching outlets found in directory.",
                            fontFamily = LibreBaskervilleFamily,
                            fontSize = 12.sp,
                            color = TextSubtle,
                            modifier = Modifier.padding(vertical = 6.dp)
                        )
                    }
                } else {
                    // Customer Selected Card
                    val cust = selectedCustomer!!
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .border(1.dp, BrandGold, RoundedCornerShape(10.dp)),
                        colors = CardDefaults.cardColors(containerColor = Color(0xFFFFFBEB)),
                        shape = RoundedCornerShape(10.dp)
                    ) {
                        Row(
                            modifier = Modifier
                                .padding(10.dp)
                                .fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = cust.name,
                                    fontFamily = LeagueSpartanFamily,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 14.sp,
                                    color = BrandNavy
                                )
                                Text(
                                    text = listOfNotNull(cust.outletCode, cust.address).joinToString(" • "),
                                    fontFamily = LibreBaskervilleFamily,
                                    fontSize = 11.sp,
                                    color = TextSecondary
                                )
                            }
                            IconButton(onClick = { selectedCustomer = null }) {
                                Icon(Icons.Default.Clear, contentDescription = "Change", tint = BrandNavy, modifier = Modifier.size(18.dp))
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                // Step 2: Ad-Hoc Reason Selection
                Text(
                    text = "2. VISIT REASON",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 12.sp,
                    color = BrandNavy
                )
                Spacer(modifier = Modifier.height(6.dp))

                LazyRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    items(AD_HOC_REASONS.size) { idx ->
                        val reason = AD_HOC_REASONS[idx]
                        val isSelected = selectedReason == reason
                        FilterChip(
                            selected = isSelected,
                            onClick = { selectedReason = reason },
                            label = {
                                Text(
                                    text = reason,
                                    fontFamily = LeagueSpartanFamily,
                                    fontSize = 11.sp,
                                    fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal
                                )
                            },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = BrandNavy,
                                selectedLabelColor = BrandWhite,
                                containerColor = SurfaceSecondary,
                                labelColor = TextPrimary
                            ),
                            shape = RoundedCornerShape(8.dp)
                        )
                    }
                }

                Spacer(modifier = Modifier.height(10.dp))

                // Step 3: Optional Notes
                OutlinedTextField(
                    value = notesText,
                    onValueChange = { notesText = it },
                    placeholder = {
                        Text("Optional visit notes / remarks...", fontSize = 12.sp, color = TextSubtle)
                    },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(8.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = BrandGold,
                        unfocusedBorderColor = BrandLightGray,
                        focusedContainerColor = BrandWhite,
                        unfocusedContainerColor = BrandWhite
                    )
                )

                Spacer(modifier = Modifier.height(18.dp))

                // Action Buttons
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    OutlinedButton(
                        onClick = onDismiss,
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(10.dp)
                    ) {
                        Text("CANCEL", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = TextSecondary)
                    }

                    Button(
                        onClick = {
                            val cust = selectedCustomer
                            if (cust != null) {
                                viewModel.createAdHocVisit(
                                    customerId = cust.id,
                                    adhocReason = selectedReason,
                                    adhocNotes = notesText.ifBlank { null },
                                    onSuccess = onVisitCreated,
                                    onError = onError
                                )
                            }
                        },
                        enabled = selectedCustomer != null && !isCreating,
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(10.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = BrandGold,
                            contentColor = BrandNavy,
                            disabledContainerColor = BrandLightGray
                        )
                    ) {
                        if (isCreating) {
                            CircularProgressIndicator(modifier = Modifier.size(16.dp), color = BrandNavy, strokeWidth = 2.dp)
                        } else {
                            Text("START VISIT", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }
}
