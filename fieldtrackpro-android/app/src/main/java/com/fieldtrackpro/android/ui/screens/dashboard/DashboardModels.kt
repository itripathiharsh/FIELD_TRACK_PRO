package com.fieldtrackpro.android.ui.screens.dashboard

import com.fieldtrackpro.android.data.model.EmployeeWorkdayResponseDto
import com.fieldtrackpro.android.data.model.VisitDto
import com.fieldtrackpro.android.ui.viewmodel.VisitsState
import com.fieldtrackpro.android.utils.DateTimeUtils

enum class WorkdayStatus { NOT_STARTED, STARTED, COMPLETED, UNKNOWN }

data class BeatItem(val id: String, val name: String, val timeLabel: String, val status: String)

sealed class BeatUi {
    object Loading : BeatUi()
    data class Error(val message: String) : BeatUi()
    data class Loaded(val planned: List<BeatItem>, val plannedTotal: Int) : BeatUi()
}

/** Everything the dashboard draws. Built by [DashboardUiMapper]; rendered by DashboardContent (stateless). */
data class DashboardUi(
    val greeting: String,
    val userName: String,
    val dateLabel: String,
    val workdayStatus: WorkdayStatus,
    val workdayDetail: String?,
    val isWorkdayLoading: Boolean,
    val isCapturingLocation: Boolean,
    val isSubmitting: Boolean,
    val workdayError: String?,
    val visitsDone: Int,
    val visitsTotal: Int,
    val adhocVisits: Int,
    val collectedToday: Double,
    val notVerified: Double,
    val verified: Double,
    val beat: BeatUi,
    val pendingOffline: Int
)

object DashboardUiMapper {

    fun greetingFor(hourOfDay: Int): String = when {
        hourOfDay < 12 -> "Good morning"
        hourOfDay < 17 -> "Good afternoon"
        else -> "Good evening"
    }

    fun workdayStatus(workday: EmployeeWorkdayResponseDto?, loadedOnce: Boolean): WorkdayStatus =
        when (workday?.session?.status?.uppercase()) {
            "STARTED" -> WorkdayStatus.STARTED
            "COMPLETED" -> WorkdayStatus.COMPLETED
            null -> if (loadedOnce) WorkdayStatus.NOT_STARTED else WorkdayStatus.UNKNOWN
            else -> WorkdayStatus.NOT_STARTED
        }

    /**
     * KPI numbers: the server's daily summary when available, otherwise counts from today's visit list.
     * "Not verified" = total - verified: the summary API does not split pending from rejected, so the label must not
     * claim the money is pending.
     */
    fun build(
        greeting: String,
        userName: String,
        dateLabel: String,
        workday: EmployeeWorkdayResponseDto?,
        workdayLoadedOnce: Boolean,
        isWorkdayLoading: Boolean,
        isCapturingLocation: Boolean,
        isSubmitting: Boolean,
        workdayError: String?,
        visitsState: VisitsState,
        pendingOffline: Int
    ): DashboardUi {
        val visits: List<VisitDto> = (visitsState as? VisitsState.Success)?.visits.orEmpty()
        val summary = workday?.summary
        val planned = visits.filter { !it.isAdHoc }
        val status = workdayStatus(workday, workdayLoadedOnce)
        val session = workday?.session
        val detail = when (status) {
            WorkdayStatus.STARTED -> "Clocked in at ${DateTimeUtils.formatDisplayTime(session?.startTime)}"
            WorkdayStatus.COMPLETED ->
                "${DateTimeUtils.formatDisplayTime(session?.startTime)} – ${DateTimeUtils.formatDisplayTime(session?.endTime)}"
            WorkdayStatus.NOT_STARTED -> "Start your day with GPS to begin visits"
            WorkdayStatus.UNKNOWN -> null
        }
        val total = summary?.collectionsTotalAmount ?: 0.0
        val verified = summary?.collectionsVerifiedAmount ?: 0.0
        val beat = when (visitsState) {
            is VisitsState.Loading -> BeatUi.Loading
            is VisitsState.Error -> BeatUi.Error(visitsState.message)
            is VisitsState.Success -> BeatUi.Loaded(
                planned = planned.take(5).map {
                    BeatItem(
                        id = it.id,
                        name = it.customerName ?: "Customer #${it.customerId.take(8)}",
                        timeLabel = DateTimeUtils.formatDisplayTime(it.scheduledAt),
                        status = it.status
                    )
                },
                plannedTotal = planned.size
            )
        }
        return DashboardUi(
            greeting = greeting,
            userName = userName,
            dateLabel = dateLabel,
            workdayStatus = status,
            workdayDetail = detail,
            isWorkdayLoading = isWorkdayLoading,
            isCapturingLocation = isCapturingLocation,
            isSubmitting = isSubmitting,
            workdayError = workdayError,
            visitsDone = summary?.completedVisits ?: visits.count { it.status.equals("COMPLETED", ignoreCase = true) },
            visitsTotal = summary?.totalVisits ?: visits.size,
            adhocVisits = summary?.adhocVisits ?: visits.count { it.isAdHoc },
            collectedToday = total,
            notVerified = (total - verified).coerceAtLeast(0.0),
            verified = verified,
            beat = beat,
            pendingOffline = pendingOffline
        )
    }
}
