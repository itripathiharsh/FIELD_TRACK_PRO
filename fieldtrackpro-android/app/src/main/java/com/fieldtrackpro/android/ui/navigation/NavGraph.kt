package com.fieldtrackpro.android.ui.navigation

import androidx.compose.runtime.LaunchedEffect

import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.navigation.NavController
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
import com.fieldtrackpro.android.ui.screens.maps.MapScreen
import com.fieldtrackpro.android.ui.screens.media.AttachmentPreviewScreen
import com.fieldtrackpro.android.ui.screens.media.MediaUploadScreen
import com.fieldtrackpro.android.ui.screens.notifications.NotificationsListScreen
import com.fieldtrackpro.android.ui.screens.planning.MonthlyPlanningScreen
import com.fieldtrackpro.android.ui.screens.profile.ProfileSettingsScreen
import com.fieldtrackpro.android.ui.screens.requirements.FormFillScreen
import com.fieldtrackpro.android.ui.screens.requirements.RequirementFormScreen
import com.fieldtrackpro.android.ui.screens.signature.SignatureScreen
import com.fieldtrackpro.android.ui.screens.auth.ChangePasswordScreen
import com.fieldtrackpro.android.ui.screens.splash.SplashScreen
import com.fieldtrackpro.android.ui.screens.sync.OfflineQueueScreen
import com.fieldtrackpro.android.ui.screens.visits.CheckInScreen
import com.fieldtrackpro.android.ui.screens.visits.CheckOutScreen
import com.fieldtrackpro.android.ui.screens.visits.SubmissionSuccessScreen
import com.fieldtrackpro.android.ui.screens.visits.TodayVisitsScreen
import com.fieldtrackpro.android.ui.screens.visits.VisitDetailsScreen
import com.fieldtrackpro.android.ui.screens.visits.VisitSummaryScreen
import com.fieldtrackpro.android.ui.viewmodel.AuthViewModel
import com.fieldtrackpro.android.ui.viewmodel.CheckInViewModel
import com.fieldtrackpro.android.ui.viewmodel.CheckOutViewModel
import com.fieldtrackpro.android.ui.viewmodel.CollectionViewModel
import com.fieldtrackpro.android.ui.viewmodel.FormFillViewModel
import com.fieldtrackpro.android.ui.viewmodel.GeofenceViewModel
import com.fieldtrackpro.android.ui.viewmodel.MediaViewModel
import com.fieldtrackpro.android.ui.viewmodel.MonthlyPlanningViewModel
import com.fieldtrackpro.android.ui.viewmodel.NotificationViewModel
import com.fieldtrackpro.android.ui.viewmodel.RequirementViewModel
import com.fieldtrackpro.android.ui.viewmodel.SignatureViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitDetailsViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitSummaryViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel
import com.fieldtrackpro.android.utils.SessionManager
import java.net.URLDecoder

