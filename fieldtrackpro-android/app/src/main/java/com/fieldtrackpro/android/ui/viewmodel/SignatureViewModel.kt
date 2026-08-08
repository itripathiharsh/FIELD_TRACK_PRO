package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.SignatureDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.data.repository.SignatureRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class SignatureState {
    object Idle : SignatureState()
    object Loading : SignatureState()
    data class ListSuccess(val items: List<SignatureDto>) : SignatureState()
    data class UploadSuccess(val signature: SignatureDto) : SignatureState()
    data class Error(val message: String) : SignatureState()
}

class SignatureViewModel(tokenManager: TokenManager) : ViewModel() {

    private val repository = SignatureRepository(ApiClient.createSignatureApi(tokenManager))

    private val _signatureState = MutableStateFlow<SignatureState>(SignatureState.Idle)
    val signatureState: StateFlow<SignatureState> = _signatureState.asStateFlow()

    fun loadVisitSignatures(visitId: String) {
        viewModelScope.launch {
            _signatureState.value = SignatureState.Loading
            when (val res = repository.getVisitSignatures(visitId)) {
                is Resource.Success -> _signatureState.value = SignatureState.ListSuccess(res.data)
                is Resource.Error -> _signatureState.value = SignatureState.Error(res.message)
                else -> {}
            }
        }
    }

    fun uploadSignature(visitId: String, signatureType: String, signatureImageBase64: String) {
        viewModelScope.launch {
            _signatureState.value = SignatureState.Loading
            when (val res = repository.uploadSignature(visitId, signatureType, signatureImageBase64)) {
                is Resource.Success -> {
                    _signatureState.value = SignatureState.UploadSuccess(res.data)
                    loadVisitSignatures(visitId)
                }
                is Resource.Error -> _signatureState.value = SignatureState.Error(res.message)
                else -> {}
            }
        }
    }
}
