package com.fieldtrackpro.android.ui.screens.sync

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.local.ConflictType
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.ui.components.EmptyState
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.StatusBadge
import com.fieldtrackpro.android.ui.theme.FieldTrackAmber
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.SurfaceOffWhite
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.theme.TextMuted
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** A short, rep-facing label for a conflict type - the raw enum name is developer-facing only. */
private fun ConflictType.displayLabel(): String = when (this) {
    ConflictType.STATUS_CHANGED -> "Visit status changed on server"
    ConflictType.VISIT_UNAVAILABLE -> "Visit no longer available"
    ConflictType.GEO_VALIDATION_FAILED -> "Location check failed"
    ConflictType.SERVER_REJECTED -> "Rejected by server"
    ConflictType.NETWORK_ERROR -> "Server error during sync"
}

@Composable
fun OfflineQueueScreen(
    offlineQueueManager: OfflineQueueManager,
    visitsViewModel: VisitsViewModel,
    onNavigateBack: () -> Unit
) {
    var queueItems by remember { mutableStateOf(offlineQueueManager.getQueue()) }
    var conflicts by remember { mutableStateOf(offlineQueueManager.getConflicts()) }
    var syncNotice by remember { mutableStateOf("") }

    val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "Offline Action Sync Queue",
                onBackClick = onNavigateBack
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(SurfaceOffWhite)
                .padding(innerPadding)
                .padding(20.dp)
        ) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Text(
                        text = "Pending Offline Queue (${queueItems.size})",
                        style = MaterialTheme.typography.titleLarge,
                        color = FieldTrackNavy
                    )
                    Text(
                        text = "Actions captured while offline are stored locally and synced once network connectivity is restored.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextMuted
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    if (syncNotice.isNotBlank()) {
                        Text(text = syncNotice, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = FieldTrackNavy)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        Button(
                            onClick = {
                                visitsViewModel.syncOfflineQueue { count ->
                                    syncNotice = "Synced $count pending action(s) to backend!"
                                    queueItems = offlineQueueManager.getQueue()
                                    conflicts = offlineQueueManager.getConflicts()
                                }
                            },
                            enabled = queueItems.isNotEmpty(),
                            modifier = Modifier.weight(1f),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = FieldTrackNavy,
                                contentColor = SurfaceWhite
                            )
                        ) {
                            Text("SYNC ALL NOW", color = SurfaceWhite)
                        }

                        OutlinedButton(
                            onClick = {
                                offlineQueueManager.clearQueue()
                                queueItems = emptyList()
                                syncNotice = "Cleared offline queue."
                            },
                            enabled = queueItems.isNotEmpty(),
                            modifier = Modifier.weight(1f)
                        ) {
                            Text("CLEAR QUEUE", color = FieldTrackNavy)
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            if (queueItems.isEmpty()) {
                EmptyState(
                    title = "Queue Clean",
                    subtitle = "All captured field actions have been successfully synced to the backend."
                )
            } else {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    items(queueItems) { action ->
                        Card(
                            modifier = Modifier.fillMaxWidth(),
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
                                Column {
                                    Text(
                                        text = "Visit ID: ${action.visitId.take(8)}...",
                                        fontSize = 14.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = TextPrimary
                                    )
                                    Text(
                                        text = "Captured: ${dateFormat.format(Date(action.timestamp))}",
                                        fontSize = 12.sp,
                                        color = TextMuted
                                    )
                                    Text(
                                        text = "Coords: ${action.latitude}, ${action.longitude}",
                                        fontSize = 12.sp,
                                        color = TextMuted
                                    )
                                }
                                StatusBadge(status = action.actionType)
                            }
                        }
                    }
                }
            }

            if (conflicts.isNotEmpty()) {
                Spacer(modifier = Modifier.height(24.dp))
                Text(
                    text = "Needs Your Attention (${conflicts.size})",
                    style = MaterialTheme.typography.titleMedium,
                    color = FieldTrackAmber
                )
                Text(
                    text = "These queued actions could not be synced automatically and need a look before they're discarded.",
                    style = MaterialTheme.typography.bodySmall,
                    color = TextMuted
                )
                Spacer(modifier = Modifier.height(10.dp))
                LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    items(conflicts, key = { it.id }) { conflict ->
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(12.dp),
                            colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
                        ) {
                            Column(modifier = Modifier.padding(16.dp)) {
                                Text(
                                    text = conflict.conflictType.displayLabel(),
                                    fontSize = 14.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = FieldTrackAmber
                                )
                                Text(
                                    text = "Visit ID: ${conflict.pendingAction.visitId.take(8)}... (${conflict.pendingAction.actionType})",
                                    fontSize = 12.sp,
                                    color = TextMuted
                                )
                                Text(
                                    text = conflict.message,
                                    fontSize = 12.sp,
                                    color = TextPrimary
                                )
                                Spacer(modifier = Modifier.height(8.dp))
                                OutlinedButton(
                                    onClick = {
                                        offlineQueueManager.removeAction(conflict.pendingAction.id)
                                        offlineQueueManager.removeConflict(conflict.id)
                                        queueItems = offlineQueueManager.getQueue()
                                        conflicts = offlineQueueManager.getConflicts()
                                    }
                                ) {
                                    Text("DISCARD THIS ACTION", color = FieldTrackNavy)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
