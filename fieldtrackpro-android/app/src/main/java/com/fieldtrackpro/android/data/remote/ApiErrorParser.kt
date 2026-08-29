package com.fieldtrackpro.android.data.remote

import com.google.gson.Gson
import com.google.gson.JsonObject

/**
 * Structured API Error representation.
 *
 * APP-ERR-001 & APP-ERR-002: Replaces raw string parsing and status code prefixes
 * with typed error envelopes and curated user-friendly messages.
 */
data class ApiError(
    val code: String? = null,
    val message: String,
    val details: Any? = null,
    val httpStatus: Int = 0
)

object ApiErrorParser {

    private val gson = Gson()

    /**
     * Parses an HTTP error response body and returns a typed [ApiError].
     * Never exposes raw JSON or unformatted technical exceptions to the user.
     */
    fun parse(responseCode: Int, errorBody: String?): ApiError {
        if (!errorBody.isNullOrBlank()) {
            try {
                val json = gson.fromJson(errorBody, JsonObject::class.java)
                if (json != null && json.has("error") && json.get("error").isJsonObject) {
                    val errorObj = json.getAsJsonObject("error")
                    val code = if (errorObj.has("code") && !errorObj.get("code").isJsonNull) {
                        errorObj.get("code").asString
                    } else null

                    val message = if (errorObj.has("message") && !errorObj.get("message").isJsonNull) {
                        errorObj.get("message").asString
                    } else null

                    val details = if (errorObj.has("details") && !errorObj.get("details").isJsonNull) {
                        errorObj.get("details")
                    } else null

                    if (!message.isNullOrBlank()) {
                        return ApiError(
                            code = code,
                            message = sanitizeMessage(message, responseCode),
                            details = details,
                            httpStatus = responseCode
                        )
                    }
                }
            } catch (e: Exception) {
                // Fallback to default user message
            }
        }

        return ApiError(
            code = "HTTP_$responseCode",
            message = defaultUserMessage(responseCode),
            httpStatus = responseCode
        )
    }

    fun defaultUserMessage(statusCode: Int): String {
        return when (statusCode) {
            401 -> "Session expired. Please sign in again."
            403 -> "You are not assigned to this visit/customer."
            404 -> "Visit or customer not found. It may have been reassigned."
            409 -> "Duplicate operation or resource already exists."
            422 -> "Validation failed. Please verify the submitted details."
            429 -> "Too many attempts. Please wait and try again."
            in 500..599 -> "Server is temporarily unavailable. Please try again shortly."
            else -> "An unexpected error occurred. Please try again."
        }
    }

    private fun sanitizeMessage(msg: String, statusCode: Int): String {
        val trimmed = msg.trim()
        if (trimmed.startsWith("{") && trimmed.endsWith("}")) {
            return defaultUserMessage(statusCode)
        }
        return trimmed
    }
}
