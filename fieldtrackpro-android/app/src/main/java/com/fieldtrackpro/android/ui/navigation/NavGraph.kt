package com.fieldtrackpro.android.ui.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.ui.screens.auth.LoginScreen
import com.fieldtrackpro.android.ui.screens.collections.CollectPaymentScreen
import com.fieldtrackpro.android.ui.screens.collections.OutletAccountScreen
import com.fieldtrackpro.android.ui.screens.dashboard.DashboardScreen
import com.fieldtrackpro.android.ui.screens.media.AttachmentPreviewScreen
import com.fieldtrackpro.android.ui.screens.media.MediaUploadScreen
import com.fieldtrackpro.android.ui.screens.profile.ProfileSettingsScreen
import com.fieldtrackpro.android.ui.screens.signature.SignatureScreen
import com.fieldtrackpro.android.ui.screens.visits.SubmissionSuccessScreen
import com.fieldtrackpro.android.ui.screens.visits.VisitSummaryScreen
import com.fieldtrackpro.android.ui.screens.splash.SplashScreen
import com.fieldtrackpro.android.ui.screens.sync.OfflineQueueScreen
import com.fieldtrackpro.android.ui.screens.visits.CheckInScreen
import com.fieldtrackpro.android.ui.screens.visits.CheckOutScreen
import com.fieldtrackpro.android.ui.screens.visits.TodayVisitsScreen
import com.fieldtrackpro.android.ui.screens.maps.MapScreen
import com.fieldtrackpro.android.ui.screens.notifications.NotificationsListScreen
import com.fieldtrackpro.android.ui.screens.requirements.RequirementFormScreen
import com.fieldtrackpro.android.ui.screens.requirements.FormFillScreen
import com.fieldtrackpro.android.ui.screens.visits.VisitDetailsScreen
import com.fieldtrackpro.android.ui.viewmodel.AuthViewModel
import com.fieldtrackpro.android.ui.viewmodel.CheckInViewModel
import com.fieldtrackpro.android.ui.viewmodel.CollectionViewModel
import com.fieldtrackpro.android.ui.viewmodel.FormFillViewModel
import com.fieldtrackpro.android.ui.viewmodel.MediaViewModel
import com.fieldtrackpro.android.ui.viewmodel.RequirementViewModel
import com.fieldtrackpro.android.ui.viewmodel.SignatureViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitDetailsViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitSummaryViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel

