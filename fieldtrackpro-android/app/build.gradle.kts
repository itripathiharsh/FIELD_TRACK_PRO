import java.util.Properties
import java.io.FileInputStream

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.fieldtrackpro.android"
    compileSdk = 35

    val localProperties = Properties()
    val localPropertiesFile = rootProject.file("local.properties")
    if (localPropertiesFile.exists()) {
        localProperties.load(FileInputStream(localPropertiesFile))
    }

    defaultConfig {
        applicationId = "com.fieldtrackpro.android"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        // MapLibre tile provider URL (environment-configurable)
        // Default: OpenStreetMap raster tiles via a public demo endpoint.
        // For production, set MAPLIBRE_TILE_URL in local.properties or gradle.properties.
        val maplibreTileUrl: String = localProperties.getProperty("MAPLIBRE_TILE_URL")?.toString()?.removeSurrounding("\"")
            ?: project.findProperty("MAPLIBRE_TILE_URL") as? String
            ?: "https://demotiles.maplibre.org/style.json"
        buildConfigField("String", "MAPLIBRE_TILE_URL", "\"$maplibreTileUrl\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            val prodBaseUrl = "https://fieldtrackpro-backend-s7hs.onrender.com/"
            buildConfigField("String", "BASE_URL", "\"$prodBaseUrl\"")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        debug {
            val debugBaseUrl: String = localProperties.getProperty("BASE_URL")?.toString()?.removeSurrounding("\"")
                ?: project.findProperty("BASE_URL") as? String
                ?: "http://10.0.2.2:8000/"
            buildConfigField("String", "BASE_URL", "\"$debugBaseUrl\"")
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

    // Firebase Cloud Messaging (FCM) for real push notifications
    implementation(libs.firebase.messaging)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.ui.test.junit4)
    debugImplementation(libs.androidx.ui.tooling)
    debugImplementation(libs.androidx.ui.test.manifest)
}

