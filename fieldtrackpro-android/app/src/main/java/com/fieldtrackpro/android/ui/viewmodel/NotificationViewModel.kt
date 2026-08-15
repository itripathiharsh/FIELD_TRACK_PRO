package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.NotificationDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.NotificationRepository
import com.fieldtrackpro.android.data.repository.Resource
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class NotificationState {
    object Idle : NotificationState()
    object Loading : NotificationState()
    data class Success(val items: List<NotificationDto>) : NotificationState()
    data class Error(val message: String) : NotificationState()
}

class NotificationViewModel(tokenManager: TokenManager) : ViewModel() {

    private val repository = NotificationRepository(ApiClient.createNotificationApi(tokenManager))

    private val _state = MutableStateFlow<NotificationState>(NotificationState.Idle)
    val state: StateFlow<NotificationState> = _state.asStateFlow()

    fun loadNotifications() {
        viewModelScope.launch {
            _state.value = NotificationState.Loading
            when (val res = repository.getMyNotifications()) {
                is Resource.Success -> _state.value = NotificationState.Success(res.data)
                is Resource.Error -> _state.value = NotificationState.Error(res.message)
                else -> {}
            }
        }
    }

    fun markAsRead(notificationId: String) {
        viewModelScope.launch {
            repository.markAsRead(notificationId)
            // Reload notifications after marking as read
            loadNotifications()
        }
    }
}
