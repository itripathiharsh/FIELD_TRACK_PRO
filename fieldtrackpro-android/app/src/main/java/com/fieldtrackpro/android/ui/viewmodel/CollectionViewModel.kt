package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.AccountSummaryDto
import com.fieldtrackpro.android.data.model.BrandAllocationInput
import com.fieldtrackpro.android.data.model.PaymentCreateRequest
import com.fieldtrackpro.android.data.model.PaymentDto
import com.fieldtrackpro.android.data.model.PaymentProofDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.CollectionRepository
import com.fieldtrackpro.android.data.repository.Resource
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.UUID

sealed class AccountState {
    object Loading : AccountState()
    data class Success(val account: AccountSummaryDto) : AccountState() {
        val summary: AccountSummaryDto get() = account
    }
    data class Error(val message: String) : AccountState()
}

sealed class CollectionState {
    object Idle : CollectionState()
    object Submitting : CollectionState()
    data class Success(val payment: PaymentDto) : CollectionState()
    data class Error(val message: String) : CollectionState()
}

/**
 * ViewModel for Collections / Payments with Brand-Wise Allocation support.
 */
class CollectionViewModel(
    private val tokenManager: TokenManager? = null,
    customRepository: CollectionRepository? = null
) : ViewModel() {

    private val repository: CollectionRepository = customRepository ?: CollectionRepository(
        ApiClient.createCollectionApi(tokenManager ?: throw IllegalArgumentException("TokenManager must not be null"))
    )

    private val _accountState = MutableStateFlow<AccountState>(AccountState.Loading)
    val accountState: StateFlow<AccountState> = _accountState.asStateFlow()

    private val _collectionState = MutableStateFlow<CollectionState>(CollectionState.Idle)
    val collectionState: StateFlow<CollectionState> = _collectionState.asStateFlow()

    // Key maintained per logical submit attempt to prevent double-charging on network retry
    private var currentSubmissionKey: String? = null

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
        allocations: List<BrandAllocationInput>? = null,
        onSubmitted: (PaymentDto) -> Unit = {}
    ) {
        // APP-RETRY-001: Synchronous submit locking
        if (_collectionState.value is CollectionState.Submitting) return
        _collectionState.value = CollectionState.Submitting

        if (amount.isBlank()) {
            _collectionState.value = CollectionState.Error("Invalid collection amount")
            return
        }

        // APP-CONTRACT-003: Maintain stable idempotency key for this logical operation across retries
        val idempotencyKey = currentSubmissionKey ?: UUID.randomUUID().toString().also { currentSubmissionKey = it }

        viewModelScope.launch {
            val req = PaymentCreateRequest(
                visitId = visitId,
                invoiceId = invoiceId,
                amount = amount,
                paymentMethod = paymentMethod,
                paymentDate = paymentDate,
                chequeNumber = chequeNumber,
                chequeBankName = chequeBankName,
                utrReference = utrReference,
                notes = notes,
                idempotencyKey = idempotencyKey,
                allocations = allocations
            )

            when (val res = repository.createPayment(req)) {
                is Resource.Success -> {
                    currentSubmissionKey = null
                    _collectionState.value = CollectionState.Success(res.data)
                    onSubmitted(res.data)
                }
                is Resource.Error -> {
                    // Preserve currentSubmissionKey so subsequent retry uses the EXACT same key
                    _collectionState.value = CollectionState.Error(res.message)
                }
                else -> {}
            }
        }
    }

    suspend fun uploadProof(paymentId: String, fileName: String, mimeType: String, fileBytes: ByteArray): Resource<PaymentProofDto> {
        return repository.uploadPaymentProof(paymentId, fileName, mimeType, fileBytes)
    }

    fun resetCollectionState() {
        currentSubmissionKey = null
        _collectionState.value = CollectionState.Idle
    }

    fun resetState() {
        currentSubmissionKey = null
        _accountState.value = AccountState.Loading
        _collectionState.value = CollectionState.Idle
    }
}
