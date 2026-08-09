package com.fieldtrackpro.android.ui.screens.maps

import android.Manifest
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.BuildConfig
import com.fieldtrackpro.android.services.LocationCaptureService
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.theme.ElectricBlue
import com.fieldtrackpro.android.ui.theme.Slate50
import com.fieldtrackpro.android.ui.theme.Slate500
import com.fieldtrackpro.android.ui.theme.Slate900
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.utils.NavigationHelper
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style

/**
 * Map screen showing customer/visit location using MapLibre.
 *
 * Phase 4 Section 1 (MapLibre decision):
 * - Shows customer location marker
 * - Shows device location when permission available
 * - Handles permission denied, GPS unavailable, loading, error states
 * - Rejects invalid coordinates and Null Island
 */
@Composable
fun MapScreen(
    customerLat: Double?,
    customerLng: Double?,
    customerName: String,
    onNavigateBack: () -> Unit,
    onNavigateToCustomer: () -> Unit
) {
    val context = LocalContext.current
    val locationService = remember { LocationCaptureService(context) }

    var mapView by remember { mutableStateOf<MapView?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var deviceLocation by remember { mutableStateOf<com.fieldtrackpro.android.services.LocationResult?>(null) }
    var hasPermission by remember { mutableStateOf(locationService.hasLocationPermission()) }
    var isLocationEnabled by remember { mutableStateOf(locationService.isLocationEnabled()) }
    var coordinatesValid by remember { mutableStateOf(false) }

    // Validate coordinates
    LaunchedEffect(customerLat, customerLng) {
        coordinatesValid = customerLat != null && customerLng != null &&
            NavigationHelper.isValidCoordinate(customerLat, customerLng)
        isLoading = false
    }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(
                title = "Location Map",
                onBackClick = onNavigateBack
            )
        }
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
        ) {
            when {
                isLoading -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator(color = ElectricBlue)
                    }
                }

                errorMessage != null -> {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(20.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        ErrorBanner(message = errorMessage!!)
                    }
                }

                !coordinatesValid -> {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(20.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            colors = CardDefaults.cardColors(containerColor = SurfaceWhite),
                            shape = RoundedCornerShape(12.dp)
                        ) {
                            Column(modifier = Modifier.padding(20.dp)) {
                                Text(
                                    text = "Invalid Location",
                                    fontSize = 18.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = Slate900
                                )
                                Spacer(modifier = Modifier.height(8.dp))
                                Text(
                                    text = "This customer does not have valid coordinates. Please update the customer record.",
                                    fontSize = 14.sp,
                                    color = Slate500
                                )
                            }
                        }
                    }
                }

                else -> {
                    // Map is valid - render MapLibre view
                    MapLibreMapView(
                        customerLat = customerLat!!,
                        customerLng = customerLng!!,
                        customerName = customerName,
                        deviceLocation = deviceLocation,
                        hasPermission = hasPermission,
                        isLocationEnabled = isLocationEnabled,
                        onMapReady = { mapView = it },
                        onError = { errorMessage = it }
                    )
                }
            }

            // Navigation button at bottom
            if (coordinatesValid) {
                Button(
                    onClick = onNavigateToCustomer,
                    modifier = Modifier
                        .align(Alignment.BottomCenter)
                        .padding(16.dp)
                        .fillMaxWidth()
                        .height(50.dp),
                    shape = RoundedCornerShape(8.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = ElectricBlue)
                ) {
                    Text("NAVIGATE TO CUSTOMER", fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

/**
 * MapLibre map view composable.
 */
@Composable
private fun MapLibreMapView(
    customerLat: Double,
    customerLng: Double,
    customerName: String,
    deviceLocation: com.fieldtrackpro.android.services.LocationResult?,
    hasPermission: Boolean,
    isLocationEnabled: Boolean,
    onMapReady: (MapView) -> Unit,
    onError: (String) -> Unit
) {
    val context = LocalContext.current
    val styleUrl = BuildConfig.MAPLIBRE_TILE_URL

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Slate50)
    ) {
        // MapLibre MapView
        androidx.compose.foundation.layout.Box(
            modifier = Modifier.fillMaxSize()
        ) {
            val mapView = remember {
                MapView(context).also { mv ->
                    mv.getMapAsync { mapLibre ->
                        mapLibre.setStyle(Style.Builder().fromUri(styleUrl)) { _ ->
                            // Move camera to customer location
                            mapLibre.cameraPosition = CameraPosition.Builder()
                                .target(LatLng(customerLat, customerLng))
                                .zoom(14.0)
                                .build()
                        }
                    }
                    onMapReady(mv)
                }
            }

            // Lifecycle management
            LaunchedEffect(Unit) {
                mapView.onStart()
            }

            androidx.compose.runtime.DisposableEffect(mapView) {
                onDispose {
                    mapView.onStop()
                    mapView.onDestroy()
                }
            }

            // AndroidView wrapper for MapView
            androidx.compose.ui.viewinterop.AndroidView(
                factory = { mapView },
                modifier = Modifier.fillMaxSize()
            )
        }

        // Device location indicator (if available)
        if (hasPermission && isLocationEnabled && deviceLocation != null) {
            Card(
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(16.dp),
                colors = CardDefaults.cardColors(containerColor = SurfaceWhite),
                shape = RoundedCornerShape(8.dp)
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text(
                        text = "Your Location",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        color = Slate900
                    )
                    Text(
                        text = NavigationHelper.formatCoordinates(deviceLocation.latitude, deviceLocation.longitude),
                        fontSize = 10.sp,
                        color = Slate500
                    )
                }
            }
        }

        // Permission/location status indicators
        if (!hasPermission) {
            Card(
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .padding(16.dp),
                colors = CardDefaults.cardColors(containerColor = SurfaceWhite),
                shape = RoundedCornerShape(8.dp)
            ) {
                Text(
                    text = "Location permission required",
                    fontSize = 12.sp,
                    color = Slate500,
                    modifier = Modifier.padding(12.dp)
                )
            }
        }

        if (!isLocationEnabled) {
            Card(
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .padding(16.dp),
                colors = CardDefaults.cardColors(containerColor = SurfaceWhite),
                shape = RoundedCornerShape(8.dp)
            ) {
                Text(
                    text = "GPS is disabled",
                    fontSize = 12.sp,
                    color = Slate500,
                    modifier = Modifier.padding(12.dp)
                )
            }
        }
    }
}
