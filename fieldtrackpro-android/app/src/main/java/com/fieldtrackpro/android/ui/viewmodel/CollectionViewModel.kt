package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.AccountSummaryDto
import com.fieldtrackpro.android.data.model.PaymentCreateRequest
import com.fieldtrackpro.android.data.model.PaymentDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.CollectionRepository
import com.fieldtrackpro.android.data.repository.Resource
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class AccountState {
    object Loading : AccountState()
    data class Success(val account: AccountSummaryDto) : AccountState()
    data class Error(val message: String) : AccountState()
}

sealed class CollectionState {
    object Idle : CollectionState()
    object Submitting : CollectionState()
    data class Success(val payment: PaymentDto) : CollectionState()
    data class Error(val message: String) : CollectionState()
}

class CollectionViewModel(tokenManager: TokenManager) : ViewModel() {

    private val repository = CollectionRepository(ApiClient.createCollectionApi(tokenManager))

    private val _accountState = MutableStateFlow<AccountState>(AccountState.Loading)
    val accountState: StateFlow<AccountState> = _accountState.asStateFlow()

    private val _collectionState = MutableStateFlow<CollectionState>(CollectionState.Idle)
    val collectionState: StateFlow<CollectionState> = _collectionState.asStateFlow()

    fun loadAccount(customerId: String) {
        viewModelScope.launch {
            _accountState.value = AccountState.Loading
            when (val res = repository.getAccountSummary(customerId)) {
                is Resource.Success -> _accountState.value = AccountState.Success(res.data)
                is Resource.Error -> _accountState.value = AccountState.Error(res.message)
                else -> {}
            }
        }
    }

    fun submitCollection(
        visitId: String,
        invoiceId: String?,
        amount: String,
        paymentMethod: String,
        paymentDate: String,
        chequeNumber: String? = null,
        chequeBankName: String? = null,
        utrReference: String? = null,
        notes: String? = null,
        onSubmitted: (PaymentDto) -> Unit = {},
    ) {
        viewModelScope.launch {
            _collectionState.value = CollectionState.Submitting
            val request = PaymentCreateRequest(
                visitId = visitId,
                invoiceId = invoiceId,
                amount = amount,
                paymentMethod = paymentMethod,
                paymentDate = paymentDate,
                chequeNumber = chequeNumber,
                chequeBankName = chequeBankName,
                utrReference = utrReference,
                notes = notes,
            )
            when (val res = repository.createPayment(request)) {
                is Resource.Success -> {
                    _collectionState.value = CollectionState.Success(res.data)
                    onSubmitted(res.data)
                }
                is Resource.Error -> _collectionState.value = CollectionState.Error(res.message)
                else -> {}
            }
        }
    }

    suspend fun uploadProof(paymentId: String, fileName: String, mimeType: String, fileBytes: ByteArray): Boolean {
        return when (repository.uploadPaymentProof(paymentId, fileName, mimeType, fileBytes)) {
            is Resource.Success -> true
            else -> false
        }
    }

    fun resetCollectionState() {
        _collectionState.value = CollectionState.Idle
    }
}
