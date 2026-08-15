package com.fieldtrackpro.android.ui.screens.requirements

import android.net.Uri
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.model.FormQuestionDto
import com.fieldtrackpro.android.data.model.FormSectionDto
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.FieldTrackAmber
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.SurfaceOffWhite
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.theme.TextMuted
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.viewmodel.FormFillState
import com.fieldtrackpro.android.ui.viewmodel.FormFillViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FormFillScreen(
    visitId: String,
    formId: String,
    viewModel: FormFillViewModel,
    onNavigateBack: () -> Unit
) {
    val state by viewModel.state.collectAsState()
    val form by viewModel.form.collectAsState()
    val answers by viewModel.answers.collectAsState()
    val fieldErrors by viewModel.fieldErrors.collectAsState()
    val isReadOnly by viewModel.isReadOnly.collectAsState()

    LaunchedEffect(visitId, formId) {
        viewModel.load(visitId, formId)
    }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(title = form?.name ?: "Requirement Form", onBackClick = onNavigateBack)
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
            if (state is FormFillState.Error) {
                ErrorBanner(message = (state as FormFillState.Error).message)
                Spacer(modifier = Modifier.height(12.dp))
            }

            if (state is FormFillState.Loading && form == null) {
                CircularProgressIndicator(color = FieldTrackNavy)
                return@Column
            }

            if (state is FormFillState.Submitted) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
                ) {
                    Column(
                        modifier = Modifier
                            .padding(24.dp)
                            .fillMaxWidth(),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = FieldTrackNavy)
                        Spacer(modifier = Modifier.height(8.dp))
                        Text("Form submitted", style = MaterialTheme.typography.titleLarge, color = FieldTrackNavy)
                        Text("Your answers have been recorded.", style = MaterialTheme.typography.bodyMedium, color = TextMuted)
                    }
                }
                Spacer(modifier = Modifier.height(16.dp))
            }

            form?.let { f ->
                Text(f.name, style = MaterialTheme.typography.headlineMedium, color = FieldTrackNavy)
                f.description?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = TextMuted) }
                Spacer(modifier = Modifier.height(16.dp))

                f.sections.forEach { section ->
                    SectionBlock(
                        section = section,
                        answers = answers,
                        fieldErrors = fieldErrors,
                        readOnly = isReadOnly,
                        viewModel = viewModel,
                        visitId = visitId
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                }

                if (!isReadOnly) {
                    Button(
                        onClick = { viewModel.submit() },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(50.dp),
                        shape = RoundedCornerShape(8.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = FieldTrackAmber,
                            contentColor = FieldTrackNavy
                        ),
                        enabled = state !is FormFillState.Loading
                    ) {
                        if (state is FormFillState.Loading) {
                            CircularProgressIndicator(color = SurfaceWhite, modifier = Modifier.height(20.dp))
                        } else {
                            Text("SUBMIT FORM", fontWeight = FontWeight.Bold, color = FieldTrackNavy)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SectionBlock(
    section: FormSectionDto,
    answers: Map<String, String?>,
    fieldErrors: Map<String, String>,
    readOnly: Boolean,
    viewModel: FormFillViewModel,
    visitId: String
) {
    Text(section.title, style = MaterialTheme.typography.titleLarge, color = FieldTrackNavy)
    section.description?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = TextMuted) }
    Spacer(modifier = Modifier.height(8.dp))
    section.questions.forEach { question ->
        QuestionInput(
            question = question,
            value = answers[question.id],
            error = fieldErrors[question.id],
            readOnly = readOnly,
            onChange = { viewModel.setAnswer(question.id, it) },
            onToggleCheckbox = { opt -> viewModel.toggleCheckboxOption(question.id, opt) },
            checkboxValues = { viewModel.decodeCheckboxValues(answers[question.id]) },
            onUpload = { fileName, mimeType, bytes -> viewModel.uploadAttachment(question.id, fileName, mimeType, bytes) },
            visitId = visitId
        )
        Spacer(modifier = Modifier.height(12.dp))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun QuestionInput(
    question: FormQuestionDto,
    value: String?,
    error: String?,
    readOnly: Boolean,
    onChange: (String?) -> Unit,
    onToggleCheckbox: (String) -> Unit,
    checkboxValues: () -> List<String>,
    onUpload: (fileName: String, mimeType: String, bytes: ByteArray) -> Unit,
    visitId: String
) {
    val label = question.questionText + if (question.required) " *" else ""
    Text(label, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = TextPrimary)
    question.helpText?.let { Text(it, fontSize = 11.sp, color = TextMuted) }

    when (question.questionType) {
        "SHORT_TEXT", "EMAIL", "PHONE", "URL" -> OutlinedTextField(
            value = value ?: "",
            onValueChange = { onChange(it.ifBlank { null }) },
            enabled = !readOnly,
            modifier = Modifier.fillMaxWidth(),
            placeholder = { question.placeholder?.let { Text(it) } }
        )

        "LONG_TEXT" -> OutlinedTextField(
            value = value ?: "",
            onValueChange = { onChange(it.ifBlank { null }) },
            enabled = !readOnly,
            minLines = 3,
            modifier = Modifier.fillMaxWidth(),
            placeholder = { question.placeholder?.let { Text(it) } }
        )

        "NUMBER" -> OutlinedTextField(
            value = value ?: "",
            onValueChange = { onChange(it.ifBlank { null }) },
            enabled = !readOnly,
            modifier = Modifier.fillMaxWidth(),
            keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(keyboardType = androidx.compose.ui.text.input.KeyboardType.Number)
        )

        "DATE" -> OutlinedTextField(
            value = value ?: "",
            onValueChange = { onChange(it.ifBlank { null }) },
            enabled = !readOnly,
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text("YYYY-MM-DD") }
        )

        "TIME" -> OutlinedTextField(
            value = value ?: "",
            onValueChange = { onChange(it.ifBlank { null }) },
            enabled = !readOnly,
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text("HH:MM") }
        )

        "DATE_TIME" -> OutlinedTextField(
            value = value ?: "",
            onValueChange = { onChange(it.ifBlank { null }) },
            enabled = !readOnly,
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text("YYYY-MM-DDTHH:MM") }
        )

        "YES_NO" -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("YES", "NO").forEach { opt ->
                Button(
                    onClick = { if (!readOnly) onChange(opt) },
                    enabled = !readOnly,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = if (value == opt) FieldTrackNavy else SurfaceWhite,
                        contentColor = if (value == opt) SurfaceWhite else FieldTrackNavy
                    ),
                    modifier = Modifier.weight(1f)
                ) {
                    Text(opt, color = if (value == opt) SurfaceWhite else FieldTrackNavy)
                }
            }
        }

        "MULTIPLE_CHOICE" -> Column {
            question.options.forEach { opt ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .selectable(selected = value == opt.value, onClick = { if (!readOnly) onChange(opt.value) }),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    RadioButton(selected = value == opt.value, onClick = { if (!readOnly) onChange(opt.value) }, enabled = !readOnly)
                    Text(opt.label, color = TextPrimary)
                }
            }
        }

        "CHECKBOXES" -> {
            val selected = checkboxValues()
            Column {
                question.options.forEach { opt ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .selectable(selected = selected.contains(opt.value), onClick = { if (!readOnly) onToggleCheckbox(opt.value) }),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Checkbox(checked = selected.contains(opt.value), onCheckedChange = { if (!readOnly) onToggleCheckbox(opt.value) }, enabled = !readOnly)
                        Text(opt.label, color = TextPrimary)
                    }
                }
            }
        }

        "DROPDOWN" -> {
            var expanded by remember { mutableStateOf(false) }
            val selectedLabel = question.options.find { it.value == value }?.label ?: ""
            ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { if (!readOnly) expanded = it }) {
                OutlinedTextField(
                    value = selectedLabel,
                    onValueChange = {},
                    readOnly = true,
                    enabled = !readOnly,
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor()
                )
                ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                    question.options.forEach { opt ->
                        DropdownMenuItem(text = { Text(opt.label) }, onClick = { onChange(opt.value); expanded = false })
                    }
                }
            }
        }

        "RATING" -> {
            val max = 5
            val current = value?.toIntOrNull() ?: 0
            Row {
                for (i in 1..max) {
                    Text(
                        text = if (i <= current) "★" else "☆",
                        fontSize = 24.sp,
                        color = FieldTrackAmber,
                        modifier = Modifier
                            .padding(end = 4.dp)
                            .selectable(selected = false, onClick = { if (!readOnly) onChange(i.toString()) })
                    )
                }
            }
        }

        "FILE_UPLOAD", "PHOTO_UPLOAD" -> FileUploadInput(
            hasValue = !value.isNullOrBlank(),
            isPhoto = question.questionType == "PHOTO_UPLOAD",
            readOnly = readOnly,
            onUpload = onUpload,
            onClear = { onChange(null) }
        )

        else -> Text("Unsupported question type: ${question.questionType}", color = TextPrimary)
    }

    error?.let { Text(it, fontSize = 11.sp, color = ErrorRed) }
}

