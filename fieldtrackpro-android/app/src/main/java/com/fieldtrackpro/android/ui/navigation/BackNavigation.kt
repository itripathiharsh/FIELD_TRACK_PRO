package com.fieldtrackpro.android.ui.navigation

import androidx.lifecycle.Lifecycle
import androidx.navigation.NavController

/**
 * Double-tap protection for back/up navigation.
 *
 * Every screen used to call popBackStack() unconditionally, so two quick taps on a back arrow popped two
 * destinations and could pop the dashboard itself, leaving an empty screen. A pop is now only allowed from a
 * destination that is fully RESUMED (the second tap lands while the first transition is running, when the
 * destination underneath is not resumed yet) and never pops the last destination.
 */
object BackNavigationGuard {
    fun canPop(currentState: Lifecycle.State?, hasPreviousDestination: Boolean): Boolean =
        hasPreviousDestination && currentState == Lifecycle.State.RESUMED
}

fun NavController.popBackStackSafely(): Boolean {
    val allowed = BackNavigationGuard.canPop(
        currentState = currentBackStackEntry?.lifecycle?.currentState,
        hasPreviousDestination = previousBackStackEntry != null
    )
    return allowed && popBackStack()
}
