package com.fieldtrackpro.android.ui.screens.auth

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Key
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextFieldColors
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.components.BrandMark
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.PrimaryButton
import com.fieldtrackpro.android.ui.components.StatusChip
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.GoldOnNavyText
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.Navy950
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SuccessGreenBg
import com.fieldtrackpro.android.ui.theme.SuccessGreenText
import com.fieldtrackpro.android.ui.theme.SystemBarIcons
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.viewmodel.AuthState
import com.fieldtrackpro.android.ui.viewmodel.AuthViewModel
import com.fieldtrackpro.android.utils.ExternalLinks
import kotlinx.coroutines.delay

enum class AuthMode {
    LOGIN, FORGOT_PASSWORD, VERIFY_OTP, SET_PASSWORD, SUCCESS
}

/**
 * Sign-in (plus forgot-password -> OTP -> new password). Design v2: the navy brand area continues from the splash and
 * a white sheet holds the form. Behaviour is unchanged; keyboard handling is fixed (keyboard types, Next/Done IME
 * actions, Done submits) and the non-secret flow state survives rotation and process recreation. Passwords are
 * deliberately NOT saved into the instance-state bundle.
 */
@Composable
fun LoginScreen(
    viewModel: AuthViewModel,
    onLoginSuccess: () -> Unit
) {
    val authState by viewModel.authState.collectAsState()
    val context = LocalContext.current
    val focusManager = LocalFocusManager.current

    var mode by rememberSaveable { mutableStateOf(AuthMode.LOGIN) }

    var identity by rememberSaveable { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var isPasswordVisible by remember { mutableStateOf(false) }

    var otp by rememberSaveable { mutableStateOf("") }
    var maskedDestination by rememberSaveable { mutableStateOf("") }
    var deliveryChannel by rememberSaveable { mutableStateOf("") }

    var newPassword by remember { mutableStateOf("") }
    var confirmPassword by remember { mutableStateOf("") }
    var isNewPasswordVisible by remember { mutableStateOf(false) }
    var isConfirmPasswordVisible by remember { mutableStateOf(false) }

    var successMessage by rememberSaveable { mutableStateOf<String?>(null) }
    var resendCooldown by rememberSaveable { mutableIntStateOf(0) }

    val isLoading = authState is AuthState.Loading

    LaunchedEffect(resendCooldown) {
        if (resendCooldown > 0) {
            delay(1000L)
            resendCooldown -= 1
        }
    }

    LaunchedEffect(authState) {
        when (val state = authState) {
            is AuthState.Authenticated -> onLoginSuccess()
            is AuthState.ForgotPasswordSuccess -> {
                successMessage = state.message
                maskedDestination = state.destination ?: identity
                deliveryChannel = state.deliveryChannel ?: if (identity.contains("@")) "EMAIL" else "SMS"
                mode = AuthMode.VERIFY_OTP
                resendCooldown = 60
                viewModel.resetAuthState()
            }
            is AuthState.OtpVerified -> {
                mode = AuthMode.SET_PASSWORD
                viewModel.resetAuthState()
            }
            is AuthState.ResetPasswordSuccess -> {
                successMessage = state.message
                mode = AuthMode.SUCCESS
                password = ""
                otp = ""
                newPassword = ""
                confirmPassword = ""
                viewModel.resetAuthState()
            }
            else -> {}
        }
    }

    fun goTo(target: AuthMode) {
        mode = target
        viewModel.resetAuthState()
    }

    val canSignIn = identity.isNotBlank() && password.isNotBlank() && !isLoading
    fun signIn() {
        if (!canSignIn) return
        focusManager.clearFocus()
        successMessage = null
        viewModel.login(identity, password)
    }

    LoginLayout(
        subtitle = when (mode) {
            AuthMode.LOGIN -> "Use your registered mobile number or email."
            AuthMode.FORGOT_PASSWORD -> "Enter your registered email or mobile number. We'll send a 6-digit code."
            AuthMode.VERIFY_OTP -> "Enter the 6-digit code we sent you."
            AuthMode.SET_PASSWORD -> "Choose a new password for your account."
            AuthMode.SUCCESS -> "Your password has been updated."
        },
        title = when (mode) {
            AuthMode.LOGIN -> "Sign in"
            AuthMode.FORGOT_PASSWORD -> "Reset password"
            AuthMode.VERIFY_OTP -> "Verify code"
            AuthMode.SET_PASSWORD -> "New password"
            AuthMode.SUCCESS -> "All set"
        }
    ) {
        if (authState is AuthState.Error) {
            ErrorBanner(message = (authState as AuthState.Error).message)
            Spacer(modifier = Modifier.height(14.dp))
        }

        val currentSuccess = successMessage
        if (currentSuccess != null && authState !is AuthState.Error && mode != AuthMode.SUCCESS) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(SuccessGreenBg)
                    .padding(12.dp)
            ) {
                Text(currentSuccess, fontWeight = FontWeight.Medium, color = SuccessGreenText, fontSize = 14.sp)
            }
            Spacer(modifier = Modifier.height(14.dp))
        }

        when (mode) {
            AuthMode.LOGIN -> {
                FtTextField(
                    value = identity,
                    onValueChange = { identity = it },
                    label = "Mobile number or email",
                    icon = Icons.Default.Person,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, autoCorrect = false, imeAction = ImeAction.Next),
                    keyboardActions = KeyboardActions(onNext = { focusManager.moveFocus(FocusDirection.Down) })
                )
                Spacer(modifier = Modifier.height(12.dp))
                FtTextField(
                    value = password,
                    onValueChange = { password = it },
                    label = "Password",
                    icon = Icons.Default.Lock,
                    secret = true,
                    revealed = isPasswordVisible,
                    onToggleReveal = { isPasswordVisible = !isPasswordVisible },
                    keyboardOptions = KeyboardOptions(
                        keyboardType = KeyboardType.Password,
                        autoCorrect = false,
                        imeAction = ImeAction.Done
                    ),
                    keyboardActions = KeyboardActions(onDone = { signIn() })
                )
                Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterEnd) {
                    TextButton(onClick = {
                        successMessage = null
                        goTo(AuthMode.FORGOT_PASSWORD)
                    }) {
                        Text("Forgot password?", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = BrandNavy)
                    }
                }
                Spacer(modifier = Modifier.height(4.dp))
                PrimaryButton(
                    text = "Sign in",
                    onClick = { signIn() },
                    enabled = canSignIn,
                    loading = isLoading,
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(modifier = Modifier.height(18.dp))
                Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    TextButton(onClick = { ExternalLinks.openPrivacyPolicy(context) }) {
                        Text("Privacy policy", fontSize = 13.sp, color = TextSecondary)
                    }
                }
            }

            AuthMode.FORGOT_PASSWORD -> {
                FtTextField(
                    value = identity,
                    onValueChange = { identity = it },
                    label = "Mobile number or email",
                    icon = Icons.Default.Person,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, autoCorrect = false, imeAction = ImeAction.Send),
                    keyboardActions = KeyboardActions(onSend = {
                        if (identity.isNotBlank() && !isLoading) {
                            successMessage = null
                            viewModel.forgotPassword(identity.trim())
                        }
                    })
                )
                Spacer(modifier = Modifier.height(16.dp))
                PrimaryButton(
                    text = "Send code",
                    onClick = {
                        successMessage = null
                        viewModel.forgotPassword(identity.trim())
                    },
                    enabled = identity.isNotBlank() && !isLoading,
                    loading = isLoading,
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(modifier = Modifier.height(8.dp))
                SheetTextAction("Back to sign in") { goTo(AuthMode.LOGIN) }
            }

            AuthMode.VERIFY_OTP -> {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(12.dp))
                        .background(Color(0xFFF3F5F9))
                        .padding(start = 14.dp, end = 4.dp, top = 6.dp, bottom = 6.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            text = if (deliveryChannel == "SMS") "CODE SENT BY SMS" else "CODE SENT BY EMAIL",
                            fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 11.sp,
                            letterSpacing = 0.8.sp, color = TextSecondary
                        )
                        Text(maskedDestination.ifBlank { identity }, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, color = TextPrimary)
                    }
                    TextButton(onClick = { goTo(AuthMode.FORGOT_PASSWORD) }) {
                        Text("Change", fontWeight = FontWeight.Bold, color = BrandNavy)
                    }
                }
                Spacer(modifier = Modifier.height(14.dp))
                FtTextField(
                    value = otp,
                    onValueChange = { otp = it.filter { ch -> ch.isDigit() }.take(6) },
                    label = "6-digit code",
                    icon = Icons.Default.Key,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword, imeAction = ImeAction.Done),
                    keyboardActions = KeyboardActions(onDone = {
                        if (otp.trim().length >= 6 && !isLoading) {
                            successMessage = null
                            viewModel.verifyOtp(identity.trim(), otp.trim())
                        }
                    })
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Didn't get the code?", fontSize = 13.sp, color = TextSecondary)
                    if (resendCooldown > 0) {
                        Text("Resend in ${resendCooldown}s", fontWeight = FontWeight.SemiBold, fontSize = 13.sp, color = TextSecondary, modifier = Modifier.padding(vertical = 14.dp))
                    } else {
                        TextButton(onClick = { viewModel.forgotPassword(identity.trim()) }) {
                            Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(16.dp), tint = BrandNavy)
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Resend code", fontWeight = FontWeight.Bold, fontSize = 13.sp, color = BrandNavy)
                        }
                    }
                }
                Spacer(modifier = Modifier.height(8.dp))
                PrimaryButton(
                    text = "Verify code",
                    onClick = {
                        successMessage = null
                        viewModel.verifyOtp(identity.trim(), otp.trim())
                    },
                    enabled = otp.trim().length >= 6 && !isLoading,
                    loading = isLoading,
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(modifier = Modifier.height(8.dp))
                SheetTextAction("Cancel") { goTo(AuthMode.LOGIN) }
            }

            AuthMode.SET_PASSWORD -> {
                val passwordsMatch = newPassword.isNotBlank() && newPassword == confirmPassword
                val passwordLengthOk = newPassword.length >= 8
                val canSave = passwordLengthOk && passwordsMatch && !isLoading
                FtTextField(
                    value = newPassword,
                    onValueChange = { newPassword = it },
                    label = "New password (min 8 characters)",
                    icon = Icons.Default.Lock,
                    secret = true,
                    revealed = isNewPasswordVisible,
                    onToggleReveal = { isNewPasswordVisible = !isNewPasswordVisible },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrect = false, imeAction = ImeAction.Next),
                    keyboardActions = KeyboardActions(onNext = { focusManager.moveFocus(FocusDirection.Down) })
                )
                Spacer(modifier = Modifier.height(12.dp))
                FtTextField(
                    value = confirmPassword,
                    onValueChange = { confirmPassword = it },
                    label = "Confirm new password",
                    icon = Icons.Default.Lock,
                    secret = true,
                    revealed = isConfirmPasswordVisible,
                    onToggleReveal = { isConfirmPasswordVisible = !isConfirmPasswordVisible },
                    isError = confirmPassword.isNotEmpty() && !passwordsMatch,
                    supporting = if (confirmPassword.isNotEmpty() && !passwordsMatch) "Passwords don't match" else null,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrect = false, imeAction = ImeAction.Done),
                    keyboardActions = KeyboardActions(onDone = {
                        if (canSave) {
                            successMessage = null
                            viewModel.resetPassword(identity.trim(), otp.trim(), newPassword)
                        }
                    })
                )
                Spacer(modifier = Modifier.height(16.dp))
                PrimaryButton(
                    text = "Save new password",
                    onClick = {
                        successMessage = null
                        viewModel.resetPassword(identity.trim(), otp.trim(), newPassword)
                    },
                    enabled = canSave,
                    loading = isLoading,
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(modifier = Modifier.height(8.dp))
                SheetTextAction("Cancel") { goTo(AuthMode.LOGIN) }
            }

            AuthMode.SUCCESS -> {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Box(
                        modifier = Modifier.size(64.dp).clip(RoundedCornerShape(20.dp)).background(SuccessGreenBg),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(Icons.Default.CheckCircle, contentDescription = null, tint = SuccessGreen, modifier = Modifier.size(36.dp))
                    }
                    Spacer(modifier = Modifier.height(14.dp))
                    Text(
                        "You can now sign in with your new password.",
                        fontSize = 15.sp, color = TextSecondary, textAlign = TextAlign.Center
                    )
                    Spacer(modifier = Modifier.height(20.dp))
                    PrimaryButton(text = "Back to sign in", onClick = { goTo(AuthMode.LOGIN) }, modifier = Modifier.fillMaxWidth())
                }
            }
        }
    }
}

