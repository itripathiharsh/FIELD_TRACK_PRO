package com.fieldtrackpro.android.update

import android.content.Context
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.os.Build
import java.io.File
import java.security.MessageDigest

/**
 * Checks a downloaded APK BEFORE it is handed to the system installer:
 *  - same package name as this app,
 *  - versionCode equal to the manifest and strictly higher than the installed one (never a downgrade),
 *  - signed with exactly the same certificate(s) as the installed app.
 *
 * The certificate check is what makes a tampered APK useless even if the hosting were compromised: an attacker
 * can change the file and the manifest's SHA-256, but cannot sign with our key. (Android would also refuse such an
 * update; checking here gives a clear message instead of a generic "App not installed".)
 */
object ApkVerifier {

    sealed class Result {
        object Ok : Result()
        data class Rejected(val message: String) : Result()
    }

    /** Pure comparison used by [verify]; unit tested. */
    fun compare(
        expectedPackage: String,
        installedVersionCode: Long,
        manifestVersionCode: Long,
        installedCertDigests: Set<String>,
        archivePackage: String?,
        archiveVersionCode: Long?,
        archiveCertDigests: Set<String>,
        /** Past certificates of the downloaded APK (Android key rotation); empty when unknown. */
        archiveCertHistory: Set<String> = emptySet()
    ): Result = when {
        archivePackage == null || archiveVersionCode == null -> Result.Rejected("The downloaded file is not a valid app package.")
        archivePackage != expectedPackage -> Result.Rejected("The downloaded file is a different app.")
        archiveVersionCode != manifestVersionCode -> Result.Rejected("The downloaded version does not match the release information.")
        archiveVersionCode <= installedVersionCode -> Result.Rejected("The downloaded file is not newer than the installed app.")
        installedCertDigests.isEmpty() || archiveCertDigests.isEmpty() -> Result.Rejected("Could not read the app signature.")
        archiveCertDigests != installedCertDigests && !archiveCertHistory.containsAll(installedCertDigests) ->
            Result.Rejected("This update is not signed with the FieldTrack Pro release key, so it was not installed.")
        else -> Result.Ok
    }

    fun verify(context: Context, apk: File, manifestVersionCode: Long): Result {
        val pm = context.packageManager
        val installed = installedInfo(context)
        val archive = archiveInfo(pm, apk)
        return compare(
            expectedPackage = context.packageName,
            installedVersionCode = installed?.let { versionCodeOf(it) } ?: Long.MAX_VALUE,
            manifestVersionCode = manifestVersionCode,
            installedCertDigests = installed?.let { certDigests(it) }.orEmpty(),
            archivePackage = archive?.packageName,
            archiveVersionCode = archive?.let { versionCodeOf(it) },
            archiveCertDigests = archive?.let { certDigests(it) }.orEmpty(),
            archiveCertHistory = archive?.let { certDigests(it, history = true) }.orEmpty()
        )
    }

    fun installedVersionCode(context: Context): Long =
        installedInfo(context)?.let { versionCodeOf(it) } ?: 0L

    @Suppress("DEPRECATION")
    private fun installedInfo(context: Context): PackageInfo? = try {
        val flags = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        context.packageManager.getPackageInfo(context.packageName, flags)
    } catch (e: Exception) {
        null
    }

    @Suppress("DEPRECATION")
    private fun archiveInfo(pm: PackageManager, apk: File): PackageInfo? = try {
        val flags = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        pm.getPackageArchiveInfo(apk.absolutePath, flags)
    } catch (e: Exception) {
        null
    }

    @Suppress("DEPRECATION")
    private fun versionCodeOf(info: PackageInfo): Long =
        if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()

    @Suppress("DEPRECATION")
    private fun certDigests(info: PackageInfo, history: Boolean = false): Set<String> {
        val sigs = if (Build.VERSION.SDK_INT >= 28) {
            val si = info.signingInfo ?: return emptySet()
            when {
                si.hasMultipleSigners() -> si.apkContentsSigners
                history -> si.signingCertificateHistory
                else -> si.apkContentsSigners // current signer(s) only, no past certificates
            }
        } else {
            info.signatures
        } ?: return emptySet()
        return sigs.map { sig ->
            MessageDigest.getInstance("SHA-256").digest(sig.toByteArray()).joinToString("") { "%02x".format(it) }
        }.toSet()
    }
}
