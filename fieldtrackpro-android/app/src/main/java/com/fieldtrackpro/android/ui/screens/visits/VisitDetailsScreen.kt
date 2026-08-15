package com.fieldtrackpro.android.ui.screens.visits

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material3.Icon
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.FormSubmissionDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.FormTemplateRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.ui.components.EmptyState
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.GeofenceStatusCard
import com.fieldtrackpro.android.ui.components.LoadingScreen
import com.fieldtrackpro.android.ui.components.StatusBadge
import com.fieldtrackpro.android.ui.theme.FieldTrackAmber
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SurfaceOffWhite
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.theme.TextMuted
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.viewmodel.VisitDetailState
import com.fieldtrackpro.android.ui.viewmodel.VisitDetailsViewModel

@Composable
fun VisitDetailsScreen(
    visitId: String,
    viewModel: VisitDetailsViewModel,
    onNavigateBack: () -> Unit,
    onNavigateToCheckIn: (String, String) -> Unit,
    onNavigateToCheckOut: (String, String) -> Unit,
    onNavigateToMedia: (String) -> Unit,
    onNavigateToOrderCapture: (String) -> Unit = {},
    onNavigateToMap: (String) -> Unit,
    onNavigateToSignature: (String) -> Unit,
    onNavigateToPreview: (mediaId: String, fileName: String, isPhoto: Boolean) -> Unit = { _, _, _ -> },
    onNavigateToFormFill: (visitId: String, formId: String) -> Unit = { _, _ -> },
    onNavigateToAccount: (visitId: String, customerId: String) -> Unit = { _, _ -> },
    geofenceViewModel: com.fieldtrackpro.android.ui.viewmodel.GeofenceViewModel
) {
    val detailState by viewModel.detailState.collectAsState()

    val context = LocalContext.current
    val formRepository = remember { FormTemplateRepository(ApiClient.createFormTemplateApi(TokenManager(context))) }
    var requiredFormSubmission by remember { mutableStateOf<FormSubmissionDto?>(null) }

    LaunchedEffect(visitId) {
        viewModel.loadVisitDetails(visitId)
    }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "Visit Details",
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
            when (val s = detailState) {
                is VisitDetailState.Loading -> LoadingScreen(message = "Retrieving visit data...")
                is VisitDetailState.Error -> EmptyState(title = "Visit Error", subtitle = s.message)
                is VisitDetailState.Success -> {
                    val visit = s.visit
                    val logs = s.geoLogs

                    LaunchedEffect(visit.requiredFormId) {
                        val formId = visit.requiredFormId
                        requiredFormSubmission = if (formId != null) {
                            when (val res = formRepository.getSubmissionForVisit(formId, visit.id)) {
                                is Resource.Success -> res.data
                                else -> null
                            }
                        } else {
                            null
                        }
                    }

                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(16.dp),
                        colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
                    ) {
                        Column(modifier = Modifier.padding(20.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "Customer #${visit.customerId.take(8)}",
                                    style = MaterialTheme.typography.titleLarge,
                                    color = FieldTrackNavy
                                )
                                StatusBadge(status = visit.status)
                            }

                            Spacer(modifier = Modifier.height(12.dp))

                            DetailItem(label = "Customer ID", value = visit.customerId)
                            DetailItem(label = "Scheduled", value = visit.scheduledAt)

                            visit.checkInAt?.let {
                                DetailItem(label = "Checked In", value = it)
                            }
                            visit.checkOutAt?.let {
                                DetailItem(label = "Checked Out", value = it)
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(20.dp))

                    val geofenceUiState by geofenceViewModel.uiState.collectAsState()

                    val locationPermissionLauncher = rememberLauncherForActivityResult(
                        contract = ActivityResultContracts.RequestMultiplePermissions()
                    ) {
                        geofenceViewModel.checkPermissions()
                    }

                    LaunchedEffect(visit.customerId) {
                        geofenceViewModel.checkPermissions()
                    }

                    LaunchedEffect(s.customer, visit.id, visit.status) {
                        if (s.customer != null && (visit.status == "PENDING" || visit.status == "FLAGGED")) {
                            geofenceViewModel.startMonitoring(
                                visitId = visit.id,
                                customer = s.customer,
                                radiusMeters = s.customer.geofenceRadiusM.toFloat()
                            )
                        } else {
                            // P1-8: the visit checked in/out (or otherwise
                            // left PENDING/FLAGGED) while this screen stayed
                            // open - monitoring is no longer relevant, so
                            // stop it now rather than leaving it registered
                            // until the screen happens to be left.
                            geofenceViewModel.stopMonitoring()
                        }
                    }

                    // P1-8: leaving this visit's details (back navigation,
                    // switching to another visit, or the screen otherwise
                    // leaving composition) must not leave its geofence
                    // registered. onDispose runs exactly once when this
                    // composable leaves composition.
                    DisposableEffect(visit.id) {
                        onDispose {
                            geofenceViewModel.stopMonitoring()
                        }
                    }

                    // Action Buttons based on status
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        if (visit.status == "PENDING" || visit.status == "FLAGGED") {
                            val canCheckIn = !geofenceUiState.isMonitoring || geofenceUiState.isInside
                            Button(
                                onClick = { onNavigateToCheckIn(visit.id, visit.customerId) },
                                modifier = Modifier.weight(1f),
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = if (canCheckIn) FieldTrackNavy else TextMuted,
                                    contentColor = SurfaceWhite
                                ),
                                enabled = canCheckIn
                            ) {
                                Text(if (canCheckIn) "CHECK-IN GPS" else "OUTSIDE AREA", color = SurfaceWhite)
                            }
                        }

                        if (visit.status == "IN_PROGRESS" || visit.status == "FLAGGED") {
                            Button(
                                onClick = { onNavigateToCheckOut(visit.id, visit.customerId) },
                                modifier = Modifier.weight(1f),
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = SuccessGreen,
                                    contentColor = SurfaceWhite
                                )
                            ) {
                                Text("CHECK-OUT GPS", color = SurfaceWhite)
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    OutlinedButton(
                        onClick = { onNavigateToMedia(visit.id) },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("ATTACHMENTS & MEDIA", color = FieldTrackNavy)
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    // P2-B: order capture - a photographed order diary note tied to this visit/outlet.
                    OutlinedButton(
                        onClick = { onNavigateToOrderCapture(visit.id) },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("CAPTURE ORDER", color = FieldTrackNavy)
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    OutlinedButton(
                        onClick = { onNavigateToSignature(visit.id) },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("DIGITAL SIGNATURE", color = FieldTrackNavy)
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    // P1: Outlet Account - outstanding/aging/history + Collect Payment.
                    OutlinedButton(
                        onClick = { onNavigateToAccount(visit.id, visit.customerId) },
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text("OUTLET ACCOUNT", color = FieldTrackNavy)
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text(
                                text = "REQUIRED FORM",
                                style = MaterialTheme.typography.titleMedium,
                                color = FieldTrackNavy
                            )
                            Spacer(modifier = Modifier.height(8.dp))

                            val requiredFormId = visit.requiredFormId
                            if (requiredFormId == null) {
                                Text("No form required for this visit.", fontSize = 13.sp, color = TextMuted)
                            } else {
                                val submission = requiredFormSubmission
                                val isSubmitted = submission?.status == "SUBMITTED"
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Column {
                                        Text(
                                            text = visit.requiredFormName ?: "Form",
                                            fontSize = 14.sp,
                                            fontWeight = FontWeight.SemiBold,
                                            color = FieldTrackNavy
                                        )
                                        if (isSubmitted) {
                                            Row(verticalAlignment = Alignment.CenterVertically) {
                                                Icon(
                                                    imageVector = Icons.Filled.CheckCircle,
                                                    contentDescription = null,
                                                    tint = SuccessGreen,
                                                    modifier = Modifier.size(14.dp)
                                                )
                                                Spacer(modifier = Modifier.width(4.dp))
                                                Text(
                                                    text = "Submitted: ${submission?.submittedAt ?: ""}",
                                                    fontSize = 11.sp,
                                                    color = TextMuted
                                                )
                                            }
                                        } else {
                                            val statusLabel = if (submission != null) "Draft saved" else "Not Started"
                                            Text("Status: $statusLabel", fontSize = 11.sp, color = TextMuted)
                                        }
                                        if (visit.requiredFormStatus == "ARCHIVED") {
                                            Text("This form has since been archived.", fontSize = 11.sp, color = FieldTrackAmber)
                                        }
                                    }
                                    if (!isSubmitted) {
                                        Button(
                                            onClick = { onNavigateToFormFill(visit.id, requiredFormId) },
                                            colors = ButtonDefaults.buttonColors(
                                                containerColor = FieldTrackAmber,
                                                contentColor = FieldTrackNavy
                                            )
                                        ) {
                                            Text(
                                                if (submission != null) "CONTINUE" else "START FORM",
                                                color = FieldTrackNavy,
                                                fontSize = 12.sp
                                            )
                                        }
                                    } else {
                                        OutlinedButton(onClick = { onNavigateToFormFill(visit.id, requiredFormId) }) {
                                            Text("VIEW", color = FieldTrackNavy, fontSize = 12.sp)
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Spacer(modifier = Modifier.height(12.dp))

                    // Geofence Status Section
                    GeofenceStatusCard(
                        isInside = geofenceUiState.isInside,
                        isOutside = geofenceUiState.isOutside,
                        hasPermission = geofenceUiState.hasPermission,
                        isLocationEnabled = geofenceUiState.isLocationEnabled,
                        isMonitoring = geofenceUiState.isMonitoring,
                        errorMessage = geofenceUiState.errorMessage
                    )

                    if (!geofenceUiState.hasPermission) {
                        Spacer(modifier = Modifier.height(8.dp))
                        OutlinedButton(
                            onClick = {
                                locationPermissionLauncher.launch(
                                    arrayOf(
                                        android.Manifest.permission.ACCESS_FINE_LOCATION,
                                        android.Manifest.permission.ACCESS_COARSE_LOCATION,
                                    )
                                )
                            },
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text("GRANT LOCATION PERMISSION", color = FieldTrackNavy)
                        }
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    // Map Preview Section
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text(
                                text = "Customer Location",
                                style = MaterialTheme.typography.titleMedium,
                                color = FieldTrackNavy
                            )
                            Spacer(modifier = Modifier.height(4.dp))
                            Text(
                                text = "View customer location on map and get directions.",
                                style = MaterialTheme.typography.bodyMedium,
                                color = TextMuted
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            OutlinedButton(
                                onClick = { onNavigateToMap(visit.customerId) },
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Text("VIEW ON MAP", color = FieldTrackNavy)
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(24.dp))

                    // Geo Logs Section
                    Text(
                        text = "Geo Verification Logs (${logs.size})",
                        style = MaterialTheme.typography.titleMedium,
                        color = FieldTrackNavy
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    if (logs.isEmpty()) {
                        Text("No geo-location check attempts recorded yet.", fontSize = 13.sp, color = TextMuted)
                    } else {
                        logs.forEach { log ->
                            Card(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 4.dp),
                                shape = RoundedCornerShape(8.dp),
                                colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
                            ) {
                                Row(
                                    modifier = Modifier
                                        .padding(12.dp)
                                        .fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Column {
                                        Text(
                                            text = log.verificationType,
                                            fontSize = 13.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = TextPrimary
                                        )
                                        Text(
                                            text = "Coords: ${log.latitude}, ${log.longitude}",
                                            fontSize = 11.sp,
                                            color = TextMuted
                                        )
                                        if (log.failureReason != null) {
                                            Text(
                                                text = "Reason: ${log.failureReason}",
                                                fontSize = 11.sp,
                                                color = FieldTrackAmber
                                            )
                                        }
                                    }
                                    StatusBadge(status = if (log.isValid) "VALID" else "INVALID")
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun DetailItem(label: String, value: String) {
    Column(modifier = Modifier.padding(vertical = 4.dp)) {
        Text(text = label, fontSize = 11.sp, color = TextMuted)
        Text(text = value, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = TextPrimary)
    }
}
