package com.fieldtrackpro.android.ui.screens.requirements

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.theme.ElectricBlue
import com.fieldtrackpro.android.ui.theme.Slate50
import com.fieldtrackpro.android.ui.theme.Slate500
import com.fieldtrackpro.android.ui.theme.Slate900
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.viewmodel.RequirementState
import com.fieldtrackpro.android.ui.viewmodel.RequirementViewModel

/**
 * Requirement Form Screen.
 *
 * Allows field representatives to capture customer requirements during a visit.
 * Fields per Requirements doc Section 4.1:
 * - Category (dropdown)
 * - Description (required)
 * - Priority (Low/Medium/High)
 * - Expected Timeline
 * - Budget Range (optional)
 * - Notes (optional)
 */
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
    val existingForm by viewModel.existingForm.collectAsState()

    var categoryExpanded by remember { mutableStateOf(false) }
    var selectedCategoryId by remember { mutableStateOf("") }
    var selectedCategoryName by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var priority by remember { mutableStateOf("MEDIUM") }
    var expectedTimeline by remember { mutableStateOf("") }
    var budgetRange by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }

    LaunchedEffect(visitId) {
        viewModel.loadCategories()
        viewModel.loadForm(visitId)
    }

    LaunchedEffect(existingForm) {
        existingForm?.let { form ->
            selectedCategoryId = form.categoryId
            selectedCategoryName = form.categoryName ?: ""
            description = form.description
            priority = form.priority
            expectedTimeline = form.expectedTimeline
            budgetRange = form.budgetRange ?: ""
            notes = form.notes ?: ""
        }
    }

    LaunchedEffect(state) {
        if (state is RequirementState.FormSubmitted) {
            onSubmitSuccess()
        }
    }

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
                .background(Slate50)
                .padding(innerPadding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState())
        ) {
            if (state is RequirementState.Error) {
                ErrorBanner(message = (state as RequirementState.Error).message)
                Spacer(modifier = Modifier.height(12.dp))
            }

            if (state is RequirementState.Loading) {
                CircularProgressIndicator()
                Spacer(modifier = Modifier.height(12.dp))
            }

            Text(
                text = "Customer Requirements",
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
                color = Slate900
            )
            Text(
                text = "Capture site requirements and customer needs.",
                fontSize = 13.sp,
                color = Slate500
            )

            Spacer(modifier = Modifier.height(16.dp))

            // Category Dropdown
            Text(text = "Category *", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Slate900)
            ExposedDropdownMenuBox(
                expanded = categoryExpanded,
                onExpandedChange = { categoryExpanded = it }
            ) {
                OutlinedTextField(
                    value = selectedCategoryName,
                    onValueChange = {},
                    readOnly = true,
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = categoryExpanded) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor()
                )
                ExposedDropdownMenu(
                    expanded = categoryExpanded,
                    onDismissRequest = { categoryExpanded = false }
                ) {
                    categories.forEach { category ->
                        DropdownMenuItem(
                            text = { Text(category.name) },
                            onClick = {
                                selectedCategoryId = category.id
                                selectedCategoryName = category.name
                                categoryExpanded = false
                            }
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Description
            Text(text = "Description *", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Slate900)
            OutlinedTextField(
                value = description,
                onValueChange = { description = it },
                modifier = Modifier.fillMaxWidth(),
                minLines = 3,
                placeholder = { Text("Describe the requirement...") }
            )

            Spacer(modifier = Modifier.height(12.dp))

            // Priority
            Text(text = "Priority *", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Slate900)
            Row {
                listOf("LOW", "MEDIUM", "HIGH").forEach { p ->
                    Button(
                        onClick = { priority = p },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (priority == p) ElectricBlue else Slate50
                        ),
                        modifier = Modifier.padding(end = 8.dp)
                    ) {
                        Text(p, fontSize = 12.sp)
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Expected Timeline
            Text(text = "Expected Timeline *", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Slate900)
            OutlinedTextField(
                value = expectedTimeline,
                onValueChange = { expectedTimeline = it },
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("e.g., 2 weeks") }
            )

            Spacer(modifier = Modifier.height(12.dp))

            // Budget Range (optional)
            Text(text = "Budget Range (optional)", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Slate900)
            OutlinedTextField(
                value = budgetRange,
                onValueChange = { budgetRange = it },
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("e.g., Rs 5000-10000") }
            )

            Spacer(modifier = Modifier.height(12.dp))

            // Notes (optional)
            Text(text = "Notes (optional)", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Slate900)
            OutlinedTextField(
                value = notes,
                onValueChange = { notes = it },
                modifier = Modifier.fillMaxWidth(),
                minLines = 2,
                placeholder = { Text("Additional notes...") }
            )

            Spacer(modifier = Modifier.height(24.dp))

            // Submit Button
            Button(
                onClick = {
                    viewModel.submitForm(
                        visitId = visitId,
                        categoryId = selectedCategoryId,
                        description = description,
                        priority = priority,
                        expectedTimeline = expectedTimeline,
                        budgetRange = budgetRange.ifBlank { null },
                        notes = notes.ifBlank { null }
                    )
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(50.dp),
                shape = RoundedCornerShape(8.dp),
                colors = ButtonDefaults.buttonColors(containerColor = ElectricBlue),
                enabled = selectedCategoryId.isNotBlank() && description.isNotBlank() &&
                    expectedTimeline.isNotBlank() && state !is RequirementState.Loading
            ) {
                if (state is RequirementState.Loading) {
                    CircularProgressIndicator(color = SurfaceWhite, modifier = Modifier.height(20.dp))
                } else {
                    Text("SUBMIT REQUIREMENTS", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}
