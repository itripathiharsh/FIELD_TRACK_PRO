package com.fieldtrackpro.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.compose.rememberNavController
import com.fieldtrackpro.android.data.local.OfflineQueueManager
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.ui.navigation.NavGraph
import com.fieldtrackpro.android.ui.theme.FieldTrackProTheme
import com.fieldtrackpro.android.ui.viewmodel.AuthViewModel
import com.fieldtrackpro.android.ui.viewmodel.CheckInViewModel
import com.fieldtrackpro.android.ui.viewmodel.CollectionViewModel
import com.fieldtrackpro.android.ui.viewmodel.FormFillViewModel
import com.fieldtrackpro.android.ui.viewmodel.GeofenceViewModel
import com.fieldtrackpro.android.ui.viewmodel.MediaViewModel
import com.fieldtrackpro.android.ui.viewmodel.NotificationViewModel
import com.fieldtrackpro.android.ui.viewmodel.RequirementViewModel
import com.fieldtrackpro.android.ui.viewmodel.SignatureViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitDetailsViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitSummaryViewModel
import com.fieldtrackpro.android.ui.viewmodel.VisitsViewModel
import com.fieldtrackpro.android.workers.OfflineSyncScheduler

/**
 * P1-7: every ViewModel here is retrieved through a [androidx.lifecycle.ViewModelProvider]
 * via the `by viewModels { ... }` delegate, never by a plain constructor call
 * in [onCreate]. `onCreate` re-runs on every configuration change (e.g.
 * rotation), and a plain `val vm = XViewModel(...)` there rebuilds every
 * ViewModel from scratch each time - silently discarding whatever
 * in-progress form/upload/check-in state it held. The Activity's
 * ViewModelStore is retained across a config-change-triggered recreate by
 * platform contract: the factory lambda below only runs on the *first*
 * creation, and every subsequent `onCreate` (after rotation) retrieves the
 * exact same instance instead. This is the platform-guaranteed mechanism for
 * this problem, not something that needs a rememberSaveable workaround.
 *
 * `formFillViewModel`, `signatureViewModel`, `visitSummaryViewModel`, and
 * `collectionViewModel` were previously not constructed here at all - they
 * fell back to default-parameter *expressions* in NavGraph's signature,
 * which Kotlin re-evaluates (constructing a brand-new instance) on every
 * recomposition of that call site, not just a configuration change. They are
 * now constructed exactly like every other ViewModel here and passed down
 * explicitly, matching NavGraph's now-fully-required parameter list.
 */
class MainActivity : ComponentActivity() {

    private val tokenManager by lazy { TokenManager(applicationContext) }
    private val offlineQueueManager by lazy { OfflineQueueManager(applicationContext) }

    private val authViewModel by viewModels<AuthViewModel> {
        viewModelFactory { initializer { AuthViewModel(tokenManager) } }
    }
    private val visitsViewModel by viewModels<VisitsViewModel> {
        viewModelFactory { initializer { VisitsViewModel(tokenManager, offlineQueueManager) } }
    }
    private val visitDetailsViewModel by viewModels<VisitDetailsViewModel> {
        viewModelFactory { initializer { VisitDetailsViewModel(tokenManager, offlineQueueManager) } }
    }
    private val checkInViewModel by viewModels<CheckInViewModel> {
        viewModelFactory { initializer { CheckInViewModel(application, tokenManager, offlineQueueManager) } }
    }
    private val mediaViewModel by viewModels<MediaViewModel> {
        viewModelFactory { initializer { MediaViewModel(application, tokenManager) } }
    }
    private val requirementViewModel by viewModels<RequirementViewModel> {
        viewModelFactory { initializer { RequirementViewModel(tokenManager) } }
    }
    private val geofenceViewModel by viewModels<GeofenceViewModel> {
        viewModelFactory { initializer { GeofenceViewModel(application) } }
    }
    private val notificationViewModel by viewModels<NotificationViewModel> {
        viewModelFactory { initializer { NotificationViewModel(tokenManager) } }
    }
    private val formFillViewModel by viewModels<FormFillViewModel> {
        viewModelFactory { initializer { FormFillViewModel(tokenManager) } }
    }
    private val signatureViewModel by viewModels<SignatureViewModel> {
        viewModelFactory { initializer { SignatureViewModel(application, tokenManager) } }
    }
    private val visitSummaryViewModel by viewModels<VisitSummaryViewModel> {
        viewModelFactory { initializer { VisitSummaryViewModel(tokenManager, offlineQueueManager) } }
    }
    private val collectionViewModel by viewModels<CollectionViewModel> {
        viewModelFactory { initializer { CollectionViewModel(tokenManager) } }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Anything left in the offline queue from a previous session (e.g.
        // the app was killed before the rep reopened Offline Queue and
        // synced manually) still gets picked up automatically the next time
        // connectivity is available - not just newly-queued actions.
        OfflineSyncScheduler.scheduleSync(application)

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
                        requirementViewModel = requirementViewModel,
                        geofenceViewModel = geofenceViewModel,
                        notificationViewModel = notificationViewModel,
                        formFillViewModel = formFillViewModel,
                        signatureViewModel = signatureViewModel,
                        visitSummaryViewModel = visitSummaryViewModel,
                        collectionViewModel = collectionViewModel
                    )
                }
            }
        }
    }
}
