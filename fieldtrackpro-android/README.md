# FieldTrack Pro Android (`fieldtrackpro-android`)

Native Kotlin / Jetpack Compose Android application for FieldTrack Pro.

## Stack

| Concern | Dependency |
|---|---|
| Language | Kotlin |
| UI Framework | Jetpack Compose + Material3 |
| Networking | Retrofit 2 + OkHttp 3 |
| Build System | Gradle 8 (Kotlin DSL) + Version Catalog |

## Requirements

- Android Studio (Ladybug or newer)
- Android SDK API 35 (compileSdk), minSdk 26
- JDK 17+
- Physical device or AVD with API 26+

## Package

```
com.fieldtrackpro.android
```

## Build

1. Open `fieldtrackpro-android/` in Android Studio.
2. Allow Gradle sync to complete.
3. Run the `app` configuration on an emulator or connected device.

> **Note:** The Android app requires a physical device or AVD for runtime verification. The backend base URL for the Android emulator is `http://10.0.2.2:8000/api/v1` (maps to host `localhost`).
