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
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import com.fieldtrackpro.android.data.local.PaymentProofStore
import com.fieldtrackpro.android.data.local.PendingAction
import com.fieldtrackpro.android.data.local.SyncConflict
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.repository.needsOutletRetake
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
    ConflictType.UNOWNED_LEGACY -> "Unowned Legacy Item (not synced)"
    ConflictType.QUEUE_CORRUPTED -> "Saved Items Could Not Be Read"
}

/** One-line title for a queued action: amount + method for payments, short visit id otherwise. */
internal fun actionTitle(action: PendingAction): String {
    if (action.isOutletProof) return "Outlet photo + GPS"
    val p = action.paymentPayload
    return if (action.isPayment && p != null) {
        "Payment \u20B9${p.amount ?: "?"} (${p.paymentMethod ?: "?"})"
    } else {
        "Visit ID: ${action.visitId.take(8)}..."
    }
}

internal fun actionSubtitle(action: PendingAction): String? {
    if (action.isOutletProof) {
        val o = action.outletProofPayload ?: return null
        val outlet = o.outletName?.takeIf { it.isNotBlank() } ?: "Outlet ${o.customerId?.take(8) ?: "?"}..."
        return "Outlet: $outlet • GPS ±%.0f m".format(o.accuracyM ?: 0.0)
    }
    val p = action.paymentPayload
    if (!action.isPayment || p == null) return null
    val outlet = p.outletName?.takeIf { it.isNotBlank() } ?: "Visit ${action.visitId.take(8)}..."
    val proofs = p.proofPaths?.size ?: 0
    return "Outlet: $outlet" + if (proofs > 0) " \u2022 $proofs proof photo(s)" else ""
}

private fun discard(manager: OfflineQueueManager, conflict: SyncConflict) {
    conflict.pendingAction.paymentPayload?.proofPaths?.forEach { PaymentProofStore.delete(it) }
    conflict.pendingAction.outletProofPayload?.photoPath?.let { com.fieldtrackpro.android.data.local.OutletProofStore.delete(it) }
    manager.removeAction(conflict.pendingAction.id)
    manager.removeConflict(conflict.id)
}

