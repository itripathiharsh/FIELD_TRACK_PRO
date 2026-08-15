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
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
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
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.StatusBadge
import com.fieldtrackpro.android.ui.theme.FieldTrackAmber
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SurfaceOffWhite
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.theme.TextMuted
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.viewmodel.VisitSummaryState
import com.fieldtrackpro.android.ui.viewmodel.VisitSummaryViewModel

@Composable
fun VisitSummaryScreen(
    visitId: String,
    viewModel: VisitSummaryViewModel,
    onNavigateBack: () -> Unit,
    onSubmit: () -> Unit,
    onCancel: () -> Unit
) {
    val state by viewModel.summaryState.collectAsState()

    LaunchedEffect(visitId) {
        viewModel.loadVisitSummary(visitId)
    }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "Visit Summary",
                onBackClick = onNavigateBack
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(SurfaceOffWhite)
                .padding(innerPadding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
        ) {
            when (val s = state) {
                is VisitSummaryState.Loading -> {
                    Column(
                        modifier = Modifier.fillMaxWidth().padding(top = 48.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        CircularProgressIndicator(color = FieldTrackNavy)
                        Spacer(modifier = Modifier.height(12.dp))
                        Text("Loading visit summary...", fontSize = 14.sp, color = TextMuted)
                    }
                }

                is VisitSummaryState.Error -> {
                    ErrorBanner(message = s.message)
                    Spacer(modifier = Modifier.height(16.dp))
                    Button(
                        onClick = onCancel,
                        colors = ButtonDefaults.buttonColors(containerColor = TextMuted, contentColor = SurfaceWhite)
                    ) {
                        Text("Go Back", color = SurfaceWhite)
                    }
                }

                is VisitSummaryState.Ready -> {
                    val visit = s.visit

                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text("Visit Details", style = MaterialTheme.typography.titleMedium, color = FieldTrackNavy)
                                StatusBadge(status = visit.status)
                            }
                            HorizontalDivider(modifier = Modifier.padding(vertical = 12.dp))

                            SummaryItem(label = "Visit ID", value = visit.id)
                            SummaryItem(label = "Customer ID", value = visit.customerId)
                            SummaryItem(label = "Scheduled", value = visit.scheduledAt)
                            SummaryItem(label = "Status", value = visit.status)
                            visit.checkInAt?.let {
                                SummaryItem(label = "Check-In", value = it)
                            }
                            visit.checkOutAt?.let {
                                SummaryItem(label = "Check-Out", value = it)
                            }
                            SummaryItem(label = "Synced", value = if (visit.synced) "Yes" else "No")
                        }
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text("Attachments", style = MaterialTheme.typography.titleMedium, color = FieldTrackNavy)
                            HorizontalDivider(modifier = Modifier.padding(vertical = 12.dp))

                            if (s.media.isEmpty()) {
                                Text("No attachments uploaded.", fontSize = 13.sp, color = TextMuted)
                            } else {
                                s.media.forEach { media ->
                                    Row(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .padding(vertical = 4.dp),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text(
                                                text = media.displayName,
                                                fontSize = 13.sp,
                                                fontWeight = FontWeight.SemiBold,
                                                color = TextPrimary
                                            )
                                            Text(
                                                text = "${media.mediaType} • ${formatBytes(media.fileSizeBytes)}",
                                                fontSize = 11.sp,
                                                color = TextMuted
                                            )
                                        }
                                        StatusBadge(status = media.mediaType)
                                    }
                                }
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text("Geo Verification Logs", style = MaterialTheme.typography.titleMedium, color = FieldTrackNavy)
                            HorizontalDivider(modifier = Modifier.padding(vertical = 12.dp))

                            if (s.geoLogs.isEmpty()) {
                                Text("No geo-verification attempts recorded.", fontSize = 13.sp, color = TextMuted)
                            } else {
                                s.geoLogs.forEach { log ->
                                    Row(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .padding(vertical = 4.dp),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text(
                                                text = log.verificationType,
                                                fontSize = 13.sp,
                                                fontWeight = FontWeight.SemiBold,
                                                color = TextPrimary
                                            )
                                            Text(
                                                text = "Distance: ${String.format("%.1f", log.distanceFromCustomerM)}m",
                                                fontSize = 11.sp,
                                                color = TextMuted
                                            )
                                            log.failureReason?.let {
                                                Text(text = it, fontSize = 11.sp, color = FieldTrackAmber)
                                            }
                                        }
                                        Text(
                                            text = if (log.isValid) "PASS" else "FAIL",
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = if (log.isValid) SuccessGreen else FieldTrackAmber
                                        )
                                    }
                                }
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(24.dp))

                    Button(
                        onClick = onSubmit,
                        modifier = Modifier.fillMaxWidth().height(50.dp),
                        shape = RoundedCornerShape(8.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = FieldTrackNavy,
                            contentColor = SurfaceWhite
                        )
                    ) {
                        Text("SUBMIT VISIT", fontWeight = FontWeight.Bold, color = SurfaceWhite)
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    Button(
                        onClick = onCancel,
                        modifier = Modifier.fillMaxWidth().height(50.dp),
                        shape = RoundedCornerShape(8.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = TextMuted,
                            contentColor = SurfaceWhite
                        )
                    ) {
                        Text("CANCEL", fontWeight = FontWeight.Bold, color = SurfaceWhite)
                    }
                }
            }
        }
    }
}

@Composable
private fun SummaryItem(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(text = label, fontSize = 12.sp, color = TextMuted)
        Text(text = value, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = TextPrimary)
    }
}

private fun formatBytes(bytes: Long): String {
    return when {
        bytes < 1024 -> "$bytes B"
        bytes < 1024 * 1024 -> "${bytes / 1024} KB"
        else -> String.format("%.1f MB", bytes / (1024.0 * 1024.0))
    }
}
