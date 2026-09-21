package com.fieldtrackpro.android.ui.screens.requirements

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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Inventory2
import androidx.compose.material.icons.filled.ReceiptLong
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.model.RequirementItemRequest
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SurfaceOffWhite
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.theme.TextMuted
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.viewmodel.RequirementState
import com.fieldtrackpro.android.ui.viewmodel.RequirementViewModel

private val SGRG_BRANDS = listOf("Samsung", "Oppo", "USHA", "Zebronics", "VU", "Philips")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RequirementFormScreen(
    visitId: String,
    viewModel: RequirementViewModel,
    onNavigateBack: () -> Unit,
    onSubmitSuccess: () -> Unit
) {
    val state by viewModel.state.collectAsState()
    val categories by viewModel.categories.collectAsState()

    // Multi-item dynamic state
    val items = remember { mutableStateListOf<RequirementItemRequest>() }

    // Current item inputs
    var brandExpanded by remember { mutableStateOf(false) }
    var currentBrand by remember { mutableStateOf("Samsung") }
    var currentModel by remember { mutableStateOf("") }
    var currentQty by remember { mutableStateOf("1") }
    var currentRate by remember { mutableStateOf("") }
    var currentItemNotes by remember { mutableStateOf("") }

    // Order level inputs
    var priority by remember { mutableStateOf("MEDIUM") }
    var generalNotes by remember { mutableStateOf("") }

    // Derive available brands from active categories + verified SGRG brands
    val brandOptions = remember(categories) {
        val catBrands = categories.map { it.name.split("(")[0].trim() }.filter { it.isNotBlank() }
        (SGRG_BRANDS + catBrands).distinct()
    }

    LaunchedEffect(visitId) {
        viewModel.loadCategories()
    }

    LaunchedEffect(state) {
        if (state is RequirementState.FormSubmitted) {
            onSubmitSuccess()
        }
    }

    // Live calculation of current input line amount
    val qtyInt = currentQty.toIntOrNull() ?: 0
    val rateDbl = currentRate.toDoubleOrNull() ?: 0.0
    val currentLineTotal = qtyInt * rateDbl

    // Running totals
    val totalQty = items.sumOf { it.requestedQuantity }
    val totalAmount = items.sumOf { it.requestedQuantity * it.expectedRate }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "Requirement Capture",
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
            if (state is RequirementState.Error) {
                ErrorBanner(message = (state as RequirementState.Error).message)
                Spacer(modifier = Modifier.height(12.dp))
            }

            Text(
                text = "Customer Requirements & Demand",
                fontFamily = LeagueSpartanFamily,
                fontWeight = FontWeight.Bold,
                fontSize = 20.sp,
                color = BrandNavy
            )
            Text(
                text = "Capture retailer product requirements, quantities, and expected rates.",
                fontFamily = LibreBaskervilleFamily,
                fontSize = 13.sp,
                color = TextSecondary
            )

            Spacer(modifier = Modifier.height(16.dp))

            // 1. ADD ITEM BUILDER CARD
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = "ADD PRODUCT REQUIREMENT",
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.Bold,
                            fontSize = 13.sp,
                            letterSpacing = 0.8.sp,
                            color = BrandNavy
                        )
                        Icon(
                            imageVector = Icons.Default.Inventory2,
                            contentDescription = null,
                            tint = BrandGold,
                            modifier = Modifier.size(20.dp)
                        )
                    }

                    Spacer(modifier = Modifier.height(12.dp))

                    // Brand Dropdown
                    Text(text = "Brand / Division *", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = TextPrimary)
                    Spacer(modifier = Modifier.height(4.dp))
                    ExposedDropdownMenuBox(
                        expanded = brandExpanded,
                        onExpandedChange = { brandExpanded = it }
                    ) {
                        OutlinedTextField(
                            value = currentBrand,
                            onValueChange = {},
                            readOnly = true,
                            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = brandExpanded) },
                            modifier = Modifier
                                .fillMaxWidth()
                                .menuAnchor(),
                            shape = RoundedCornerShape(8.dp)
                        )
                        ExposedDropdownMenu(
                            expanded = brandExpanded,
                            onDismissRequest = { brandExpanded = false }
                        ) {
                            brandOptions.forEach { brand ->
                                DropdownMenuItem(
                                    text = { Text(brand) },
                                    onClick = {
                                        currentBrand = brand
                                        brandExpanded = false
                                    }
                                )
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(10.dp))

                    // Model / Product Name
                    Text(text = "Product / Model Name *", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = TextPrimary)
                    Spacer(modifier = Modifier.height(4.dp))
                    OutlinedTextField(
                        value = currentModel,
                        onValueChange = { currentModel = it },
                        modifier = Modifier.fillMaxWidth(),
                        placeholder = { Text("e.g., S25 Ultra 12/256 or A16 5G") },
                        shape = RoundedCornerShape(8.dp),
                        singleLine = true
                    )

                    Spacer(modifier = Modifier.height(10.dp))

                    // Quantity and Rate in two columns
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(text = "Quantity (Pcs) *", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = TextPrimary)
                            Spacer(modifier = Modifier.height(4.dp))
                            OutlinedTextField(
                                value = currentQty,
                                onValueChange = { currentQty = it.filter { ch -> ch.isDigit() } },
                                modifier = Modifier.fillMaxWidth(),
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                placeholder = { Text("1") },
                                shape = RoundedCornerShape(8.dp),
                                singleLine = true
                            )
                        }
                        Column(modifier = Modifier.weight(1f)) {
                            Text(text = "Exp. Rate (₹) *", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = TextPrimary)
                            Spacer(modifier = Modifier.height(4.dp))
                            OutlinedTextField(
                                value = currentRate,
                                onValueChange = { currentRate = it.filter { ch -> ch.isDigit() || ch == '.' } },
                                modifier = Modifier.fillMaxWidth(),
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                                placeholder = { Text("e.g. 30000") },
                                shape = RoundedCornerShape(8.dp),
                                singleLine = true
                            )
                        }
                    }

                    if (currentLineTotal > 0) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.End
                        ) {
                            Text(
                                text = "Line Amount: ₹${"%,.0f".format(currentLineTotal)}",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                fontSize = 13.sp,
                                color = BrandNavy
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(14.dp))

                    // Add Item Button
                    Button(
                        onClick = {
                            if (currentModel.isNotBlank() && qtyInt > 0 && rateDbl > 0) {
                                items.add(
                                    RequirementItemRequest(
                                        brandName = currentBrand,
                                        productModel = currentModel.trim(),
                                        requestedQuantity = qtyInt,
                                        expectedRate = rateDbl,
                                        notes = currentItemNotes.ifBlank { null }
                                    )
                                )
                                // Clear input fields for next item
                                currentModel = ""
                                currentQty = "1"
                                currentRate = ""
                                currentItemNotes = ""
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(8.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = BrandNavy, contentColor = BrandWhite),
                        enabled = currentModel.isNotBlank() && qtyInt > 0 && rateDbl > 0
                    ) {
                        Icon(imageVector = Icons.Default.Add, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(modifier = Modifier.width(6.dp))
                        Text("+ ADD TO REQUIREMENT LIST", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold)
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // 2. CAPTURED ITEMS LIST
            if (items.isNotEmpty()) {
                Text(
                    text = "ADDED REQUIREMENT ITEMS (${items.size})",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 13.sp,
                    letterSpacing = 0.8.sp,
                    color = BrandNavy
                )
                Spacer(modifier = Modifier.height(8.dp))

                items.forEachIndexed { index, item ->
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp),
                        shape = RoundedCornerShape(10.dp),
                        colors = CardDefaults.cardColors(containerColor = SurfaceWhite),
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
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Box(
                                        modifier = Modifier
                                            .background(BrandNavy.copy(alpha = 0.1f), RoundedCornerShape(4.dp))
                                            .padding(horizontal = 6.dp, vertical = 2.dp)
                                    ) {
                                        Text(
                                            text = item.brandName.uppercase(),
                                            fontFamily = LeagueSpartanFamily,
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 10.sp,
                                            color = BrandNavy
                                        )
                                    }
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Text(
                                        text = item.productModel,
                                        fontFamily = LeagueSpartanFamily,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 14.sp,
                                        color = BrandNavy
                                    )
                                }
                                Spacer(modifier = Modifier.height(4.dp))
                                Text(
                                    text = "${item.requestedQuantity} pcs @ ₹${"%,.0f".format(item.expectedRate)} = ₹${"%,.0f".format(item.requestedQuantity * item.expectedRate)}",
                                    fontFamily = LibreBaskervilleFamily,
                                    fontSize = 12.sp,
                                    color = TextSecondary
                                )
                            }
                            IconButton(onClick = { items.removeAt(index) }) {
                                Icon(
                                    imageVector = Icons.Default.Delete,
                                    contentDescription = "Remove",
                                    tint = ErrorRed,
                                    modifier = Modifier.size(20.dp)
                                )
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Running Total KPI Card
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .border(1.dp, BrandGold.copy(alpha = 0.5f), RoundedCornerShape(10.dp)),
                    shape = RoundedCornerShape(10.dp),
                    colors = CardDefaults.cardColors(containerColor = BrandGold.copy(alpha = 0.08f))
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(14.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text(
                                text = "TOTAL REQUESTED VALUE",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                fontSize = 11.sp,
                                letterSpacing = 0.8.sp,
                                color = BrandNavy
                            )
                            Text(
                                text = "$totalQty items across ${items.size} line(s)",
                                fontFamily = LibreBaskervilleFamily,
                                fontSize = 12.sp,
                                color = TextSecondary
                            )
                        }
                        Text(
                            text = "₹${"%,.0f".format(totalAmount)}",
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.Bold,
                            fontSize = 20.sp,
                            color = BrandNavy
                        )
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))
            }

            // 3. PRIORITY SELECTOR
            Text(text = "Priority", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = TextPrimary)
            Spacer(modifier = Modifier.height(4.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("LOW", "MEDIUM", "HIGH").forEach { p ->
                    Button(
                        onClick = { priority = p },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (priority == p) BrandNavy else SurfaceWhite,
                            contentColor = if (priority == p) BrandWhite else TextPrimary
                        ),
                        shape = RoundedCornerShape(8.dp),
                        border = if (priority != p) androidx.compose.foundation.BorderStroke(1.dp, BrandLightGray) else null,
                        modifier = Modifier.weight(1f)
                    ) {
                        Text(p, fontSize = 12.sp, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold)
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // 4. NOTES (Optional)
            Text(text = "Delivery / Order Notes (Optional)", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = TextPrimary)
            Spacer(modifier = Modifier.height(4.dp))
            OutlinedTextField(
                value = generalNotes,
                onValueChange = { generalNotes = it },
                modifier = Modifier.fillMaxWidth(),
                minLines = 2,
                placeholder = { Text("Special packaging, delivery timeline, or instructions...") },
                shape = RoundedCornerShape(8.dp)
            )

            Spacer(modifier = Modifier.height(24.dp))

            // 5. SUBMIT BUTTON
            val hasPendingInputs = currentModel.isNotBlank() && qtyInt > 0 && rateDbl > 0
            val effectiveItemsCount = items.size + (if (hasPendingInputs) 1 else 0)

            Button(
                onClick = {
                    val finalItems = items.toMutableList()
                    if (hasPendingInputs) {
                        finalItems.add(
                            RequirementItemRequest(
                                brandName = currentBrand,
                                productModel = currentModel.trim(),
                                requestedQuantity = qtyInt,
                                expectedRate = rateDbl,
                                notes = currentItemNotes.ifBlank { null }
                            )
                        )
                    }
                    if (finalItems.isNotEmpty()) {
                        viewModel.submitMultiItemRequirement(
                            visitId = visitId,
                            items = finalItems,
                            priority = priority,
                            notes = generalNotes.ifBlank { null }
                        )
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(52.dp),
                shape = RoundedCornerShape(10.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = BrandGold,
                    contentColor = BrandNavy
                ),
                enabled = effectiveItemsCount > 0 && state !is RequirementState.Loading
            ) {
                if (state is RequirementState.Loading) {
                    CircularProgressIndicator(color = BrandNavy, modifier = Modifier.size(24.dp))
                } else {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(imageVector = Icons.Default.ReceiptLong, contentDescription = null, modifier = Modifier.size(20.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            "SUBMIT REQUIREMENTS ($effectiveItemsCount ITEMS)",
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.Bold,
                            fontSize = 14.sp
                        )
                    }
                }
            }
            Spacer(modifier = Modifier.height(24.dp))
        }
    }
}
