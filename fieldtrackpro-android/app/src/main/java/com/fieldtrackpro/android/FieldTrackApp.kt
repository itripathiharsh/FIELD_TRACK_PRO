package com.fieldtrackpro.android

import android.app.Application
import org.maplibre.android.MapLibre

class FieldTrackApp : Application() {
    override fun onCreate() {
        super.onCreate()
        try {
            MapLibre.getInstance(this)
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
}
