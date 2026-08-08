package com.fieldtrackpro.android.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalContext
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.ui.screens.auth.LoginScreen
import com.fieldtrackpro.android.ui.screens.dashboard.DashboardScreen
import com.fieldtrackpro.android.ui.screens.media.MediaUploadScreen
import com.fieldtrackpro.android.ui.screens.profile.ProfileSettingsScreen
import com.fieldtrackpro.android.ui.screens.splash.SplashScreen
import com.fieldtrackpro.android.ui.screens.sync.OfflineQueueScreen
import com.fieldtrackpro.android.ui.screens.visits.CheckInScreen
import com.fieldtrackpro.android.ui.screens.visits.CheckOutScreen
import com.fieldtrackpro.android.ui.screens.visits.TodayVisitsScreen
import com.fieldtrackpro.android.ui.screens.visits.VisitDetailsScreen
import com.fieldtrackpro.android.ui.viewmodel.AuthViewModel
import com.fieldtrackpro.android.ui.viewmodel.CheckInViewModel
import com.fieldtrackpro.android.ui.viewmodel.MediaViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitDetailsViewModel
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
    mediaViewModel: MediaViewModel
) {
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
                onNavigateToSync = { navController.navigate(Screen.OfflineQueue.route) }
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
                onNavigateToMedia = { vId -> navController.navigate(Screen.MediaUpload.createRoute(vId)) }
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
                onNavigateBack = { navController.popBackStack() }
            )
        }

        composable(Screen.ProfileSettings.route) {
            ProfileSettingsScreen(
                tokenManager = tokenManager,
                authViewModel = authViewModel,
                onNavigateBack = { navController.popBackStack() },
                onLogout = {
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
    }
}
