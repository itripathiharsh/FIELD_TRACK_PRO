import java.text.SimpleDateFormat
import java.util.Date
import java.io.FileInputStream
import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

// Config lookup order: environment variable -> local.properties -> gradle property (-P / gradle.properties).
val localProperties = Properties().apply {
    val f = rootProject.file("local.properties")
    if (f.exists()) FileInputStream(f).use { load(it) }
}

// Non-secret production settings, committed: release.properties (backend, map style, privacy/deletion pages...).
val releaseProperties = Properties().apply {
    val f = rootProject.file("release.properties")
    if (f.exists()) FileInputStream(f).use { load(it) }
}

fun rawValue(name: String): String? =
    System.getenv(name)?.trim()?.removeSurrounding("\"")?.takeIf { it.isNotBlank() }
        ?: localProperties.getProperty(name)?.trim()?.removeSurrounding("\"")?.takeIf { it.isNotBlank() }
        ?: (project.findProperty(name) as? String)?.trim()?.removeSurrounding("\"")?.takeIf { it.isNotBlank() }

// Secret signing settings live OUTSIDE the repository: FIELDTRACK_SIGNING_PROPERTIES (env var, local.properties or -P)
// points to a properties file holding RELEASE_STORE_FILE / RELEASE_STORE_PASSWORD / RELEASE_KEY_ALIAS /
// RELEASE_KEY_PASSWORD. Never commit that file or the keystore.
val signingProperties = Properties().apply {
    val path = rawValue("FIELDTRACK_SIGNING_PROPERTIES")
    if (path != null) {
        val f = file(path)
        if (f.exists()) FileInputStream(f).use { load(it) }
    }
}

// Lookup order: env var -> local.properties -> -P / gradle.properties -> external signing file -> release.properties.
fun configValue(name: String): String? =
    rawValue(name)
        ?: signingProperties.getProperty(name)?.trim()?.takeIf { it.isNotBlank() }
        ?: releaseProperties.getProperty(name)?.trim()?.takeIf { it.isNotBlank() }

fun buildConfigString(value: String): String =
    "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""

// Single source of truth for the app version (Play: versionCode must strictly increase per upload).
// 4 / 1.1.0: offline payments, outlet-proof capture/queue, queue schema + session/auth hardening.
// 6 / 1.3.0: premium UI (design system v2, new mark), workday GPS/permission fixes, release URL guard. (5 / 1.2.0 was the
// landing-page debug build.)
val appVersionCode = 6
val appVersionName = "1.3.0"

val releaseStoreFile = configValue("RELEASE_STORE_FILE")
val releaseStorePassword = configValue("RELEASE_STORE_PASSWORD")
val releaseKeyAlias = configValue("RELEASE_KEY_ALIAS")
val releaseKeyPassword = configValue("RELEASE_KEY_PASSWORD")
val releaseSigningComplete = releaseStoreFile != null && file(releaseStoreFile).exists() &&
    releaseStorePassword != null && releaseKeyAlias != null && releaseKeyPassword != null

// Release-only required configuration (no silent fallbacks). Debug builds may leave these unset.
val maplibreTileUrlValue = configValue("MAPLIBRE_TILE_URL")
val privacyPolicyUrlValue = configValue("PRIVACY_POLICY_URL")
val deletionUrlValue = configValue("DELETION_URL")
// Release backend. Production is the OVH host; RELEASE_BASE_URL may override it (env var, local.properties or -P), but
// the release guard below refuses anything that is not https, is a local/private address, or is the retired Render host.
val productionBaseUrl = "https://51-79-158-138.sslip.io/"
val releaseBaseUrlValue: String = (configValue("RELEASE_BASE_URL") ?: productionBaseUrl).let { if (it.endsWith("/")) it else "$it/" }
val blockedReleaseHosts = listOf("onrender.com", "fieldtrackpro-backend-s7hs", "localhost", "127.0.0.1", "10.0.2.2", "192.168.", "10.0.0.")
// In-app updates: static release manifest + versioned APKs on the existing free Vercel site (see
// design-review/IN_APP_UPDATES.md). UPDATE_MANIFEST_URL may override (https + allowed host only); blank disables.
val defaultUpdateManifestUrl = "https://fieldtrack-pro-rosy.vercel.app/downloads/app-update.json"
val updateManifestUrlValue: String = configValue("UPDATE_MANIFEST_URL") ?: defaultUpdateManifestUrl
val updateAllowedHostsValue: String = configValue("UPDATE_ALLOWED_HOSTS") ?: "fieldtrack-pro-rosy.vercel.app"
val allowNoFcm = configValue("ALLOW_NO_FCM")?.equals("true", ignoreCase = true) == true
val hasGoogleServicesJson = file("google-services.json").exists()

