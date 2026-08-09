package com.fieldtrackpro.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.compose.rememberNavController
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.ui.navigation.NavGraph
import com.fieldtrackpro.android.ui.theme.FieldTrackProTheme
import com.fieldtrackpro.android.ui.viewmodel.AuthViewModel
import com.fieldtrackpro.android.ui.viewmodel.CheckInViewModel
import com.fieldtrackpro.android.ui.viewmodel.MediaViewModel
import com.fieldtrackpro.android.ui.viewmodel.RequirementViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitDetailsViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val tokenManager = TokenManager(applicationContext)
        val offlineQueueManager = OfflineQueueManager(applicationContext)

        val authViewModel = AuthViewModel(tokenManager)
        val visitsViewModel = VisitsViewModel(tokenManager, offlineQueueManager)
        val visitDetailsViewModel = VisitDetailsViewModel(tokenManager, offlineQueueManager)
        val checkInViewModel = CheckInViewModel(tokenManager, offlineQueueManager)
        val mediaViewModel = MediaViewModel(tokenManager)
        val requirementViewModel = RequirementViewModel(tokenManager)

        setContent {
            FieldTrackProTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val navController = rememberNavController()
                    NavGraph(
                        navController = navController,
                        tokenManager = tokenManager,
                        offlineQueueManager = offlineQueueManager,
                        authViewModel = authViewModel,
                        visitsViewModel = visitsViewModel,
                        visitDetailsViewModel = visitDetailsViewModel,
                        checkInViewModel = checkInViewModel,
                        mediaViewModel = mediaViewModel,
                        requirementViewModel = requirementViewModel
                    )
                }
            }
        }
    }
}
