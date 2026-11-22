package com.fieldtrackpro.android.ui.components

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.R
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.ErrorRedBg
import com.fieldtrackpro.android.ui.theme.KpiNumber
import com.fieldtrackpro.android.ui.theme.LabelCaps
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.Navy100
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.theme.TextSubtle

/*
 * FieldTrack Pro design system v2 - shared building blocks.
 * Rules: a surface gets a border OR a shadow (never both); gold is a signal colour (one primary action per screen);
 * touch targets are at least 48 dp; labels are at least 11 sp.
 */

/** The FieldTrack mark (gold shield with a map-pin cut-out). [height] is the mark's height; width follows (3:4). */
@Composable
fun BrandMark(height: Dp, modifier: Modifier = Modifier, contentDescription: String? = null) {
    Image(
        painter = painterResource(R.drawable.ic_brand_mark),
        contentDescription = contentDescription,
        modifier = modifier.size(width = height * 0.75f, height = height)
    )
}

private val ButtonShape = RoundedCornerShape(12.dp)

private enum class ButtonKind { PRIMARY, SIGNAL, DANGER }

@Composable
private fun FilledAction(
    text: String,
    onClick: () -> Unit,
    kind: ButtonKind,
    modifier: Modifier,
    enabled: Boolean,
    loading: Boolean,
    icon: ImageVector?
) {
    val (container, content) = when (kind) {
        ButtonKind.PRIMARY -> BrandNavy to BrandWhite
        ButtonKind.SIGNAL -> BrandGold to BrandNavy
        ButtonKind.DANGER -> ErrorRed to BrandWhite
    }
    Button(
        onClick = onClick,
        enabled = enabled && !loading,
        shape = ButtonShape,
        colors = ButtonDefaults.buttonColors(
            containerColor = container,
            contentColor = content,
            disabledContainerColor = if (loading) container else BrandLightGray,
            disabledContentColor = if (loading) content else TextSubtle
        ),
        modifier = modifier.heightIn(min = 52.dp)
    ) {
        if (loading) {
            CircularProgressIndicator(color = content, strokeWidth = 2.dp, modifier = Modifier.size(20.dp))
        } else {
            if (icon != null) {
                Icon(icon, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
            }
            Text(text, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 15.sp, letterSpacing = 0.4.sp)
        }
    }
}

/** Navy filled button: the default primary action on light screens. */
@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, loading: Boolean = false, icon: ImageVector? = null) =
    FilledAction(text, onClick, ButtonKind.PRIMARY, modifier, enabled, loading, icon)

/** Gold filled button with navy text: the one signal action on a screen (Start Day, Sign in on navy). */
@Composable
fun SignalButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, loading: Boolean = false, icon: ImageVector? = null) =
    FilledAction(text, onClick, ButtonKind.SIGNAL, modifier, enabled, loading, icon)

/** Red filled button: only for confirming a destructive action inside a dialog. */
@Composable
fun DangerButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, loading: Boolean = false, icon: ImageVector? = null) =
    FilledAction(text, onClick, ButtonKind.DANGER, modifier, enabled, loading, icon)

/** Outlined button; [color] is navy by default, red for destructive entry points (Log out). */
@Composable
fun OutlineButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, color: Color = BrandNavy, enabled: Boolean = true, icon: ImageVector? = null) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        shape = ButtonShape,
        border = BorderStroke(1.5.dp, if (enabled) color else BrandLightGray),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = color),
        modifier = modifier.heightIn(min = 52.dp)
    ) {
        if (icon != null) {
            Icon(icon, contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
        }
        Text(text, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 15.sp, letterSpacing = 0.4.sp)
    }
}

/** Uppercase section eyebrow with an optional trailing text action. */
@Composable
fun SectionHeader(title: String, modifier: Modifier = Modifier, actionLabel: String? = null, onAction: (() -> Unit)? = null) {
    Row(
        modifier = modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(title.uppercase(), style = LabelCaps, color = TextSecondary, modifier = Modifier.weight(1f))
        if (actionLabel != null && onAction != null) {
            TextButton(onClick = onAction) {
                Text(actionLabel, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = BrandNavy)
            }
        }
    }
}

