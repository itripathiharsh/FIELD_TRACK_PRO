package com.fieldtrackpro.android.ui.screens.maps

import android.Manifest
import android.content.Context
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Looper
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloseFullscreen
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.Navigation
import androidx.compose.material.icons.filled.OpenInFull
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import com.fieldtrackpro.android.ui.theme.*
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.CustomerRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.services.LocationCaptureService
import com.fieldtrackpro.android.services.LocationResult
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.theme.FieldTrackAmber
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.SurfaceOffWhite
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.theme.TextMuted
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.utils.NavigationHelper
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.sources.GeoJsonSource

private const val OSM_STYLE_JSON = """
{
  "version": 8,
  "sources": {
    "osm": {
      "type": "raster",
      "tiles": [
        "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "https://b.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "https://c.tile.openstreetmap.org/{z}/{x}/{y}.png"
      ],
      "tileSize": 256,
      "attribution": "© OpenStreetMap contributors"
    }
  },
  "layers": [
    {
      "id": "osm-tiles",
      "type": "raster",
      "source": "osm",
      "minzoom": 0,
      "maxzoom": 19
    }
  ]
}
"""

@Composable
fun MapScreen(
    customerId: String,
    onNavigateBack: () -> Unit
) {
    val context = LocalContext.current
    val locationService = remember { LocationCaptureService(context) }

    var customer by remember { mutableStateOf<CustomerDto?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var deviceLocation by remember { mutableStateOf<LocationResult?>(null) }
    var hasPermission by remember { mutableStateOf(locationService.hasLocationPermission()) }
    var isLocationEnabled by remember { mutableStateOf(locationService.isLocationEnabled()) }
    var isExpanded by remember { mutableStateOf(false) }

    // Handle back button when map is expanded
    BackHandler(enabled = isExpanded) {
        isExpanded = false
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        hasPermission = permissions[Manifest.permission.ACCESS_FINE_LOCATION] == true ||
                permissions[Manifest.permission.ACCESS_COARSE_LOCATION] == true
    }

    LaunchedEffect(Unit) {
        if (!hasPermission) {
            permissionLauncher.launch(
                arrayOf(
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION
                )
            )
        }
    }

    // Lifecycle-bound live location listener for real-time salesperson GPS tracking
    DisposableEffect(hasPermission) {
        val locationManager = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager
        val listener = object : LocationListener {
            override fun onLocationChanged(loc: Location) {
                deviceLocation = LocationResult(
                    latitude = loc.latitude,
                    longitude = loc.longitude,
                    accuracy = loc.accuracy,
                    isMockLocation = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) loc.isMock else false,
                    timestamp = loc.time
                )
            }
            override fun onProviderEnabled(provider: String) { isLocationEnabled = true }
            override fun onProviderDisabled(provider: String) {}
        }

        if (hasPermission && locationManager != null) {
            try {
                // Get last known location immediately
                val lastGps = locationManager.getLastKnownLocation(LocationManager.GPS_PROVIDER)
                val lastNet = locationManager.getLastKnownLocation(LocationManager.NETWORK_PROVIDER)
                val bestLast = when {
                    lastGps != null && lastNet != null -> if (lastGps.time > lastNet.time) lastGps else lastNet
                    lastGps != null -> lastGps
                    else -> lastNet
                }
                if (bestLast != null) {
                    deviceLocation = LocationResult(
                        latitude = bestLast.latitude,
                        longitude = bestLast.longitude,
                        accuracy = bestLast.accuracy,
                        isMockLocation = if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S) bestLast.isMock else false,
                        timestamp = bestLast.time
                    )
                }

                if (locationManager.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
                    locationManager.requestLocationUpdates(
                        LocationManager.GPS_PROVIDER,
                        2000L,
                        1f,
                        listener,
                        Looper.getMainLooper()
                    )
                }
                if (locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                    locationManager.requestLocationUpdates(
                        LocationManager.NETWORK_PROVIDER,
                        2000L,
                        1f,
                        listener,
                        Looper.getMainLooper()
                    )
                }
            } catch (e: SecurityException) {
                // Ignore permission issue
            }
        }

        onDispose {
            try {
                locationManager?.removeUpdates(listener)
            } catch (e: Exception) {}
        }
    }

    LaunchedEffect(customerId) {
        try {
            val tokenManager = TokenManager(context)
            val customerRepository = CustomerRepository(
                customerApi = ApiClient.createCustomerApi(tokenManager)
            )
            when (val result = customerRepository.getCustomerById(customerId)) {
                is Resource.Success -> {
                    customer = result.data
                    isLoading = false
                }
                is Resource.Error -> {
                    errorMessage = result.message
                    isLoading = false
                }
                else -> {
                    isLoading = false
                }
            }
        } catch (e: Exception) {
            errorMessage = "Failed to load customer: ${e.localizedMessage}"
            isLoading = false
        }
    }

    Scaffold(
        topBar = {
            if (!isExpanded) {
                FieldTrackTopAppBar(
                    title = customer?.let { "Location: ${it.name}" } ?: "Location Map",
                    onBackClick = onNavigateBack
                )
            }
        }
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(if (isExpanded) androidx.compose.foundation.layout.PaddingValues(0.dp) else innerPadding)
                .background(SurfaceOffWhite)
        ) {
            when {
                isLoading -> {
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator(color = FieldTrackNavy)
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

                customer == null -> {
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
                                    text = "Customer Not Found",
                                    style = MaterialTheme.typography.titleLarge,
                                    color = FieldTrackNavy
                                )
                                Spacer(modifier = Modifier.height(8.dp))
                                Text(
                                    text = "The requested customer could not be found.",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = TextMuted
                                )
                            }
                        }
                    }
                }

                else -> {
                    val cust = customer!!
                    val lat = cust.latitude
                    val lng = cust.longitude
                    val coordinatesValid = NavigationHelper.isValidCoordinate(lat, lng)

                    if (!coordinatesValid) {
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
                                        style = MaterialTheme.typography.titleLarge,
                                        color = FieldTrackNavy
                                    )
                                    Spacer(modifier = Modifier.height(8.dp))
                                    Text(
                                        text = "This customer does not have valid coordinates. Please update the customer record.",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = TextMuted
                                    )
                                }
                            }
                        }
                    } else {
                        // Dynamic Geodesic Distance
                        val distanceM = if (deviceLocation != null) {
                            LocationCaptureService.calculateDistanceM(
                                deviceLocation!!.latitude,
                                deviceLocation!!.longitude,
                                lat,
                                lng
                            )
                        } else null

                        val distanceText = distanceM?.let { dist ->
                            if (dist < 1000) "${dist.toInt()} m" else String.format(java.util.Locale.US, "%.1f km", dist / 1000.0)
                        }

                        if (isExpanded) {
                            // ==================== EXPANDED FULLSCREEN MAP ====================
                            Box(modifier = Modifier.fillMaxSize()) {
                                MapLibreMapView(
                                    customerLat = lat,
                                    customerLng = lng,
                                    customerName = cust.name,
                                    customerId = cust.id,
                                    geofenceRadiusM = cust.geofenceRadiusM,
                                    deviceLocation = deviceLocation,
                                    modifier = Modifier.fillMaxSize(),
                                    onError = { errorMessage = it }
                                )

                                // Floating Top Controls: Back/Collapse & Distance Info
                                Surface(
                                    modifier = Modifier
                                        .align(Alignment.TopCenter)
                                        .padding(top = 40.dp, start = 16.dp, end = 16.dp)
                                        .fillMaxWidth(),
                                    shape = RoundedCornerShape(16.dp),
                                    color = SurfaceWhite.copy(alpha = 0.95f),
                                    shadowElevation = 6.dp
                                ) {
                                    Row(
                                        modifier = Modifier
                                            .padding(horizontal = 14.dp, vertical = 10.dp)
                                            .fillMaxWidth(),
                                        verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.SpaceBetween
                                    ) {
                                        Row(
                                            verticalAlignment = Alignment.CenterVertically,
                                            modifier = Modifier.weight(1f)
                                        ) {
                                            IconButton(
                                                onClick = { isExpanded = false },
                                                modifier = Modifier.size(36.dp)
                                            ) {
                                                Icon(
                                                    imageVector = Icons.Filled.CloseFullscreen,
                                                    contentDescription = "Collapse Map",
                                                    tint = FieldTrackNavy
                                                )
                                            }
                                            Spacer(modifier = Modifier.width(8.dp))
                                            Column {
                                                Text(
                                                    text = cust.name,
                                                    fontWeight = FontWeight.Bold,
                                                    fontSize = 14.sp,
                                                    color = TextPrimary,
                                                    maxLines = 1
                                                )
                                                if (distanceText != null) {
                                                    Text(
                                                        text = "Distance: $distanceText",
                                                        fontSize = 12.sp,
                                                        fontWeight = FontWeight.SemiBold,
                                                        color = Color(0xFF2563EB)
                                                    )
                                                }
                                            }
                                        }

                                        // Map Legend
                                        MapLegendChip()
                                    }
                                }

                                // Sticky Bottom Navigation Button
                                Surface(
                                    modifier = Modifier
                                        .align(Alignment.BottomCenter)
                                        .fillMaxWidth(),
                                    color = SurfaceWhite.copy(alpha = 0.95f),
                                    shadowElevation = 12.dp
                                ) {
                                    Column(
                                        modifier = Modifier.padding(16.dp)
                                    ) {
                                        Button(
                                            onClick = {
                                                NavigationHelper.navigateToCustomer(context, lat, lng, cust.name)
                                            },
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .height(52.dp),
                                            shape = RoundedCornerShape(10.dp),
                                            colors = ButtonDefaults.buttonColors(
                                                containerColor = FieldTrackNavy,
                                                contentColor = SurfaceWhite
                                            )
                                        ) {
                                            Icon(
                                                imageVector = Icons.Filled.Navigation,
                                                contentDescription = null,
                                                tint = SurfaceWhite,
                                                modifier = Modifier.size(18.dp)
                                            )
                                            Spacer(modifier = Modifier.width(8.dp))
                                            Text(
                                                "NAVIGATE TO CUSTOMER",
                                                fontWeight = FontWeight.Bold,
                                                fontSize = 14.sp,
                                                color = SurfaceWhite
                                            )
                                        }
                                    }
                                }
                            }
                        } else {
                            // ==================== COLLAPSED COMPACT MAP VIEW ====================
                            Column(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .verticalScroll(rememberScrollState())
                                    .padding(bottom = 80.dp)
                            ) {
                                // 1. Map Preview Card
                                Box(
                                    modifier = Modifier
                                        .padding(16.dp)
                                        .fillMaxWidth()
                                        .height(280.dp)
                                        .shadow(4.dp, shape = RoundedCornerShape(16.dp))
                                        .clip(RoundedCornerShape(16.dp))
                                        .background(SurfaceWhite)
                                ) {
                                    MapLibreMapView(
                                        customerLat = lat,
                                        customerLng = lng,
                                        customerName = cust.name,
                                        customerId = cust.id,
                                        geofenceRadiusM = cust.geofenceRadiusM,
                                        deviceLocation = deviceLocation,
                                        modifier = Modifier.fillMaxSize(),
                                        onError = { errorMessage = it }
                                    )

                                    // Floating Map Legend on Top Left
                                    Box(
                                        modifier = Modifier
                                            .align(Alignment.TopStart)
                                            .padding(10.dp)
                                    ) {
                                        MapLegendChip()
                                    }

                                    // Floating Expand Button on Top Right
                                    Surface(
                                        modifier = Modifier
                                            .align(Alignment.TopEnd)
                                            .padding(10.dp)
                                            .clickable { isExpanded = true },
                                        shape = RoundedCornerShape(8.dp),
                                        color = SurfaceWhite.copy(alpha = 0.92f),
                                        shadowElevation = 3.dp
                                    ) {
                                        Row(
                                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Icon(
                                                imageVector = Icons.Filled.OpenInFull,
                                                contentDescription = "Expand Map",
                                                tint = FieldTrackNavy,
                                                modifier = Modifier.size(15.dp)
                                            )
                                            Spacer(modifier = Modifier.width(4.dp))
                                            Text(
                                                text = "Expand",
                                                fontSize = 12.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = FieldTrackNavy
                                            )
                                        }
                                    }
                                }

                                // 2. Detailed Information Card
                                Card(
                                    modifier = Modifier
                                        .padding(horizontal = 16.dp)
                                        .fillMaxWidth(),
                                    colors = CardDefaults.cardColors(containerColor = SurfaceWhite),
                                    shape = RoundedCornerShape(16.dp),
                                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                                ) {
                                    Column(modifier = Modifier.padding(18.dp)) {
                                        // Header Row: Outlet Name & Live Distance Badge
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.SpaceBetween,
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Column(modifier = Modifier.weight(1f)) {
                                                Text(
                                                    text = cust.name,
                                                    fontSize = 16.sp,
                                                    fontWeight = FontWeight.Bold,
                                                    color = TextPrimary
                                                )
                                                Text(
                                                    text = "Outlet ID: ${cust.id.take(8)}",
                                                    fontSize = 11.sp,
                                                    color = TextMuted
                                                )
                                            }
                                             if (distanceText != null) {
                                                Surface(
                                                    shape = RoundedCornerShape(8.dp),
                                                    color = BrandGoldLight
                                                ) {
                                                    Text(
                                                        text = distanceText,
                                                        fontSize = 14.sp,
                                                        fontWeight = FontWeight.Bold,
                                                        color = BrandNavy,
                                                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp)
                                                    )
                                                }
                                            }
                                        }

                                        Spacer(modifier = Modifier.height(14.dp))

                                        // Salesperson (You) Live Coordinates Row
                                        Row(
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .background(SurfaceSecondary, shape = RoundedCornerShape(10.dp))
                                                .padding(12.dp),
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Box(
                                                modifier = Modifier
                                                    .size(12.dp)
                                                    .background(BrandNavy, shape = CircleShape)
                                                    .border(2.dp, BrandWhite, CircleShape)
                                            )
                                            Spacer(modifier = Modifier.width(10.dp))
                                            Column {
                                                Text(
                                                    text = "You (Live GPS)",
                                                    fontSize = 12.sp,
                                                    fontWeight = FontWeight.Bold,
                                                    color = BrandNavy
                                                )
                                                if (deviceLocation != null) {
                                                    Text(
                                                        text = "Lat: ${String.format(java.util.Locale.US, "%.6f", deviceLocation!!.latitude)}, Lng: ${String.format(java.util.Locale.US, "%.6f", deviceLocation!!.longitude)}",
                                                        fontSize = 11.sp,
                                                        color = TextPrimary
                                                    )
                                                } else {

                                                    Text(
                                                        text = "Acquiring live GPS fix...",
                                                        fontSize = 11.sp,
                                                        color = FieldTrackAmber
                                                    )
                                                }
                                            }
                                        }

                                        Spacer(modifier = Modifier.height(10.dp))

                                        // Customer Outlet Coordinates Row
                                        Row(
                                            modifier = Modifier
                                                .fillMaxWidth()
                                                .background(Color(0xFFFFFBEB), shape = RoundedCornerShape(10.dp))
                                                .padding(12.dp),
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Box(
                                                modifier = Modifier
                                                    .size(12.dp)
                                                    .background(Color(0xFFDC2626), shape = CircleShape)
                                                    .border(2.dp, Color.White, CircleShape)
                                            )
                                            Spacer(modifier = Modifier.width(10.dp))
                                            Column {
                                                Text(
                                                    text = "Customer Outlet",
                                                    fontSize = 12.sp,
                                                    fontWeight = FontWeight.Bold,
                                                    color = Color(0xFF991B1B)
                                                )
                                                Text(
                                                    text = "Lat: ${String.format(java.util.Locale.US, "%.6f", lat)}, Lng: ${String.format(java.util.Locale.US, "%.6f", lng)}",
                                                    fontSize = 11.sp,
                                                    color = TextPrimary
                                                )
                                            }
                                        }

                                        Spacer(modifier = Modifier.height(10.dp))

                                        // Geofence info badge
                                        Text(
                                            text = "Geofence Radius: ${cust.geofenceRadiusM} meters around outlet",
                                            fontSize = 11.sp,
                                            color = TextMuted
                                        )
                                    }
                                }

                                Spacer(modifier = Modifier.height(20.dp))
                            }

                            // Sticky Bottom Navigation Button in Collapsed Mode
                            Surface(
                                modifier = Modifier
                                    .align(Alignment.BottomCenter)
                                    .fillMaxWidth(),
                                color = SurfaceWhite,
                                shadowElevation = 10.dp
                            ) {
                                Box(modifier = Modifier.padding(16.dp)) {
                                    Button(
                                        onClick = {
                                            NavigationHelper.navigateToCustomer(context, lat, lng, cust.name)
                                        },
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .height(52.dp),
                                        shape = RoundedCornerShape(10.dp),
                                        colors = ButtonDefaults.buttonColors(
                                            containerColor = FieldTrackNavy,
                                            contentColor = SurfaceWhite
                                        )
                                    ) {
                                        Icon(
                                            imageVector = Icons.Filled.Navigation,
                                            contentDescription = null,
                                            tint = SurfaceWhite,
                                            modifier = Modifier.size(18.dp)
                                        )
                                        Spacer(modifier = Modifier.width(8.dp))
                                        Text(
                                            "NAVIGATE TO CUSTOMER",
                                            fontWeight = FontWeight.Bold,
                                            fontSize = 14.sp,
                                            color = SurfaceWhite
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MapLegendChip() {
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = SurfaceWhite.copy(alpha = 0.95f),
        shadowElevation = 3.dp
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Blue You dot
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .background(Color(0xFF2563EB), shape = CircleShape)
            )
            Spacer(modifier = Modifier.width(4.dp))
            Text("You", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = TextPrimary)

            Spacer(modifier = Modifier.width(10.dp))

            // Red Customer dot
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .background(Color(0xFFDC2626), shape = CircleShape)
            )
            Spacer(modifier = Modifier.width(4.dp))
            Text("Customer", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = TextPrimary)
        }
    }
}

