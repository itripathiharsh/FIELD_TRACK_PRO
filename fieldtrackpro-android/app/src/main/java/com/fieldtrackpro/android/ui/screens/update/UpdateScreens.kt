package com.fieldtrackpro.android.ui.screens.update

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.SystemUpdate
import androidx.compose.material.icons.filled.VerifiedUser
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.fieldtrackpro.android.ui.components.BrandMark
import com.fieldtrackpro.android.ui.components.InlineErrorCard
import com.fieldtrackpro.android.ui.components.PrimaryButton
import com.fieldtrackpro.android.ui.components.SignalButton
import com.fieldtrackpro.android.ui.components.StatusChip
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.GoldOnNavyText
import com.fieldtrackpro.android.ui.theme.LabelCaps
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.Navy100
import com.fieldtrackpro.android.ui.theme.Navy950
import com.fieldtrackpro.android.ui.theme.SuccessGreenText
import com.fieldtrackpro.android.ui.theme.SystemBarIcons
import com.fieldtrackpro.android.ui.theme.TextOnNavyMuted
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.theme.TextSubtle
import com.fieldtrackpro.android.update.UpdateManifest
import com.fieldtrackpro.android.update.UpdateUiState
import java.util.Locale

private fun UpdateUiState.manifestOrNull(): UpdateManifest? = when (this) {
    UpdateUiState.Hidden -> null
    is UpdateUiState.Available -> manifest
    is UpdateUiState.Downloading -> manifest
    is UpdateUiState.Verifying -> manifest
    is UpdateUiState.NeedsInstallPermission -> manifest
    is UpdateUiState.Installing -> manifest
    is UpdateUiState.Failed -> manifest
}

internal fun formatMb(bytes: Long): String = String.format(Locale.US, "%.1f MB", bytes / 1_048_576.0)

/**
 * Shows the right update surface for [state]: nothing, the optional-update dialog, or (via [MandatoryUpdateScreen],
 * rendered by MainActivity INSTEAD of the app) the blocking screen.
 */
@Composable
fun OptionalUpdateDialog(
    state: UpdateUiState,
    onUpdateNow: () -> Unit,
    onLater: () -> Unit,
    onOpenInstallPermission: () -> Unit
) {
    if (state == UpdateUiState.Hidden || state.isMandatory) return
    val canDismiss = state is UpdateUiState.Available || state is UpdateUiState.Failed || state is UpdateUiState.NeedsInstallPermission
    Dialog(
        onDismissRequest = { if (canDismiss) onLater() },
        properties = DialogProperties(dismissOnBackPress = canDismiss, dismissOnClickOutside = false, usePlatformDefaultWidth = false)
    ) {
        Surface(
            shape = RoundedCornerShape(24.dp),
            color = BrandWhite,
            shadowElevation = 8.dp,
            modifier = Modifier.padding(horizontal = 20.dp).widthIn(max = 460.dp).fillMaxWidth()
        ) {
            UpdateCardContent(state, mandatory = false, onUpdateNow, onLater, onOpenInstallPermission)
        }
    }
}

/** Blocking screen for a mandatory update. Back leaves the app (it cannot be bypassed). */
@Composable
fun MandatoryUpdateScreen(
    state: UpdateUiState,
    onUpdateNow: () -> Unit,
    onOpenInstallPermission: () -> Unit,
    onExitApp: () -> Unit
) {
    SystemBarIcons(darkIcons = false)
    BackHandler { onExitApp() }
    Box(
        Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(BrandNavy, Navy950)))
            .statusBarsPadding()
            .navigationBarsPadding(),
        contentAlignment = Alignment.Center
    ) {
        Column(
            Modifier.verticalScroll(rememberScrollState()).padding(20.dp).widthIn(max = 480.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text("FieldTrack Pro", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 20.sp, color = BrandWhite)
            Spacer(Modifier.height(20.dp))
            Surface(shape = RoundedCornerShape(24.dp), color = BrandWhite, modifier = Modifier.fillMaxWidth()) {
                UpdateCardContent(state, mandatory = true, onUpdateNow, onLater = {}, onOpenInstallPermission)
            }
            Spacer(Modifier.height(16.dp))
            Text(
                "Your saved work and any unsynced items stay on this phone and sync after the update.",
                fontSize = 13.sp, color = TextOnNavyMuted
            )
        }
    }
}

