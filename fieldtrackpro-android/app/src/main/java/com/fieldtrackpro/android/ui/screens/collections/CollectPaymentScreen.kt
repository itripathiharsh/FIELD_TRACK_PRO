package com.fieldtrackpro.android.ui.screens.collections

import android.Manifest
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountBalance
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.CreditCard
import androidx.compose.material.icons.filled.Money
import androidx.compose.material.icons.filled.Payments
import androidx.compose.material.icons.filled.ReceiptLong
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import com.fieldtrackpro.android.data.model.BrandAllocationInput
import com.fieldtrackpro.android.data.model.BrandSummaryDto
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.theme.BrandBlack
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.viewmodel.AccountState
import com.fieldtrackpro.android.ui.viewmodel.CollectionState
import com.fieldtrackpro.android.ui.viewmodel.CollectionViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import com.fieldtrackpro.android.data.local.PaymentProofStore
import java.io.File
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private val PAYMENT_METHODS = listOf("CASH", "CHEQUE", "ONLINE")

private fun formatRupees(amount: Double): String = com.fieldtrackpro.android.utils.MoneyFormat.inr(amount)

/** Saver for the per-brand amount map: flat [brand, amount, brand, amount...] list. */
private val BrandAmountsSaver = androidx.compose.runtime.saveable.Saver<androidx.compose.runtime.snapshots.SnapshotStateMap<String, String>, ArrayList<String>>(
    save = { map -> ArrayList<String>(map.size * 2).also { out -> map.forEach { (k, v) -> out.add(k); out.add(v) } } },
    restore = { flat ->
        mutableStateMapOf<String, String>().also { m ->
            var i = 0
            while (i + 1 < flat.size) { m[flat[i]] = flat[i + 1]; i += 2 }
        }
    }
)

private fun todayIso(): String =
    SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())