/** Navy brand header + white form sheet. Stateless; also used by the screenshot test. */
@Composable
fun LoginLayout(title: String, subtitle: String, content: @Composable () -> Unit) {
    SystemBarIcons(darkIcons = false)
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BrandWhite)
            .verticalScroll(rememberScrollState())
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(Brush.verticalGradient(listOf(BrandNavy, Navy950)))
                .statusBarsPadding()
                .padding(top = 40.dp, bottom = 52.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            BrandMark(height = 64.dp, contentDescription = "FieldTrack Pro")
            Spacer(Modifier.height(14.dp))
            Text("FieldTrack Pro", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 26.sp, letterSpacing = (-0.3).sp, color = BrandWhite)
            Spacer(Modifier.height(10.dp))
            StatusChip(text = "Employee app", container = BrandGold.copy(alpha = 0.16f), content = GoldOnNavyText)
        }
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .offset(y = (-24).dp)
                .clip(RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp))
                .background(BrandWhite)
                .navigationBarsPadding()
                .padding(horizontal = 24.dp, vertical = 28.dp)
                .widthIn(max = 520.dp)
        ) {
            Text(title, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 24.sp, color = BrandNavy)
            Spacer(Modifier.height(4.dp))
            Text(subtitle, fontSize = 15.sp, lineHeight = 21.sp, color = TextSecondary)
            Spacer(Modifier.height(22.dp))
            content()
        }
    }
}

