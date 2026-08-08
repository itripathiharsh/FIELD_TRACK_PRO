package com.fieldtrackpro.android.ui.screens.visits

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Scaffold
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.components.EmptyState
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.LoadingScreen
import com.fieldtrackpro.android.ui.components.StatusBadge
import com.fieldtrackpro.android.ui.theme.Slate50
import com.fieldtrackpro.android.ui.theme.Slate500
import com.fieldtrackpro.android.ui.theme.Slate900
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.viewmodel.VisitsState
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel

@Composable
fun TodayVisitsScreen(
    viewModel: VisitsViewModel,
    onNavigateBack: () -> Unit,
    onNavigateToVisitDetails: (String) -> Unit
) {
    val state by viewModel.visitsState.collectAsState()
    var selectedFilter by remember { mutableStateOf<String?>(null) }

    val filterOptions = listOf("ALL", "PENDING", "IN_PROGRESS", "COMPLETED", "FLAGGED")

    LaunchedEffect(selectedFilter) {
        viewModel.loadVisits(if (selectedFilter == "ALL") null else selectedFilter)
    }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "Today's Visits",
                onBackClick = onNavigateBack
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(Slate50)
                .padding(innerPadding)
                .padding(16.dp)
        ) {
            // Filter Pills
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(filterOptions) { filter ->
                    FilterChip(
                        selected = (selectedFilter == filter) || (selectedFilter == null && filter == "ALL"),
                        onClick = { selectedFilter = if (filter == "ALL") null else filter },
                        label = { Text(filter.replace("_", " ")) }
                    )
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            when (val s = state) {
                is VisitsState.Loading -> LoadingScreen(message = "Fetching visit schedule...")
                is VisitsState.Error -> EmptyState(title = "Notice", subtitle = s.message)
                is VisitsState.Success -> {
                    val visits = s.visits
                    if (visits.isEmpty()) {
                        EmptyState(
                            title = "No Visits Found",
                            subtitle = "No assigned visits match the selected filter criteria."
                        )
                    } else {
                        LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            items(visits) { visit ->
                                Card(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable { onNavigateToVisitDetails(visit.id) },
                                    shape = RoundedCornerShape(12.dp),
                                    colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
                                ) {
                                    Column(modifier = Modifier.padding(16.dp)) {
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.SpaceBetween,
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Text(
                                                text = visit.customerName ?: "Customer #${visit.customerId.take(8)}",
                                                fontSize = 16.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = Slate900
                                            )
                                            StatusBadge(status = visit.status)
                                        }

                                        Spacer(modifier = Modifier.height(6.dp))

                                        Text(
                                            text = "Purpose: ${visit.purpose}",
                                            fontSize = 13.sp,
                                            color = Slate500
                                        )

                                        if (!visit.customerAddress.isNull_or_empty()) {
                                            Spacer(modifier = Modifier.height(4.dp))
                                            Text(
                                                text = "📍 ${visit.customerAddress}",
                                                fontSize = 12.sp,
                                                color = Slate500
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

private fun String?.isNull_or_empty(): Boolean = this == null || this.trim().isEmpty()
