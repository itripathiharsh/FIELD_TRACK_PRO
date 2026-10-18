package com.fieldtrackpro.android.ui.components

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
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
fun OutletPhotoSection(customerId: String) {
    val context = LocalContext.current
    val api = remember(customerId) { ApiClient.createOutletProofApi(TokenManager.getInstance(context)) }
    val bitmap by produceState<Bitmap?>(null, customerId) {
        value = withContext(Dispatchers.IO) {
            try {
                val response = api.getOutletImage(customerId)
                val bytes = if (response.isSuccessful) response.body()?.bytes() else null
                bytes?.let { ImageDownsampler.decodeSampledBitmapForDisplay(it, 800) }
            } catch (e: Exception) {
                null
            }
        }
    }
    val bmp = bitmap ?: return
    Column(modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
        Text("Outlet photo", fontSize = 12.sp, fontWeight = FontWeight.Bold, color = BrandNavy)
        Box(
            modifier = Modifier.fillMaxWidth().height(140.dp).clip(RoundedCornerShape(10.dp)).background(SurfaceSecondary),
            contentAlignment = Alignment.Center
        ) {
            Image(
                bitmap = bmp.asImageBitmap(),
                contentDescription = "Outlet photo",
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxWidth().height(140.dp)
            )
        }
        Text("Verified live photo", fontSize = 10.sp, color = TextSecondary)
    }
}