/**
 * Calculates optimal camera center and zoom level to frame both locations smoothly.
 */
private fun calculateCameraForLocations(
    customerLat: Double,
    customerLng: Double,
    userLocation: LocationResult?
): Pair<LatLng, Double> {
    if (userLocation == null) {
        return LatLng(customerLat, customerLng) to 15.2
    }
    val centerLat = (customerLat + userLocation.latitude) / 2.0
    val centerLng = (customerLng + userLocation.longitude) / 2.0
    val latDiff = Math.abs(customerLat - userLocation.latitude)
    val lngDiff = Math.abs(customerLng - userLocation.longitude)
    val maxDiff = maxOf(latDiff, lngDiff * 1.2)

    val zoom = when {
        maxDiff > 3.0 -> 6.5
        maxDiff > 1.5 -> 7.5
        maxDiff > 0.8 -> 8.5
        maxDiff > 0.4 -> 9.5
        maxDiff > 0.2 -> 10.5
        maxDiff > 0.08 -> 11.8 // ~10-15 km
        maxDiff > 0.04 -> 12.8 // ~4-8 km
        maxDiff > 0.02 -> 13.8 // ~2-4 km
        maxDiff > 0.01 -> 14.8 // ~1-2 km
        maxDiff > 0.003 -> 15.8 // ~300-800m
        else -> 16.5 // < 300m
    }
    return LatLng(centerLat, centerLng) to zoom
}

