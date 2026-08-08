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
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.ui.components.EmptyState
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.StatusBadge
import com.fieldtrackpro.android.ui.theme.ElectricBlue
import com.fieldtrackpro.android.ui.theme.Slate50
import com.fieldtrackpro.android.ui.theme.Slate500
import com.fieldtrackpro.android.ui.theme.Slate900
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun OfflineQueueScreen(
    offlineQueueManager: OfflineQueueManager,
    visitsViewModel: VisitsViewModel,
    onNavigateBack: () -> Unit
) {
    var queueItems by remember { mutableStateOf(offlineQueueManager.getQueue()) }
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
                .background(Slate50)
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
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = Slate900
                    )
                    Text(
                        text = "Actions captured while offline are stored locally and synced once network connectivity is restored.",
                        fontSize = 13.sp,
                        color = Slate500
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    if (syncNotice.isNotBlank()) {
                        Text(text = syncNotice, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = ElectricBlue)
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
                                }
                            },
                            enabled = queueItems.isNotEmpty(),
                            modifier = Modifier.weight(1f),
                            colors = ButtonDefaults.buttonColors(containerColor = ElectricBlue)
                        ) {
                            Text("SYNC ALL NOW")
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
                            Text("CLEAR QUEUE")
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
                                        color = Slate900
                                    )
                                    Text(
                                        text = "Captured: ${dateFormat.format(Date(action.timestamp))}",
                                        fontSize = 12.sp,
                                        color = Slate500
                                    )
                                    Text(
                                        text = "Coords: ${action.latitude}, ${action.longitude}",
                                        fontSize = 12.sp,
                                        color = Slate500
                                    )
                                }
                                StatusBadge(status = action.actionType)
                            }
                        }
                    }
                }
            }
        }
    }
}
