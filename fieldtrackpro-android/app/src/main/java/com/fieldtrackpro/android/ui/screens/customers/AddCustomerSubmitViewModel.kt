package com.fieldtrackpro.android.ui.screens.customers

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.model.CustomerProspectCreate
import com.fieldtrackpro.android.data.repository.Resource
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class AddCustomerSubmitState {
    object Idle : AddCustomerSubmitState()
    object Submitting : AddCustomerSubmitState()
    data class Created(val customer: CustomerDto) : AddCustomerSubmitState()
    data class Failed(val message: String, val code: Int?, val errorCode: String?) : AddCustomerSubmitState()
}

/**
 * Runs the "create prospect" request outside the composition.
 *
 * It used to run in a rememberCoroutineScope with a plain `remember` busy flag: rotating mid-request cancelled the
 * call on the client (the server may still have created the outlet) and re-enabled the button, so a second tap could
 * create a duplicate. A ViewModel survives rotation, and a second submit while one is in flight is ignored.
 */
class AddCustomerSubmitViewModel(
    private val create: suspend (CustomerProspectCreate) -> Resource<CustomerDto>
) : ViewModel() {

    private val _state = MutableStateFlow<AddCustomerSubmitState>(AddCustomerSubmitState.Idle)
    val state: StateFlow<AddCustomerSubmitState> = _state.asStateFlow()

    /** Returns false when a submission is already running. */
    fun submit(payload: CustomerProspectCreate): Boolean {
        if (_state.value is AddCustomerSubmitState.Submitting) return false
        _state.value = AddCustomerSubmitState.Submitting
        viewModelScope.launch {
            _state.value = when (val res = create(payload)) {
                is Resource.Success -> AddCustomerSubmitState.Created(res.data)
                is Resource.Error -> AddCustomerSubmitState.Failed(res.message, res.code, res.errorCode)
                else -> AddCustomerSubmitState.Idle
            }
        }
        return true
    }

    /** Called once the UI has handled a Created/Failed result. */
    fun acknowledge() {
        if (_state.value !is AddCustomerSubmitState.Submitting) _state.value = AddCustomerSubmitState.Idle
    }
}
