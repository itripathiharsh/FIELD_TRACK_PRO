package com.fieldtrackpro.android.ui.screens.proof

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import com.fieldtrackpro.android.ui.theme.FieldTrackProTheme
import com.google.gson.Gson

/**
 * Hosts the outlet-proof camera in its OWN full-screen window.
 *
 * Why an Activity and not a Compose Dialog: a dialog is a separate floating window. On many devices it is laid out
 * between the system bars, and the insets that Compose reads inside it are not the real ones, so the shutter could
 * end up under the gesture/navigation bar. An Activity window with enableEdgeToEdge() gets the real system-bar
 * insets (the same mechanism every other screen of the app relies on), and the layout then simply respects them.
 */
class OutletProofCaptureActivity : ComponentActivity() {
    private val vm by viewModels<OutletProofCaptureViewModel>()

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(Color.TRANSPARENT)
        )
        super.onCreate(savedInstanceState)
        window.setBackgroundDrawable(ColorDrawable(Color.BLACK))
        if (savedInstanceState == null) vm.reset() // a fresh capture session; rotation keeps the existing one

        val customerId = intent.getStringExtra(EXTRA_CUSTOMER_ID)
        val outletName = intent.getStringExtra(EXTRA_OUTLET_NAME)
        setContent {
            FieldTrackProTheme {
                OutletProofCaptureScreen(
                    vm = vm,
                    customerId = customerId,
                    outletName = outletName,
                    onCancel = {
                        setResult(Activity.RESULT_CANCELED)
                        finish()
                    },
                    onConfirmed = { payload ->
                        setResult(Activity.RESULT_OK, Intent().putExtra(EXTRA_PAYLOAD, Gson().toJson(payload)))
                        finish()
                    }
                )
            }
        }
    }

    companion object {
        const val EXTRA_CUSTOMER_ID = "customer_id"
        const val EXTRA_OUTLET_NAME = "outlet_name"
        const val EXTRA_PAYLOAD = "payload_json"
    }
}
