package com.fieldtrackpro.android.ui.screens.sync

import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** A short, rep-facing label for a conflict type - the raw enum name is developer-facing only. */
private fun ConflictType.displayLabel(): String = when (this) {
    ConflictType.STATUS_CHANGED -> "Visit Status Changed on Server"
    ConflictType.VISIT_UNAVAILABLE -> "Visit No Longer Available"
    ConflictType.GEO_VALIDATION_FAILED -> "Location Check Failed"
    ConflictType.SERVER_REJECTED -> "Rejected by Server"
    ConflictType.NETWORK_ERROR -> "Network Error During Sync"
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
    val dateFormat = remember { SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()) }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "Offline Action Queue",
                onBackClick = onNavigateBack
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .background(SurfaceSecondary)
                .padding(innerPadding)
                .padding(16.dp)
        ) {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, BrandLightGray, RoundedCornerShape(14.dp)),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = BrandWhite),
                elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Text(
                        text = "Pending Offline Queue (${queueItems.size})",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = BrandNavy
                    )
                    Text(
                        text = "Actions captured while offline are stored locally and synced once network connectivity is restored.",
                        fontFamily = LibreBaskervilleFamily,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Normal,
                        color = TextSecondary
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    if (syncNotice.isNotBlank()) {
                        Text(
                            text = syncNotice,
                            fontFamily = LeagueSpartanFamily,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Bold,
                            color = BrandNavy
                        )
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
                            shape = RoundedCornerShape(8.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = BrandNavy,
                                contentColor = BrandWhite
                            )
                        ) {
                            Text(
                                "SYNC ALL NOW",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                fontSize = 13.sp,
                                color = BrandWhite
                            )
                        }

                        OutlinedButton(
                            onClick = {
                                offlineQueueManager.clearQueue()
                                queueItems = emptyList()
                                syncNotice = "Cleared offline queue."
                            },
                            enabled = queueItems.isNotEmpty(),
                            modifier = Modifier.weight(1f),
                            shape = RoundedCornerShape(8.dp)
                        ) {
                            Text(
                                "CLEAR QUEUE",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                fontSize = 13.sp,
                                color = BrandNavy
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(20.dp))

            if (queueItems.isEmpty()) {
                EmptyState(
                    title = "Queue Clean",
                    subtitle = "All captured field actions have been successfully synced to the backend."
                )
            } else {
                LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    items(queueItems) { action ->
                        Card(
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
                                Column {
                                    Text(
                                        text = "Visit ID: ${action.visitId.take(8)}...",
                                        fontFamily = LeagueSpartanFamily,
                                        fontSize = 15.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = BrandNavy
                                    )
                                    Spacer(modifier = Modifier.height(2.dp))
                                    Text(
                                        text = "Captured: ${dateFormat.format(Date(action.timestamp))}",
                                        fontFamily = LibreBaskervilleFamily,
                                        fontSize = 13.sp,
                                        fontWeight = FontWeight.Normal,
                                        color = TextSecondary
                                    )
                                    Text(
                                        text = "Coords: ${action.latitude}, ${action.longitude}",
                                        fontFamily = LibreBaskervilleFamily,
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Normal,
                                        color = TextSubtle
                                    )
                                }
                                StatusBadge(status = action.actionType)
                            }
                        }
                    }
                }
            }

            if (conflicts.isNotEmpty()) {
                Spacer(modifier = Modifier.height(20.dp))
                Text(
                    text = "NEEDS YOUR ATTENTION (${conflicts.size})",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 0.8.sp,
                    color = BrandGoldDark
                )
                Text(
                    text = "These queued actions could not be synced automatically and need a look before they're discarded.",
                    fontFamily = LibreBaskervilleFamily,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Normal,
                    color = TextSecondary
                )
                Spacer(modifier = Modifier.height(10.dp))
                LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    items(conflicts, key = { it.id }) { conflict ->
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
                            shape = RoundedCornerShape(12.dp),
                            colors = CardDefaults.cardColors(containerColor = BrandWhite),
                            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                        ) {
                            Column(modifier = Modifier.padding(14.dp)) {
                                Text(
                                    text = conflict.conflictType.displayLabel(),
                                    fontFamily = LeagueSpartanFamily,
                                    fontSize = 14.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = BrandGoldDark
                                )
                                Text(
                                    text = "Visit ID: ${conflict.pendingAction.visitId.take(8)}... (${conflict.pendingAction.actionType})",
                                    fontFamily = LibreBaskervilleFamily,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Normal,
                                    color = TextSecondary
                                )
                                Text(
                                    text = conflict.message,
                                    fontFamily = LibreBaskervilleFamily,
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.Normal,
                                    color = TextPrimary
                                )
                                Spacer(modifier = Modifier.height(8.dp))
                                OutlinedButton(
                                    onClick = {
                                        offlineQueueManager.removeAction(conflict.pendingAction.id)
                                        offlineQueueManager.removeConflict(conflict.id)
                                        queueItems = offlineQueueManager.getQueue()
                                        conflicts = offlineQueueManager.getConflicts()
                                    },
                                    shape = RoundedCornerShape(8.dp)
                                ) {
                                    Text("DISCARD THIS ACTION", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 12.sp, color = BrandNavy)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