private fun buildUserGeoJson(location: LocationResult?): String {
    if (location == null) {
        return """{"type":"FeatureCollection","features":[]}"""
    }
    return """{"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[${location.longitude},${location.latitude}]},"properties":{"type":"user","title":"You"}}]}"""
}

@Composable
private fun MapLibreMapView(
    customerLat: Double,
    customerLng: Double,
    customerName: String,
    customerId: String,
    geofenceRadiusM: Int,
    deviceLocation: LocationResult?,
    modifier: Modifier = Modifier,
    onError: (String) -> Unit
) {
    val context = LocalContext.current
    var mapLibreInstance by remember { mutableStateOf<org.maplibre.android.maps.MapLibreMap?>(null) }
    var mapStyleInstance by remember { mutableStateOf<Style?>(null) }

    // Re-frame camera and update user marker whenever deviceLocation changes
    LaunchedEffect(deviceLocation, mapLibreInstance, mapStyleInstance) {
        val map = mapLibreInstance
        val style = mapStyleInstance
        if (map != null && style != null) {
            try {
                val userSource = style.getSourceAs<GeoJsonSource>("user-source")
                userSource?.setGeoJson(buildUserGeoJson(deviceLocation))

                val (targetCenter, targetZoom) = calculateCameraForLocations(
                    customerLat,
                    customerLng,
                    deviceLocation
                )
                map.easeCamera(
                    CameraUpdateFactory.newCameraPosition(
                        CameraPosition.Builder()
                            .target(targetCenter)
                            .zoom(targetZoom)
                            .build()
                    ),
                    800
                )
            } catch (e: Exception) {
                // Ignore transient update issue
            }
        }
    }

    Box(modifier = modifier) {
        val mapView = remember {
            try {
                org.maplibre.android.MapLibre.getInstance(context)
            } catch (e: Exception) {
                // Ignore if already initialized
            }
            MapView(context).also { mv ->
                mv.getMapAsync { mapLibre ->
                    mapLibreInstance = mapLibre
                    try {
                        mapLibre.setStyle(Style.Builder().fromJson(OSM_STYLE_JSON)) { style ->
                            mapStyleInstance = style

                            // Initial camera framing
                            val (initialCenter, initialZoom) = calculateCameraForLocations(
                                customerLat,
                                customerLng,
                                deviceLocation
                            )
                            mapLibre.cameraPosition = CameraPosition.Builder()
                                .target(initialCenter)
                                .zoom(initialZoom)
                                .build()

                            // 1. Customer Geofence & Pin Source (RED/AMBER MARKER)
                            val customerGeoJson = buildString {
                                append("""{"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[$customerLng,$customerLat]},"properties":{"name":""")
                                append(customerName.replace("\"", "\\\""))
                                append(""","id":"$customerId","radius":$geofenceRadiusM,"type":"customer"}}]}""")
                            }
                            val customerSource = GeoJsonSource("customer-source", customerGeoJson)
                            style.addSource(customerSource)

                            // Customer Geofence Halo
                            val geofenceLayer = CircleLayer("customer-geofence", "customer-source")
                            geofenceLayer.setProperties(
                                PropertyFactory.circleColor("#EF444426"),
                                PropertyFactory.circleRadius(geofenceRadiusM.toFloat()),
                                PropertyFactory.circleStrokeWidth(1.5f),
                                PropertyFactory.circleStrokeColor("#EF4444")
                            )
                            style.addLayer(geofenceLayer)

                            // Customer Main Pin Circle (Red with thick white border)
                            val customerCircleLayer = CircleLayer("customer-circle", "customer-source")
                            customerCircleLayer.setProperties(
                                PropertyFactory.circleColor("#DC2626"),
                                PropertyFactory.circleRadius(12f),
                                PropertyFactory.circleStrokeWidth(3.5f),
                                PropertyFactory.circleStrokeColor("#FFFFFF")
                            )
                            style.addLayer(customerCircleLayer)

                            // Customer Inner Pin Center Dot
                            val customerInnerDot = CircleLayer("customer-inner-dot", "customer-source")
                            customerInnerDot.setProperties(
                                PropertyFactory.circleColor("#7F1D1D"),
                                PropertyFactory.circleRadius(5f)
                            )
                            style.addLayer(customerInnerDot)

                            // 2. Salesperson Live GPS Source (VIBRANT BLUE MARKER)
                            val userSource = GeoJsonSource("user-source", buildUserGeoJson(deviceLocation))
                            style.addSource(userSource)

                            // Salesperson Pulse Ring
                            val userPulseLayer = CircleLayer("user-pulse", "user-source")
                            userPulseLayer.setProperties(
                                PropertyFactory.circleColor("#3B82F633"),
                                PropertyFactory.circleRadius(22f)
                            )
                            style.addLayer(userPulseLayer)

                            // Salesperson Main Dot (Vibrant Blue with white border)
                            val userCircleLayer = CircleLayer("user-circle", "user-source")
                            userCircleLayer.setProperties(
                                PropertyFactory.circleColor("#2563EB"),
                                PropertyFactory.circleRadius(10f),
                                PropertyFactory.circleStrokeWidth(3.5f),
                                PropertyFactory.circleStrokeColor("#FFFFFF")
                            )
                            style.addLayer(userCircleLayer)

                            // Salesperson Inner Dot
                            val userInnerDot = CircleLayer("user-inner-dot", "user-source")
                            userInnerDot.setProperties(
                                PropertyFactory.circleColor("#1D4ED8"),
                                PropertyFactory.circleRadius(4f)
                            )
                            style.addLayer(userInnerDot)
                        }
                    } catch (e: Exception) {
                        onError("Map error: ${e.localizedMessage}")
                    }
                }
            }
        }

        LaunchedEffect(Unit) {
            mapView.onStart()
        }

        DisposableEffect(mapView) {
            onDispose {
                mapView.onStop()
                mapView.onDestroy()
            }
        }

        androidx.compose.ui.viewinterop.AndroidView(
            factory = { mapView },
            modifier = Modifier.fillMaxSize()
        )

        // Floating Recenter / Fit Both Button (Bottom Right)
        Surface(
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(10.dp)
                .clickable {
                    mapLibreInstance?.let { map ->
                        val (targetCenter, targetZoom) = calculateCameraForLocations(
                            customerLat,
                            customerLng,
                            deviceLocation
                        )
                        map.easeCamera(
                            CameraUpdateFactory.newCameraPosition(
                                CameraPosition.Builder()
                                    .target(targetCenter)
                                    .zoom(targetZoom)
                                    .build()
                            ),
                            800
                        )
                    }
                },
            shape = CircleShape,
            color = SurfaceWhite.copy(alpha = 0.95f),
            shadowElevation = 4.dp
        ) {
            Box(
                modifier = Modifier.padding(8.dp),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    imageVector = Icons.Filled.MyLocation,
                    contentDescription = "Fit Both Locations",
                    tint = BrandNavy,
                    modifier = Modifier.size(20.dp)
                )
            }
        }
    }
}

