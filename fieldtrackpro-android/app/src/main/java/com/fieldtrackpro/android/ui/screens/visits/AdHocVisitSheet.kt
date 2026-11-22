package com.fieldtrackpro.android.ui.screens.visits

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.GpsFixed
import androidx.compose.material.icons.filled.LocationOff
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.search.CustomerSearchState
import com.fieldtrackpro.android.services.LocationCaptureService
import com.fieldtrackpro.android.ui.components.CustomerPicker
import com.fieldtrackpro.android.ui.components.OutlineButton
import com.fieldtrackpro.android.ui.components.SignalButton
import com.fieldtrackpro.android.ui.screens.planning.FieldBlock
import com.fieldtrackpro.android.ui.screens.planning.SheetHeader
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.SuccessGreenBg
import com.fieldtrackpro.android.ui.theme.SuccessGreenText
import com.fieldtrackpro.android.ui.theme.WarningGoldBg
import com.fieldtrackpro.android.ui.theme.WarningGoldText
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel

/** GPS readiness shown in the sheet. The visit itself is GPS-verified at check-in, exactly as before. */
enum class GpsReadiness { READY, PERMISSION_NEEDED, LOCATION_OFF }

/**
 * Start an off-beat (ad-hoc) visit. Business logic is unchanged: it calls VisitsViewModel.createAdHocVisit with the
 * customer, reason and notes; location is verified when the employee checks in at the outlet.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AdHocVisitSheet(
    viewModel: VisitsViewModel,
    onDismiss: () -> Unit,
    onVisitCreated: (VisitDto) -> Unit,
    onError: (String) -> Unit
) {
    val context = LocalContext.current
    val search by viewModel.adHocSearch.state.collectAsState()
    val isCreating by viewModel.isCreatingAdHocVisit.collectAsState()
    val gps = remember {
        val svc = LocationCaptureService(context)
        when {
            !svc.hasLocationPermission() -> GpsReadiness.PERMISSION_NEEDED
            !svc.isLocationEnabled() -> GpsReadiness.LOCATION_OFF
            else -> GpsReadiness.READY
        }
    }
    LaunchedEffect(Unit) { viewModel.adHocSearch.start() }

    ModalBottomSheet(
        onDismissRequest = { if (!isCreating) { viewModel.adHocSearch.clear(); onDismiss() } },
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = BrandWhite,
        shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp)
    ) {
        AdHocVisitForm(
            search = search,
            gps = gps,
            isCreating = isCreating,
            onQueryChange = viewModel.adHocSearch::onQueryChange,
            onCancel = { viewModel.adHocSearch.clear(); onDismiss() },
            onStart = { customer, reason, notes ->
                viewModel.createAdHocVisit(
                    customerId = customer.id,
                    adhocReason = reason,
                    adhocNotes = notes,
                    onSuccess = {
                        viewModel.adHocSearch.clear()
                        onVisitCreated(it)
                    },
                    onError = onError
                )
            }
        )
    }
}

/** Form body (rendered by the screenshot test). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun AdHocVisitForm(
    search: CustomerSearchState,
    gps: GpsReadiness,
    isCreating: Boolean,
    onQueryChange: (String) -> Unit,
    onCancel: () -> Unit,
    onStart: (CustomerDto, String, String?) -> Unit,
    preselected: CustomerDto? = null
) {
    var selected by remember { mutableStateOf(preselected) }
    var reason by rememberSaveable { mutableStateOf(AD_HOC_REASONS[0]) }
    var notes by rememberSaveable { mutableStateOf("") }
    var tried by remember { mutableStateOf(false) }

    Column(
        Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).imePadding().navigationBarsPadding()
            .padding(horizontal = 20.dp).padding(bottom = 20.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
    ) {
        SheetHeader("Start an off-beat visit", "Visit an outlet that is not on today's beat.")

        CustomerPicker(
            state = search,
            selected = selected,
            onQueryChange = onQueryChange,
            onSelect = { selected = it },
            onClearSelection = { selected = null },
            label = "Outlet"
        )
        if (tried && selected == null) Text("Choose an outlet to continue.", fontSize = 13.sp, color = ErrorRed)

        FieldBlock("Reason for the visit") {
            // Wrapping chips: nothing is clipped horizontally on narrow phones.
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                AD_HOC_REASONS.forEach { r ->
                    val on = r == reason
                    Text(
                        r,
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = if (on) FontWeight.Bold else FontWeight.Medium,
                        fontSize = 14.sp,
                        color = if (on) BrandWhite else BrandNavy,
                        modifier = Modifier
                            .clip(RoundedCornerShape(50))
                            .background(if (on) BrandNavy else BrandWhite)
                            .border(1.dp, if (on) BrandNavy else BrandLightGray, RoundedCornerShape(50))
                            .clickable(role = Role.RadioButton) { reason = r }
                            .heightIn(min = 40.dp)
                            .padding(horizontal = 14.dp, vertical = 10.dp)
                    )
                }
            }
        }

        FieldBlock("Remarks (optional)") {
            OutlinedTextField(
                value = notes,
                onValueChange = { notes = it.take(500) },
                placeholder = { Text("What is this visit about?") },
                minLines = 2,
                maxLines = 5,
                shape = RoundedCornerShape(14.dp),
                colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = BrandGold, unfocusedBorderColor = BrandLightGray),
                modifier = Modifier.fillMaxWidth()
            )
        }

        GpsStatusRow(gps)

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlineButton("Cancel", onClick = onCancel, enabled = !isCreating, modifier = Modifier.weight(1f))
            SignalButton(
                text = "Start visit",
                onClick = {
                    tried = true
                    val c = selected ?: return@SignalButton
                    onStart(c, reason, notes.ifBlank { null })
                },
                loading = isCreating,
                modifier = Modifier.weight(1.4f)
            )
        }
    }
}

@Composable
private fun GpsStatusRow(gps: GpsReadiness) {
    val (bg, fg, text) = when (gps) {
        GpsReadiness.READY -> Triple(SuccessGreenBg, SuccessGreenText, "GPS is on. Your location is verified when you check in at the outlet.")
        GpsReadiness.PERMISSION_NEEDED -> Triple(WarningGoldBg, WarningGoldText, "Location permission is needed to check in. You'll be asked when you check in.")
        GpsReadiness.LOCATION_OFF -> Triple(WarningGoldBg, WarningGoldText, "Location is off. Turn it on before you check in at the outlet.")
    }
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(bg).padding(12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(if (gps == GpsReadiness.READY) Icons.Default.GpsFixed else Icons.Default.LocationOff, contentDescription = null, tint = fg, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(10.dp))
        Text(text, fontSize = 13.sp, lineHeight = 18.sp, color = fg, fontWeight = FontWeight.Medium)
    }
}
