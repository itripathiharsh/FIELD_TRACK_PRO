package com.fieldtrackpro.android.ui.screens.visits

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.components.EmptyState
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.LoadingScreen
import com.fieldtrackpro.android.ui.components.StatusBadge
import com.fieldtrackpro.android.ui.theme.AmberWarning
import com.fieldtrackpro.android.ui.theme.ElectricBlue
import com.fieldtrackpro.android.ui.theme.EmeraldGreen
import com.fieldtrackpro.android.ui.theme.Slate50
import com.fieldtrackpro.android.ui.theme.Slate500
import com.fieldtrackpro.android.ui.theme.Slate900
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.viewmodel.VisitDetailState
import com.fieldtrackpro.android.ui.viewmodel.VisitDetailsViewModel

@Composable
fun VisitDetailsScreen(
    visitId: String,
    viewModel: VisitDetailsViewModel,
    onNavigateBack: () -> Unit,
    onNavigateToCheckIn: (String, String) -> Unit,
    onNavigateToCheckOut: (String, String) -> Unit,
    onNavigateToMedia: (String) -> Unit
) {
    val detailState by viewModel.detailState.collectAsState()

    LaunchedEffect(visitId) {
        viewModel.loadVisitDetails(visitId)
    }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "Visit Details",
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
                .verticalScroll(rememberScrollState())
        ) {
            when (val s = detailState) {
                is VisitDetailState.Loading -> LoadingScreen(message = "Retrieving visit data...")
                is VisitDetailState.Error -> EmptyState(title = "Visit Error", subtitle = s.message)
                is VisitDetailState.Success -> {
                    val visit = s.visit
                    val logs = s.geoLogs

                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(16.dp),
                        colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
                    ) {
                        Column(modifier = Modifier.padding(20.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = visit.customerName ?: "Customer #${visit.customerId.take(8)}",
                                    fontSize = 18.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = Slate900
                                )
                                StatusBadge(status = visit.status)
                            }

                            Spacer(modifier = Modifier.height(12.dp))

                            DetailItem(label = "Purpose", value = visit.purpose)
                            DetailItem(label = "Customer ID", value = visit.customerId)
                            DetailItem(label = "Address", value = visit.customerAddress ?: "Not specified")
                            DetailItem(label = "Scheduled Start", value = visit.scheduledStartTime)
                            DetailItem(label = "Scheduled End", value = visit.scheduledEndTime)

                            if (visit.actualCheckInTime != null) {
                                DetailItem(label = "Checked In", value = visit.actualCheckInTime)
                            }
                            if (visit.actualCheckOutTime != null) {
                                DetailItem(label = "Checked Out", value = visit.actualCheckOutTime)
                            }
                            if (visit.verificationFailureCount > 0) {
                                DetailItem(
                                    label = "Verification Failures",
                                    value = "${visit.verificationFailureCount} failed attempt(s)"
                                )
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(20.dp))

                    // Action Buttons based on status
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        if (visit.status == "PENDING" || visit.status == "FLAGGED") {
                            Button(
                                onClick = { onNavigateToCheckIn(visit.id, visit.customerId) },
                                modifier = Modifier.weight(1f),
                                colors = ButtonDefaults.buttonColors(containerColor = ElectricBlue)
                            ) {
                                Text("CHECK-IN GPS")
                            }
                        }

                        if (visit.status == "IN_PROGRESS" || visit.status == "FLAGGED") {
                            Button(
                                onClick = { onNavigateToCheckOut(visit.id, visit.customerId) },
                                modifier = Modifier.weight(1f),
                                colors = ButtonDefaults.buttonColors(containerColor = EmeraldGreen)
                            ) {
                                Text("CHECK-OUT GPS")
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    OutlinedButton(
                        onClick = { onNavigateToMedia(visit.id) },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("ATTACHMENTS & MEDIA")
                    }

                    Spacer(modifier = Modifier.height(24.dp))

                    // Geo Logs Section
                    Text(
                        text = "Geo Verification Logs (${logs.size})",
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                        color = Slate900
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    if (logs.isEmpty()) {
                        Text("No geo-location check attempts recorded yet.", fontSize = 13.sp, color = Slate500)
                    } else {
                        logs.forEach { log ->
                            Card(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 4.dp),
                                shape = RoundedCornerShape(8.dp),
                                colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
                            ) {
                                Row(
                                    modifier = Modifier
                                        .padding(12.dp)
                                        .fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Column {
                                        Text(
                                            text = log.verificationType,
                                            fontSize = 13.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = Slate900
                                        )
                                        Text(
                                            text = "Coords: ${log.latitude}, ${log.longitude}",
                                            fontSize = 11.sp,
                                            color = Slate500
                                        )
                                        if (log.failureReason != null) {
                                            Text(
                                                text = "Reason: ${log.failureReason}",
                                                fontSize = 11.sp,
                                                color = AmberWarning
                                            )
                                        }
                                    }
                                    StatusBadge(status = if (log.isValid) "VALID" else "INVALID")
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
fun DetailItem(label: String, value: String) {
    Column(modifier = Modifier.padding(vertical = 4.dp)) {
        Text(text = label, fontSize = 11.sp, color = Slate500)
        Text(text = value, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Slate900)
    }
}