@Composable
fun NavGraph(
    navController: NavHostController,
    tokenManager: TokenManager,
    offlineQueueManager: OfflineQueueManager,
    authViewModel: AuthViewModel,
    visitsViewModel: VisitsViewModel,
    visitDetailsViewModel: VisitDetailsViewModel,
    checkInViewModel: CheckInViewModel,
    mediaViewModel: MediaViewModel,
    requirementViewModel: RequirementViewModel,
    formFillViewModel: FormFillViewModel,
    geofenceViewModel: com.fieldtrackpro.android.ui.viewmodel.GeofenceViewModel,
    notificationViewModel: com.fieldtrackpro.android.ui.viewmodel.NotificationViewModel,
    signatureViewModel: SignatureViewModel,
    visitSummaryViewModel: VisitSummaryViewModel,
    collectionViewModel: CollectionViewModel
) {
    // P1-7: every ViewModel above is now a required parameter, owned by
    // MainActivity's ViewModelStore-backed properties. None of them may be
    // constructed here with a default-expression value again - Kotlin
    // re-evaluates a default *expression* (unlike a required argument) on
    // every recomposition of this call site, which is exactly the bug this
    // fixes (formFillViewModel/signatureViewModel/visitSummaryViewModel/
    // collectionViewModel previously had no home in MainActivity at all and
    // were silently rebuilt - discarding in-progress form/signature state -
    // on effectively any recomposition, not just a rotation).
    NavHost(
        navController = navController,
        startDestination = Screen.Splash.route
    ) {
        composable(Screen.Splash.route) {
            SplashScreen(
                tokenManager = tokenManager,
                onNavigateToLogin = {
                    navController.navigate(Screen.Login.route) {
                        popUpTo(Screen.Splash.route) { inclusive = true }
                    }
                },
                onNavigateToDashboard = {
                    navController.navigate(Screen.Dashboard.route) {
                        popUpTo(Screen.Splash.route) { inclusive = true }
                    }
                }
            )
        }

        composable(Screen.Login.route) {
            LoginScreen(
                viewModel = authViewModel,
                onLoginSuccess = {
                    navController.navigate(Screen.Dashboard.route) {
                        popUpTo(Screen.Login.route) { inclusive = true }
                    }
                }
            )
        }

        composable(Screen.Dashboard.route) {
            DashboardScreen(
                visitsViewModel = visitsViewModel,
                tokenManager = tokenManager,
                onNavigateToVisits = { navController.navigate(Screen.TodayVisits.route) },
                onNavigateToVisitDetails = { vId -> navController.navigate(Screen.VisitDetails.createRoute(vId)) },
                onNavigateToProfile = { navController.navigate(Screen.ProfileSettings.route) },
                onNavigateToSync = { navController.navigate(Screen.OfflineQueue.route) },
                onNavigateToNotifications = { navController.navigate(Screen.Notifications.route) }
            )
        }

        composable(Screen.TodayVisits.route) {
            TodayVisitsScreen(
                viewModel = visitsViewModel,
                onNavigateBack = { navController.popBackStack() },
                onNavigateToVisitDetails = { vId -> navController.navigate(Screen.VisitDetails.createRoute(vId)) }
            )
        }

        composable(
            route = Screen.VisitDetails.route,
            arguments = listOf(navArgument("visitId") { type = NavType.StringType })
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            VisitDetailsScreen(
                visitId = visitId,
                viewModel = visitDetailsViewModel,
                onNavigateBack = { navController.popBackStack() },
                onNavigateToCheckIn = { vId, cId -> navController.navigate(Screen.CheckIn.createRoute(vId, cId)) },
                onNavigateToCheckOut = { vId, cId -> navController.navigate(Screen.CheckOut.createRoute(vId, cId)) },
                onNavigateToMedia = { vId -> navController.navigate(Screen.MediaUpload.createRoute(vId)) },
                onNavigateToOrderCapture = { vId -> navController.navigate(Screen.OrderCapture.createRoute(vId)) },
                onNavigateToSignature = { vId -> navController.navigate(Screen.Signature.createRoute(vId)) },
                onNavigateToPreview = { mediaId, fileName, isPhoto ->
                    navController.navigate(Screen.AttachmentPreview.createRoute(mediaId, fileName, isPhoto))
                },
                onNavigateToFormFill = { vId, formId -> navController.navigate(Screen.FormFill.createRoute(vId, formId)) },
                geofenceViewModel = geofenceViewModel,
                onNavigateToMap = { cId -> navController.navigate(Screen.Map.createRoute(cId)) },
                onNavigateToAccount = { vId, cId -> navController.navigate(Screen.OutletAccount.createRoute(vId, cId)) }
            )
        }

        composable(
            route = Screen.OutletAccount.route,
            arguments = listOf(
                navArgument("visitId") { type = NavType.StringType },
                navArgument("customerId") { type = NavType.StringType }
            )
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            val customerId = backStackEntry.arguments?.getString("customerId") ?: ""
            OutletAccountScreen(
                visitId = visitId,
                customerId = customerId,
                viewModel = collectionViewModel,
                onNavigateBack = { navController.popBackStack() },
                onNavigateToCollectPayment = { vId, cId -> navController.navigate(Screen.CollectPayment.createRoute(vId, cId)) }
            )
        }

        composable(
            route = Screen.CollectPayment.route,
            arguments = listOf(
                navArgument("visitId") { type = NavType.StringType },
                navArgument("customerId") { type = NavType.StringType }
            )
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            val customerId = backStackEntry.arguments?.getString("customerId") ?: ""
            CollectPaymentScreen(
                visitId = visitId,
                customerId = customerId,
                viewModel = collectionViewModel,
                onNavigateBack = { navController.popBackStack() },
                onSuccess = {
                    collectionViewModel.resetCollectionState()
                    navController.popBackStack()
                }
            )
        }

        composable(
            route = Screen.FormFill.route,
            arguments = listOf(
                navArgument("visitId") { type = NavType.StringType },
                navArgument("formId") { type = NavType.StringType }
            )
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            val formId = backStackEntry.arguments?.getString("formId") ?: ""
            FormFillScreen(
                visitId = visitId,
                formId = formId,
                viewModel = formFillViewModel,
                onNavigateBack = { navController.popBackStack() }
            )
        }

        composable(
            route = Screen.CheckIn.route,
            arguments = listOf(
                navArgument("visitId") { type = NavType.StringType },
                navArgument("customerId") { type = NavType.StringType }
            )
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            val customerId = backStackEntry.arguments?.getString("customerId") ?: ""
            CheckInScreen(
                visitId = visitId,
                customerId = customerId,
                viewModel = checkInViewModel,
                onNavigateBack = { navController.popBackStack() },
                onSuccess = { navController.popBackStack() }
            )
        }

        composable(
            route = Screen.CheckOut.route,
            arguments = listOf(
                navArgument("visitId") { type = NavType.StringType },
                navArgument("customerId") { type = NavType.StringType }
            )
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            val customerId = backStackEntry.arguments?.getString("customerId") ?: ""
            CheckOutScreen(
                visitId = visitId,
                customerId = customerId,
                viewModel = checkInViewModel,
                onNavigateBack = { navController.popBackStack() },
                onSuccess = { navController.popBackStack() }
            )
        }

        composable(
            route = Screen.MediaUpload.route,
            arguments = listOf(navArgument("visitId") { type = NavType.StringType })
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            MediaUploadScreen(
                visitId = visitId,
                viewModel = mediaViewModel,
                onNavigateBack = { navController.popBackStack() },
                onPreviewMedia = { mediaId, fileName, isPhoto ->
                    navController.navigate(
                        Screen.AttachmentPreview.createRoute(mediaId, fileName, isPhoto)
                    )
                }
            )
        }

        // P2-B: order capture - same screen/pipeline as MediaUpload, in order mode.
        composable(
            route = Screen.OrderCapture.route,
            arguments = listOf(navArgument("visitId") { type = NavType.StringType })
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            MediaUploadScreen(
                visitId = visitId,
                viewModel = mediaViewModel,
                onNavigateBack = { navController.popBackStack() },
                onPreviewMedia = { mediaId, fileName, isPhoto ->
                    navController.navigate(
                        Screen.AttachmentPreview.createRoute(mediaId, fileName, isPhoto)
                    )
                },
                isOrderMode = true
            )
        }

        composable(Screen.ProfileSettings.route) {
            ProfileSettingsScreen(
                tokenManager = tokenManager,
                authViewModel = authViewModel,
                onNavigateBack = { navController.popBackStack() },
                onLogout = {
                    // P1-8: a geofence registered for the session that's
                    // ending must not keep running in the background.
                    geofenceViewModel.stopMonitoring()
                    navController.navigate(Screen.Login.route) {
                        popUpTo(0) { inclusive = true }
                    }
                }
            )
        }

        composable(Screen.OfflineQueue.route) {
            OfflineQueueScreen(
                offlineQueueManager = offlineQueueManager,
                visitsViewModel = visitsViewModel,
                onNavigateBack = { navController.popBackStack() }
            )
        }

        composable(Screen.Notifications.route) {
            NotificationsListScreen(
                viewModel = notificationViewModel,
                onNavigateBack = { navController.popBackStack() },
                onNavigateToVisitDetails = { vId -> navController.navigate(Screen.VisitDetails.createRoute(vId)) }
            )
        }

        composable(
            route = Screen.Map.route,
            arguments = listOf(navArgument("customerId") { type = NavType.StringType })
        ) { backStackEntry ->
            val customerId = backStackEntry.arguments?.getString("customerId") ?: ""
            MapScreen(
                customerId = customerId,
                onNavigateBack = { navController.popBackStack() }
            )
        }

        composable(
            route = Screen.AttachmentPreview.route,
            arguments = listOf(
                navArgument("mediaId") { type = NavType.StringType },
                navArgument("fileName") { type = NavType.StringType },
                navArgument("isPhoto") { type = NavType.BoolType }
            )
        ) { backStackEntry ->
            val mediaId = backStackEntry.arguments?.getString("mediaId") ?: ""
            val fileName = backStackEntry.arguments?.getString("fileName") ?: "attachment"
            val isPhoto = backStackEntry.arguments?.getBoolean("isPhoto") ?: false
            AttachmentPreviewScreen(
                mediaId = mediaId,
                fileName = fileName,
                isPhoto = isPhoto,
                onNavigateBack = { navController.popBackStack() }
            )
        }

        composable(
            route = Screen.VisitSummary.route,
            arguments = listOf(navArgument("visitId") { type = NavType.StringType })
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            VisitSummaryScreen(
                visitId = visitId,
                viewModel = visitSummaryViewModel,
                onNavigateBack = { navController.popBackStack() },
                onSubmit = { navController.navigate(Screen.SubmissionSuccess.createRoute(visitId)) },
                onCancel = { navController.popBackStack() }
            )
        }

        composable(
            route = Screen.SubmissionSuccess.route,
            arguments = listOf(navArgument("visitId") { type = NavType.StringType })
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            SubmissionSuccessScreen(
                visitId = visitId,
                onNavigateToDashboard = {
                    navController.navigate(Screen.Dashboard.route) {
                        popUpTo(Screen.Splash.route) { inclusive = true }
                    }
                }
            )
        }

        composable(
            route = Screen.RequirementForm.route,
            arguments = listOf(navArgument("visitId") { type = NavType.StringType })
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            RequirementFormScreen(
                visitId = visitId,
                viewModel = requirementViewModel,
                onNavigateBack = { navController.popBackStack() },
                onSubmitSuccess = {
                    navController.navigate(Screen.SubmissionSuccess.createRoute(visitId))
                }
            )
        }

        composable(
            route = Screen.Signature.route,
            arguments = listOf(navArgument("visitId") { type = NavType.StringType })
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            SignatureScreen(
                visitId = visitId,
                viewModel = signatureViewModel,
                onNavigateBack = { navController.popBackStack() },
                onComplete = {
                    navController.navigate(Screen.SubmissionSuccess.createRoute(visitId))
                }
            )
        }
    }
}
