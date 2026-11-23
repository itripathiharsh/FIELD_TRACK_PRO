package com.fieldtrackpro.android.screens

import android.graphics.Bitmap
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import com.fieldtrackpro.android.data.local.OutletProofPayload
import com.fieldtrackpro.android.data.model.OutletProofRead
import com.fieldtrackpro.android.ui.screens.proof.OutletProofCard
import com.fieldtrackpro.android.ui.theme.FieldTrackProTheme
import com.fieldtrackpro.android.ui.viewmodel.ProofUi
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File
import java.io.FileOutputStream

/** The captured storefront photo must be visible in every capture state, including after the upload succeeded. */
@OptIn(ExperimentalTestApi::class)
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(application = android.app.Application::class)
class OutletProofPhotoPreviewTest {
    @get:Rule val rule = createAndroidComposeRule<androidx.activity.ComponentActivity>()

    private fun jpeg(): File {
        val f = File.createTempFile("proof_preview_", ".jpg")
        val bmp = Bitmap.createBitmap(400, 300, Bitmap.Config.ARGB_8888).apply { eraseColor(android.graphics.Color.rgb(180, 120, 60)) }
        FileOutputStream(f).use { bmp.compress(Bitmap.CompressFormat.JPEG, 90, it) }
        return f
    }

    private fun payload(path: String?) = OutletProofPayload(
        idempotencyKey = "k", customerId = "c1", photoPath = path, accuracyM = 14.78,
        capturedAtEpochMs = System.currentTimeMillis()
    )

    private fun show(ui: ProofUi) {
        rule.setContent { FieldTrackProTheme { OutletProofCard(ui = ui, onCapture = {}, onRetry = {}, onRetake = {}) } }
    }

    @Test fun photoIsShownWhileUploading() {
        val f = jpeg()
        show(ProofUi.Uploading(payload(f.absolutePath)))
        rule.waitUntilExactlyOneExists(androidx.compose.ui.test.hasContentDescription("Outlet photo"), 5_000)
        rule.onNodeWithContentDescription("Outlet photo").assertIsDisplayed()
    }

    @Test fun photoStaysVisibleAfterUploadSucceeded() {
        val f = jpeg()
        show(ProofUi.Uploaded(payload(f.absolutePath), OutletProofRead(id = "p", status = "APPROVED")))
        rule.waitUntilExactlyOneExists(androidx.compose.ui.test.hasContentDescription("Outlet photo"), 5_000)
        rule.onNodeWithContentDescription("Outlet photo").assertIsDisplayed()
    }

    @Test fun photoIsShownWhenUploadFailedAndRetryIsPossible() {
        val f = jpeg()
        show(ProofUi.Failed("No internet", payload(f.absolutePath), canRetry = true, retakeRequired = false))
        rule.waitUntilExactlyOneExists(androidx.compose.ui.test.hasContentDescription("Outlet photo"), 5_000)
        rule.onNodeWithContentDescription("Outlet photo").assertIsDisplayed()
    }
}
