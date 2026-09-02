package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.UserDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.AuthRepository
import com.fieldtrackpro.android.data.repository.Resource
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class AuthState {
    object Idle : AuthState()
    object Loading : AuthState()
    data class Authenticated(val user: UserDto) : AuthState()
    data class Error(val message: String) : AuthState()
    data class ForgotPasswordSuccess(val message: String, val destination: String? = null, val deliveryChannel: String? = null) : AuthState()
    data class OtpVerified(val message: String) : AuthState()
    data class ResetPasswordSuccess(val message: String) : AuthState()
}

/**
 * Authentication ViewModel.
 *
 * APP-AUTH-004: Double-tap / concurrent submission protection.
 * APP-AUTH-005: Formats user-friendly error messages.
 */
class AuthViewModel(
    private val tokenManager: TokenManager
) : ViewModel() {

    private val authRepository = AuthRepository(
        authApi = ApiClient.createAuthApi(tokenManager),
        tokenManager = tokenManager
    )

    private val _authState = MutableStateFlow<AuthState>(AuthState.Idle)
    val authState: StateFlow<AuthState> = _authState.asStateFlow()

    private var lastSubmitTimestamp = 0L

    fun login(identity: String, pass: String) {
        val now = System.currentTimeMillis()
        if (_authState.value is AuthState.Loading || (now - lastSubmitTimestamp < 800L)) {
            return
        }
        lastSubmitTimestamp = now

        viewModelScope.launch {
            _authState.value = AuthState.Loading
            when (val result = authRepository.login(identity, pass)) {
                is Resource.Success -> _authState.value = AuthState.Authenticated(result.data)
                is Resource.Error -> _authState.value = AuthState.Error(result.message)
                else -> {}
            }
        }
    }

    fun logout() {
        viewModelScope.launch {
            authRepository.logout()
            _authState.value = AuthState.Idle
        }
    }

    fun resetAuthState() {
        _authState.value = AuthState.Idle
    }

    fun forgotPassword(identifier: String) {
        if (_authState.value is AuthState.Loading) return
        viewModelScope.launch {
            _authState.value = AuthState.Loading
            when (val result = authRepository.forgotPassword(identifier)) {
                is Resource.Success -> _authState.value = AuthState.ForgotPasswordSuccess(
                    message = result.data.message,
                    destination = result.data.destination,
                    deliveryChannel = result.data.deliveryChannel
                )
                is Resource.Error -> _authState.value = AuthState.Error(result.message)
                else -> {}
            }
        }
    }

    fun verifyOtp(identifier: String, otp: String) {
        if (_authState.value is AuthState.Loading) return
        viewModelScope.launch {
            _authState.value = AuthState.Loading
            when (val result = authRepository.verifyOtp(identifier, otp)) {
                is Resource.Success -> _authState.value = AuthState.OtpVerified(result.data)
                is Resource.Error -> _authState.value = AuthState.Error(result.message)
                else -> {}
            }
        }
    }

    fun resetPassword(identifier: String, otp: String, newPassword: String) {
        if (_authState.value is AuthState.Loading) return
        viewModelScope.launch {
            _authState.value = AuthState.Loading
            when (val result = authRepository.resetPassword(identifier, otp, newPassword)) {
                is Resource.Success -> _authState.value = AuthState.ResetPasswordSuccess(result.data)
                is Resource.Error -> _authState.value = AuthState.Error(result.message)
                else -> {}
            }
        }
    }

    fun checkAuthStatus(): Boolean = authRepository.isLoggedIn()
}
