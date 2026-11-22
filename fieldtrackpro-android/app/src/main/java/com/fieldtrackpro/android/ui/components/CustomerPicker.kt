package com.fieldtrackpro.android.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Storefront
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.model.CustomerDto
import com.fieldtrackpro.android.search.CustomerSearchState
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandGoldDark
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.LabelCaps
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.Navy100
import com.fieldtrackpro.android.ui.theme.Navy50
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.theme.TextSubtle

/** "OUT-1234 · Area, Territory" line for a customer row. */
fun customerSubtitle(c: CustomerDto): String {
    val code = c.outletCode ?: c.dmsCode
    val place = listOfNotNull(c.areaName, c.territoryName).filter { it.isNotBlank() }.joinToString(", ")
        .ifBlank { c.address?.takeIf { it.isNotBlank() } ?: "" }
    return listOfNotNull(code, place.takeIf { it.isNotBlank() }).joinToString(" · ")
}

/**
 * Customer search + ranked results + selected state, shared by the Add Visit and Off-Beat Visit sheets.
 * The list is a plain Column (not lazy) so it scrolls together with the rest of the sheet above the keyboard.
 */
@Composable
fun CustomerPicker(
    state: CustomerSearchState,
    selected: CustomerDto?,
    onQueryChange: (String) -> Unit,
    onSelect: (CustomerDto) -> Unit,
    onClearSelection: () -> Unit,
    modifier: Modifier = Modifier,
    label: String = "Customer"
) {
    val focus = LocalFocusManager.current
    Column(modifier, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(label.uppercase(), style = LabelCaps, color = TextSecondary)
        if (selected != null) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(14.dp))
                    .background(BrandGold.copy(alpha = 0.12f))
                    .border(1.5.dp, BrandGold, RoundedCornerShape(14.dp))
                    .padding(start = 14.dp, end = 4.dp, top = 10.dp, bottom = 10.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(Icons.Default.CheckCircle, contentDescription = null, tint = BrandGoldDark, modifier = Modifier.size(22.dp))
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(selected.name, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, fontSize = 16.sp, color = BrandNavy)
                    val sub = customerSubtitle(selected)
                    if (sub.isNotBlank()) Text(sub, fontSize = 13.sp, color = TextSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
                TextButton(onClick = onClearSelection) {
                    Text("Change", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold, color = BrandNavy)
                }
            }
            return@Column
        }

        OutlinedTextField(
            value = state.query,
            onValueChange = onQueryChange,
            placeholder = { Text("Search by outlet name, code or area") },
            leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = TextSecondary) },
            trailingIcon = {
                when {
                    state.isLoading -> CircularProgressIndicator(strokeWidth = 2.dp, modifier = Modifier.size(18.dp), color = BrandNavy)
                    state.query.isNotEmpty() -> IconButton(onClick = { onQueryChange("") }) {
                        Icon(Icons.Default.Close, contentDescription = "Clear search", tint = TextSecondary)
                    }
                }
            },
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            keyboardActions = KeyboardActions(onSearch = { focus.clearFocus() }),
            shape = RoundedCornerShape(14.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = BrandGold, unfocusedBorderColor = BrandLightGray,
                focusedContainerColor = BrandWhite, unfocusedContainerColor = Navy50,
                focusedTextColor = TextPrimary, unfocusedTextColor = TextPrimary
            ),
            modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp)
        )

        state.hint?.let { Text(it, fontSize = 12.sp, color = TextSubtle) }

        when {
            state.error != null -> InlineErrorCard(message = "Search failed: ${state.error}", onRetry = { onQueryChange(state.query) })
            state.results.isEmpty() && state.isLoading -> repeat(3) { SkeletonBlock(height = 56.dp) }
            state.results.isEmpty() && state.query.isNotBlank() -> EmptyResults(state.query)
            state.results.isEmpty() && state.portfolioError != null ->
                InlineErrorCard(message = "Couldn't load your outlets: ${state.portfolioError}")
            state.results.isEmpty() -> Text("Type an outlet name, code or area to search.", fontSize = 14.sp, color = TextSecondary)
            else -> Column(
                Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(14.dp))
                    .border(1.dp, BrandLightGray, RoundedCornerShape(14.dp))
                    .background(BrandWhite)
            ) {
                val shown = state.results.take(25)
                shown.forEachIndexed { i, r ->
                    if (i > 0) HorizontalDivider(color = BrandLightGray, modifier = Modifier.padding(start = 56.dp))
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .clickable(role = Role.Button) {
                                focus.clearFocus()
                                onSelect(r.customer)
                            }
                            .heightIn(min = 56.dp)
                            .padding(horizontal = 14.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Box(Modifier.size(30.dp).clip(RoundedCornerShape(9.dp)).background(Navy100), contentAlignment = Alignment.Center) {
                            Icon(Icons.Default.Storefront, contentDescription = null, tint = BrandNavy, modifier = Modifier.size(17.dp))
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(r.customer.name, fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold, fontSize = 15.sp,
                                color = BrandNavy, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            val sub = customerSubtitle(r.customer)
                            if (sub.isNotBlank()) Text(sub, fontSize = 12.sp, lineHeight = 16.sp, color = TextSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        }
                        if (!r.inScope) {
                            Spacer(Modifier.width(8.dp))
                            StatusChip("Other area", container = Navy100, content = TextSecondary)
                        }
                    }
                }
                if (state.results.size > shown.size) {
                    Text("Showing the top ${shown.size} matches. Type more to narrow down.", fontSize = 12.sp, color = TextSubtle,
                        modifier = Modifier.padding(14.dp))
                }
            }
        }
    }
}

@Composable
private fun EmptyResults(query: String) {
    Column(Modifier.fillMaxWidth().padding(vertical = 10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text("No outlets match “${query.trim()}”", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, color = BrandNavy)
        Text("Check the spelling, or search by outlet code or area.", fontSize = 13.sp, color = TextSecondary)
    }
}