@Composable
private fun FileUploadInput(
    hasValue: Boolean,
    isPhoto: Boolean,
    readOnly: Boolean,
    onUpload: (fileName: String, mimeType: String, bytes: ByteArray) -> Unit,
    onClear: () -> Unit
) {
    val context = LocalContext.current
    val pickerLauncher = rememberLauncherForActivityResult(contract = ActivityResultContracts.GetContent()) { uri: Uri? ->
        if (uri != null) {
            try {
                val mimeType = context.contentResolver.getType(uri) ?: if (isPhoto) "image/jpeg" else "application/pdf"
                val inputStream = context.contentResolver.openInputStream(uri)
                val bytes = inputStream?.readBytes()
                inputStream?.close()
                if (bytes != null && bytes.isNotEmpty()) {
                    val fileName = uri.lastPathSegment ?: "attachment_${System.currentTimeMillis()}"
                    onUpload(fileName, mimeType, bytes)
                }
            } catch (e: Exception) {
            }
        }
    }

    if (hasValue) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(if (isPhoto) "Photo attached" else "File attached", color = TextPrimary)
            if (!readOnly) {
                OutlinedButton(onClick = onClear) { Text("Remove", color = FieldTrackNavy) }
            }
        }
    } else {
        OutlinedButton(
            onClick = { pickerLauncher.launch(if (isPhoto) "image/*" else "*/*") },
            enabled = !readOnly,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text(if (isPhoto) "Select photo to upload" else "Select file to upload", color = FieldTrackNavy)
        }
    }
}
