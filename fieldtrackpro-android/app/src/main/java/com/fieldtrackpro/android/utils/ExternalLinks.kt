package com.fieldtrackpro.android.utils

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import com.fieldtrackpro.android.BuildConfig

/** Opens the configured privacy policy (BuildConfig.PRIVACY_POLICY_URL) in the browser. */
object ExternalLinks {

    /** Only http(s) URLs are ever opened. */
    fun isOpenableWebUrl(url: String?): Boolean {
        val trimmed = url?.trim().orEmpty()
        return trimmed.startsWith("https://", ignoreCase = true) || trimmed.startsWith("http://", ignoreCase = true)
    }

    fun openPrivacyPolicy(context: Context) = openUrl(context, BuildConfig.PRIVACY_POLICY_URL, "Privacy policy")

    fun openDeletionPage(context: Context) = openUrl(context, BuildConfig.DELETION_URL, "Account deletion page")

    private fun openUrl(context: Context, url: String, label: String) {
        if (!isOpenableWebUrl(url)) {
            Toast.makeText(context, "$label link is not configured for this build.", Toast.LENGTH_LONG).show()
            return
        }
        try {
            context.startActivity(
                Intent(Intent.ACTION_VIEW, Uri.parse(url.trim())).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(context, "No browser available to open the link.", Toast.LENGTH_LONG).show()
        }
    }
}
