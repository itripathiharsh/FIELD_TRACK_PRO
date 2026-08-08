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
}

class AuthViewModel(
    private val tokenManager: TokenManager
) : ViewModel() {

    private val authRepository = AuthRepository(
        authApi = ApiClient.createAuthApi(tokenManager),
        tokenManager = tokenManager
    )

    private val _authState = MutableStateFlow<AuthState>(AuthState.Idle)
    val authState: StateFlow<AuthState> = _authState.asStateFlow()

    fun login(identity: String, pass: String) {
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

    fun checkAuthStatus(): Boolean = authRepository.isLoggedIn()
}
