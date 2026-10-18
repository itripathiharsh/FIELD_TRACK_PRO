package com.fieldtrackpro.android.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.repository.PaymentSubmitOutcome
import com.fieldtrackpro.android.data.repository.PaymentSubmitter
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
    /** Not an error: the payment is stored on the device and syncs automatically when online. */
    data class SavedOffline(val amount: String, val message: String = SAVED_OFFLINE_MESSAGE) : CollectionState()
    data class Error(val message: String) : CollectionState()

    companion object {
        const val SAVED_OFFLINE_MESSAGE = "Saved offline — will sync automatically"
    }
}

/**
 * ViewModel for Collections / Payments with Brand-Wise Allocation support.
 */
class CollectionViewModel(
    private val tokenManager: TokenManager? = null,
    customRepository: CollectionRepository? = null,
    offlineQueueManager: OfflineQueueManager? = null,
    customSubmitter: PaymentSubmitter? = null
) : ViewModel() {

    private val repository: CollectionRepository = customRepository ?: CollectionRepository(
        ApiClient.createCollectionApi(tokenManager ?: throw IllegalArgumentException("TokenManager must not be null"))
    )

    private val submitter: PaymentSubmitter = customSubmitter ?: PaymentSubmitter(repository, offlineQueueManager)

    private val _accountState = MutableStateFlow<AccountState>(AccountState.Loading)
    val accountState: StateFlow<AccountState> = _accountState.asStateFlow()

    private val _collectionState = MutableStateFlow<CollectionState>(CollectionState.Idle)
    val collectionState: StateFlow<CollectionState> = _collectionState.asStateFlow()

    // Key maintained per logical submit attempt to prevent double-charging on network retry
    private var currentSubmissionKey: String? = null

    // Bumped by every reset. A submission that finishes AFTER the user left the form (system Back mid-flight) must
    // not write its result - or call onSubmitted(), which pops a screen - into whatever form is open by then.
    // The payment itself is unaffected: it was already created/queued under its own idempotency key.
    @Volatile private var formGeneration = 0

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
        customerId: String? = null,
        outletName: String? = null,
        proofPaths: List<String> = emptyList(),
        onSubmitted: (PaymentDto) -> Unit = {}
    ) {
        // APP-RETRY-001: Synchronous submit locking (also blocks re-submitting an already saved-offline form)
        if (_collectionState.value is CollectionState.Submitting ||
            _collectionState.value is CollectionState.SavedOffline) return

        if (amount.isBlank()) {
            _collectionState.value = CollectionState.Error("Invalid collection amount")
            return
        }
        _collectionState.value = CollectionState.Submitting

        // Generated ONCE per form submission; reused by every retry, online or from the offline queue.
        val idempotencyKey = currentSubmissionKey ?: UUID.randomUUID().toString().also { currentSubmissionKey = it }
        val generation = formGeneration

        viewModelScope.launch {
            val outcome = submitter.submit(
                userId = tokenManager?.getUserId(),
                visitId = visitId,
                customerId = customerId,
                outletName = outletName,
                idempotencyKey = idempotencyKey,
                invoiceId = invoiceId,
                amount = amount,
                paymentMethod = paymentMethod,
                paymentDate = paymentDate,
                chequeNumber = chequeNumber,
                chequeBankName = chequeBankName,
                utrReference = utrReference,
                notes = notes,
                allocations = allocations,
                proofPaths = proofPaths
            )
            if (generation != formGeneration) return@launch // the form was left meanwhile: result is stale
            when (outcome) {
                is PaymentSubmitOutcome.Created -> {
                    currentSubmissionKey = null
                    _collectionState.value = CollectionState.Success(outcome.payment)
                    onSubmitted(outcome.payment)
                }
                is PaymentSubmitOutcome.CreatedProofsQueued -> {
                    currentSubmissionKey = null
                    _collectionState.value = CollectionState.Success(outcome.payment)
                    onSubmitted(outcome.payment)
                }
                is PaymentSubmitOutcome.SavedOffline -> {
                    // The queue entry now owns the key; a brand-new submission gets a new key.
                    currentSubmissionKey = null
                    _collectionState.value = CollectionState.SavedOffline(amount)
                }
                is PaymentSubmitOutcome.Rejected -> {
                    // Preserve currentSubmissionKey so a retry after fixing the form uses the EXACT same key
                    _collectionState.value = CollectionState.Error(outcome.message)
                }
            }
        }
    }

    suspend fun uploadProof(paymentId: String, fileName: String, mimeType: String, fileBytes: ByteArray): Resource<PaymentProofDto> {
        return repository.uploadPaymentProof(paymentId, fileName, mimeType, fileBytes)
    }

    fun resetCollectionState() {
        formGeneration++
        currentSubmissionKey = null
        _collectionState.value = CollectionState.Idle
    }

    fun resetState() {
        formGeneration++
        currentSubmissionKey = null
        _accountState.value = AccountState.Loading
        _collectionState.value = CollectionState.Idle
    }
}