android {
    namespace = "com.fieldtrackpro.android"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.fieldtrackpro.android"
        minSdk = 26
        targetSdk = 35
        versionCode = appVersionCode
        versionName = appVersionName

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // Web URL where an account (and its data) deletion can be requested without the app (Play requirement).
        buildConfigField("String", "DELETION_URL", buildConfigString(deletionUrlValue ?: ""))
        buildConfigField("String", "BUILD_STAMP", "\"" + SimpleDateFormat("yyyy-MM-dd HH:mm").format(Date()) + "\"")
        buildConfigField("String", "UPDATE_MANIFEST_URL", buildConfigString(updateManifestUrlValue))
        buildConfigField("String", "UPDATE_ALLOWED_HOSTS", buildConfigString(updateAllowedHostsValue))
    }

    signingConfigs {
        getByName("debug") {
            storeFile = file(System.getProperty("user.home") + "/.android/debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
            enableV1Signing = true
            enableV2Signing = true
            enableV3Signing = true
            enableV4Signing = false
        }
        create("release") {
            // Populated only when all RELEASE_* values are present. There is deliberately NO fallback
            // to the debug keystore: release tasks fail with a clear message instead (see taskGraph check below).
            if (releaseSigningComplete) {
                storeFile = file(releaseStoreFile!!)
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
                enableV1Signing = true
                enableV2Signing = true
                enableV3Signing = true
                enableV4Signing = false
            }
        }
    }

    buildTypes {
        release {
            if (releaseSigningComplete) {
                signingConfig = signingConfigs.getByName("release")
            }
            isDebuggable = false
            isMinifyEnabled = true
            isShrinkResources = true
            buildConfigField("String", "BASE_URL", buildConfigString(releaseBaseUrlValue))
            // Required for release; the build fails (see taskGraph check below) if these are missing.
            buildConfigField("String", "MAPLIBRE_TILE_URL", buildConfigString(maplibreTileUrlValue ?: ""))
            buildConfigField("String", "PRIVACY_POLICY_URL", buildConfigString(privacyPolicyUrlValue ?: ""))
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            signingConfig = signingConfigs.getByName("debug")
            val debugBaseUrl: String = configValue("BASE_URL") ?: "http://10.0.2.2:8000/"
            buildConfigField("String", "BASE_URL", buildConfigString(debugBaseUrl))
            // Debug may use the MapLibre demo style; set MAPLIBRE_TILE_URL to override.
            buildConfigField(
                "String", "MAPLIBRE_TILE_URL",
                buildConfigString(maplibreTileUrlValue ?: "https://demotiles.maplibre.org/style.json")
            )
            // Optional in debug: the Privacy Policy action shows "not configured" when blank.
            buildConfigField("String", "PRIVACY_POLICY_URL", buildConfigString(privacyPolicyUrlValue ?: ""))
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
        // Needed by the Robolectric screenshot test (design review images; skipped unless -PcaptureScreens=true).
        unitTests.isIncludeAndroidResources = true
        unitTests.all {
            it.systemProperty("captureScreens", (project.findProperty("captureScreens") as? String) ?: "false")
            it.systemProperty("screensDir", rootProject.file("design-review/screens").absolutePath)
            // Opt-in release artifact check (ReleaseArtifactVerificationTest).
            it.systemProperty("releaseManifest", (project.findProperty("releaseManifest") as? String) ?: "")
            it.systemProperty("releaseApk", (project.findProperty("releaseApk") as? String) ?: "")
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.ui.text.google.fonts)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.material)
    implementation(libs.androidx.material.icons.extended)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)

    // Networking Foundation
    implementation(libs.retrofit)
    implementation(libs.retrofit.converter.gson)
    implementation(libs.okhttp.logging)

    // FT-027: Keystore-backed encrypted credential storage.
    implementation(libs.androidx.security.crypto)

    // WorkManager for resilient uploads (Phase 6 Section 7)
    implementation(libs.androidx.work.runtime.ktx)

    // MapLibre SDK (Phase 4 Section 1 - MapLibre decision)
    implementation(libs.maplibre.sdk)
    implementation(libs.maplibre.annotations)

    // Google Play Services Location for Geofencing (Phase 4 Section 3)
    implementation(libs.gms.play.services.location)

    // CameraX: in-app live capture for outlet proofs (no gallery picker in that flow)
    implementation(libs.androidx.camera.core)
    implementation(libs.androidx.camera.camera2)
    implementation(libs.androidx.camera.lifecycle)
    implementation(libs.androidx.camera.view)

    // Firebase Cloud Messaging (FCM) for real push notifications
    implementation(libs.firebase.messaging)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    // Test-only: JVM rendering of Compose screens for design-review screenshots.
    testImplementation(libs.robolectric)
    testImplementation(platform(libs.androidx.compose.bom))
    testImplementation(libs.androidx.ui.test.junit4)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.ui.test.junit4)
    debugImplementation(libs.androidx.ui.tooling)
    debugImplementation(libs.androidx.ui.test.manifest)
}

