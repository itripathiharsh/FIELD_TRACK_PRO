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
    // P2-B: order capture - a distinct nav destination (Visit -> Order),
    // reusing MediaUploadScreen in isOrderMode rather than a second camera flow.
    object OrderCapture : Screen("order_capture/{visitId}") {
        fun createRoute(visitId: String) = "order_capture/$visitId"
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
    object RequirementForm : Screen("requirement_form/{visitId}") {
        fun createRoute(visitId: String) = "requirement_form/$visitId"
    }
    object FormFill : Screen("form_fill/{visitId}/{formId}") {
        fun createRoute(visitId: String, formId: String) = "form_fill/$visitId/$formId"
    }
    object Notifications : Screen("notifications")
    object Signature : Screen("signature/{visitId}") {
        fun createRoute(visitId: String) = "signature/$visitId"
    }
    object OutletAccount : Screen("outlet_account/{visitId}/{customerId}") {
        fun createRoute(visitId: String, customerId: String) = "outlet_account/$visitId/$customerId"
    }
    object CollectPayment : Screen("collect_payment/{visitId}/{customerId}") {
        fun createRoute(visitId: String, customerId: String) = "collect_payment/$visitId/$customerId"
    }
}