/** KPI tile: caption + large tabular value. White surface with a soft shadow (no border). */
@Composable
fun StatTile(label: String, value: String, modifier: Modifier = Modifier, valueColor: Color = BrandNavy, supporting: String? = null) {
    Surface(
        modifier = modifier.semantics(mergeDescendants = true) {},
        shape = RoundedCornerShape(14.dp),
        color = BrandWhite,
        shadowElevation = 2.dp
    ) {
        Column(Modifier.padding(horizontal = 14.dp, vertical = 12.dp)) {
            Text(label.uppercase(), style = LabelCaps.copy(fontSize = 11.sp), color = TextSubtle, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.height(4.dp))
            // Long amounts (₹1,25,450.50) step down instead of being cut off on narrow phones / large font scale.
            val valueSize = when {
                value.length > 12 -> 18.sp
                value.length > 9 -> 20.sp
                else -> 24.sp
            }
            Text(value, style = KpiNumber.copy(fontSize = valueSize), color = valueColor, maxLines = 1, softWrap = false, overflow = TextOverflow.Visible)
            if (supporting != null) {
                Text(supporting, fontSize = 12.sp, color = TextSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

/** Quick-action tile: icon in a rounded square + a short label. [emphasized] = navy tile with a gold icon. */
@Composable
fun ActionTile(label: String, icon: ImageVector, onClick: () -> Unit, modifier: Modifier = Modifier, emphasized: Boolean = false) {
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(14.dp))
            .clickable(role = Role.Button, onClick = onClick)
            .padding(vertical = 8.dp, horizontal = 2.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Box(
            modifier = Modifier
                .size(52.dp)
                .clip(RoundedCornerShape(16.dp))
                .background(if (emphasized) BrandNavy else Navy100),
            contentAlignment = Alignment.Center
        ) {
            Icon(icon, contentDescription = null, tint = if (emphasized) BrandGold else BrandNavy, modifier = Modifier.size(24.dp))
        }
        Spacer(Modifier.height(8.dp))
        Text(
            label,
            fontFamily = LeagueSpartanFamily,
            fontWeight = FontWeight.SemiBold,
            fontSize = 13.sp,
            lineHeight = 16.sp,
            color = BrandNavy,
            textAlign = TextAlign.Center,
            maxLines = 2
        )
    }
}

/** Inline error that names the cause and offers Retry, without replacing the screen's actions. */
@Composable
fun InlineErrorCard(message: String, modifier: Modifier = Modifier, onRetry: (() -> Unit)? = null, actionLabel: String = "Retry") {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(12.dp))
            .background(ErrorRedBg)
            .padding(start = 14.dp, end = 4.dp, top = 6.dp, bottom = 6.dp)
            .semantics { contentDescription = "Error: $message" },
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(Icons.Default.ErrorOutline, contentDescription = null, tint = ErrorRed, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(10.dp))
        Text(message, fontSize = 14.sp, color = Color(0xFF7F1D1D), modifier = Modifier.weight(1f).padding(vertical = 8.dp))
        if (onRetry != null) {
            TextButton(onClick = onRetry) {
                Text(actionLabel, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = ErrorRed)
            }
        }
    }
}

/** Shimmering placeholder block for loading states. */
@Composable
fun SkeletonBlock(modifier: Modifier = Modifier, height: Dp = 56.dp) {
    val transition = rememberInfiniteTransition(label = "skeleton")
    val a by transition.animateFloat(
        initialValue = 0.45f,
        targetValue = 0.9f,
        animationSpec = infiniteRepeatable(tween(800), RepeatMode.Reverse),
        label = "skeletonAlpha"
    )
    Box(
        modifier
            .fillMaxWidth()
            .height(height)
            .alpha(a)
            .clip(RoundedCornerShape(12.dp))
            .background(Navy100)
    )
}

/** Small rounded status chip. */
@Composable
fun StatusChip(text: String, container: Color, content: Color, modifier: Modifier = Modifier, dot: Color? = null) {
    Row(
        modifier = modifier
            .clip(RoundedCornerShape(50))
            .background(container)
            .padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (dot != null) {
            Box(Modifier.size(7.dp).clip(CircleShape).background(dot))
            Spacer(Modifier.width(6.dp))
        }
        Text(text.uppercase(), style = LabelCaps.copy(fontSize = 11.sp), color = content, maxLines = 1)
    }
}

/** White list group (settings-style rows). */
@Composable
fun ListGroup(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Surface(
        modifier = modifier.fillMaxWidth().border(1.dp, BrandLightGray, RoundedCornerShape(14.dp)),
        shape = RoundedCornerShape(14.dp),
        color = BrandWhite
    ) { Column { content() } }
}
