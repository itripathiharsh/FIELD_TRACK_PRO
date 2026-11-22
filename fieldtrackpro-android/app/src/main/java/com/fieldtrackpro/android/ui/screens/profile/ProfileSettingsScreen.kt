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
import androidx.compose.material.icons.automirrored.filled.ExitToApp
import androidx.compose.material.icons.filled.Badge
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Email
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material.icons.filled.Place
import androidx.compose.material.icons.filled.PrivacyTip
import androidx.compose.material.icons.filled.Sync
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.heightIn
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

    val profileRevision by authViewModel.profileRevision.collectAsState()
    LaunchedEffect(Unit) { authViewModel.refreshProfile() }
    val profile = remember(profileRevision) {
        ProfileUi(
            name = tokenManager.getUserName() ?: "Field representative",
            role = com.fieldtrackpro.android.utils.Roles.displayRole(tokenManager.getUserRole()),
            phone = tokenManager.getUserPhone(),
            email = tokenManager.getUserEmail(),
            employeeCode = tokenManager.getEmployeeCode(),
            territory = tokenManager.getTerritoryName(),
            appVersion = com.fieldtrackpro.android.BuildConfig.VERSION_NAME
        )
    }

    ProfileContent(
        profile = profile,
        pendingCount = pendingItems().size,
        onBack = onNavigateBack,
        onSyncQueue = { onSyncNow { } },
        onPrivacy = { ExternalLinks.openPrivacyPolicy(context) },
        onLogout = {
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
        onRequestDeletion = {
            authViewModel.resetDeletionState()
            deletionUnsyncedCount = pendingItems().size
            showDeletionDialog = true
        }
    )
}

data class ProfileUi(
    val name: String,
    val role: String,
    val phone: String?,
    val email: String?,
    val employeeCode: String?,
    val territory: String?,
    val appVersion: String
)

/** Stateless profile & settings (design v2); also used by the screenshot test. */
@Composable
fun ProfileContent(
    profile: ProfileUi,
    pendingCount: Int,
    onBack: () -> Unit,
    onSyncQueue: () -> Unit,
    onPrivacy: () -> Unit,
    onLogout: () -> Unit,
    onRequestDeletion: () -> Unit
) {
    com.fieldtrackpro.android.ui.theme.SystemBarIcons(darkIcons = true)
    Scaffold(
        topBar = { FieldTrackTopAppBar(title = "Profile & settings", onBackClick = onBack) },
        containerColor = SurfaceSecondary
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                val initials = profile.name.split(" ")
                    .mapNotNull { word -> word.firstOrNull { it.isLetter() } }
                    .take(2).joinToString("") { it.uppercase() }.ifBlank { "?" }
                Box(
                    modifier = Modifier.size(64.dp).clip(CircleShape).background(BrandNavy),
                    contentAlignment = Alignment.Center
                ) {
                    Text(initials, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 24.sp, color = BrandGold)
                }
                Spacer(modifier = Modifier.width(16.dp))
                Column {
                    Text(profile.name, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 22.sp, color = BrandNavy)
                    Spacer(modifier = Modifier.height(6.dp))
                    val chip = listOfNotNull(profile.role, profile.territory?.takeIf { it.isNotBlank() }).joinToString(" · ")
                    com.fieldtrackpro.android.ui.components.StatusChip(
                        text = chip,
                        container = com.fieldtrackpro.android.ui.theme.Navy100,
                        content = BrandNavy
                    )
                }
            }

            com.fieldtrackpro.android.ui.components.SectionHeader("Account")
            com.fieldtrackpro.android.ui.components.ListGroup {
                ProfileRow(Icons.Default.Phone, "Mobile number", profile.phone)
                ProfileRow(Icons.Default.Email, "Email", profile.email)
                ProfileRow(Icons.Default.Badge, "Employee code", profile.employeeCode)
                ProfileRow(Icons.Default.Place, "Territory", profile.territory, last = true)
            }

            com.fieldtrackpro.android.ui.components.SectionHeader("App")
            com.fieldtrackpro.android.ui.components.ListGroup {
                ProfileRow(
                    Icons.Default.Sync,
                    "Sync queue",
                    if (pendingCount == 0) "All synced" else "$pendingCount waiting",
                    onClick = if (pendingCount > 0) onSyncQueue else null
                )
                ProfileRow(Icons.Default.PrivacyTip, "Privacy policy", null, onClick = onPrivacy, showChevron = true)
                ProfileRow(Icons.Default.Info, "App version", profile.appVersion, last = true)
            }

            com.fieldtrackpro.android.ui.components.OutlineButton(
                text = "Log out",
                onClick = onLogout,
                color = ErrorRed,
                icon = Icons.AutoMirrored.Filled.ExitToApp,
                modifier = Modifier.fillMaxWidth()
            )
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                TextButton(onClick = onRequestDeletion) {
                    Text("Request account deletion", fontSize = 14.sp, color = ErrorRed)
                }
            }
        }
    }
}

@Composable
private fun ProfileRow(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    value: String?,
    last: Boolean = false,
    onClick: (() -> Unit)? = null,
    showChevron: Boolean = false
) {
    Column {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)
                .heightIn(min = 56.dp)
                .padding(horizontal = 16.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(icon, contentDescription = null, tint = TextSecondary, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(14.dp))
            Text(label, fontSize = 15.sp, color = TextPrimary, modifier = Modifier.weight(1f))
            if (value != null || !showChevron) {
                Text(
                    value?.takeIf { it.isNotBlank() } ?: "Not set",
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Medium,
                    color = if (value.isNullOrBlank()) com.fieldtrackpro.android.ui.theme.TextSubtle else BrandNavy
                )
            }
            if (showChevron || onClick != null) {
                Icon(Icons.Default.ChevronRight, contentDescription = null, tint = com.fieldtrackpro.android.ui.theme.TextSubtle)
            }
        }
        if (!last) androidx.compose.material3.HorizontalDivider(color = BrandLightGray, modifier = Modifier.padding(start = 50.dp))
    }
}