@Composable
internal fun UpdateCardContent(
    state: UpdateUiState,
    mandatory: Boolean,
    onUpdateNow: () -> Unit,
    onLater: () -> Unit,
    onOpenInstallPermission: () -> Unit
) {
    val manifest = state.manifestOrNull() ?: return
    Column {
        // Header band
        Column(
            Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp))
                .background(Brush.verticalGradient(listOf(BrandNavy, Navy950)))
                .padding(horizontal = 22.dp, vertical = 20.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                BrandMark(height = 40.dp)
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        if (mandatory) "Update required" else "Update available",
                        fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 22.sp, color = BrandWhite
                    )
                    Spacer(Modifier.height(6.dp))
                    val size = manifest.apkSizeBytes?.let { " · ${formatMb(it)}" } ?: ""
                    StatusChip("Version ${manifest.versionName}$size", container = BrandGold.copy(alpha = 0.16f), content = GoldOnNavyText)
                }
            }
        }

        Column(Modifier.padding(horizontal = 22.dp, vertical = 18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            val reason = (state as? UpdateUiState.Available)?.reason
            if (mandatory) {
                Text(
                    reason ?: "This update is required to keep using FieldTrack Pro.",
                    fontSize = 15.sp, lineHeight = 21.sp, color = BrandNavy, fontWeight = FontWeight.Medium
                )
            }

            val notes = manifest.releaseNotes.orEmpty().filter { it.isNotBlank() }.take(8)
            if (notes.isNotEmpty()) {
                Text("WHAT'S NEW", style = LabelCaps, color = TextSecondary)
                Column(Modifier.heightIn(max = 180.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    notes.forEach { note ->
                        Row(verticalAlignment = Alignment.Top) {
                            Box(Modifier.padding(top = 7.dp).size(6.dp).clip(CircleShape).background(BrandGold))
                            Spacer(Modifier.width(10.dp))
                            Text(note.take(200), fontSize = 15.sp, lineHeight = 21.sp, color = BrandNavy)
                        }
                    }
                }
            }

            when (state) {
                is UpdateUiState.Downloading -> ProgressBlock(state.downloaded, state.total)
                is UpdateUiState.Verifying -> StepLine("Checking the download is genuine…")
                is UpdateUiState.Installing -> StepLine("Opening the Android installer. Tap Install to finish.")
                is UpdateUiState.NeedsInstallPermission -> Text(
                    "To install updates, allow FieldTrack Pro to install apps. Android will open the setting; switch it on and come back.",
                    fontSize = 14.sp, lineHeight = 20.sp, color = TextSecondary
                )
                is UpdateUiState.Failed -> InlineErrorCard(message = state.message)
                else -> Unit
            }

            val isBusy = state is UpdateUiState.Downloading || state is UpdateUiState.Verifying || state is UpdateUiState.Installing
            // While busy the progress block is the only action; no half-disabled button.
            if (!isBusy) Row(
                Modifier.fillMaxWidth().padding(top = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                val busy = state is UpdateUiState.Downloading || state is UpdateUiState.Verifying || state is UpdateUiState.Installing
                if (!mandatory && !busy) {
                    TextButton(onClick = onLater, modifier = Modifier.heightIn(min = 52.dp)) {
                        Text("Later", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 15.sp, color = TextSecondary)
                    }
                }
                Spacer(Modifier.weight(1f))
                when (state) {
                    is UpdateUiState.NeedsInstallPermission ->
                        PrimaryButton("Allow installs", onClick = onOpenInstallPermission)
                    is UpdateUiState.Failed ->
                        SignalButton("Retry", onClick = onUpdateNow, icon = Icons.Default.SystemUpdate)
                    else -> SignalButton(
                        text = "Update now",
                        onClick = onUpdateNow,
                        loading = busy,
                        icon = Icons.Default.SystemUpdate
                    )
                }
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.VerifiedUser, contentDescription = null, tint = SuccessGreenText, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text(
                    "Downloaded over HTTPS, checked against its SHA-256 and our signature, then installed by Android.",
                    fontSize = 12.sp, lineHeight = 16.sp, color = TextSubtle
                )
            }
        }
    }
}

@Composable
private fun ProgressBlock(done: Long, total: Long?) {
    Column(Modifier.semantics { liveRegion = LiveRegionMode.Polite }) {
        val fraction = if (total != null && total > 0) (done.toFloat() / total).coerceIn(0f, 1f) else null
        if (fraction != null) {
            LinearProgressIndicator(
                progress = { fraction },
                color = BrandGold,
                trackColor = Navy100,
                modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp))
            )
        } else {
            LinearProgressIndicator(color = BrandGold, trackColor = Navy100, modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)))
        }
        Spacer(Modifier.height(8.dp))
        Row {
            Text("Downloading…", fontSize = 13.sp, color = TextSecondary, modifier = Modifier.weight(1f))
            Text(
                if (total != null && total > 0) "${formatMb(done)} of ${formatMb(total)} · ${(fraction!! * 100).toInt()}%" else formatMb(done),
                fontSize = 13.sp, color = BrandNavy, fontWeight = FontWeight.SemiBold
            )
        }
    }
}

@Composable
private fun StepLine(text: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        LinearProgressIndicator(color = BrandGold, trackColor = Navy100, modifier = Modifier.width(48.dp).height(6.dp).clip(RoundedCornerShape(3.dp)))
        Spacer(Modifier.width(12.dp))
        Text(text, fontSize = 14.sp, color = TextSecondary)
    }
}
