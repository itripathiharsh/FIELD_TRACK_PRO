package com.fieldtrackpro.android.ui.screens.customers

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
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
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Business
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material.icons.filled.Receipt
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.ShoppingBag
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.CustomerProspectCreate
import com.fieldtrackpro.android.data.model.CustomerRequirementCreate
import com.fieldtrackpro.android.data.model.GeoPointDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.CustomerRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.services.LocationCaptureService
import com.fieldtrackpro.android.services.LocationResult
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import kotlinx.coroutines.launch

/**
 * Screen for field employees to register a new Customer / Outlet prospect,
 * capture associated brands, specify business requirements/opportunities,
 * and pin device GPS coordinates.
 */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun AddCustomerScreen(
    onNavigateBack: () -> Unit,
    onCustomerCreated: (CustomerDto) -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val locationService = remember { LocationCaptureService(context) }
    val customerRepository = remember {
        CustomerRepository(ApiClient.createCustomerApi(TokenManager(context)))
    }

    // Form fields
    var name by remember { mutableStateOf("") }
    var contactPerson by remember { mutableStateOf("") }
    var contactNumber by remember { mutableStateOf("") }
    var gstNumber by remember { mutableStateOf("") }
    var address by remember { mutableStateOf("") }
    var outletCode by remember { mutableStateOf("") }

    // Brands
    var availableBrands by remember { mutableStateOf(emptyList<String>()) }
    var selectedBrands by remember { mutableStateOf(setOf<String>()) }
    var isAddBrandDialogOpen by remember { mutableStateOf(false) }

    // Requirement toggle & fields
    var hasRequirement by remember { mutableStateOf(true) }
    var reqBrand by remember { mutableStateOf("") }
    var reqType by remember { mutableStateOf("Initial Dealership & Stock") }
    var reqProductDetails by remember { mutableStateOf("") }
    var reqQuantity by remember { mutableStateOf("") }
    var reqExpectedValue by remember { mutableStateOf("") }
    var reqFollowUpDate by remember { mutableStateOf("") }
    var reqNotes by remember { mutableStateOf("") }

    // GPS location
    var isCapturingLocation by remember { mutableStateOf(false) }
    var locationResult by remember { mutableStateOf<LocationResult?>(null) }
    var locationError by remember { mutableStateOf<String?>(null) }

    // Submission & Duplicate Handling
    var isSubmitting by remember { mutableStateOf(false) }
    var submitError by remember { mutableStateOf<String?>(null) }
    var duplicateWarningMessage by remember { mutableStateOf<String?>(null) }

    fun captureLocation() {
        if (!locationService.hasLocationPermission()) {
            locationError = "Location permission required"
            return
        }
        if (!locationService.isLocationEnabled()) {
            locationError = "Please turn on GPS"
            return
        }
        isCapturingLocation = true
        locationError = null
        scope.launch {
            try {
                val loc = locationService.getCurrentLocation()
                locationResult = loc
            } catch (e: Exception) {
                locationError = e.localizedMessage ?: "Failed to get GPS fix"
            } finally {
                isCapturingLocation = false
            }
        }
    }

    LaunchedEffect(Unit) {
        captureLocation()
        // Load master brands
        scope.launch {
            when (val bRes = customerRepository.getBrandNames()) {
                is Resource.Success -> {
                    if (bRes.data.isNotEmpty()) {
                        availableBrands = bRes.data
                    }
                }
                else -> {}
            }
        }
    }

    fun submitProspect(force: Boolean = false) {
        if (name.isBlank()) {
            Toast.makeText(context, "Outlet name is required", Toast.LENGTH_SHORT).show()
            return
        }
        if (contactNumber.isBlank()) {
            Toast.makeText(context, "Contact number is required", Toast.LENGTH_SHORT).show()
            return
        }

        isSubmitting = true
        submitError = null
        duplicateWarningMessage = null

        scope.launch {
            val reqDto = if (hasRequirement && reqProductDetails.isNotBlank()) {
                CustomerRequirementCreate(
                    brand = reqBrand.ifBlank { selectedBrands.firstOrNull() },
                    requirementType = reqType.ifBlank { null },
                    productDetails = reqProductDetails.trim(),
                    quantity = reqQuantity.toIntOrNull(),
                    expectedValue = reqExpectedValue.toDoubleOrNull(),
                    followUpDate = reqFollowUpDate.ifBlank { null },
                    notes = reqNotes.ifBlank { null }
                )
            } else null

            val locDto = locationResult?.let {
                GeoPointDto(latitude = it.latitude, longitude = it.longitude)
            }

            val prospectPayload = CustomerProspectCreate(
                name = name.trim(),
                contactNumber = contactNumber.trim(),
                contactPerson = contactPerson.trim().ifEmpty { null },
                gstNumber = gstNumber.trim().ifEmpty { null },
                address = address.trim().ifEmpty { null },
                outletCode = outletCode.trim().ifEmpty { null },
                brands = selectedBrands.toList(),
                requirement = reqDto,
                location = locDto,
                gpsAccuracyMeters = locationResult?.accuracy?.toDouble(),
                force = force
            )

            when (val res = customerRepository.createCustomerProspect(prospectPayload)) {
                is Resource.Success -> {
                    Toast.makeText(context, "Outlet added successfully!", Toast.LENGTH_LONG).show()
                    onCustomerCreated(res.data)
                    onNavigateBack()
                }
                is Resource.Error -> {
                    if (res.code == 409) {
                        duplicateWarningMessage = res.message
                    } else {
                        submitError = res.message
                    }
                }
                else -> {}
            }
            isSubmitting = false
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Add New Outlet / Prospect", fontWeight = FontWeight.Bold, fontSize = 18.sp, color = BrandWhite) },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back", tint = BrandWhite)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = BrandNavy)
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Section 1: Outlet Details
            Card(
                colors = CardDefaults.cardColors(containerColor = Color.White),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Business, contentDescription = null, tint = BrandNavy, modifier = Modifier.size(20.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Outlet Information", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = BrandNavy)
                    }

                    OutlinedTextField(
                        value = name,
                        onValueChange = { name = it },
                        label = { Text("Outlet / Store Name *") },
                        placeholder = { Text("e.g. Sharma Electricals & Hardware") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )

                    OutlinedTextField(
                        value = contactPerson,
                        onValueChange = { contactPerson = it },
                        label = { Text("Contact Person / Owner") },
                        placeholder = { Text("e.g. Ramesh Sharma") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )

                    OutlinedTextField(
                        value = contactNumber,
                        onValueChange = { contactNumber = it },
                        label = { Text("Mobile Number *") },
                        placeholder = { Text("e.g. 9876543210") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )

                    OutlinedTextField(
                        value = gstNumber,
                        onValueChange = { gstNumber = it.uppercase() },
                        label = { Text("GST Number (Optional)") },
                        placeholder = { Text("e.g. 07AAAAA0000A1Z5") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )

                    OutlinedTextField(
                        value = address,
                        onValueChange = { address = it },
                        label = { Text("Full Address / Landmark") },
                        placeholder = { Text("Shop No. 5, Main Market Road") },
                        modifier = Modifier.fillMaxWidth(),
                        maxLines = 2
                    )

                    OutlinedTextField(
                        value = outletCode,
                        onValueChange = { outletCode = it },
                        label = { Text("DMS / ERP Code (Optional)") },
                        placeholder = { Text("e.g. SGR00142") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                }
            }

            // Section 2: Associated Brands
            Card(
                colors = CardDefaults.cardColors(containerColor = Color.White),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.ShoppingBag, contentDescription = null, tint = BrandNavy, modifier = Modifier.size(20.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Brand Portfolio (Multi-Select)", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = BrandNavy)
                    }

                    Text("Select all product brands dealt by this outlet:", fontSize = 12.sp, color = TextSecondary)

                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        availableBrands.forEach { brand ->
                            val isSelected = selectedBrands.contains(brand)
                            FilterChip(
                                selected = isSelected,
                                onClick = {
                                    selectedBrands = if (isSelected) selectedBrands - brand else selectedBrands + brand
                                },
                                label = { Text(brand, fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal) },
                                leadingIcon = if (isSelected) {
                                    { Icon(Icons.Default.Check, contentDescription = null, modifier = Modifier.size(16.dp)) }
                                } else null,
                                colors = FilterChipDefaults.filterChipColors(
                                    selectedContainerColor = BrandNavy,
                                    selectedLabelColor = BrandWhite,
                                    selectedLeadingIconColor = BrandWhite
                                )
                            )
                        }

                        // Add New Brand Chip
                        FilterChip(
                            selected = false,
                            onClick = { isAddBrandDialogOpen = true },
                            label = { Text("+ Add New Brand", fontWeight = FontWeight.Bold, color = BrandNavy) },
                            leadingIcon = { Icon(Icons.Default.Add, contentDescription = null, tint = BrandGold, modifier = Modifier.size(16.dp)) },
                            colors = FilterChipDefaults.filterChipColors(
                                containerColor = SurfaceSecondary
                            )
                        )
                    }
                }
            }

            // Section 3: Business Requirement / Opportunity
            Card(
                colors = CardDefaults.cardColors(containerColor = Color.White),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.Receipt, contentDescription = null, tint = BrandNavy, modifier = Modifier.size(20.dp))
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Initial Requirement / Order", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = BrandNavy)
                        }
                        Switch(checked = hasRequirement, onCheckedChange = { hasRequirement = it })
                    }

                    if (hasRequirement) {
                        OutlinedTextField(
                            value = reqType,
                            onValueChange = { reqType = it },
                            label = { Text("Requirement Type") },
                            placeholder = { Text("e.g. Initial Dealership & Stock") },
                            modifier = Modifier.fillMaxWidth()
                        )

                        OutlinedTextField(
                            value = reqProductDetails,
                            onValueChange = { reqProductDetails = it },
                            label = { Text("Product Details & SKU Demand *") },
                            placeholder = { Text("e.g. 50 Ceiling Fans, 20 Water Heaters") },
                            modifier = Modifier.fillMaxWidth()
                        )

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            OutlinedTextField(
                                value = reqQuantity,
                                onValueChange = { reqQuantity = it },
                                label = { Text("Quantity") },
                                placeholder = { Text("70") },
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                modifier = Modifier.weight(1f)
                            )
                            OutlinedTextField(
                                value = reqExpectedValue,
                                onValueChange = { reqExpectedValue = it },
                                label = { Text("Est. Value (₹)") },
                                placeholder = { Text("150000") },
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                                modifier = Modifier.weight(1f)
                            )
                        }

                        OutlinedTextField(
                            value = reqFollowUpDate,
                            onValueChange = { reqFollowUpDate = it },
                            label = { Text("Follow-up Date (YYYY-MM-DD)") },
                            placeholder = { Text("2026-09-05") },
                            modifier = Modifier.fillMaxWidth()
                        )

                        OutlinedTextField(
                            value = reqNotes,
                            onValueChange = { reqNotes = it },
                            label = { Text("Opportunity Notes") },
                            placeholder = { Text("Customer interested in festive dealer schemes") },
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                }
            }

            // Section 4: GPS Location
            Card(
                colors = CardDefaults.cardColors(containerColor = Color.White),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.LocationOn, contentDescription = null, tint = BrandNavy, modifier = Modifier.size(20.dp))
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Store GPS Position", fontWeight = FontWeight.Bold, fontSize = 15.sp, color = BrandNavy)
                        }
                        IconButton(onClick = { captureLocation() }, modifier = Modifier.size(28.dp)) {
                            Icon(Icons.Default.Refresh, contentDescription = "Refresh GPS", tint = BrandNavy)
                        }
                    }

                    if (isCapturingLocation) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp, color = BrandNavy)
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Acquiring GPS fix at current location...", fontSize = 12.sp, color = TextSecondary)
                        }
                    } else if (locationResult != null) {
                        val loc = locationResult!!
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(8.dp))
                                .background(SuccessGreen.copy(alpha = 0.1f))
                                .border(1.dp, SuccessGreen.copy(alpha = 0.3f), RoundedCornerShape(8.dp))
                                .padding(10.dp)
                        ) {
                            Column {
                                Text(
                                    text = "%.6f, %.6f".format(loc.latitude, loc.longitude),
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 13.sp,
                                    color = BrandNavy
                                )
                                Spacer(modifier = Modifier.height(2.dp))
                                Text(
                                    text = "Accuracy: ±%.1fm · Status: PENDING APPROVAL".format(loc.accuracy),
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Medium,
                                    color = SuccessGreen
                                )
                            }
                        }
                    } else {
                        Text(
                            text = locationError ?: "No GPS fix available. Ensure location is enabled.",
                            fontSize = 12.sp,
                            color = Color.Red
                        )
                    }

                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(6.dp))
                            .background(SurfaceSecondary)
                            .padding(8.dp),
                        verticalAlignment = Alignment.Top
                    ) {
                        Icon(Icons.Default.Info, contentDescription = null, tint = TextSecondary, modifier = Modifier.size(14.dp))
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(
                            text = "New outlet location is saved in PENDING APPROVAL state until verified by Admin.",
                            fontSize = 11.sp,
                            color = TextSecondary
                        )
                    }
                }
            }

            if (submitError != null) {
                Text(
                    text = submitError!!,
                    color = Color.Red,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.SemiBold
                )
            }

            // Submit Button
            Button(
                onClick = { submitProspect(force = false) },
                enabled = !isSubmitting,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(50.dp),
                colors = ButtonDefaults.buttonColors(containerColor = BrandNavy),
                shape = RoundedCornerShape(10.dp)
            ) {
                if (isSubmitting) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp), color = BrandWhite, strokeWidth = 2.dp)
                } else {
                    Text("Register Outlet & Submit", fontSize = 16.sp, fontWeight = FontWeight.Bold, color = BrandWhite)
                }
            }
        }
    }

    // Duplicate Customer Warning Alert Dialog
    if (duplicateWarningMessage != null) {
        AlertDialog(
            onDismissRequest = { duplicateWarningMessage = null },
            icon = {
                Icon(Icons.Default.Warning, contentDescription = null, tint = BrandGold, modifier = Modifier.size(32.dp))
            },
            title = {
                Text("Potential Duplicate Outlet", fontWeight = FontWeight.Bold, fontSize = 17.sp, color = BrandNavy)
            },
            text = {
                Text(duplicateWarningMessage!!, fontSize = 13.sp, color = TextPrimary)
            },
            confirmButton = {
                Button(
                    onClick = {
                        duplicateWarningMessage = null
                        submitProspect(force = true)
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = BrandGold)
                ) {
                    Text("Proceed Anyway (Force Add)", color = BrandNavy, fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                OutlinedButton(onClick = { duplicateWarningMessage = null }) {
                    Text("Review Details")
                }
            }
        )
    }

    // Dynamic Add Brand Alert Dialog
    if (isAddBrandDialogOpen) {
        var newBrandName by remember { mutableStateOf("") }
        var isAddingBrand by remember { mutableStateOf(false) }
        var addBrandError by remember { mutableStateOf<String?>(null) }

        AlertDialog(
            onDismissRequest = { if (!isAddingBrand) isAddBrandDialogOpen = false },
            title = { Text("Add New Brand", fontWeight = FontWeight.Bold, color = BrandNavy) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Enter brand name to add to master catalog:", fontSize = 13.sp, color = TextSecondary)
                    OutlinedTextField(
                        value = newBrandName,
                        onValueChange = {
                            newBrandName = it
                            addBrandError = null
                        },
                        label = { Text("Brand Name *") },
                        placeholder = { Text("e.g. Panasonic") },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true
                    )
                    if (addBrandError != null) {
                        Text(addBrandError ?: "", color = Color.Red, fontSize = 12.sp)
                    }
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        val trimmed = newBrandName.trim()
                        if (trimmed.isBlank()) {
                            addBrandError = "Brand name cannot be empty"
                            return@Button
                        }
                        isAddingBrand = true
                        scope.launch {
                            when (val res = customerRepository.createBrand(trimmed)) {
                                is Resource.Success -> {
                                    val createdBrand = res.data.name
                                    if (!availableBrands.contains(createdBrand)) {
                                        availableBrands = (availableBrands + createdBrand).sorted()
                                    }
                                    selectedBrands = selectedBrands + createdBrand
                                    isAddBrandDialogOpen = false
                                }
                                is Resource.Error -> {
                                    addBrandError = res.message ?: "Failed to add brand"
                                }
                                else -> {}
                            }
                            isAddingBrand = false
                        }
                    },
                    enabled = !isAddingBrand && newBrandName.isNotBlank(),
                    colors = ButtonDefaults.buttonColors(containerColor = BrandNavy)
                ) {
                    if (isAddingBrand) {
                        CircularProgressIndicator(modifier = Modifier.size(16.dp), color = BrandWhite, strokeWidth = 2.dp)
                    } else {
                        Text("Add Brand", color = BrandWhite, fontWeight = FontWeight.Bold)
                    }
                }
            },
            dismissButton = {
                OutlinedButton(
                    onClick = { isAddBrandDialogOpen = false },
                    enabled = !isAddingBrand
                ) {
                    Text("Cancel")
                }
            }
        )
    }
}