@Composable
private fun SheetTextAction(label: String, onClick: () -> Unit) {
    Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        TextButton(onClick = onClick, modifier = Modifier.heightIn(min = 48.dp)) {
            Text(label, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 15.sp, color = BrandNavy)
        }
    }
}

@Composable
private fun ftFieldColors(): TextFieldColors = OutlinedTextFieldDefaults.colors(
    focusedTextColor = TextPrimary,
    unfocusedTextColor = TextPrimary,
    cursorColor = BrandNavy,
    focusedBorderColor = BrandGold,
    unfocusedBorderColor = BrandLightGray,
    focusedLabelColor = BrandNavy,
    unfocusedLabelColor = TextSecondary,
    focusedLeadingIconColor = BrandNavy,
    unfocusedLeadingIconColor = TextSecondary,
    focusedContainerColor = BrandWhite,
    unfocusedContainerColor = BrandWhite
)

@Composable
private fun FtTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    icon: ImageVector,
    keyboardOptions: KeyboardOptions,
    keyboardActions: KeyboardActions,
    secret: Boolean = false,
    revealed: Boolean = false,
    onToggleReveal: (() -> Unit)? = null,
    isError: Boolean = false,
    supporting: String? = null
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        leadingIcon = { Icon(icon, contentDescription = null, modifier = Modifier.size(20.dp)) },
        trailingIcon = if (secret && onToggleReveal != null) {
            {
                IconButton(onClick = onToggleReveal) {
                    Icon(
                        imageVector = if (revealed) Icons.Filled.Visibility else Icons.Filled.VisibilityOff,
                        contentDescription = if (revealed) "Hide password" else "Show password",
                        tint = TextSecondary
                    )
                }
            }
        } else null,
        visualTransformation = if (secret && !revealed) PasswordVisualTransformation() else VisualTransformation.None,
        singleLine = true,
        isError = isError,
        supportingText = supporting?.let { { Text(it) } },
        keyboardOptions = keyboardOptions,
        keyboardActions = keyboardActions,
        shape = RoundedCornerShape(12.dp),
        colors = ftFieldColors(),
        modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)
    )
}