if (hasGoogleServicesJson) {
    apply(plugin = "com.google.gms.google-services")
} else {
    logger.warn(
        "WARNING: app/google-services.json is missing. FCM push notifications are DISABLED in this build " +
            "(the app will run, but will not receive pushes). Download google-services.json from the " +
            "Firebase console (package com.fieldtrackpro.android) and place it in the app/ directory."
    )
}

// ---------------------------------------------------------------------------------------------
// Release guard rails. Evaluated only when a release assemble/bundle/package task is actually in
// the task graph, so debug builds and unit tests are unaffected.
// ---------------------------------------------------------------------------------------------
gradle.taskGraph.whenReady {
    val releaseTaskRegex = Regex("^(assemble|bundle|package|sign|validateSigning|publish)\\w*Release\\w*$")
    val releaseRequested = allTasks.any { it.project == project && releaseTaskRegex.matches(it.name) }
    if (releaseRequested) {
        val problems = mutableListOf<String>()
        if (releaseSigningComplete && (releaseKeyAlias == "androiddebugkey" || file(releaseStoreFile!!).name == "debug.keystore")) {
            problems += "Release builds must not be signed with the Android debug key."
        }
        if (!releaseSigningComplete) {
            problems += "Release signing is not configured. Set ALL of: RELEASE_STORE_FILE (path to an existing keystore), " +
                "RELEASE_STORE_PASSWORD, RELEASE_KEY_ALIAS, RELEASE_KEY_PASSWORD " +
                "(environment variables, local.properties, or -P gradle properties). " +
                "Release builds never fall back to the debug keystore."
        }
        if (maplibreTileUrlValue == null) {
            problems += "MAPLIBRE_TILE_URL is required for release builds (env var, local.properties or -P property); " +
                "the public demo tile server must not be used in production."
        }
        if (privacyPolicyUrlValue == null) {
            problems += "PRIVACY_POLICY_URL is required for release builds (env var, local.properties or -P property); " +
                "Google Play requires an in-app privacy policy link."
        }
        if (deletionUrlValue == null) {
            problems += "DELETION_URL is required for release builds (env var, local.properties or -P property); " +
                "Google Play requires a web link where users can request account and data deletion."
        }
        // Both public links must be https (Play policy / cleartext is blocked by the manifest anyway).
        fun isHttpsUrl(v: String) = v.startsWith("https://", ignoreCase = true) && v.length > "https://".length &&
            !v.substring("https://".length).startsWith("/")
        if (privacyPolicyUrlValue != null && !isHttpsUrl(privacyPolicyUrlValue)) {
            problems += "PRIVACY_POLICY_URL must be an https:// URL."
        }
        if (deletionUrlValue != null && !isHttpsUrl(deletionUrlValue)) {
            problems += "DELETION_URL must be an https:// URL."
        }
        if (!releaseBaseUrlValue.startsWith("https://", ignoreCase = true)) {
            problems += "RELEASE_BASE_URL must be an https:// URL (got a non-https value)."
        }
        blockedReleaseHosts.firstOrNull { releaseBaseUrlValue.contains(it, ignoreCase = true) }?.let {
            problems += "RELEASE_BASE_URL points at a blocked host ('$it'). Release builds must use the production backend " +
                "($productionBaseUrl); the old Render host and local addresses are refused."
        }
        if (updateManifestUrlValue.isNotBlank()) {
            val manifestHost = Regex("^https://([^/:?#]+)", RegexOption.IGNORE_CASE).find(updateManifestUrlValue)?.groupValues?.get(1)
            val hosts = updateAllowedHostsValue.split(',').map { it.trim().lowercase() }.filter { it.isNotEmpty() }
            if (manifestHost == null || manifestHost.lowercase() !in hosts) {
                problems += "UPDATE_MANIFEST_URL must be an https:// URL on one of UPDATE_ALLOWED_HOSTS ($hosts)."
            }
        }
        if (!hasGoogleServicesJson && !allowNoFcm) {
            problems += "app/google-services.json is missing, so push notifications would not work. Download it from " +
                "the Firebase console and place it in app/, or explicitly opt out with ALLOW_NO_FCM=true."
        }
        if (problems.isNotEmpty()) {
            throw GradleException(
                "Release build configuration is incomplete:\n" +
                    problems.joinToString("\n") { " - $it" }
            )
        }
    }
}
