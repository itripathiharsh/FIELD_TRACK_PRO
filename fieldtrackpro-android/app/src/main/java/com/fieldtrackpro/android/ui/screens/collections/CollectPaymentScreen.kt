package com.fieldtrackpro.android.ui.screens.collections

import android.net.Uri
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
import kotlinx.coroutines.launch
import java.io.File
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private val PAYMENT_METHODS = listOf("CASH", "CHEQUE", "ONLINE")

private fun formatRupees(amount: Double): String {
    val formatter = NumberFormat.getCurrencyInstance(Locale("en", "IN"))
    formatter.maximumFractionDigits = 2
    return formatter.format(amount)
}

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

    val brandAmounts = remember { mutableStateMapOf<String, String>() }
    var method by remember { mutableStateOf("CASH") }
    var paymentDate by remember { mutableStateOf(todayIso()) }
    var chequeNumber by remember { mutableStateOf("") }
    var chequeBankName by remember { mutableStateOf("") }
    var utrReference by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }

    var proofUri by remember { mutableStateOf<Uri?>(null) }
    var tempCameraUri by remember { mutableStateOf<Uri?>(null) }
    var isUploadingProof by remember { mutableStateOf(false) }
    var fieldError by remember { mutableStateOf<String?>(null) }

    val cameraLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.TakePicture()
    ) { success ->
        if (success && tempCameraUri != null) {
            proofUri = tempCameraUri
        }
    }

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
                                    try {
                                        val photoFile = File.createTempFile(
                                            "PAY_PROOF_${System.currentTimeMillis()}_",
                                            ".jpg",
                                            context.cacheDir
                                        )
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

                                viewModel.submitCollection(
                                    visitId = visitId,
                                    invoiceId = null,
                                    amount = totalAmount.toString(),
                                    paymentMethod = method,
                                    paymentDate = paymentDate,
                                    chequeNumber = if (method == "CHEQUE") chequeNumber else null,
                                    chequeBankName = if (method == "CHEQUE") chequeBankName.ifBlank { null } else null,
                                    utrReference = if (method == "ONLINE") utrReference else null,
                                    notes = notes.ifBlank { null },
                                    allocations = allocationsList,
                                    onSubmitted = { payment ->
                                        val uri = proofUri
                                        if (uri != null) {
                                            coroutineScope.launch {
                                                isUploadingProof = true
                                                try {
                                                    val bytes = context.contentResolver.openInputStream(uri)?.readBytes()
                                                    if (bytes != null && bytes.isNotEmpty()) {
                                                        viewModel.uploadProof(payment.id, "proof_${payment.id}.jpg", "image/jpeg", bytes)
                                                    }
                                                } finally {
                                                    isUploadingProof = false
                                                    onSuccess()
                                                }
                                            }
                                        } else {
                                            onSuccess()
                                        }
                                    }
                                )
                            },
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(52.dp),
                            shape = RoundedCornerShape(10.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = BrandNavy,
                                contentColor = BrandWhite
                            ),
                            enabled = state !is CollectionState.Submitting && !isUploadingProof && totalAmount > 0
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
