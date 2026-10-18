# ProGuard / R8 rules for FieldTrack Pro (release builds: minify + shrinkResources enabled).
# The default `proguard-android-optimize.txt` rules are applied in addition to this file.

# ---------------------------------------------------------------------------------------------
# Attributes needed for reflection-based JSON (Gson) and Retrofit generics / annotations
# ---------------------------------------------------------------------------------------------
-keepattributes Signature
-keepattributes *Annotation*
-keepattributes InnerClasses,EnclosingMethod
-keepattributes RuntimeVisibleAnnotations,RuntimeVisibleParameterAnnotations,AnnotationDefault
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile

# ---------------------------------------------------------------------------------------------
# Gson-serialized models. These are (de)serialized reflectively, so field names and the
# no-arg/Unsafe construction path must survive obfuscation. @SerializedName is also honoured.
# ---------------------------------------------------------------------------------------------
# Network DTOs (request/response bodies)
-keep class com.fieldtrackpro.android.data.model.** { *; }
# Persisted offline queue / conflicts (stored as JSON in EncryptedSharedPreferences)
-keep class com.fieldtrackpro.android.data.local.PendingAction { *; }
-keep class com.fieldtrackpro.android.data.local.PaymentQueuePayload { *; }
-keep class com.fieldtrackpro.android.data.local.OutletProofPayload { *; }
-keep class com.fieldtrackpro.android.data.local.SyncConflict { *; }
-keep class com.fieldtrackpro.android.data.local.ConflictType { *; }
# Error DTO parsed from error bodies
-keep class com.fieldtrackpro.android.data.remote.ApiError { *; }

# Gson internals: keep fields annotated with @SerializedName on any class (belt and braces)
-keepclassmembers,allowobfuscation class * {
    @com.google.gson.annotations.SerializedName <fields>;
}
-keep class com.google.gson.reflect.TypeToken { *; }
-keep class * extends com.google.gson.reflect.TypeToken
-keep class * implements com.google.gson.TypeAdapterFactory
-keep class * implements com.google.gson.JsonSerializer
-keep class * implements com.google.gson.JsonDeserializer
-dontwarn sun.misc.Unsafe

# ---------------------------------------------------------------------------------------------
# Retrofit: API interfaces (methods carry the HTTP annotations, generics carry the response types)
# ---------------------------------------------------------------------------------------------
-keep interface com.fieldtrackpro.android.data.api.** { *; }
-keepclassmembers,allowshrinking,allowobfuscation interface * {
    @retrofit2.http.* <methods>;
}
-if interface * { @retrofit2.http.* <methods>; }
-keep,allowobfuscation interface <1>
# Keep generic signatures of Retrofit Response / suspend continuation return types
-keep,allowobfuscation,allowshrinking class kotlin.coroutines.Continuation
-keep,allowobfuscation,allowshrinking class retrofit2.Response
-dontwarn retrofit2.KotlinExtensions
-dontwarn retrofit2.KotlinExtensions$*

# ---------------------------------------------------------------------------------------------
# OkHttp / Okio
# ---------------------------------------------------------------------------------------------
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**
-dontwarn javax.annotation.**
-dontwarn okio.**

# ---------------------------------------------------------------------------------------------
# MapLibre
# ---------------------------------------------------------------------------------------------
-keep class org.maplibre.** { *; }
-dontwarn org.maplibre.**
-dontwarn com.mapbox.**

# ---------------------------------------------------------------------------------------------
# Firebase / Google Play Services (consumer rules cover most; keep warnings quiet)
# ---------------------------------------------------------------------------------------------
-dontwarn com.google.firebase.**
-dontwarn com.google.android.gms.**
-keep class com.google.firebase.messaging.FirebaseMessagingService { *; }

# CameraX: ships its own consumer rules; keep quiet about optional/vendor classes it probes reflectively.
-dontwarn androidx.camera.**

# AndroidX security-crypto (Tink) optional dependencies
-dontwarn com.google.errorprone.annotations.**
-dontwarn javax.annotation.concurrent.**

# ---------------------------------------------------------------------------------------------
# WorkManager workers are instantiated reflectively by class name
# ---------------------------------------------------------------------------------------------
-keep class * extends androidx.work.ListenableWorker {
    public <init>(android.content.Context, androidx.work.WorkerParameters);
}

# ---------------------------------------------------------------------------------------------
# Strip verbose logging from release builds (Log.w/Log.e are kept for diagnostics)
# ---------------------------------------------------------------------------------------------
-assumenosideeffects class android.util.Log {
    public static int v(...);
    public static int d(...);
    public static int i(...);
}
