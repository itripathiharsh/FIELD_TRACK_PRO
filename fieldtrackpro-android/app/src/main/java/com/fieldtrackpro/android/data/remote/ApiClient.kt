package com.fieldtrackpro.android.data.remote

import com.fieldtrackpro.android.data.api.AuthApi
import com.fieldtrackpro.android.data.api.CustomerApi
import com.fieldtrackpro.android.data.api.GeoApi
import com.fieldtrackpro.android.data.api.MediaApi
import com.fieldtrackpro.android.data.api.RequirementApi
import com.fieldtrackpro.android.data.api.SignatureApi
import com.fieldtrackpro.android.data.api.VisitApi
import com.fieldtrackpro.android.BuildConfig
import com.fieldtrackpro.android.data.local.TokenManager
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object ApiClient {
    // Default emulator base URL pointing to host FastAPI backend (http://10.0.2.2:8000/)
    private var baseUrl: String = "http://10.0.2.2:8000/"

    fun setCustomBaseUrl(url: String) {
        if (url.isNotBlank()) {
            baseUrl = if (url.endsWith("/")) url else "$url/"
            retrofitInstance = null // reset for dynamic backend URL switching
        }
    }

    fun getBaseUrl(): String = baseUrl

    private var retrofitInstance: Retrofit? = null

    fun getRetrofit(tokenManager: TokenManager): Retrofit {
        if (retrofitInstance == null) {
            val authInterceptor = Interceptor { chain ->
                val originalRequest = chain.request()
                val token = tokenManager.getAccessToken()
                val requestBuilder = originalRequest.newBuilder()
                if (!token.isNull_or_empty()) {
                    requestBuilder.header("Authorization", "Bearer $token")
                }
                chain.proceed(requestBuilder.build())
            }

            // Security Design s9: never log full tokens or request bodies.
            // BODY level printed the Authorization header and every payload,
            // including credentials, into logcat on release builds.
            val loggingInterceptor = HttpLoggingInterceptor().apply {
                level = if (BuildConfig.DEBUG) {
                    HttpLoggingInterceptor.Level.BASIC
                } else {
                    HttpLoggingInterceptor.Level.NONE
                }
                redactHeader("Authorization")
            }

            val okHttpClient = OkHttpClient.Builder()
                .addInterceptor(authInterceptor)
                .addInterceptor(loggingInterceptor)
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(15, TimeUnit.SECONDS)
                .writeTimeout(15, TimeUnit.SECONDS)
                .build()

            retrofitInstance = Retrofit.Builder()
                .baseUrl(baseUrl)
                .client(okHttpClient)
                .addConverterFactory(GsonConverterFactory.create())
                .build()
        }
        return retrofitInstance!!
    }

    fun createAuthApi(tokenManager: TokenManager): AuthApi =
        getRetrofit(tokenManager).create(AuthApi::class.java)

    fun createVisitApi(tokenManager: TokenManager): VisitApi =
        getRetrofit(tokenManager).create(VisitApi::class.java)

    fun createCustomerApi(tokenManager: TokenManager): CustomerApi =
        getRetrofit(tokenManager).create(CustomerApi::class.java)

    fun createMediaApi(tokenManager: TokenManager): MediaApi =
        getRetrofit(tokenManager).create(MediaApi::class.java)

    fun createGeoApi(tokenManager: TokenManager): GeoApi =
        getRetrofit(tokenManager).create(GeoApi::class.java)

    fun createRequirementApi(tokenManager: TokenManager): RequirementApi =
        getRetrofit(tokenManager).create(RequirementApi::class.java)

    fun createSignatureApi(tokenManager: TokenManager): SignatureApi =
        getRetrofit(tokenManager).create(SignatureApi::class.java)

    private fun String?.isNull_or_empty(): Boolean = this == null || this.trim().isEmpty()
}
