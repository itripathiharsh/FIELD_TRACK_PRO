package com.fieldtrackpro.android.ui.screens.visits

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.automirrored.filled.ArrowForwardIos
import androidx.compose.material.icons.filled.AccountBalanceWallet
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Draw
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Map
import androidx.compose.material.icons.filled.ReceiptLong
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
                .background(SurfaceSecondary)
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

                    // Main Customer Card
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .border(1.dp, BrandLightGray, RoundedCornerShape(14.dp)),
                        shape = RoundedCornerShape(14.dp),
                        colors = CardDefaults.cardColors(containerColor = BrandWhite),
                        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                    ) {
                        Column(modifier = Modifier.padding(18.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = visit.customerName ?: "Outlet #${visit.customerId.take(8)}",
                                    fontFamily = LeagueSpartanFamily,
                                    fontSize = 18.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = BrandNavy,
                                    modifier = Modifier.weight(1f)
                                )
                                StatusBadge(status = visit.status)
                            }

                            Spacer(modifier = Modifier.height(14.dp))

                            val areaContext = listOfNotNull(visit.areaName, visit.territoryName).joinToString(", ")
                            if (areaContext.isNotEmpty()) {
                                DetailItem(label = "Area / Territory", value = areaContext)
                            }
                            if (!visit.customerAddress.isNullOrEmpty()) {
                                DetailItem(label = "Customer Address", value = visit.customerAddress)
                            }
                            
                            DetailItem(label = "Customer ID", value = visit.customerId)
                            DetailItem(label = "Scheduled For", value = visit.scheduledAt)

                            visit.checkInAt?.let {
                                DetailItem(label = "Checked In", value = it)
                            }
                            visit.checkOutAt?.let {
                                DetailItem(label = "Checked Out", value = it)
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(14.dp))

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
                            geofenceViewModel.stopMonitoring()
                        }
                    }

                    DisposableEffect(visit.id) {
                        onDispose {
                            geofenceViewModel.stopMonitoring()
                        }
                    }

                    // Geofence status card
                    GeofenceStatusCard(
                        isInside = geofenceUiState.isInside,
                        isOutside = geofenceUiState.isOutside,
                        hasPermission = geofenceUiState.hasPermission,
                        isLocationEnabled = geofenceUiState.isLocationEnabled,
                        isMonitoring = geofenceUiState.isMonitoring,
                        errorMessage = geofenceUiState.errorMessage,
                        distanceM = geofenceUiState.distanceM,
                        geofenceRadiusM = s.customer?.geofenceRadiusM?.toDouble(),
                        isLoadingLocation = geofenceUiState.isLoadingLocation
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    // Primary Action Button (Check-In or Check-Out)
                    if (visit.status == "PENDING" || visit.status == "FLAGGED") {
                        val canCheckIn = !geofenceUiState.isMonitoring || geofenceUiState.isInside
                        Button(
                            onClick = { onNavigateToCheckIn(visit.id, visit.customerId) },
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(52.dp),
                            shape = RoundedCornerShape(10.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (canCheckIn) BrandNavy else BrandLightGray,
                                contentColor = if (canCheckIn) BrandWhite else TextSecondary
                            ),
                            enabled = canCheckIn
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(
                                    imageVector = Icons.Default.LocationOn,
                                    contentDescription = null,
                                    tint = if (canCheckIn) BrandGold else TextSecondary,
                                    modifier = Modifier.size(20.dp)
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    if (canCheckIn) "CHECK-IN GPS VERIFICATION" else "OUTSIDE CUSTOMER RADIUS",
                                    fontFamily = LeagueSpartanFamily,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 14.sp,
                                    letterSpacing = 0.5.sp,
                                    color = if (canCheckIn) BrandWhite else TextSecondary
                                )
                            }
                        }
                    }

                    if (visit.status == "IN_PROGRESS") {
                        Button(
                            onClick = { onNavigateToCheckOut(visit.id, visit.customerId) },
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(52.dp),
                            shape = RoundedCornerShape(10.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = SuccessGreen,
                                contentColor = BrandWhite
                            )
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(
                                    imageVector = Icons.Default.CheckCircle,
                                    contentDescription = null,
                                    tint = BrandWhite,
                                    modifier = Modifier.size(20.dp)
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    "COMPLETE & CHECK-OUT GPS",
                                    fontFamily = LeagueSpartanFamily,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 14.sp,
                                    letterSpacing = 0.5.sp,
                                    color = BrandWhite
                                )
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(20.dp))

                    // Action Tiles Section Header
                    Text(
                        text = "VISIT OPERATIONS & WORKFLOW",
                        fontFamily = LeagueSpartanFamily,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 1.sp,
                        color = BrandNavy
                    )

                    Spacer(modifier = Modifier.height(10.dp))

                    // Map Navigation Tile
                    ActionTile(
                        title = "Live Map & Routing",
                        subtitle = "View customer location, radius & live navigation",
                        icon = Icons.Default.Map,
                        onClick = { onNavigateToMap(visit.customerId) }
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    // Media & Attachments Tile
                    ActionTile(
                        title = "Attachments & Media",
                        subtitle = "Upload outlet photos, invoices & site proofs",
                        icon = Icons.Default.Image,
                        onClick = { onNavigateToMedia(visit.id) }
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    // Order Capture Tile
                    ActionTile(
                        title = "Capture Order / MIS",
                        subtitle = "Record stock requirement, diary notes & order info",
                        icon = Icons.Default.ReceiptLong,
                        onClick = { onNavigateToOrderCapture(visit.id) }
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    // Digital Signature Tile
                    ActionTile(
                        title = "Digital Customer Signature",
                        subtitle = "Capture signatory name, phone & authorization",
                        icon = Icons.Default.Draw,
                        onClick = { onNavigateToSignature(visit.id) }
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    // Outlet Account Tile
                    ActionTile(
                        title = "Outlet Account & Payments",
                        subtitle = "Collections overview, aging & payment receipt",
                        icon = Icons.Default.AccountBalanceWallet,
                        onClick = { onNavigateToAccount(visit.id, visit.customerId) }
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    // Required Form Card
                    val requiredFormId = visit.requiredFormId
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = BrandWhite)
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = "REQUIRED FORM",
                                    fontFamily = LeagueSpartanFamily,
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.Bold,
                                    letterSpacing = 0.8.sp,
                                    color = BrandNavy
                                )
                                if (requiredFormId != null) {
                                    val isSubmitted = requiredFormSubmission?.status == "SUBMITTED"
                                    StatusBadge(status = if (isSubmitted) "COMPLETED" else "PENDING")
                                }
                            }
                            Spacer(modifier = Modifier.height(8.dp))

                            if (requiredFormId == null) {
                                Text(
                                    "No mandatory audit form attached to this visit.",
                                    fontFamily = LibreBaskervilleFamily,
                                    fontSize = 13.sp,
                                    color = TextSecondary
                                )
                            } else {
                                val submission = requiredFormSubmission
                                val isSubmitted = submission?.status == "SUBMITTED"

                                if (isSubmitted) {
                                    Text(
                                        "Form responses captured and verified.",
                                        fontFamily = LibreBaskervilleFamily,
                                        fontSize = 13.sp,
                                        color = TextSecondary
                                    )
                                } else {
                                    Text(
                                        "Complete the mandatory customer audit checklist.",
                                        fontFamily = LibreBaskervilleFamily,
                                        fontSize = 13.sp,
                                        color = TextSecondary
                                    )
                                    Spacer(modifier = Modifier.height(10.dp))
                                    Button(
                                        onClick = { onNavigateToFormFill(visit.id, requiredFormId) },
                                        modifier = Modifier.fillMaxWidth(),
                                        shape = RoundedCornerShape(8.dp),
                                        colors = ButtonDefaults.buttonColors(containerColor = BrandGold)
                                    ) {
                                        Text(
                                            "FILL REQUIRED FORM",
                                            fontFamily = LeagueSpartanFamily,
                                            fontWeight = FontWeight.Bold,
                                            color = BrandBlack
                                        )
                                    }
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
fun ActionTile(
    title: String,
    subtitle: String,
    icon: ImageVector,
    onClick: () -> Unit
) {
    Card(
        onClick = onClick,
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = BrandWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(40.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(BrandNavy)
                    .border(1.dp, BrandGold, RoundedCornerShape(8.dp)),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = BrandGold,
                    modifier = Modifier.size(20.dp)
                )
            }

            Spacer(modifier = Modifier.width(12.dp))

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = title,
                    fontFamily = LeagueSpartanFamily,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Bold,
                    color = BrandNavy
                )
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = subtitle,
                    fontFamily = LibreBaskervilleFamily,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Normal,
                    color = TextSecondary
                )
            }

            Icon(
                imageVector = Icons.AutoMirrored.Filled.ArrowForwardIos,
                contentDescription = null,
                tint = BrandNavy.copy(alpha = 0.4f),
                modifier = Modifier.size(14.dp)
            )
        }
    }
}

@Composable
fun DetailItem(label: String, value: String) {
    Column(modifier = Modifier.padding(vertical = 3.dp)) {
        Text(
            text = label.uppercase(),
            fontFamily = LeagueSpartanFamily,
            fontSize = 11.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 0.8.sp,
            color = BrandNavy.copy(alpha = 0.75f)
        )
        Spacer(modifier = Modifier.height(1.dp))
        Text(
            text = value,
            fontFamily = LibreBaskervilleFamily,
            fontSize = 14.sp,
            fontWeight = FontWeight.Normal,
            color = BrandNavy
        )
    }
}