@Composable
fun NavGraph(
    navController: NavHostController,
    authViewModel: AuthViewModel,
    visitsViewModel: VisitsViewModel,
    visitDetailsViewModel: VisitDetailsViewModel,
    checkInViewModel: CheckInViewModel,
    checkOutViewModel: CheckOutViewModel,
    mediaViewModel: MediaViewModel,
    requirementViewModel: RequirementViewModel,
    formFillViewModel: FormFillViewModel,
    notificationViewModel: NotificationViewModel,
    signatureViewModel: SignatureViewModel,
    visitSummaryViewModel: VisitSummaryViewModel,
    collectionViewModel: CollectionViewModel,
    geofenceViewModel: GeofenceViewModel,
    tokenManager: TokenManager,
    offlineQueueManager: OfflineQueueManager,
    monthlyPlanningViewModel: MonthlyPlanningViewModel? = null
) {
    // Leaving the payment form by ANY route (system Back, top-bar back, deep link) discards its view-model state:
    // a stale "Saved offline"/error banner and the previous submission's idempotency key must not leak into the
    // next form. Submitting from the form itself still resets in onSuccess. A rotation does not change the
    // destination, so an in-flight submission keeps its key across recreation.
    DisposableEffect(navController) {
        var previousRoute: String? = null
        val listener = NavController.OnDestinationChangedListener { _, destination, _ ->
            if (previousRoute == Screen.CollectPayment.route && destination.route != Screen.CollectPayment.route) {
                collectionViewModel.resetCollectionState()
            }
            previousRoute = destination.route
        }
        navController.addOnDestinationChangedListener(listener)
        onDispose { navController.removeOnDestinationChangedListener(listener) }
    }

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
                        launchSingleTop = true
                    }
                },
                onNavigateToDashboard = {
                    val pendingDeepLink = SessionManager.consumePendingDeepLink()
                    navController.navigate(Screen.Dashboard.route) {
                        popUpTo(Screen.Splash.route) { inclusive = true }
                        launchSingleTop = true
                    }
                    if (pendingDeepLink != null && pendingDeepLink.isNotBlank()) {
                        navController.navigate(Screen.VisitDetails.createRoute(pendingDeepLink))
                    }
                },
                onNavigateToChangePassword = {
                    navController.navigate(Screen.ChangePassword.route) {
                        popUpTo(Screen.Splash.route) { inclusive = true }
                        launchSingleTop = true
                    }
                }
            )
        }

        composable(Screen.ChangePassword.route) {
            ChangePasswordScreen(
                viewModel = authViewModel,
                onPasswordChanged = {
                    navController.navigate(Screen.Dashboard.route) {
                        popUpTo(0) { inclusive = true }
                        launchSingleTop = true
                    }
                },
                onLogout = {
                    navController.navigate(Screen.Login.route) {
                        popUpTo(0) { inclusive = true }
                        launchSingleTop = true
                    }
                }
            )
        }

        composable(Screen.Login.route) {
            LoginScreen(
                viewModel = authViewModel,
                onLoginSuccess = {
                    if (tokenManager.isPasswordChangeRequired()) {
                        // Forced password change: nothing else works until it is done.
                        navController.navigate(Screen.ChangePassword.route) {
                            popUpTo(Screen.Login.route) { inclusive = true }
                            launchSingleTop = true
                        }
                        return@LoginScreen
                    }
                    val pendingDeepLink = SessionManager.consumePendingDeepLink()
                    navController.navigate(Screen.Dashboard.route) {
                        popUpTo(Screen.Login.route) { inclusive = true }
                        launchSingleTop = true
                    }
                    if (pendingDeepLink != null && pendingDeepLink.isNotBlank()) {
                        navController.navigate(Screen.VisitDetails.createRoute(pendingDeepLink))
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
                onNavigateToNotifications = { navController.navigate(Screen.Notifications.route) },
                onNavigateToAddCustomer = { navController.navigate(Screen.AddCustomer.route) },
                onNavigateToMonthlyPlanning = { navController.navigate(Screen.MonthlyPlanning.route) },
                onNavigateToPerformance = { navController.navigate(Screen.EmployeeDashboard.route) }
            )
        }

        composable(Screen.EmployeeDashboard.route) {
            val vm = androidx.lifecycle.viewmodel.compose.viewModel {
                com.fieldtrackpro.android.performance.EmployeeDashboardViewModel(
                    source = com.fieldtrackpro.android.performance.ApiEmployeeDashboardSource(tokenManager),
                    role = { tokenManager.getUserRole() }
                )
            }
            com.fieldtrackpro.android.performance.EmployeeDashboardScreen(
                viewModel = vm,
                onNavigateBack = { navController.popBackStackSafely() }
            )
        }

        composable(Screen.MonthlyPlanning.route) {
            val planningVm = monthlyPlanningViewModel ?: androidx.lifecycle.viewmodel.compose.viewModel {
                MonthlyPlanningViewModel(tokenManager)
            }
            MonthlyPlanningScreen(
                viewModel = planningVm,
                onNavigateBack = { navController.popBackStackSafely() }
            )
        }

        composable(Screen.AddCustomer.route) {
            com.fieldtrackpro.android.ui.screens.customers.AddCustomerScreen(
                onNavigateBack = { navController.popBackStackSafely() },
                onCustomerCreated = {
                    visitsViewModel.loadVisits(refresh = true)
                    visitsViewModel.loadDashboardVisits()
                    navController.popBackStack()
                }
            )
        }

        composable(Screen.TodayVisits.route) {
            TodayVisitsScreen(
                viewModel = visitsViewModel,
                onNavigateBack = { navController.popBackStackSafely() },
                onNavigateToVisitDetails = { vId -> navController.navigate(Screen.VisitDetails.createRoute(vId)) }
            )
        }

        composable(
            route = Screen.VisitDetails.route,
            arguments = listOf(navArgument("visitId") { type = NavType.StringType })
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            if (visitId.isBlank()) {
                LaunchedEffect(Unit) { navController.popBackStack() }
                return@composable
            }
            VisitDetailsScreen(
                visitId = visitId,
                viewModel = visitDetailsViewModel,
                onNavigateBack = { navController.popBackStackSafely() },
                onNavigateToCheckIn = { vId, cId -> navController.navigate(Screen.CheckIn.createRoute(vId, cId)) },
                onNavigateToCheckOut = { vId, cId -> navController.navigate(Screen.CheckOut.createRoute(vId, cId)) },
                onNavigateToMedia = { vId -> navController.navigate(Screen.MediaUpload.createRoute(vId)) },
                onNavigateToOrderCapture = { vId -> navController.navigate(Screen.OrderCapture.createRoute(vId)) },
                onNavigateToSignature = { vId -> navController.navigate(Screen.Signature.createRoute(vId)) },
                onNavigateToPreview = { mediaId, fileName, isPhoto ->
                    navController.navigate(
                        Screen.AttachmentPreview.createRoute(mediaId, fileName, isPhoto)
                    )
                },
                onNavigateToFormFill = { vId, formId -> navController.navigate(Screen.FormFill.createRoute(vId, formId)) },
                geofenceViewModel = geofenceViewModel,
                onNavigateToMap = { cId -> navController.navigate(Screen.Map.createRoute(cId)) },
                onNavigateToAccount = { vId, cId -> navController.navigate(Screen.OutletAccount.createRoute(vId, cId)) },
                onNavigateToVisitSummary = { vId -> navController.navigate(Screen.VisitSummary.createRoute(vId)) },
                onNavigateToRequirementForm = { vId -> navController.navigate(Screen.RequirementForm.createRoute(vId)) }
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
            if (visitId.isBlank() || customerId.isBlank()) {
                LaunchedEffect(Unit) { navController.popBackStack() }
                return@composable
            }
            OutletAccountScreen(
                visitId = visitId,
                customerId = customerId,
                viewModel = collectionViewModel,
                onNavigateBack = { navController.popBackStackSafely() },
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
            if (visitId.isBlank() || customerId.isBlank()) {
                LaunchedEffect(Unit) { navController.popBackStack() }
                return@composable
            }
            CollectPaymentScreen(
                visitId = visitId,
                customerId = customerId,
                viewModel = collectionViewModel,
                onNavigateBack = { navController.popBackStackSafely() },
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
            if (visitId.isBlank() || formId.isBlank()) {
                LaunchedEffect(Unit) { navController.popBackStack() }
                return@composable
            }
            FormFillScreen(
                visitId = visitId,
                formId = formId,
                viewModel = formFillViewModel,
                onNavigateBack = { navController.popBackStackSafely() }
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
            if (visitId.isBlank()) {
                LaunchedEffect(Unit) { navController.popBackStack() }
                return@composable
            }
            CheckInScreen(
                visitId = visitId,
                customerId = customerId,
                viewModel = checkInViewModel,
                onNavigateBack = { navController.popBackStackSafely() },
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
            if (visitId.isBlank()) {
                LaunchedEffect(Unit) { navController.popBackStack() }
                return@composable
            }
            CheckOutScreen(
                visitId = visitId,
                customerId = customerId,
                viewModel = checkOutViewModel,
                onNavigateBack = { navController.popBackStackSafely() },
                onSuccess = { navController.popBackStack() }
            )
        }

        composable(
            route = Screen.MediaUpload.route,
            arguments = listOf(navArgument("visitId") { type = NavType.StringType })
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            if (visitId.isBlank()) {
                LaunchedEffect(Unit) { navController.popBackStack() }
                return@composable
            }
            MediaUploadScreen(
                visitId = visitId,
                viewModel = mediaViewModel,
                isOrderMode = false,
                onNavigateBack = { navController.popBackStackSafely() },
                onPreviewMedia = { mediaId, fileName, isPhoto ->
                    navController.navigate(
                        Screen.AttachmentPreview.createRoute(mediaId, fileName, isPhoto)
                    )
                }
            )
        }

        composable(
            route = Screen.OrderCapture.route,
            arguments = listOf(navArgument("visitId") { type = NavType.StringType })
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            if (visitId.isBlank()) {
                LaunchedEffect(Unit) { navController.popBackStack() }
                return@composable
            }
            MediaUploadScreen(
                visitId = visitId,
                viewModel = mediaViewModel,
                isOrderMode = true,
                onNavigateBack = { navController.popBackStackSafely() },
                onPreviewMedia = { mediaId, fileName, isPhoto ->
                    navController.navigate(
                        Screen.AttachmentPreview.createRoute(mediaId, fileName, isPhoto)
                    )
                }
            )
        }

        composable(Screen.ProfileSettings.route) {
            ProfileSettingsScreen(
                tokenManager = tokenManager,
                authViewModel = authViewModel,
                offlineQueueManager = offlineQueueManager,
                onSyncNow = { onDone -> visitsViewModel.syncOfflineQueue { onDone() } },
                onNavigateBack = { navController.popBackStackSafely() },
                onLogout = {
                    navController.navigate(Screen.Login.route) {
                        popUpTo(0) { inclusive = true }
                        launchSingleTop = true
                    }
                }
            )
        }

        composable(Screen.OfflineQueue.route) {
            OfflineQueueScreen(
                offlineQueueManager = offlineQueueManager,
                visitsViewModel = visitsViewModel,
                tokenManager = tokenManager,
                onNavigateBack = { navController.popBackStackSafely() }
            )
        }

        composable(Screen.Notifications.route) {
            NotificationsListScreen(
                viewModel = notificationViewModel,
                onNavigateBack = { navController.popBackStackSafely() },
                onNavigateToVisitDetails = { vId -> navController.navigate(Screen.VisitDetails.createRoute(vId)) }
            )
        }

        composable(
            route = Screen.Map.route,
            arguments = listOf(navArgument("customerId") { type = NavType.StringType })
        ) { backStackEntry ->
            val customerId = backStackEntry.arguments?.getString("customerId") ?: ""
            if (customerId.isBlank()) {
                LaunchedEffect(Unit) { navController.popBackStack() }
                return@composable
            }
            MapScreen(
                customerId = customerId,
                onNavigateBack = { navController.popBackStackSafely() }
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
            val rawFileName = backStackEntry.arguments?.getString("fileName") ?: "attachment"
            val isPhoto = backStackEntry.arguments?.getBoolean("isPhoto") ?: false
            if (mediaId.isBlank()) {
                LaunchedEffect(Unit) { navController.popBackStack() }
                return@composable
            }
            val decodedFileName = try {
                URLDecoder.decode(rawFileName, "UTF-8")
            } catch (e: Exception) {
                rawFileName
            }
            AttachmentPreviewScreen(
                mediaId = mediaId,
                fileName = decodedFileName,
                isPhoto = isPhoto,
                onNavigateBack = { navController.popBackStackSafely() }
            )
        }

        composable(
            route = Screen.VisitSummary.route,
            arguments = listOf(navArgument("visitId") { type = NavType.StringType })
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            if (visitId.isBlank()) {
                LaunchedEffect(Unit) { navController.popBackStack() }
                return@composable
            }
            VisitSummaryScreen(
                visitId = visitId,
                viewModel = visitSummaryViewModel,
                onNavigateBack = { navController.popBackStackSafely() },
                onNavigateToCheckIn = { vId, cId -> navController.navigate(Screen.CheckIn.createRoute(vId, cId)) },
                onNavigateToCheckOut = { vId, cId -> navController.navigate(Screen.CheckOut.createRoute(vId, cId)) },
                onCancel = { navController.popBackStackSafely() }
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
                        popUpTo(Screen.Dashboard.route) { inclusive = false }
                        launchSingleTop = true
                    }
                }
            )
        }

        composable(
            route = Screen.RequirementForm.route,
            arguments = listOf(navArgument("visitId") { type = NavType.StringType })
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            if (visitId.isBlank()) {
                LaunchedEffect(Unit) { navController.popBackStack() }
                return@composable
            }
            RequirementFormScreen(
                visitId = visitId,
                viewModel = requirementViewModel,
                onNavigateBack = { navController.popBackStackSafely() },
                onSubmitSuccess = {
                    navController.popBackStack()
                }
            )
        }

        composable(
            route = Screen.Signature.route,
            arguments = listOf(navArgument("visitId") { type = NavType.StringType })
        ) { backStackEntry ->
            val visitId = backStackEntry.arguments?.getString("visitId") ?: ""
            if (visitId.isBlank()) {
                LaunchedEffect(Unit) { navController.popBackStack() }
                return@composable
            }
            SignatureScreen(
                visitId = visitId,
                viewModel = signatureViewModel,
                onNavigateBack = { navController.popBackStackSafely() },
                onComplete = {
                    navController.popBackStack()
                }
            )
        }
    }
}
