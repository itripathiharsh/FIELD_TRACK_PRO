package com.fieldtrackpro.android.ui.components

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.local.TokenManager
import com.fieldtrackpro.android.data.remote.ApiClient
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.utils.ImageDownsampler
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Small "Outlet photo" thumbnail of the outlet's approved primary proof, loaded through the authenticated
 * GET /customers/{id}/outlet-image with the app's own OkHttp client (the bucket stays private). Shown only when the
 * customer DTO says a photo exists. A plain downsampled bitmap decode is enough here (no image library needed).
 */
@Composable
fun OutletPhotoSection(customerId: String, reloadKey: Int = 0) {
    val context = LocalContext.current
    val api = remember(customerId) { ApiClient.createOutletProofApi(TokenManager.getInstance(context)) }
    var attempt by remember(customerId) { androidx.compose.runtime.mutableIntStateOf(0) }
    val state by produceState<PhotoState>(PhotoState.Loading, customerId, reloadKey, attempt) {
        value = PhotoState.Loading
        value = withContext(Dispatchers.IO) {
            try {
                val response = api.getOutletImage(customerId)
                when {
                    response.isSuccessful -> {
                        val bytes = response.body()?.bytes()
                        val bmp = bytes?.let { ImageDownsampler.decodeSampledBitmapForDisplay(it, 800) }
                        if (bmp != null) PhotoState.Ready(bmp) else PhotoState.Failed("The photo could not be shown.")
                    }
                    response.code() == 404 -> PhotoState.Empty
                    else -> PhotoState.Failed("The photo could not be loaded (${response.code()}).")
                }
            } catch (e: Exception) {
                PhotoState.Failed("Check your connection and try again.")
            }
        }
    }
    Column(modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
        Text("Outlet photo", fontSize = 12.sp, fontWeight = FontWeight.Bold, color = BrandNavy)
        Box(
            modifier = Modifier.fillMaxWidth().height(160.dp).clip(RoundedCornerShape(10.dp)).background(SurfaceSecondary),
            contentAlignment = Alignment.Center
        ) {
            when (val st = state) {
                is PhotoState.Loading -> androidx.compose.material3.CircularProgressIndicator(
                    modifier = Modifier.size(24.dp), strokeWidth = 2.dp, color = BrandNavy
                )
                is PhotoState.Ready -> Image(
                    bitmap = st.bitmap.asImageBitmap(),
                    contentDescription = "Outlet photo",
                    contentScale = ContentScale.Crop,
                    modifier = Modifier.fillMaxWidth().height(160.dp)
                )
                is PhotoState.Empty -> Text("No outlet photo yet", fontSize = 12.sp, color = TextSecondary)
                is PhotoState.Failed -> Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(st.message, fontSize = 12.sp, color = TextSecondary)
                    androidx.compose.material3.TextButton(onClick = { attempt++ }) {
                        Text("Try again", fontWeight = FontWeight.Bold, color = BrandNavy)
                    }
                }
            }
        }
        if (state is PhotoState.Ready) Text("Verified live photo", fontSize = 10.sp, color = TextSecondary)
    }
}

private sealed class PhotoState {
    object Loading : PhotoState()
    data class Ready(val bitmap: Bitmap) : PhotoState()
    object Empty : PhotoState()
    data class Failed(val message: String) : PhotoState()
}
