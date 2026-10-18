package com.fieldtrackpro.android.ui.screens.profile

import android.widget.Toast
import androidx.compose.foundation.BorderStroke
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.TextButton
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import com.fieldtrackpro.android.ui.viewmodel.AccountDeletionState
import com.fieldtrackpro.android.utils.ExternalLinks
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ExitToApp
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.local.LogoutDecision
import com.fieldtrackpro.android.data.local.LogoutPolicy
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.SyncBeforeLogoutResult
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.screens.visits.DetailItem
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.viewmodel.AuthViewModel

@Composable
fun ProfileSettingsScreen(
    tokenManager: TokenManager,
    authViewModel: AuthViewModel,
    onNavigateBack: () -> Unit,
    onLogout: () -> Unit,
    /** Queue to inspect for unsynced items before logout / account deletion (null = no check). */
    offlineQueueManager: OfflineQueueManager? = null,
    /** Runs the existing offline sync path and calls back when it finishes. */
    onSyncNow: (onDone: () -> Unit) -> Unit = { it() }
) {
    val context = LocalContext.current
    val deletionState by authViewModel.deletionState.collectAsState()
    var showDeletionDialog by remember { mutableStateOf(false) }
    var deletionReason by remember { mutableStateOf("") }
    // Re-authentication for the irreversible deletion. Deliberately plain remember (never saved/restored) and
    // wiped whenever the dialog closes; never logged.
    var deletionPassword by remember { mutableStateOf("") }
    LaunchedEffect(showDeletionDialog) { if (!showDeletionDialog) deletionPassword = "" }

    // Unsynced-items guard (logout / account deletion). Queue is per user, so only the current user's items count.
    val currentUserId = tokenManager.getUserId()
    fun pendingItems() = offlineQueueManager?.getQueueForUser(currentUserId) ?: emptyList()
    var logoutPrompt by remember { mutableStateOf<LogoutDecision.ConfirmUnsynced?>(null) }
    var logoutSyncing by remember { mutableStateOf(false) }
    var logoutNotice by remember { mutableStateOf<String?>(null) }
    var deletionUnsyncedCount by remember { mutableStateOf(0) }

    // On a successful deletion request the session is already cleared: go back to login.
    LaunchedEffect(deletionState) {
        val state = deletionState
        if (state is AccountDeletionState.Submitted) {
            Toast.makeText(context, state.message, Toast.LENGTH_LONG).show()
            showDeletionDialog = false
            authViewModel.resetDeletionState()
            onLogout()
        }
    }

    logoutPrompt?.let { prompt ->
        AlertDialog(
            onDismissRequest = { if (!logoutSyncing) { logoutPrompt = null; logoutNotice = null } },
            title = {
                Text("Unsynced items", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = BrandNavy)
            },
            text = {
                Column {
                    Text(LogoutPolicy.logoutWarning(prompt.count, prompt.description), fontSize = 14.sp, color = TextPrimary)
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(LogoutPolicy.LOGOUT_ANYWAY_CONFIRMATION, fontSize = 12.sp, color = TextSecondary)
                    val notice = logoutNotice
                    if (notice != null) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(notice, fontSize = 12.sp, color = ErrorRed)
                    }
                }
            },
            confirmButton = {
                TextButton(
                    enabled = !logoutSyncing,
                    onClick = {
                        logoutSyncing = true
                        logoutNotice = null
                        onSyncNow {
                            logoutSyncing = false
                            when (val result = LogoutPolicy.afterSync(pendingItems())) {
                                is SyncBeforeLogoutResult.AllSynced -> {
                                    logoutPrompt = null
                                    authViewModel.logout()
                                    onLogout()
                                }
                                is SyncBeforeLogoutResult.StillPending -> {
                                    logoutPrompt = LogoutDecision.ConfirmUnsynced(result.remaining, result.description)
                                    logoutNotice = LogoutPolicy.stillPendingMessage(result.remaining)
                                }
                            }
                        }
                    }
                ) {
                    Text(if (logoutSyncing) "SYNCING..." else "SYNC NOW", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = BrandNavy)
                }
            },
            dismissButton = {
                Row {
                    TextButton(enabled = !logoutSyncing, onClick = { logoutPrompt = null; logoutNotice = null }) {
                        Text("CANCEL", fontFamily = LeagueSpartanFamily, color = BrandNavy)
                    }
                    TextButton(
                        enabled = !logoutSyncing,
                        onClick = {
                            // Queue stays on the device (not deleted) and remains tied to this user id.
                            logoutPrompt = null
                            logoutNotice = null
                            Toast.makeText(context, LogoutPolicy.LOGOUT_ANYWAY_CONFIRMATION, Toast.LENGTH_LONG).show()
                            authViewModel.logout()
                            onLogout()
                        }
                    ) {
                        Text("LOG OUT ANYWAY", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = ErrorRed)
                    }
                }
            }
        )
    }

    if (showDeletionDialog) {
        val isSubmitting = deletionState is AccountDeletionState.Submitting
        AlertDialog(
            onDismissRequest = { if (!isSubmitting) showDeletionDialog = false },
            title = {
                Text("Request account deletion", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = BrandNavy)
            },
            text = {
                Column {
                    Text(
                        "This permanently deletes your account. You will be signed out, everything stored on this " +
                            "device for your account (including unsynced items) is erased, and you can no longer sign in. " +
                            "Some business records (visits, invoices) may be retained as required by law or by your employer.",
                        fontSize = 13.sp,
                        color = TextPrimary
                    )
                    if (deletionUnsyncedCount > 0) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            "You have $deletionUnsyncedCount unsynced item${if (deletionUnsyncedCount == 1) "" else "s"}. " +
                                LogoutPolicy.DELETION_WARNING,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Bold,
                            color = ErrorRed
                        )
                    }
                    Spacer(modifier = Modifier.height(12.dp))
                    OutlinedTextField(
                        value = deletionReason,
                        onValueChange = { deletionReason = it.take(500) },
                        label = { Text("Reason (optional)") },
                        enabled = !isSubmitting,
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    val wrongPassword = deletionState as? AccountDeletionState.IncorrectPassword
                    OutlinedTextField(
                        value = deletionPassword,
                        onValueChange = {
                            deletionPassword = it
                            if (wrongPassword != null) authViewModel.resetDeletionState()
                        },
                        label = { Text("Current password (required)") },
                        singleLine = true,
                        enabled = !isSubmitting,
                        isError = wrongPassword != null,
                        visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation(),
                        keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(
                            keyboardType = androidx.compose.ui.text.input.KeyboardType.Password,
                            autoCorrect = false
                        ),
                        supportingText = wrongPassword?.let { { Text(it.message, color = ErrorRed) } },
                        modifier = Modifier.fillMaxWidth()
                    )
                    val failed = deletionState as? AccountDeletionState.Failed
                    if (failed != null) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(failed.message, fontSize = 12.sp, color = ErrorRed)
                    }
                }
            },
            confirmButton = {
                TextButton(
                    enabled = !isSubmitting && deletionPassword.isNotEmpty(),
                    onClick = { authViewModel.requestAccountDeletion(deletionPassword, deletionReason) }
                ) {
                    Text(
                        if (isSubmitting) "SUBMITTING..." else "DELETE MY ACCOUNT",
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = FontWeight.Bold,
                        color = ErrorRed
                    )
                }
            },
            dismissButton = {
                TextButton(enabled = !isSubmitting, onClick = { showDeletionDialog = false }) {
                    Text("CANCEL", fontFamily = LeagueSpartanFamily, color = BrandNavy)
                }
            }
        )
    }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "Profile & Settings",
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
                .verticalScroll(rememberScrollState())
        ) {
            // Profile Hero Card
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, BrandLightGray, RoundedCornerShape(14.dp)),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = BrandWhite),
                elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Box(
                            modifier = Modifier
                                .size(56.dp)
                                .clip(CircleShape)
                                .background(BrandNavy)
                                .border(2.dp, BrandGold, CircleShape),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = Icons.Default.Person,
                                contentDescription = null,
                                tint = BrandGold,
                                modifier = Modifier.size(32.dp)
                            )
                        }

                        Spacer(modifier = Modifier.width(16.dp))

                        Column {
                            Text(
                                text = tokenManager.getUserName() ?: "Field Representative",
                                fontFamily = LeagueSpartanFamily,
                                fontSize = 20.sp,
                                fontWeight = FontWeight.Bold,
                                color = BrandNavy
                            )
                            Row(
                                modifier = Modifier.padding(top = 4.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Box(
                                    modifier = Modifier
                                        .clip(RoundedCornerShape(4.dp))
                                        .background(BrandGold.copy(alpha = 0.2f))
                                        .border(1.dp, BrandGold, RoundedCornerShape(4.dp))
                                        .padding(horizontal = 8.dp, vertical = 2.dp)
                                ) {
                                    val roleText = com.fieldtrackpro.android.utils.Roles.displayRole(tokenManager.getUserRole())
                                    Text(
                                        text = roleText,
                                        fontFamily = LeagueSpartanFamily,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 11.sp,
                                        letterSpacing = 0.8.sp,
                                        color = BrandNavy
                                    )
                                }
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(20.dp))

                    Text(
                        text = "EMPLOYEE SPECIFICATIONS",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 1.sp,
                        color = BrandNavy
                    )

                    Spacer(modifier = Modifier.height(10.dp))

                    DetailItem(label = "Email Address", value = tokenManager.getUserEmail()?.ifBlank { "N/A" } ?: "N/A")
                    DetailItem(label = "Phone Number", value = tokenManager.getUserPhone()?.ifBlank { "N/A" } ?: "N/A")
                    DetailItem(label = "Employee Code", value = tokenManager.getEmployeeCode()?.ifBlank { "N/A" } ?: "N/A")
                    DetailItem(label = "Assigned Territory", value = tokenManager.getTerritoryName()?.ifBlank { "N/A" } ?: "N/A")
                    DetailItem(label = "Security Protocol", value = "Keystore-backed Hardware Authentication")
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            Button(
                onClick = {
                    when (val decision = LogoutPolicy.decide(pendingItems())) {
                        is LogoutDecision.Proceed -> {
                            authViewModel.logout()
                            onLogout()
                        }
                        is LogoutDecision.ConfirmUnsynced -> {
                            logoutNotice = null
                            logoutPrompt = decision
                        }
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(52.dp),
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = ErrorRed,
                    contentColor = BrandWhite
                )
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.ExitToApp,
                        contentDescription = null,
                        tint = BrandWhite,
                        modifier = Modifier.size(20.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        "LOGOUT ACTIVE SESSION",
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp,
                        letterSpacing = 0.8.sp,
                        color = BrandWhite
                    )
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            OutlinedButton(
                onClick = { ExternalLinks.openPrivacyPolicy(context) },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(48.dp),
                shape = RoundedCornerShape(10.dp),
                border = BorderStroke(1.dp, BrandNavy)
            ) {
                Text(
                    "PRIVACY POLICY",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 13.sp,
                    letterSpacing = 0.8.sp,
                    color = BrandNavy
                )
            }

            Spacer(modifier = Modifier.height(12.dp))

            OutlinedButton(
                onClick = {
                    authViewModel.resetDeletionState()
                    deletionUnsyncedCount = pendingItems().size
                    showDeletionDialog = true
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(48.dp),
                shape = RoundedCornerShape(10.dp),
                border = BorderStroke(1.dp, ErrorRed)
            ) {
                Text(
                    "REQUEST ACCOUNT DELETION",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 13.sp,
                    letterSpacing = 0.8.sp,
                    color = ErrorRed
                )
            }
        }
    }
}
