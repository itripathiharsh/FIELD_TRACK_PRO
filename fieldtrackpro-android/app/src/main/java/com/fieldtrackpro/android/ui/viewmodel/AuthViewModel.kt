package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.UserDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.AuthRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.utils.PasswordRules
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

sealed class AccountDeletionState {
    object Idle : AccountDeletionState()
    object Submitting : AccountDeletionState()
    data class Submitted(val message: String) : AccountDeletionState()
    /** Wrong password (inline error under the password field; the dialog stays open). */
    data class IncorrectPassword(val message: String) : AccountDeletionState()
    data class Failed(val message: String) : AccountDeletionState()
}

sealed class ChangePasswordState {
    object Idle : ChangePasswordState()
    object Submitting : ChangePasswordState()
    object Success : ChangePasswordState()
    data class Error(val message: String) : ChangePasswordState()
}

/**
 * Authentication ViewModel.
 *
 * APP-AUTH-004: Double-tap / concurrent submission protection.
 * APP-AUTH-005: Formats user-friendly error messages.
 */
class AuthViewModel(
    private val tokenManager: TokenManager,
    /** Invoked after the session ends (logout / account deletion) to cancel scheduled background work. */
    private val onSessionEnded: () -> Unit = {},
    /** Account deletion succeeded: wipe every piece of local data of that user ([userId] captured before the session was cleared). */
    private val onAccountDeleted: (userId: String?) -> Unit = {},
    /** The forced/voluntary password change succeeded: resume sync + notification work. */
    private val onPasswordChanged: () -> Unit = {}
) : ViewModel() {

    private val authRepository = AuthRepository(
        authApi = ApiClient.createAuthApi(tokenManager),
        tokenManager = tokenManager
    )

    private val _authState = MutableStateFlow<AuthState>(AuthState.Idle)
    val authState: StateFlow<AuthState> = _authState.asStateFlow()

    private val _deletionState = MutableStateFlow<AccountDeletionState>(AccountDeletionState.Idle)
    val deletionState: StateFlow<AccountDeletionState> = _deletionState.asStateFlow()

    private val _changePasswordState = MutableStateFlow<ChangePasswordState>(ChangePasswordState.Idle)
    val changePasswordState: StateFlow<ChangePasswordState> = _changePasswordState.asStateFlow()

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
            onSessionEnded()
            _authState.value = AuthState.Idle
        }
    }

    /**
     * Play account-deletion: DELETE /auth/me with the current password (masked field in the dialog, never logged).
     * On success the session is cleared and ALL local user data is wiped (queue, conflicts, proof photos, drafts,
     * prefs, scheduled work), then the UI goes to login.
     */
    fun requestAccountDeletion(password: String, reason: String?) {
        if (_deletionState.value is AccountDeletionState.Submitting) return
        if (password.isEmpty()) {
            _deletionState.value = AccountDeletionState.IncorrectPassword("Enter your current password to confirm.")
            return
        }
        val deletedUserId = tokenManager.getUserId()
        viewModelScope.launch {
            _deletionState.value = AccountDeletionState.Submitting
            when (val result = authRepository.requestAccountDeletion(password, reason)) {
                is Resource.Success -> {
                    onSessionEnded()
                    try { onAccountDeleted(deletedUserId) } catch (e: Exception) { /* wipe is best effort; session is already gone */ }
                    _authState.value = AuthState.Idle
                    _deletionState.value = AccountDeletionState.Submitted(
                        result.data.message ?: "Account deletion requested."
                    )
                }
                is Resource.Error -> _deletionState.value =
                    if (result.message == AuthRepository.INCORRECT_PASSWORD_MESSAGE) AccountDeletionState.IncorrectPassword(result.message)
                    else AccountDeletionState.Failed(result.message)
                else -> {}
            }
        }
    }

    /** Set a new password (forced after an admin reset, or voluntary). Validation mirrors [PasswordRules]. */
    fun changePassword(current: String, new: String, confirm: String) {
        if (_changePasswordState.value is ChangePasswordState.Submitting) return
        PasswordRules.validate(current, new, confirm)?.let {
            _changePasswordState.value = ChangePasswordState.Error(it.message)
            return
        }
        viewModelScope.launch {
            _changePasswordState.value = ChangePasswordState.Submitting
            when (val result = authRepository.changePassword(current, new)) {
                is Resource.Success -> {
                    _changePasswordState.value = ChangePasswordState.Success
                    onPasswordChanged()
                }
                is Resource.Error -> _changePasswordState.value = ChangePasswordState.Error(result.message)
                else -> {}
            }
        }
    }

    fun resetChangePasswordState() {
        _changePasswordState.value = ChangePasswordState.Idle
    }

    fun isPasswordChangeRequired(): Boolean = tokenManager.isPasswordChangeRequired()

    fun resetDeletionState() {
        _deletionState.value = AccountDeletionState.Idle
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