@Composable
fun OfflineQueueScreen(
    offlineQueueManager: OfflineQueueManager,
    visitsViewModel: VisitsViewModel,
    tokenManager: TokenManager? = null,
    onNavigateBack: () -> Unit
) {
    val currentUserId = tokenManager?.getUserId()
    var queueItems by remember { mutableStateOf(offlineQueueManager.getQueueForUser(currentUserId)) }
    var conflicts by remember { mutableStateOf(offlineQueueManager.getConflictsForUser(currentUserId)) }
    var syncNotice by remember { mutableStateOf("") }
    var quarantined by remember { mutableStateOf(offlineQueueManager.getQuarantinedConflicts()) }
    var showQuarantineConfirm by remember { mutableStateOf(false) }
    var quarantineRevealed by remember { mutableStateOf(false) }
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
                                    queueItems = offlineQueueManager.getQueueForUser(currentUserId)
                                    conflicts = offlineQueueManager.getConflictsForUser(currentUserId)
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
                                // Only the signed-in user's items: never wipe another employee's queue.
                                if (currentUserId != null) offlineQueueManager.clearQueueForUser(currentUserId)
                                queueItems = offlineQueueManager.getQueueForUser(currentUserId)
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
                                        text = actionTitle(action),
                                        fontFamily = LeagueSpartanFamily,
                                        fontSize = 15.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = BrandNavy
                                    )
                                    actionSubtitle(action)?.let {
                                        Text(
                                            text = it,
                                            fontFamily = LibreBaskervilleFamily,
                                            fontSize = 13.sp,
                                            color = TextSecondary
                                        )
                                    }
                                    Spacer(modifier = Modifier.height(2.dp))
                                    Text(
                                        text = "Captured: ${dateFormat.format(Date(action.timestamp))}",
                                        fontFamily = LibreBaskervilleFamily,
                                        fontSize = 13.sp,
                                        fontWeight = FontWeight.Normal,
                                        color = TextSecondary
                                    )
                                    if (!action.isPayment && !action.isOutletProof) {
                                        Text(
                                            text = "Coords: ${action.latitude}, ${action.longitude}",
                                            fontFamily = LibreBaskervilleFamily,
                                            fontSize = 12.sp,
                                            fontWeight = FontWeight.Normal,
                                            color = TextSubtle
                                        )
                                    }
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
                                    text = "${actionTitle(conflict.pendingAction)} (${conflict.pendingAction.actionType})" +
                                        (actionSubtitle(conflict.pendingAction)?.let { " \u2022 $it" } ?: ""),
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
                                if (conflict.needsOutletRetake) {
                                    // Stale/unusable queued outlet photo: offer a RETAKE (live capture at the outlet).
                                    com.fieldtrackpro.android.ui.screens.proof.OutletProofRetakeAction(
                                        conflict = conflict,
                                        offlineQueueManager = offlineQueueManager,
                                        onResolved = {
                                            queueItems = offlineQueueManager.getQueueForUser(currentUserId)
                                            conflicts = offlineQueueManager.getConflictsForUser(currentUserId)
                                        }
                                    )
                                    Spacer(modifier = Modifier.height(8.dp))
                                }
                                OutlinedButton(
                                    onClick = {
                                        discard(offlineQueueManager, conflict)
                                        queueItems = offlineQueueManager.getQueueForUser(currentUserId)
                                        conflicts = offlineQueueManager.getConflictsForUser(currentUserId)
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

            if (quarantined.isNotEmpty()) {
                Spacer(modifier = Modifier.height(20.dp))
                Text(
                    text = "UNOWNED LEGACY ITEMS (${quarantined.size})",
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 0.8.sp,
                    color = BrandGoldDark
                )
                Text(
                    text = "Saved by an older app version with no owner. They are never synced automatically.",
                    fontFamily = LibreBaskervilleFamily,
                    fontSize = 12.sp,
                    color = TextSecondary
                )
                if (!quarantineRevealed) {
                    OutlinedButton(onClick = { showQuarantineConfirm = true }, shape = RoundedCornerShape(8.dp)) {
                        Text("REVIEW", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 12.sp, color = BrandNavy)
                    }
                } else {
                    Spacer(modifier = Modifier.height(10.dp))
                    LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        items(quarantined, key = { it.id }) { conflict ->
                            Card(
                                modifier = Modifier.fillMaxWidth().border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
                                shape = RoundedCornerShape(12.dp),
                                colors = CardDefaults.cardColors(containerColor = BrandWhite)
                            ) {
                                Column(modifier = Modifier.padding(14.dp)) {
                                    Text(
                                        text = "${actionTitle(conflict.pendingAction)} (${conflict.pendingAction.actionType})",
                                        fontFamily = LeagueSpartanFamily, fontSize = 14.sp,
                                        fontWeight = FontWeight.Bold, color = BrandGoldDark
                                    )
                                    Text(
                                        text = "Captured: ${dateFormat.format(Date(conflict.pendingAction.timestamp))}",
                                        fontFamily = LibreBaskervilleFamily, fontSize = 12.sp, color = TextSecondary
                                    )
                                    Text(
                                        text = conflict.message,
                                        fontFamily = LibreBaskervilleFamily, fontSize = 13.sp, color = TextPrimary
                                    )
                                    Spacer(modifier = Modifier.height(8.dp))
                                    OutlinedButton(
                                        onClick = {
                                            discard(offlineQueueManager, conflict)
                                            quarantined = offlineQueueManager.getQuarantinedConflicts()
                                        },
                                        shape = RoundedCornerShape(8.dp)
                                    ) {
                                        Text("DISCARD", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 12.sp, color = BrandNavy)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if (showQuarantineConfirm) {
        AlertDialog(
            onDismissRequest = { showQuarantineConfirm = false },
            title = { Text("Show unowned legacy items?") },
            text = {
                Text(
                    "These items were saved by an older app version and cannot be tied to any employee. " +
                        "They will not be synced. Only continue if you are the person who handles them."
                )
            },
            confirmButton = {
                TextButton(onClick = { quarantineRevealed = true; showQuarantineConfirm = false }) { Text("SHOW") }
            },
            dismissButton = {
                TextButton(onClick = { showQuarantineConfirm = false }) { Text("CANCEL") }
            }
        )
    }
}
