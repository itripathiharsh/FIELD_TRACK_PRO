package com.fieldtrackpro.android.ui.screens.dashboard

import androidx.compose.foundation.background
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.LoadingScreen
import com.fieldtrackpro.android.ui.components.OfflineSyncBanner
import com.fieldtrackpro.android.ui.components.StatusBadge
import com.fieldtrackpro.android.ui.theme.AmberWarning
import com.fieldtrackpro.android.ui.theme.CoralRed
import com.fieldtrackpro.android.ui.theme.ElectricBlue
import com.fieldtrackpro.android.ui.theme.EmeraldGreen
import com.fieldtrackpro.android.ui.theme.Slate50
import com.fieldtrackpro.android.ui.theme.Slate500
import com.fieldtrackpro.android.ui.theme.Slate700
import com.fieldtrackpro.android.ui.theme.Slate900
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.viewmodel.VisitsState
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel

@Composable
fun DashboardScreen(
    visitsViewModel: VisitsViewModel,
    tokenManager: TokenManager,
    onNavigateToVisits: () -> Unit,
    onNavigateToVisitDetails: (String) -> Unit,
    onNavigateToProfile: () -> Unit,
    onNavigateToSync: () -> Unit
) {
    val visitsState by visitsViewModel.visitsState.collectAsState()
    val pendingOfflineCount by visitsViewModel.pendingOfflineCount.collectAsState()

    LaunchedEffect(Unit) {
        visitsViewModel.loadVisits()
    }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "FieldTrack Pro",
                actions = {
                    IconButton(onClick = { visitsViewModel.loadVisits() }) {
                        Icon(imageVector = Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                    IconButton(onClick = onNavigateToProfile) {
                        Icon(imageVector = Icons.Default.Person, contentDescription = "Profile")
                    }
                }
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(Slate50)
                .padding(innerPadding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
        ) {
            // Welcome Header
            Text(
                text = "Welcome back, ${tokenManager.getUserName()}",
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                color = Slate900
            )
            Text(
                text = "Role: ${tokenManager.getUserRole()}",
                fontSize = 13.sp,
                color = Slate500
            )

            Spacer(modifier = Modifier.height(16.dp))

            // Offline Sync Banner
            OfflineSyncBanner(
                pendingCount = pendingOfflineCount,
                onSyncClick = onNavigateToSync
            )

            Spacer(modifier = Modifier.height(16.dp))

            when (val state = visitsState) {
                is VisitsState.Loading -> LoadingScreen(message = "Syncing dashboard telemetry...")
                is VisitsState.Error -> {
                    Text(
                        text = "Dashboard notice: ${state.message}",
                        color = CoralRed,
                        fontSize = 13.sp
                    )
                }
                is VisitsState.Success -> {
                    val visits = state.visits
                    val pendingCount = visits.count { it.status == "PENDING" }
                    val inProgressCount = visits.count { it.status == "IN_PROGRESS" }
                    val completedCount = visits.count { it.status == "COMPLETED" }
                    val flaggedCount = visits.count { it.status == "FLAGGED" }

                    // Metric Cards Grid
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        MetricCard(
                            title = "Pending",
                            value = pendingCount.toString(),
                            color = ElectricBlue,
                            modifier = Modifier.weight(1f)
                        )
                        MetricCard(
                            title = "In Progress",
                            value = inProgressCount.toString(),
                            color = EmeraldGreen,
                            modifier = Modifier.weight(1f)
                        )
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        MetricCard(
                            title = "Completed",
                            value = completedCount.toString(),
                            color = EmeraldGreen,
                            modifier = Modifier.weight(1f)
                        )
                        MetricCard(
                            title = "Flagged",
                            value = flaggedCount.toString(),
                            color = AmberWarning,
                            modifier = Modifier.weight(1f)
                        )
                    }

                    Spacer(modifier = Modifier.height(24.dp))

                    // Quick Actions
                    Text(
                        text = "Quick Actions",
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                        color = Slate900
                    )
                    Spacer(modifier = Modifier.height(12.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        QuickActionButton(
                            title = "Today's Visits",
                            icon = Icons.AutoMirrored.Filled.List,
                            onClick = onNavigateToVisits,
                            modifier = Modifier.weight(1f)
                        )
                        QuickActionButton(
                            title = "Offline Queue",
                            icon = Icons.Default.Sync,
                            onClick = onNavigateToSync,
                            modifier = Modifier.weight(1f)
                        )
                    }

                    Spacer(modifier = Modifier.height(24.dp))

                    // Recent Visits Summary
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "Assigned Visits (${visits.size})",
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                            color = Slate900
                        )
                        Text(
                            text = "View All",
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Bold,
                            color = ElectricBlue,
                            modifier = Modifier.clickable { onNavigateToVisits() }
                        )
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    visits.take(5).forEach { visit ->
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp)
                                .clickable { onNavigateToVisitDetails(visit.id) },
                            shape = RoundedCornerShape(12.dp),
                            colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
                        ) {
                            Row(
                                modifier = Modifier
                                    .padding(16.dp)
                                    .fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = "Customer #${visit.customerId.take(8)}",
                                        fontSize = 15.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = Slate900
                                    )
                                    Text(
                                        text = visit.scheduledAt,
                                        fontSize = 13.sp,
                                        color = Slate500
                                    )
                                }
                                StatusBadge(status = visit.status)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun MetricCard(title: String, value: String, color: Color, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(text = title, fontSize = 12.sp, color = Slate500)
            Spacer(modifier = Modifier.height(4.dp))
            Text(text = value, fontSize = 24.sp, fontWeight = FontWeight.Bold, color = color)
        }
    }
}

@Composable
fun QuickActionButton(title: String, icon: ImageVector, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier.clickable { onClick() },
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(36.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(ElectricBlue.copy(alpha = 0.15f)),
                contentAlignment = Alignment.Center
            ) {
                Icon(imageVector = icon, contentDescription = null, tint = ElectricBlue)
            }
            Spacer(modifier = Modifier.width(10.dp))
            Text(text = title, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = Slate900)
        }
    }
}

