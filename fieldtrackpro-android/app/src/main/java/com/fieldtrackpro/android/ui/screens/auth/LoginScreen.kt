package com.fieldtrackpro.android.ui.screens.auth

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
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.ArrowForward
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Key
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SuccessGreenBg
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.viewmodel.AuthState
import com.fieldtrackpro.android.ui.viewmodel.AuthViewModel
import kotlinx.coroutines.delay

enum class AuthMode {
    LOGIN, FORGOT_PASSWORD, VERIFY_OTP, SET_PASSWORD, SUCCESS
}

@Composable
fun LoginScreen(
    viewModel: AuthViewModel,
    onLoginSuccess: () -> Unit
) {
    val authState by viewModel.authState.collectAsState()
    
    var mode by remember { mutableStateOf(AuthMode.LOGIN) }

    var identity by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var isPasswordVisible by remember { mutableStateOf(false) }
    
    var otp by remember { mutableStateOf("") }
    var maskedDestination by remember { mutableStateOf("") }
    var deliveryChannel by remember { mutableStateOf("") }

    var newPassword by remember { mutableStateOf("") }
    var confirmPassword by remember { mutableStateOf("") }
    var isNewPasswordVisible by remember { mutableStateOf(false) }
    var isConfirmPasswordVisible by remember { mutableStateOf(false) }
    
    var successMessage by remember { mutableStateOf<String?>(null) }
    var resendCooldown by remember { mutableIntStateOf(0) }

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

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(SurfaceSecondary)
            .padding(20.dp),
        contentAlignment = Alignment.Center
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(16.dp))
                .background(BrandWhite)
                .border(1.dp, BrandLightGray, RoundedCornerShape(16.dp))
                .shadow(4.dp, RoundedCornerShape(16.dp), spotColor = BrandNavy.copy(alpha = 0.1f))
                .padding(24.dp)
                .verticalScroll(rememberScrollState()),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            // Brand Logo & Header
            Box(
                modifier = Modifier
                    .size(52.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(BrandNavy)
                    .border(1.5.dp, BrandGold, RoundedCornerShape(12.dp)),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Default.Shield,
                    contentDescription = "FieldTrack Shield",
                    tint = BrandGold,
                    modifier = Modifier.size(30.dp)
                )
            }

            Spacer(modifier = Modifier.height(14.dp))

            Text(
                text = "FieldTrack Pro",
                fontFamily = LeagueSpartanFamily,
                fontWeight = FontWeight.Bold,
                fontSize = 26.sp,
                letterSpacing = (-0.5).sp,
                color = BrandNavy
            )

            // Gold brand pill badge
            Box(
                modifier = Modifier
                    .padding(top = 4.dp, bottom = 6.dp)
                    .clip(RoundedCornerShape(4.dp))
                    .background(BrandGold.copy(alpha = 0.18f))
                    .border(1.dp, BrandGold.copy(alpha = 0.4f), RoundedCornerShape(4.dp))
                    .padding(horizontal = 8.dp, vertical = 2.dp)
            ) {
                Text(
                    text = "EMPLOYEE OPERATIONS",
                    fontFamily = LeagueSpartanFamily,
                    fontWeight = FontWeight.Bold,
                    fontSize = 10.sp,
                    letterSpacing = 1.sp,
                    color = BrandNavy
                )
            }

            Text(
                text = when (mode) {
                    AuthMode.LOGIN -> "Precision Field Force Intelligence & Geolocation Verification"
                    AuthMode.FORGOT_PASSWORD -> "Enter your registered email or mobile to request a security code"
                    AuthMode.VERIFY_OTP -> "Verify the 6-digit security code dispatched to your account"
                    AuthMode.SET_PASSWORD -> "Set a new secure password for your account"
                    AuthMode.SUCCESS -> "Your credentials have been securely updated"
                },
                fontFamily = LibreBaskervilleFamily,
                fontSize = 14.sp,
                lineHeight = 20.sp,
                fontWeight = FontWeight.Normal,
                color = TextSecondary,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(horizontal = 8.dp)
            )

            Spacer(modifier = Modifier.height(20.dp))

            if (authState is AuthState.Error) {
                ErrorBanner(message = (authState as AuthState.Error).message)
                Spacer(modifier = Modifier.height(14.dp))
            }
            
            val currentSuccess = successMessage
            if (currentSuccess != null && authState !is AuthState.Error && mode != AuthMode.SUCCESS) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(8.dp))
                        .background(SuccessGreenBg)
                        .border(1.dp, SuccessGreen.copy(alpha = 0.4f), RoundedCornerShape(8.dp))
                        .padding(12.dp)
                ) {
                    Text(
                        text = currentSuccess,
                        fontFamily = LeagueSpartanFamily,
                        fontWeight = FontWeight.Medium,
                        color = Color(0xFF065F46),
                        fontSize = 13.sp
                    )
                }
                Spacer(modifier = Modifier.height(14.dp))
            }

            when (mode) {
                AuthMode.LOGIN -> {
                    OutlinedTextField(
                        value = identity,
                        onValueChange = { identity = it },
                        label = { 
                            Text(
                                "Email or Mobile Number",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.SemiBold
                            ) 
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Person,
                                contentDescription = null,
                                tint = BrandNavy.copy(alpha = 0.7f),
                                modifier = Modifier.size(20.dp)
                            )
                        },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = TextPrimary,
                            unfocusedTextColor = TextPrimary,
                            cursorColor = BrandNavy,
                            focusedBorderColor = BrandGold,
                            unfocusedBorderColor = BrandLightGray,
                            focusedLabelColor = BrandNavy,
                            unfocusedLabelColor = TextSecondary,
                            focusedContainerColor = BrandWhite,
                            unfocusedContainerColor = BrandWhite
                        )
                    )

                    Spacer(modifier = Modifier.height(12.dp))

                    OutlinedTextField(
                        value = password,
                        onValueChange = { password = it },
                        label = { 
                            Text(
                                "Password",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.SemiBold
                            ) 
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Lock,
                                contentDescription = null,
                                tint = BrandNavy.copy(alpha = 0.7f),
                                modifier = Modifier.size(20.dp)
                            )
                        },
                        singleLine = true,
                        visualTransformation = if (isPasswordVisible) VisualTransformation.None else PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = if (isPasswordVisible) KeyboardType.Text else KeyboardType.Password),
                        trailingIcon = {
                            IconButton(onClick = { isPasswordVisible = !isPasswordVisible }) {
                                Icon(
                                    imageVector = if (isPasswordVisible) Icons.Filled.Visibility else Icons.Filled.VisibilityOff,
                                    contentDescription = if (isPasswordVisible) "Hide password" else "Show password",
                                    tint = BrandNavy.copy(alpha = 0.7f)
                                )
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = TextPrimary,
                            unfocusedTextColor = TextPrimary,
                            cursorColor = BrandNavy,
                            focusedBorderColor = BrandGold,
                            unfocusedBorderColor = BrandLightGray,
                            focusedLabelColor = BrandNavy,
                            unfocusedLabelColor = TextSecondary,
                            focusedContainerColor = BrandWhite,
                            unfocusedContainerColor = BrandWhite
                        )
                    )
                    
                    Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterEnd) {
                        TextButton(onClick = { 
                            mode = AuthMode.FORGOT_PASSWORD
                            successMessage = null
                            viewModel.resetAuthState()
                        }) {
                            Text(
                                "Forgot Password?",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                fontSize = 13.sp,
                                color = BrandNavy
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    Button(
                        onClick = { 
                            successMessage = null
                            viewModel.login(identity, password) 
                        },
                        enabled = identity.isNotBlank() && password.isNotBlank() && authState !is AuthState.Loading,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp),
                        shape = RoundedCornerShape(10.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = BrandNavy,
                            contentColor = BrandWhite,
                            disabledContainerColor = BrandLightGray,
                            disabledContentColor = TextSecondary
                        )
                    ) {
                        if (authState is AuthState.Loading) {
                            CircularProgressIndicator(color = BrandGold, modifier = Modifier.size(24.dp))
                        } else {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.Center
                            ) {
                                Text(
                                    "SIGN IN TO FIELD FORCE",
                                    fontFamily = LeagueSpartanFamily,
                                    fontSize = 15.sp,
                                    fontWeight = FontWeight.Bold,
                                    letterSpacing = 0.8.sp,
                                    color = BrandWhite
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Icon(
                                    imageVector = Icons.Default.ArrowForward,
                                    contentDescription = null,
                                    tint = BrandGold,
                                    modifier = Modifier.size(18.dp)
                                )
                            }
                        }
                    }
                }
                
                AuthMode.FORGOT_PASSWORD -> {
                    OutlinedTextField(
                        value = identity,
                        onValueChange = { identity = it },
                        label = { 
                            Text(
                                "Email or Mobile Number",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.SemiBold
                            ) 
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Person,
                                contentDescription = null,
                                tint = BrandNavy.copy(alpha = 0.7f),
                                modifier = Modifier.size(20.dp)
                            )
                        },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = TextPrimary,
                            unfocusedTextColor = TextPrimary,
                            cursorColor = BrandNavy,
                            focusedBorderColor = BrandGold,
                            unfocusedBorderColor = BrandLightGray,
                            focusedLabelColor = BrandNavy,
                            unfocusedLabelColor = TextSecondary
                        )
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    Button(
                        onClick = { 
                            successMessage = null
                            viewModel.forgotPassword(identity.trim()) 
                        },
                        enabled = identity.isNotBlank() && authState !is AuthState.Loading,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(50.dp),
                        shape = RoundedCornerShape(10.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = BrandNavy)
                    ) {
                        if (authState is AuthState.Loading) {
                            CircularProgressIndicator(color = BrandGold, modifier = Modifier.size(24.dp))
                        } else {
                            Text(
                                "SEND VERIFICATION CODE",
                                fontFamily = LeagueSpartanFamily,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Bold,
                                color = BrandWhite
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    TextButton(onClick = { 
                        mode = AuthMode.LOGIN
                        viewModel.resetAuthState()
                    }) {
                        Text(
                            "Back to Sign In",
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.Bold,
                            color = BrandNavy
                        )
                    }
                }

                AuthMode.VERIFY_OTP -> {
                    // Masked Destination Info Card
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(10.dp))
                            .background(SurfaceSecondary)
                            .border(1.dp, BrandLightGray, RoundedCornerShape(10.dp))
                            .padding(12.dp)
                    ) {
                        Column {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text(
                                    text = if (deliveryChannel == "SMS") "SMS CODE DISPATCHED" else "EMAIL CODE DISPATCHED",
                                    fontFamily = LeagueSpartanFamily,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 11.sp,
                                    color = BrandNavy
                                )
                                TextButton(
                                    onClick = { 
                                        mode = AuthMode.FORGOT_PASSWORD
                                        viewModel.resetAuthState()
                                    }
                                ) {
                                    Text("Change", fontSize = 12.sp, color = BrandNavy, fontWeight = FontWeight.Bold)
                                }
                            }
                            Text(
                                text = maskedDestination.ifBlank { identity },
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 14.sp,
                                color = TextPrimary
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(14.dp))

                    OutlinedTextField(
                        value = otp,
                        onValueChange = { otp = it.filter { ch -> ch.isDigit() }.take(6) },
                        label = { 
                            Text(
                                "6-Digit Security Code",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.SemiBold
                            ) 
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Key,
                                contentDescription = null,
                                tint = BrandNavy.copy(alpha = 0.7f),
                                modifier = Modifier.size(20.dp)
                            )
                        },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = TextPrimary,
                            unfocusedTextColor = TextPrimary,
                            focusedBorderColor = BrandGold,
                            unfocusedBorderColor = BrandLightGray
                        )
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "Didn't receive code?",
                            fontFamily = LibreBaskervilleFamily,
                            fontSize = 12.sp,
                            color = TextSecondary
                        )
                        if (resendCooldown > 0) {
                            Text(
                                text = "Resend in ${resendCooldown}s",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                fontSize = 12.sp,
                                color = TextSecondary
                            )
                        } else {
                            TextButton(onClick = {
                                viewModel.forgotPassword(identity.trim())
                            }) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(14.dp), tint = BrandNavy)
                                    Spacer(modifier = Modifier.width(4.dp))
                                    Text("Resend Code", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 12.sp, color = BrandNavy)
                                }
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(10.dp))

                    Button(
                        onClick = { 
                            successMessage = null
                            viewModel.verifyOtp(identity.trim(), otp.trim()) 
                        },
                        enabled = otp.trim().length >= 6 && authState !is AuthState.Loading,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(50.dp),
                        shape = RoundedCornerShape(10.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = BrandNavy)
                    ) {
                        if (authState is AuthState.Loading) {
                            CircularProgressIndicator(color = BrandGold, modifier = Modifier.size(24.dp))
                        } else {
                            Text(
                                "VERIFY CODE",
                                fontFamily = LeagueSpartanFamily,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Bold,
                                color = BrandWhite
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    TextButton(onClick = { 
                        mode = AuthMode.LOGIN
                        viewModel.resetAuthState()
                    }) {
                        Text(
                            "Cancel",
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.Bold,
                            color = BrandNavy
                        )
                    }
                }

                AuthMode.SET_PASSWORD -> {
                    OutlinedTextField(
                        value = newPassword,
                        onValueChange = { newPassword = it },
                        label = { 
                            Text(
                                "New Password (min 8 chars)",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.SemiBold
                            ) 
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Lock,
                                contentDescription = null,
                                tint = BrandNavy.copy(alpha = 0.7f),
                                modifier = Modifier.size(20.dp)
                            )
                        },
                        singleLine = true,
                        visualTransformation = if (isNewPasswordVisible) VisualTransformation.None else PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = if (isNewPasswordVisible) KeyboardType.Text else KeyboardType.Password),
                        trailingIcon = {
                            IconButton(onClick = { isNewPasswordVisible = !isNewPasswordVisible }) {
                                Icon(
                                    imageVector = if (isNewPasswordVisible) Icons.Filled.Visibility else Icons.Filled.VisibilityOff,
                                    contentDescription = null,
                                    tint = BrandNavy
                                )
                            }
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

                    Spacer(modifier = Modifier.height(10.dp))

                    OutlinedTextField(
                        value = confirmPassword,
                        onValueChange = { confirmPassword = it },
                        label = { 
                            Text(
                                "Confirm New Password",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.SemiBold
                            ) 
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Lock,
                                contentDescription = null,
                                tint = BrandNavy.copy(alpha = 0.7f),
                                modifier = Modifier.size(20.dp)
                            )
                        },
                        singleLine = true,
                        visualTransformation = if (isConfirmPasswordVisible) VisualTransformation.None else PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = if (isConfirmPasswordVisible) KeyboardType.Text else KeyboardType.Password),
                        trailingIcon = {
                            IconButton(onClick = { isConfirmPasswordVisible = !isConfirmPasswordVisible }) {
                                Icon(
                                    imageVector = if (isConfirmPasswordVisible) Icons.Filled.Visibility else Icons.Filled.VisibilityOff,
                                    contentDescription = null,
                                    tint = BrandNavy
                                )
                            }
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

                    Spacer(modifier = Modifier.height(16.dp))

                    val passwordsMatch = newPassword.isNotBlank() && newPassword == confirmPassword
                    val passwordLengthOk = newPassword.length >= 8

                    Button(
                        onClick = { 
                            successMessage = null
                            viewModel.resetPassword(identity.trim(), otp.trim(), newPassword) 
                        },
                        enabled = passwordLengthOk && passwordsMatch && authState !is AuthState.Loading,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(50.dp),
                        shape = RoundedCornerShape(10.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = BrandNavy)
                    ) {
                        if (authState is AuthState.Loading) {
                            CircularProgressIndicator(color = BrandGold, modifier = Modifier.size(24.dp))
                        } else {
                            Text(
                                "SAVE NEW PASSWORD",
                                fontFamily = LeagueSpartanFamily,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Bold,
                                color = BrandWhite
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    TextButton(onClick = { 
                        mode = AuthMode.LOGIN
                        viewModel.resetAuthState()
                    }) {
                        Text(
                            "Cancel",
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.Bold,
                            color = BrandNavy
                        )
                    }
                }

                AuthMode.SUCCESS -> {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 12.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Box(
                            modifier = Modifier
                                .size(64.dp)
                                .clip(RoundedCornerShape(16.dp))
                                .background(SuccessGreenBg)
                                .border(1.dp, SuccessGreen.copy(alpha = 0.5f), RoundedCornerShape(16.dp)),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                imageVector = Icons.Default.CheckCircle,
                                contentDescription = null,
                                tint = SuccessGreen,
                                modifier = Modifier.size(36.dp)
                            )
                        }

                        Spacer(modifier = Modifier.height(14.dp))

                        Text(
                            text = "Password Reset Successful",
                            fontFamily = LeagueSpartanFamily,
                            fontWeight = FontWeight.Bold,
                            fontSize = 20.sp,
                            color = BrandNavy
                        )

                        Spacer(modifier = Modifier.height(6.dp))

                        Text(
                            text = "Your password has been changed. You can now sign in with your new credentials.",
                            fontFamily = LibreBaskervilleFamily,
                            fontSize = 13.sp,
                            color = TextSecondary,
                            textAlign = TextAlign.Center
                        )

                        Spacer(modifier = Modifier.height(20.dp))

                        Button(
                            onClick = { 
                                mode = AuthMode.LOGIN
                                viewModel.resetAuthState()
                            },
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(50.dp),
                            shape = RoundedCornerShape(10.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = BrandNavy)
                        ) {
                            Text(
                                "BACK TO SIGN IN",
                                fontFamily = LeagueSpartanFamily,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Bold,
                                color = BrandWhite
                            )
                        }
                    }
                }
            }
        }
    }
}
