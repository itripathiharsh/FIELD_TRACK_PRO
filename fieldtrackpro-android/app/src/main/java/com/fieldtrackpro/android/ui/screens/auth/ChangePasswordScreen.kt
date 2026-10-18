package com.fieldtrackpro.android.ui.screens.auth

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.viewmodel.AuthViewModel
import com.fieldtrackpro.android.ui.viewmodel.ChangePasswordState
import com.fieldtrackpro.android.utils.PasswordRules

/**
 * Full-screen "Set a new password" gate. Shown after login / at start while the account has
 * must_change_password = true, or whenever any API call answers 403 PASSWORD_CHANGE_REQUIRED.
 * Back is swallowed (nothing else works until the password is changed); LOG OUT stays available.
 * Fields are plain remember (never persisted/restored) so passwords are not written to saved state.
 */
@Composable
fun ChangePasswordScreen(
    viewModel: AuthViewModel,
    onPasswordChanged: () -> Unit,
    onLogout: () -> Unit
) {
    val state by viewModel.changePasswordState.collectAsState()
    var current by remember { mutableStateOf("") }
    var new by remember { mutableStateOf("") }
    var confirm by remember { mutableStateOf("") }

    BackHandler(enabled = true) { /* the change is mandatory; logging out is the only exit */ }

    LaunchedEffect(state) {
        if (state is ChangePasswordState.Success) {
            viewModel.resetChangePasswordState()
            onPasswordChanged()
        }
    }

    val submitting = state is ChangePasswordState.Submitting
    val clientIssue = if (new.isNotEmpty() || confirm.isNotEmpty()) PasswordRules.validate(current.ifEmpty { "-" }, new, confirm) else null
    val serverError = (state as? ChangePasswordState.Error)?.message

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BrandWhite)
            .systemBarsPadding()
            .imePadding()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Spacer(modifier = Modifier.height(16.dp))
        Text(
            "Set a new password",
            fontFamily = LeagueSpartanFamily,
            fontWeight = FontWeight.Bold,
            fontSize = 26.sp,
            color = BrandNavy
        )
        Text(
            "For your security you must choose a new password before you can continue. " +
                "Use at least ${PasswordRules.MIN_LENGTH} characters (at most ${PasswordRules.MAX_BYTES} bytes) " +
                "that differs from your current password.",
            fontSize = 14.sp,
            color = BrandNavy
        )
        PasswordField("Current password", current, !submitting) { current = it; viewModel.resetChangePasswordState() }
        PasswordField("New password", new, !submitting) { new = it; viewModel.resetChangePasswordState() }
        PasswordField("Confirm new password", confirm, !submitting) { confirm = it; viewModel.resetChangePasswordState() }

        val message = serverError ?: clientIssue?.takeIf { it != PasswordRules.Issue.CURRENT_EMPTY }?.message
        if (message != null) {
            Text(message, fontSize = 13.sp, color = ErrorRed)
        }

        Button(
            onClick = { viewModel.changePassword(current, new, confirm) },
            enabled = !submitting && current.isNotEmpty() && new.isNotEmpty() && confirm.isNotEmpty(),
            shape = RoundedCornerShape(10.dp),
            colors = ButtonDefaults.buttonColors(containerColor = BrandNavy, contentColor = BrandWhite),
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp)
        ) {
            if (submitting) {
                CircularProgressIndicator(color = BrandGold, modifier = Modifier.size(24.dp))
            } else {
                Text("SET NEW PASSWORD", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold)
            }
        }

        TextButton(
            enabled = !submitting,
            onClick = {
                viewModel.resetChangePasswordState()
                viewModel.logout()
                onLogout()
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("LOG OUT", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = BrandNavy)
        }
    }
}

@Composable
private fun PasswordField(label: String, value: String, enabled: Boolean, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        singleLine = true,
        enabled = enabled,
        visualTransformation = PasswordVisualTransformation(),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrect = false),
        modifier = Modifier.fillMaxWidth()
    )
}
