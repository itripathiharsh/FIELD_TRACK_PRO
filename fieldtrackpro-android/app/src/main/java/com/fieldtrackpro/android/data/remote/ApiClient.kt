package com.fieldtrackpro.android.data.remote

import com.fieldtrackpro.android.BuildConfig
import com.fieldtrackpro.android.data.api.AuthApi
import com.fieldtrackpro.android.data.api.CollectionApi
import com.fieldtrackpro.android.data.api.CustomerApi
import com.fieldtrackpro.android.data.api.DashboardApi
import com.fieldtrackpro.android.data.api.DeviceApi
import com.fieldtrackpro.android.data.api.FormTemplateApi
import com.fieldtrackpro.android.data.api.GeoApi
import com.fieldtrackpro.android.data.api.MediaApi
import com.fieldtrackpro.android.data.api.NotificationApi
import com.fieldtrackpro.android.data.api.RequirementApi
import com.fieldtrackpro.android.data.api.SignatureApi
import com.fieldtrackpro.android.data.api.VisitApi
import com.fieldtrackpro.android.data.local.TokenManager
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {
    // Default emulator base URL pointing to host FastAPI backend (http://10.0.2.2:8000/)
    private var baseUrl: String = BuildConfig.BASE_URL

    private val lock = Any()
    @Volatile
    private var retrofitInstance: Retrofit? = null

    /**
     * P0-3: a debug/QA convenience only. Production builds must not let a
     * user redirect all API traffic - including the bearer token on every
     * request - to an arbitrary endpoint.
     */
    fun setCustomBaseUrl(url: String) {
        if (!BuildConfig.DEBUG) {
            return
        }
        if (url.isNotBlank()) {
            synchronized(lock) {
                baseUrl = if (url.endsWith("/")) url else "$url/"
                retrofitInstance = null // reset for dynamic backend URL switching
            }
        }
    }

    fun getBaseUrl(): String = baseUrl

    /**
     * APP-API-001: Thread-safe double-checked singleton Retrofit instance.
     * APP-AUTH-001: Attached TokenAuthenticator for global 401 recovery.
     * APP-API-004: Attached TransientRetryInterceptor for 502/503/504 retry.
     * APP-API-003: Preserved 15s standard API timeout.
     */
    fun getRetrofit(tokenManager: TokenManager): Retrofit {
        return retrofitInstance ?: synchronized(lock) {
            retrofitInstance ?: createRetrofit(tokenManager).also { retrofitInstance = it }
        }
    }

    /**
     * APP-API-002: Single unified OkHttpClient factory eliminating copy-pasted interceptor pipelines.
     */
    fun createOkHttpClient(tokenManager: TokenManager, timeoutSeconds: Long = 15): OkHttpClient {
        val authInterceptor = Interceptor { chain ->
            val originalRequest = chain.request()
            val token = tokenManager.getAccessToken()
            val requestBuilder = originalRequest.newBuilder()
            if (!token.isNullOrBlank()) {
                requestBuilder.header("Authorization", "Bearer $token")
            }
            chain.proceed(requestBuilder.build())
        }

        val loggingInterceptor = HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) {
                HttpLoggingInterceptor.Level.BASIC
            } else {
                HttpLoggingInterceptor.Level.NONE
            }
            redactHeader("Authorization")
        }

        val tokenAuthenticator = TokenAuthenticator(tokenManager, ::getBaseUrl)
        val transientRetryInterceptor = TransientRetryInterceptor()

        return OkHttpClient.Builder()
            .addInterceptor(authInterceptor)
            .addInterceptor(transientRetryInterceptor)
            .addInterceptor(loggingInterceptor)
            .authenticator(tokenAuthenticator)
            .connectTimeout(timeoutSeconds, TimeUnit.SECONDS)
            .readTimeout(timeoutSeconds, TimeUnit.SECONDS)
            .writeTimeout(timeoutSeconds, TimeUnit.SECONDS)
            .build()
    }

    private fun createRetrofit(tokenManager: TokenManager): Retrofit {
        val okHttpClient = createOkHttpClient(tokenManager, timeoutSeconds = 15)

        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
    }

    fun createAuthApi(tokenManager: TokenManager): AuthApi =
        getRetrofit(tokenManager).create(AuthApi::class.java)

    fun createVisitApi(tokenManager: TokenManager): VisitApi =
        getRetrofit(tokenManager).create(VisitApi::class.java)

    fun createCustomerApi(tokenManager: TokenManager): CustomerApi =
        getRetrofit(tokenManager).create(CustomerApi::class.java)

    fun createDashboardApi(tokenManager: TokenManager): DashboardApi =
        getRetrofit(tokenManager).create(DashboardApi::class.java)

    fun createMediaApi(tokenManager: TokenManager): MediaApi =
        getRetrofit(tokenManager).create(MediaApi::class.java)

    /**
     * APP-API-002 / APP-API-003: Dedicated 45s client for large photo/media uploads and downloads,
     * sharing the exact same unified authentication and retry policy.
     */
    fun createOkHttpClientForDownload(tokenManager: TokenManager): OkHttpClient =
        createOkHttpClient(tokenManager, timeoutSeconds = 45)

    fun createGeoApi(tokenManager: TokenManager): GeoApi =
        getRetrofit(tokenManager).create(GeoApi::class.java)

    fun createRequirementApi(tokenManager: TokenManager): RequirementApi =
        getRetrofit(tokenManager).create(RequirementApi::class.java)

    fun createFormTemplateApi(tokenManager: TokenManager): FormTemplateApi =
        getRetrofit(tokenManager).create(FormTemplateApi::class.java)

    fun createSignatureApi(tokenManager: TokenManager): SignatureApi =
        getRetrofit(tokenManager).create(SignatureApi::class.java)

    fun createNotificationApi(tokenManager: TokenManager): NotificationApi =
        getRetrofit(tokenManager).create(NotificationApi::class.java)

    fun createDeviceApi(tokenManager: TokenManager): DeviceApi =
        getRetrofit(tokenManager).create(DeviceApi::class.java)

    fun createCollectionApi(tokenManager: TokenManager): CollectionApi =
        getRetrofit(tokenManager).create(CollectionApi::class.java)
}
