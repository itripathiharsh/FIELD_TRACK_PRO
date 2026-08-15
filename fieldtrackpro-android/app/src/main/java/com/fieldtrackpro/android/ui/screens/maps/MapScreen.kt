package com.fieldtrackpro.android.ui.screens.maps

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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.BuildConfig
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.data.repository.CustomerRepository
import com.fieldtrackpro.android.data.repository.Resource
import com.fieldtrackpro.android.services.LocationCaptureService
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.SurfaceOffWhite
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.theme.TextMuted
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.utils.NavigationHelper
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.sources.GeoJsonSource

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
    var deviceLocation by remember { mutableStateOf<com.fieldtrackpro.android.services.LocationResult?>(null) }
    var hasPermission by remember { mutableStateOf(locationService.hasLocationPermission()) }
    var isLocationEnabled by remember { mutableStateOf(locationService.isLocationEnabled()) }

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
            FieldTrackTopAppBar(
                title = customer?.let { "Location: ${it.name}" } ?: "Location Map",
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
                        MapLibreMapView(
                            customerLat = lat,
                            customerLng = lng,
                            customerName = cust.name,
                            customerId = cust.id,
                            geofenceRadiusM = cust.geofenceRadiusM,
                            deviceLocation = deviceLocation,
                            hasPermission = hasPermission,
                            isLocationEnabled = isLocationEnabled,
                            onError = { errorMessage = it }
                        )
                    }

                    Button(
                        onClick = {
                            NavigationHelper.navigateToCustomer(context, lat, lng, cust.name)
                        },
                        modifier = Modifier
                            .align(Alignment.BottomCenter)
                            .padding(16.dp)
                            .fillMaxWidth()
                            .height(50.dp),
                        shape = RoundedCornerShape(8.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = FieldTrackNavy,
                            contentColor = SurfaceWhite
                        )
                    ) {
                        Text("NAVIGATE TO CUSTOMER", fontWeight = FontWeight.Bold, color = SurfaceWhite)
                    }
                }
            }
        }
    }
}

@Composable
private fun MapLibreMapView(
    customerLat: Double,
    customerLng: Double,
    customerName: String,
    customerId: String,
    geofenceRadiusM: Int,
    deviceLocation: com.fieldtrackpro.android.services.LocationResult?,
    hasPermission: Boolean,
    isLocationEnabled: Boolean,
    onError: (String) -> Unit
) {
    val context = LocalContext.current
    val styleUrl = BuildConfig.MAPLIBRE_TILE_URL

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(SurfaceOffWhite)
    ) {
        Box(
            modifier = Modifier.fillMaxSize()
        ) {
            val mapView = remember {
                MapView(context).also { mv ->
                    mv.getMapAsync { mapLibre ->
                        try {
                            mapLibre.setStyle(Style.Builder().fromUri(styleUrl)) { style ->
                                mapLibre.cameraPosition = CameraPosition.Builder()
                                    .target(LatLng(customerLat, customerLng))
                                    .zoom(14.0)
                                    .build()

                                val geoJsonData = buildString {
                                    append("""{"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Point","coordinates":[$customerLng,$customerLat]},"properties":{"name":""")
                                    append(customerName.replace("\"", "\\\""))
                                    append(""","id":"$customerId","radius":$geofenceRadiusM}}]}""")
                                }

                                val source = GeoJsonSource("customer-source", geoJsonData)
                                style.addSource(source)

                                val circleLayer = CircleLayer("customer-circle", "customer-source")
                                circleLayer.setProperties(
                                    PropertyFactory.circleColor("#FCA311"),
                                    PropertyFactory.circleRadius(12f),
                                    PropertyFactory.circleStrokeWidth(2f),
                                    PropertyFactory.circleStrokeColor("#FFFFFF")
                                )
                                style.addLayer(circleLayer)

                                val geofenceLayer = CircleLayer("customer-geofence", "customer-source")
                                geofenceLayer.setProperties(
                                    PropertyFactory.circleColor("#FCA31122"),
                                    PropertyFactory.circleRadius(geofenceRadiusM.toFloat()),
                                    PropertyFactory.circleStrokeWidth(1f),
                                    PropertyFactory.circleStrokeColor("#FCA311")
                                )
                                style.addLayerBelow(geofenceLayer, "customer-circle")

                                mapLibre.addOnMapClickListener { point ->
                                    val clicked = LatLng(customerLat, customerLng)
                                    val distance = point.distanceTo(clicked)
                                    if (distance < 500.0) {
                                        true
                                    } else {
                                        false
                                    }
                                }
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
        }

        // Customer info card overlay
        Card(
            modifier = Modifier
                .align(Alignment.TopStart)
                .padding(16.dp),
            colors = CardDefaults.cardColors(containerColor = SurfaceWhite),
            shape = RoundedCornerShape(8.dp)
        ) {
            Column(modifier = Modifier.padding(12.dp)) {
                Text(
                    text = customerName,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimary
                )
                Text(
                    text = "ID: ${customerId.take(8)}",
                    fontSize = 11.sp,
                    color = TextMuted
                )
                Text(
                    text = "Geofence: ${geofenceRadiusM}m",
                    fontSize = 11.sp,
                    color = TextMuted
                )
                Text(
                    text = NavigationHelper.formatCoordinates(customerLat, customerLng),
                    fontSize = 10.sp,
                    color = TextMuted
                )
            }
        }

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
                        color = TextPrimary
                    )
                    Text(
                        text = NavigationHelper.formatCoordinates(deviceLocation.latitude, deviceLocation.longitude),
                        fontSize = 10.sp,
                        color = TextMuted
                    )
                }
            }
        }

        if (!hasPermission) {
            Card(
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(16.dp),
                colors = CardDefaults.cardColors(containerColor = SurfaceWhite),
                shape = RoundedCornerShape(8.dp)
            ) {
                Text(
                    text = "Location permission required",
                    fontSize = 12.sp,
                    color = TextMuted,
                    modifier = Modifier.padding(12.dp)
                )
            }
        }

        if (!isLocationEnabled) {
            Card(
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(16.dp),
                colors = CardDefaults.cardColors(containerColor = SurfaceWhite),
                shape = RoundedCornerShape(8.dp)
            ) {
                Text(
                    text = "GPS is disabled",
                    fontSize = 12.sp,
                    color = TextMuted,
                    modifier = Modifier.padding(12.dp)
                )
            }
        }
    }
}
