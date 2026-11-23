package com.fieldtrackpro.android.ui.screens.visits

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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.LocationCaptureButton
import com.fieldtrackpro.android.ui.theme.BrandBlack
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.viewmodel.CheckInState
import com.fieldtrackpro.android.BuildConfig
import com.fieldtrackpro.android.utils.GeoDecision
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.TextButton
import com.fieldtrackpro.android.ui.viewmodel.CheckInViewModel
import com.fieldtrackpro.android.utils.CoordinateValidator

@Composable
fun CheckInScreen(
    visitId: String,
    customerId: String,
    viewModel: CheckInViewModel,
    onNavigateBack: () -> Unit,
    onSuccess: () -> Unit
) {
    val state by viewModel.state.collectAsState()
    var simulateOffline by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        viewModel.resetState()
    }

    if (state is CheckInState.ActionSuccess) {
        LaunchedEffect(state) {
            viewModel.resetState()
            onSuccess()
        }
    }

    val busy = state is CheckInState.Collecting || state is CheckInState.Processing

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "Check In",
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
                        text = "Check in at the outlet",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = BrandNavy
                    )
                    Text(
                        text = "Your location is checked against the outlet's saved GPS position. No photo is needed. " +
                            "Indoors the signal can be weaker: the app waits up to 45 seconds for a good reading.",
                        fontFamily = LibreBaskervilleFamily,
                        fontSize = 13.sp,
                        color = TextSecondary
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    (state as? CheckInState.Collecting)?.let { c ->
                        CollectingCard(c, onCancel = { viewModel.cancelCollection() })
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    (state as? CheckInState.Error)?.let { ErrorBanner(message = it.message); Spacer(modifier = Modifier.height(12.dp)) }
                    (state as? CheckInState.InvalidCoordinates)?.let { ErrorBanner(message = it.message); Spacer(modifier = Modifier.height(12.dp)) }
                    (state as? CheckInState.GeoRejected)?.let { ErrorBanner(message = it.message); Spacer(modifier = Modifier.height(12.dp)) }
                    (state as? CheckInState.LowAccuracy)?.let { ErrorBanner(message = it.message); Spacer(modifier = Modifier.height(12.dp)) }
                    (state as? CheckInState.StaleLocation)?.let { ErrorBanner(message = it.message); Spacer(modifier = Modifier.height(12.dp)) }

                    (state as? CheckInState.NeedsVerification)?.let { v ->
                        NoticeCard(
                            title = "LOCATION NOT CERTAIN",
                            body = "The GPS reading is about ${v.distanceM.toInt()} m from the outlet with an accuracy of ±${v.accuracyM.toInt()} m, " +
                                "so the app cannot tell whether you are at the shop. You can move closer to the entrance and try again, " +
                                "or ask an administrator to verify your visit."
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        OutlinedButton(
                            onClick = { viewModel.requestVerification(visitId) },
                            modifier = Modifier.fillMaxWidth().height(46.dp),
                            shape = RoundedCornerShape(10.dp)
                        ) {
                            Text("REQUEST ADMIN VERIFICATION", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 13.sp, color = BrandNavy)
                        }
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    (state as? CheckInState.VerificationRequested)?.let {
                        NoticeCard(title = "REQUEST SENT", body = it.message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    (state as? CheckInState.Conflict)?.let {
                        NoticeCard(title = "SCHEDULE CONFLICT", body = it.message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    (state as? CheckInState.Queued)?.let {
                        NoticeCard(title = "QUEUED FOR SYNC", body = it.message)
                        Spacer(modifier = Modifier.height(12.dp))
                    }

                    if (BuildConfig.DEBUG) {
                        // QA aid only: send this check-in through the offline queue.
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(
                                checked = simulateOffline,
                                onCheckedChange = { simulateOffline = it },
                                colors = CheckboxDefaults.colors(checkedColor = BrandNavy, checkmarkColor = BrandGold)
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = "Debug: simulate offline (queue this check-in)",
                                fontFamily = LeagueSpartanFamily,
                                fontSize = 13.sp,
                                color = TextPrimary
                            )
                        }
                        Spacer(modifier = Modifier.height(8.dp))
                    }

                    Button(
                        onClick = { viewModel.startCheckIn(visitId, customerId, simulateOffline) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp),
                        shape = RoundedCornerShape(10.dp),
                        enabled = !busy,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = BrandNavy,
                            contentColor = BrandWhite,
                            disabledContainerColor = BrandLightGray,
                            disabledContentColor = TextSecondary
                        )
                    ) {
                        if (state is CheckInState.Processing) {
                            CircularProgressIndicator(color = BrandGold, modifier = Modifier.size(24.dp))
                        } else {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(
                                    imageVector = Icons.Default.LocationOn,
                                    contentDescription = null,
                                    tint = if (!busy) BrandGold else TextSecondary,
                                    modifier = Modifier.size(20.dp)
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    if (state is CheckInState.Collecting) "GETTING LOCATION…" else "CHECK IN",
                                    fontFamily = LeagueSpartanFamily,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 14.sp,
                                    letterSpacing = 0.5.sp,
                                    color = if (!busy) BrandWhite else TextSecondary
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CollectingCard(c: CheckInState.Collecting, onCancel: () -> Unit) {
    val verdict = when (c.outcome) {
        GeoDecision.Outcome.INSIDE -> "Inside the outlet radius"
        GeoDecision.Outcome.OUTSIDE -> "Outside the outlet radius"
        GeoDecision.Outcome.UNCERTAIN -> "Not certain yet, improving…"
        GeoDecision.Outcome.POOR_FIX -> "Waiting for a usable GPS fix…"
        null -> "Looking for GPS…"
    }
    Card(
        modifier = Modifier.fillMaxWidth().border(1.dp, BrandGold, RoundedCornerShape(8.dp)),
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = BrandGold.copy(alpha = 0.12f))
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                text = "GETTING A RELIABLE LOCATION",
                fontFamily = LeagueSpartanFamily, fontSize = 12.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.5.sp, color = BrandNavy
            )
            Spacer(modifier = Modifier.height(6.dp))
            LinearProgressIndicator(
                progress = { (c.elapsedS / 45f).coerceIn(0f, 1f) },
                modifier = Modifier.fillMaxWidth(),
                color = BrandNavy
            )
            Spacer(modifier = Modifier.height(6.dp))
            val acc = c.bestAccuracyM?.let { "best GPS ±${it.toInt()} m" } ?: "no GPS reading yet"
            val dist = c.distanceM?.let { " · about ${it.toInt()} m from the outlet" } ?: ""
            Text(
                text = "$verdict\n$acc$dist · ${c.elapsedS}s of 45s",
                fontFamily = LibreBaskervilleFamily, fontSize = 12.sp, color = TextPrimary
            )
            TextButton(onClick = onCancel) { Text("Cancel", color = BrandNavy, fontWeight = FontWeight.Bold) }
        }
    }
}

@Composable
private fun NoticeCard(title: String, body: String) {
    Card(
        modifier = Modifier.fillMaxWidth().border(1.dp, BrandGold, RoundedCornerShape(8.dp)),
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = BrandGold.copy(alpha = 0.12f))
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                text = title,
                fontFamily = LeagueSpartanFamily, fontSize = 12.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.5.sp, color = BrandNavy
            )
            Text(text = body, fontFamily = LibreBaskervilleFamily, fontSize = 12.sp, color = TextPrimary)
        }
    }
}