@Composable
fun CollectPaymentScreen(
    visitId: String,
    customerId: String,
    viewModel: CollectionViewModel,
    onNavigateBack: () -> Unit,
    onSuccess: () -> Unit
) {
    val context = LocalContext.current
    val coroutineScope = rememberCoroutineScope()

    val state by viewModel.collectionState.collectAsState()
    val accountState by viewModel.accountState.collectAsState()

    LaunchedEffect(customerId) {
        viewModel.loadAccount(customerId)
    }

    // Form state survives rotation / dark-mode toggle / process death (rememberSaveable -> saved instance state).
    val brandAmounts = rememberSaveable(saver = BrandAmountsSaver) { mutableStateMapOf<String, String>() }
    var method by rememberSaveable { mutableStateOf("CASH") }
    var paymentDate by rememberSaveable { mutableStateOf(todayIso()) }
    var chequeNumber by rememberSaveable { mutableStateOf("") }
    var chequeBankName by rememberSaveable { mutableStateOf("") }
    var utrReference by rememberSaveable { mutableStateOf("") }
    var notes by rememberSaveable { mutableStateOf("") }

    var proofUri by rememberSaveable { mutableStateOf<Uri?>(null) }
    var tempCameraUri by rememberSaveable { mutableStateOf<Uri?>(null) }
    var isUploadingProof by remember { mutableStateOf(false) }
    var fieldError by remember { mutableStateOf<String?>(null) }

    val cameraLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.TakePicture()
    ) { success ->
        if (success && tempCameraUri != null) {
            proofUri = tempCameraUri
        }
    }

    fun launchProofCamera() {
        try {
            val photoFile = com.fieldtrackpro.android.ui.components.createCaptureFile(context, "PAY_PROOF_${System.currentTimeMillis()}_")
            val uri = FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                photoFile
            )
            tempCameraUri = uri
            cameraLauncher.launch(uri)
        } catch (e: Exception) {
            fieldError = "Could not launch camera: ${e.localizedMessage}"
        }
    }

    var hasCameraPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED
        )
    }
    // Permanent denial => rationale + "Open app settings" (the system prompt would silently do nothing).
    val onCameraDenied = com.fieldtrackpro.android.ui.components.rememberPermissionDeniedHandler(
        com.fieldtrackpro.android.ui.components.PermissionDisclosureKind.CAMERA, Manifest.permission.CAMERA
    )
    val cameraPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { granted ->
        hasCameraPermission = granted
        if (granted) launchProofCamera() else onCameraDenied()
    }
    val requestCameraPermission = com.fieldtrackpro.android.ui.components.rememberWithDisclosure(
        com.fieldtrackpro.android.ui.components.PermissionDisclosureKind.CAMERA
    ) { cameraPermissionLauncher.launch(Manifest.permission.CAMERA) }

    // Determine brands list directly from dynamic account state
    val brandSummaryList: List<BrandSummaryDto> = remember(accountState) {
        (accountState as? AccountState.Success)?.summary?.brandSummary ?: emptyList()
    }

    // Calculate dynamic sum across all brand inputs
    val totalAmount = brandAmounts.values.mapNotNull { it.toDoubleOrNull() }.filter { it > 0 }.sum()

    Scaffold(
        topBar = { FieldTrackTopAppBar(title = "Collect Payment", onBackClick = onNavigateBack) },
        containerColor = SurfaceSecondary
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Header Card
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, BrandLightGray, RoundedCornerShape(14.dp)),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = BrandWhite),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.ReceiptLong,
                                contentDescription = null,
                                tint = BrandGold,
                                modifier = Modifier.size(22.dp)
                            )
                            Text(
                                text = "Brand-Wise Payment Collection",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                fontSize = 16.sp,
                                color = BrandNavy
                            )
                        }
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Allocate payment across active brand ledgers. Total is automatically computed.",
                            fontFamily = LibreBaskervilleFamily,
                            fontSize = 12.sp,
                            color = TextSecondary
                        )
                    }
                }

                if (fieldError != null) {
                    ErrorBanner(message = fieldError!!)
                }

                if (state is CollectionState.Error) {
                    ErrorBanner(message = (state as CollectionState.Error).message)
                }

                if (state is CollectionState.SavedOffline) {
                    // Not an error: the payment is safely stored on the device and syncs by itself.
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = BrandWhite),
                        border = androidx.compose.foundation.BorderStroke(1.dp, SuccessGreen)
                    ) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.CheckCircle, contentDescription = null, tint = SuccessGreen)
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    (state as CollectionState.SavedOffline).message,
                                    fontFamily = LeagueSpartanFamily,
                                    fontWeight = FontWeight.Bold,
                                    color = SuccessGreen
                                )
                            }
                            Spacer(modifier = Modifier.height(6.dp))
                            Text(
                                "No connection right now. Your payment of ${(state as CollectionState.SavedOffline).amount} " +
                                    "(with its proof photo, if any) is stored on this device and is sent automatically " +
                                    "when you are back online. See Offline Queue for status.",
                                color = TextPrimary
                            )
                            Spacer(modifier = Modifier.height(10.dp))
                            Button(
                                onClick = { onSuccess() },
                                modifier = Modifier.fillMaxWidth(),
                                colors = ButtonDefaults.buttonColors(containerColor = BrandNavy, contentColor = BrandWhite)
                            ) { Text("DONE") }
                        }
                    }
                }

                // Brand-Wise Allocation Card
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, BrandLightGray, RoundedCornerShape(14.dp)),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = BrandWhite),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = "BRAND-WISE ALLOCATION",
                                fontFamily = LeagueSpartanFamily,
                                fontSize = 12.sp,
                                fontWeight = FontWeight.Bold,
                                letterSpacing = 0.8.sp,
                                color = BrandNavy
                            )
                            if (accountState is AccountState.Loading) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(4.dp)
                                ) {
                                    CircularProgressIndicator(
                                        modifier = Modifier.size(12.dp),
                                        strokeWidth = 1.5.dp,
                                        color = BrandGold
                                    )
                                    Text(
                                        "Syncing...",
                                        fontFamily = LibreBaskervilleFamily,
                                        fontSize = 11.sp,
                                        color = TextSecondary
                                    )
                                }
                            }
                        }

                        Spacer(modifier = Modifier.height(12.dp))

                        brandSummaryList.forEach { brandDto ->
                            val brandName = brandDto.brand
                            val outstanding = brandDto.totalOutstanding.toDoubleOrNull() ?: 0.0

                            Card(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 4.dp),
                                shape = RoundedCornerShape(10.dp),
                                colors = CardDefaults.cardColors(containerColor = SurfaceSecondary),
                                border = androidx.compose.foundation.BorderStroke(1.dp, BrandLightGray)
                            ) {
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(12.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(
                                            text = brandName,
                                            fontFamily = LeagueSpartanFamily,
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 15.sp,
                                            color = BrandNavy
                                        )
                                        Spacer(modifier = Modifier.height(2.dp))
                                        Text(
                                            text = "Outstanding: ${formatRupees(outstanding)}",
                                            fontFamily = LibreBaskervilleFamily,
                                            fontSize = 12.sp,
                                            color = if (outstanding > 0) BrandNavy else TextSecondary,
                                            fontWeight = if (outstanding > 0) FontWeight.SemiBold else FontWeight.Normal
                                        )
                                        if (outstanding > 0) {
                                            Spacer(modifier = Modifier.height(4.dp))
                                            Text(
                                                text = "PAY FULL DUE",
                                                fontFamily = LeagueSpartanFamily,
                                                fontSize = 10.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = BrandGold,
                                                modifier = Modifier.clickable {
                                                    brandAmounts[brandName] = String.format(Locale.US, "%.2f", outstanding)
                                                }
                                            )
                                        }
                                    }

                                    OutlinedTextField(
                                        value = brandAmounts[brandName] ?: "",
                                        onValueChange = { brandAmounts[brandName] = it },
                                        placeholder = { Text("0", fontFamily = LeagueSpartanFamily, fontSize = 13.sp) },
                                        prefix = { Text("₹ ", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 13.sp, color = BrandNavy) },
                                        modifier = Modifier.width(140.dp),
                                        shape = RoundedCornerShape(8.dp),
                                        singleLine = true,
                                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                                        colors = OutlinedTextFieldDefaults.colors(
                                            focusedTextColor = TextPrimary,
                                            unfocusedTextColor = TextPrimary,
                                            focusedBorderColor = BrandGold,
                                            unfocusedBorderColor = BrandLightGray,
                                            focusedContainerColor = BrandWhite,
                                            unfocusedContainerColor = BrandWhite
                                        )
                                    )
                                }
                            }
                        }

                        Spacer(modifier = Modifier.height(14.dp))

                        // Dynamic Total Summary Box
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(10.dp),
                            colors = CardDefaults.cardColors(containerColor = BrandNavy)
                        ) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(14.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Column {
                                    Text(
                                        text = "TOTAL PAYMENT AMOUNT",
                                        fontFamily = LeagueSpartanFamily,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 11.sp,
                                        letterSpacing = 0.5.sp,
                                        color = BrandLightGray
                                    )
                                    Text(
                                        text = "Auto-calculated from brand inputs",
                                        fontFamily = LibreBaskervilleFamily,
                                        fontSize = 10.sp,
                                        color = BrandWhite.copy(alpha = 0.7f)
                                    )
                                }
                                Text(
                                    text = formatRupees(totalAmount),
                                    fontFamily = LeagueSpartanFamily,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 18.sp,
                                    color = BrandGold
                                )
                            }
                        }
                    }
                }

                // Payment Details Form Card
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, BrandLightGray, RoundedCornerShape(14.dp)),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = BrandWhite),
                    elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(
                            text = "PAYMENT METHOD",
                            fontFamily = LeagueSpartanFamily,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 0.8.sp,
                            color = BrandNavy
                        )
                        Spacer(modifier = Modifier.height(8.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            PAYMENT_METHODS.forEach { m ->
                                val selected = method == m
                                Surface(
                                    shape = RoundedCornerShape(8.dp),
                                    color = if (selected) BrandNavy else SurfaceSecondary,
                                    border = androidx.compose.foundation.BorderStroke(
                                        1.dp,
                                        if (selected) BrandNavy else BrandLightGray
                                    ),
                                    modifier = Modifier
                                        .weight(1f)
                                        .clickable { method = m }
                                ) {
                                    Row(
                                        modifier = Modifier.padding(vertical = 10.dp),
                                        horizontalArrangement = Arrangement.Center,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Icon(
                                            imageVector = when (m) {
                                                "CASH" -> Icons.Default.Money
                                                "CHEQUE" -> Icons.Default.CreditCard
                                                else -> Icons.Default.AccountBalance
                                            },
                                            contentDescription = null,
                                            tint = if (selected) BrandGold else TextSecondary,
                                            modifier = Modifier.size(16.dp)
                                        )
                                        Spacer(modifier = Modifier.width(6.dp))
                                        Text(
                                            text = m,
                                            fontFamily = LeagueSpartanFamily,
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 12.sp,
                                            color = if (selected) BrandWhite else TextPrimary
                                        )
                                    }
                                }
                            }
                        }

                        Spacer(modifier = Modifier.height(14.dp))

                        OutlinedTextField(
                            value = paymentDate,
                            onValueChange = { paymentDate = it },
                            label = { 
                                Text(
                                    "Payment Date (YYYY-MM-DD)",
                                    fontFamily = LeagueSpartanFamily,
                                    fontWeight = FontWeight.SemiBold
                                ) 
                            },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(10.dp),
                            singleLine = true,
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedTextColor = TextPrimary,
                                unfocusedTextColor = TextPrimary,
                                focusedBorderColor = BrandGold,
                                unfocusedBorderColor = BrandLightGray
                            )
                        )

                        if (method == "CHEQUE") {
                            Spacer(modifier = Modifier.height(10.dp))
                            OutlinedTextField(
                                value = chequeNumber,
                                onValueChange = { chequeNumber = it },
                                label = { Text("Cheque Number *", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold) },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(10.dp),
                                singleLine = true,
                                colors = OutlinedTextFieldDefaults.colors(
                                    focusedTextColor = TextPrimary,
                                    unfocusedTextColor = TextPrimary,
                                    focusedBorderColor = BrandGold,
                                    unfocusedBorderColor = BrandLightGray
                                )
                            )

                            Spacer(modifier = Modifier.height(10.dp))
                            OutlinedTextField(
                                value = chequeBankName,
                                onValueChange = { chequeBankName = it },
                                label = { Text("Bank Name (Optional)", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold) },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(10.dp),
                                singleLine = true,
                                colors = OutlinedTextFieldDefaults.colors(
                                    focusedTextColor = TextPrimary,
                                    unfocusedTextColor = TextPrimary,
                                    focusedBorderColor = BrandGold,
                                    unfocusedBorderColor = BrandLightGray
                                )
                            )
                        }

                        if (method == "ONLINE") {
                            Spacer(modifier = Modifier.height(10.dp))
                            OutlinedTextField(
                                value = utrReference,
                                onValueChange = { utrReference = it },
                                label = { Text("UTR Reference / Transaction ID *", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold) },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(10.dp),
                                singleLine = true,
                                colors = OutlinedTextFieldDefaults.colors(
                                    focusedTextColor = TextPrimary,
                                    unfocusedTextColor = TextPrimary,
                                    focusedBorderColor = BrandGold,
                                    unfocusedBorderColor = BrandLightGray
                                )
                            )
                        }

                        Spacer(modifier = Modifier.height(14.dp))

                        // Proof Photo
                        Text(
                            text = "PAYMENT PROOF PHOTO",
                            fontFamily = LeagueSpartanFamily,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Bold,
                            letterSpacing = 0.8.sp,
                            color = BrandNavy
                        )
                        Spacer(modifier = Modifier.height(6.dp))

                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .background(SurfaceSecondary, RoundedCornerShape(10.dp))
                                .border(1.dp, BrandLightGray, RoundedCornerShape(10.dp))
                                .padding(12.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            if (proofUri != null) {
                                Row(
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                                ) {
                                    Icon(
                                        imageVector = Icons.Default.CheckCircle,
                                        contentDescription = null,
                                        tint = SuccessGreen,
                                        modifier = Modifier.size(18.dp)
                                    )
                                    Text(
                                        "Payment proof photo attached",
                                        fontFamily = LibreBaskervilleFamily,
                                        fontSize = 12.sp,
                                        color = SuccessGreen,
                                        fontWeight = FontWeight.Bold
                                    )
                                }
                                Spacer(modifier = Modifier.height(8.dp))
                            }

                            OutlinedButton(
                                onClick = {
                                    if (hasCameraPermission) {
                                        launchProofCamera()
                                    } else {
                                        requestCameraPermission()
                                    }
                                },
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(8.dp),
                                colors = ButtonDefaults.outlinedButtonColors(
                                    containerColor = BrandWhite,
                                    contentColor = BrandNavy
                                ),
                                border = androidx.compose.foundation.BorderStroke(1.dp, BrandNavy)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.CameraAlt,
                                    contentDescription = null,
                                    tint = BrandNavy,
                                    modifier = Modifier.size(18.dp)
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    if (proofUri == null) "CAPTURE PAYMENT PROOF PHOTO" else "RETAKE PROOF PHOTO",
                                    fontFamily = LeagueSpartanFamily,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 12.sp,
                                    color = BrandNavy
                                )
                            }
                        }

                        Spacer(modifier = Modifier.height(12.dp))

                        OutlinedTextField(
                            value = notes,
                            onValueChange = { notes = it },
                            label = { 
                                Text(
                                    "Notes / Remarks (Optional)",
                                    fontFamily = LeagueSpartanFamily,
                                    fontWeight = FontWeight.SemiBold
                                ) 
                            },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(10.dp),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedTextColor = TextPrimary,
                                unfocusedTextColor = TextPrimary,
                                focusedBorderColor = BrandGold,
                                unfocusedBorderColor = BrandLightGray
                            )
                        )

                        Spacer(modifier = Modifier.height(20.dp))

                        Button(
                            onClick = {
                                fieldError = null
                                if (totalAmount <= 0) {
                                    fieldError = "Please enter an amount for at least one brand."
                                    return@Button
                                }
                                if (totalAmount > 9999999999.99) {
                                    fieldError = "Payment amount cannot exceed ₹9,99,99,99,999.99."
                                    return@Button
                                }
                                if (method == "CHEQUE" && chequeNumber.isBlank()) {
                                    fieldError = "Cheque number is required for cheque payments."
                                    return@Button
                                }
                                if (method == "ONLINE" && utrReference.isBlank()) {
                                    fieldError = "UTR reference is required for online payments."
                                    return@Button
                                }

                                val allocationsList = brandAmounts.mapNotNull { (brand, amtStr) ->
                                    val amt = amtStr.toDoubleOrNull()
                                    if (amt != null && amt > 0) BrandAllocationInput(brand, amt) else null
                                }

                                if (allocationsList.isEmpty()) {
                                    fieldError = "Please enter a valid payment amount against at least one brand."
                                    return@Button
                                }

                                val amountText = totalAmount.toString()
                                val methodNow = method
                                val outletName = (accountState as? AccountState.Success)?.summary?.customerName
                                coroutineScope.launch {
                                    // Copy the proof into app-private storage first so it survives until it syncs.
                                    isUploadingProof = true
                                    val proofPaths = try {
                                        val uri = proofUri
                                        if (uri == null) emptyList() else {
                                            val path = withContext(Dispatchers.IO) { PaymentProofStore.copyToPrivate(context, uri) }
                                            if (path == null) {
                                                fieldError = "Could not read the proof photo. Please retake it."
                                                isUploadingProof = false
                                                return@launch
                                            }
                                            listOf(path)
                                        }
                                    } finally {
                                        isUploadingProof = false
                                    }
                                    viewModel.submitCollection(
                                        visitId = visitId,
                                        invoiceId = null,
                                        amount = amountText,
                                        paymentMethod = methodNow,
                                        paymentDate = paymentDate,
                                        chequeNumber = if (methodNow == "CHEQUE") chequeNumber else null,
                                        chequeBankName = if (methodNow == "CHEQUE") chequeBankName.ifBlank { null } else null,
                                        utrReference = if (methodNow == "ONLINE") utrReference else null,
                                        notes = notes.ifBlank { null },
                                        allocations = allocationsList,
                                        customerId = customerId,
                                        outletName = outletName,
                                        proofPaths = proofPaths,
                                        onSubmitted = { onSuccess() }
                                    )
                                }
                            },
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(52.dp),
                            shape = RoundedCornerShape(10.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = BrandNavy,
                                contentColor = BrandWhite
                            ),
                            enabled = state !is CollectionState.Submitting && state !is CollectionState.SavedOffline && !isUploadingProof && totalAmount > 0
                        ) {
                            if (state is CollectionState.Submitting || isUploadingProof) {
                                CircularProgressIndicator(color = BrandGold, modifier = Modifier.size(24.dp))
                            } else {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(
                                        imageVector = Icons.Default.Payments,
                                        contentDescription = null,
                                        tint = BrandGold,
                                        modifier = Modifier.size(20.dp)
                                    )
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Text(
                                        if (totalAmount > 0) "SUBMIT PAYMENT (${formatRupees(totalAmount)})" else "SUBMIT PAYMENT COLLECTION",
                                        fontFamily = LeagueSpartanFamily,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 14.sp,
                                        letterSpacing = 0.5.sp,
                                        color = BrandWhite
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
