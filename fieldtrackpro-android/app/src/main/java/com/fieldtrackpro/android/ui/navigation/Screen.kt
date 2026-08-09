package com.fieldtrackpro.android.ui.navigation

sealed class Screen(val route: String) {
    object Splash : Screen("splash")
    object Login : Screen("login")
    object Dashboard : Screen("dashboard")
    object TodayVisits : Screen("today_visits")
    object VisitDetails : Screen("visit_details/{visitId}") {
        fun createRoute(visitId: String) = "visit_details/$visitId"
    }
    object CheckIn : Screen("check_in/{visitId}/{customerId}") {
        fun createRoute(visitId: String, customerId: String) = "check_in/$visitId/$customerId"
    }
    object CheckOut : Screen("check_out/{visitId}/{customerId}") {
        fun createRoute(visitId: String, customerId: String) = "check_out/$visitId/$customerId"
    }
    object MediaUpload : Screen("media_upload/{visitId}") {
        fun createRoute(visitId: String) = "media_upload/$visitId"
    }
    object ProfileSettings : Screen("profile_settings")
    object OfflineQueue : Screen("offline_queue")
    object Map : Screen("map/{customerId}") {
        fun createRoute(customerId: String) = "map/$customerId"
    }
    object AttachmentPreview : Screen("attachment_preview/{mediaId}/{fileName}/{isPhoto}") {
        fun createRoute(mediaId: String, fileName: String, isPhoto: Boolean) =
            "attachment_preview/$mediaId/$fileName/$isPhoto"
    }
    object VisitSummary : Screen("visit_summary/{visitId}") {
        fun createRoute(visitId: String) = "visit_summary/$visitId"
    }
    object SubmissionSuccess : Screen("submission_success/{visitId}") {
        fun createRoute(visitId: String) = "submission_success/$visitId"
    }
}
