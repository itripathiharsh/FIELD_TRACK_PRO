package com.fieldtrackpro.android.ui.screens.collections

import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Payments
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.model.AccountSummaryDto
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.LoadingScreen
import com.fieldtrackpro.android.ui.components.StatusBadge
import com.fieldtrackpro.android.ui.theme.BrandBlack
import com.fieldtrackpro.android.ui.theme.BrandGold
import com.fieldtrackpro.android.ui.theme.BrandLightGray
import com.fieldtrackpro.android.ui.theme.BrandNavy
import com.fieldtrackpro.android.ui.theme.BrandWhite
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.LeagueSpartanFamily
import com.fieldtrackpro.android.ui.theme.LibreBaskervilleFamily
import com.fieldtrackpro.android.ui.theme.SuccessGreen
import com.fieldtrackpro.android.ui.theme.SurfaceSecondary
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.theme.TextSecondary
import com.fieldtrackpro.android.ui.viewmodel.AccountState
import com.fieldtrackpro.android.ui.viewmodel.CollectionViewModel

private fun formatCurrency(value: String): String {
    val n = value.toDoubleOrNull() ?: 0.0
    return "₹${"%,.0f".format(n)}"
}

@Composable
fun OutletAccountScreen(
    visitId: String,
    customerId: String,
    viewModel: CollectionViewModel,
    onNavigateBack: () -> Unit,
    onNavigateToCollectPayment: (visitId: String, customerId: String) -> Unit,
) {
    val state by viewModel.accountState.collectAsState()

    LaunchedEffect(customerId) {
        viewModel.loadAccount(customerId)
    }

    Scaffold(
        topBar = {
            FieldTrackTopAppBar(title = "Outlet Account & Ledger", onBackClick = onNavigateBack)
        }
    ) { innerPadding ->
        when (val s = state) {
            is AccountState.Loading -> LoadingScreen(message = "Retrieving ledger telemetry...", modifier = Modifier.padding(innerPadding))
            is AccountState.Error -> Column(modifier = Modifier.padding(innerPadding).padding(16.dp)) {
                ErrorBanner(message = s.message)
            }
            is AccountState.Success -> {
                val account = s.account
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(SurfaceSecondary)
                        .padding(innerPadding)
                        .padding(16.dp)
                        .verticalScroll(rememberScrollState())
                ) {
                    AccountHeader(account)
                    Spacer(modifier = Modifier.height(14.dp))
                    AccountMetrics(account)
                    Spacer(modifier = Modifier.height(16.dp))

                    Button(
                        onClick = { onNavigateToCollectPayment(visitId, customerId) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(52.dp),
                        shape = RoundedCornerShape(10.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = BrandNavy, contentColor = BrandWhite)
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                imageVector = Icons.Default.Payments,
                                contentDescription = null,
                                tint = BrandGold,
                                modifier = Modifier.size(20.dp)
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                "COLLECT PAYMENT NOW",
                                fontFamily = LeagueSpartanFamily,
                                fontWeight = FontWeight.Bold,
                                fontSize = 14.sp,
                                letterSpacing = 0.5.sp,
                                color = BrandWhite
                            )
                        }
                    }
                    Spacer(modifier = Modifier.height(16.dp))

                    if (account.brandSummary.isNotEmpty()) {
                        SectionCard(title = "BRAND-WISE SUMMARY") {
                            account.brandSummary.forEach { b ->
                                Column(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween
                                    ) {
                                        Text(
                                            b.brand,
                                            fontFamily = LeagueSpartanFamily,
                                            fontSize = 14.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = BrandNavy
                                        )
                                        Text(
                                            formatCurrency(b.totalOutstanding),
                                            fontFamily = LeagueSpartanFamily,
                                            fontSize = 14.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = BrandGold
                                        )
                                    }
                                    Text(
                                        "Invoiced ${formatCurrency(b.totalInvoiced)} · Paid ${formatCurrency(b.totalPaid)}" +
                                            if (b.overdueAmount.toDoubleOrNull() != null && b.overdueAmount.toDouble() > 0)
                                                " · Overdue ${formatCurrency(b.overdueAmount)}"
                                            else "",
                                        fontFamily = LibreBaskervilleFamily,
                                        fontSize = 12.sp,
                                        color = if (b.overdueAmount.toDoubleOrNull()?.let { it > 0 } == true) ErrorRed else TextSecondary
                                    )
                                }
                            }
                        }
                        Spacer(modifier = Modifier.height(14.dp))
                    }

                    if (account.recentInvoices.isNotEmpty()) {
                        SectionCard(title = "RECENT INVOICES") {
                            account.recentInvoices.forEach { inv ->
                                Column(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                        Text(
                                            inv.invoiceNumber,
                                            fontFamily = LeagueSpartanFamily,
                                            fontSize = 13.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = BrandNavy
                                        )
                                        StatusBadge(status = inv.paymentStatus)
                                    }
                                    Spacer(modifier = Modifier.height(2.dp))
                                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                        Text(
                                            "Total: ${formatCurrency(inv.amount)}",
                                            fontFamily = LibreBaskervilleFamily,
                                            fontSize = 12.sp,
                                            color = TextSecondary
                                        )
                                        Text(
                                            "Bal: ${formatCurrency(inv.remainingAmount)}",
                                            fontFamily = LeagueSpartanFamily,
                                            fontSize = 13.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = if (inv.paymentStatus == "PAID") SuccessGreen else BrandGold
                                        )
                                    }
                                }
                            }
                        }
                        Spacer(modifier = Modifier.height(14.dp))
                    }

                    if (account.recentPayments.isNotEmpty()) {
                        SectionCard(title = "PAYMENT HISTORY") {
                            account.recentPayments.forEach { p ->
                                Column(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                        Text(
                                            formatCurrency(p.amount),
                                            fontFamily = LeagueSpartanFamily,
                                            fontSize = 15.sp,
                                            fontWeight = FontWeight.Bold,
                                            color = SuccessGreen
                                        )
                                        StatusBadge(status = p.status)
                                    }
                                    Text(
                                        "${p.paymentMethod} · ${p.paymentDate}",
                                        fontFamily = LibreBaskervilleFamily,
                                        fontSize = 12.sp,
                                        color = TextSecondary
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

@Composable
private fun AccountHeader(account: AccountSummaryDto) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, BrandLightGray, RoundedCornerShape(14.dp)),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = BrandWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Text(
                account.customerName,
                fontFamily = LeagueSpartanFamily,
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
                color = BrandNavy
            )
            val outletCode = account.outletCode
            if (!outletCode.isNullOrBlank()) {
                Text(
                    "Code: $outletCode",
                    fontFamily = LibreBaskervilleFamily,
                    fontSize = 12.sp,
                    color = TextSecondary
                )
            }
            if (account.overdueAmount.toDoubleOrNull()?.let { it > 0 } == true) {
                Spacer(modifier = Modifier.height(8.dp))
                StatusBadge(status = "OVERDUE")
            }
        }
    }
}

@Composable
private fun AccountMetrics(account: AccountSummaryDto) {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
        MetricTile(
            title = "TOTAL OUTSTANDING",
            value = formatCurrency(account.totalOutstanding),
            color = BrandNavy,
            modifier = Modifier.weight(1f)
        )
        val isOverdue = account.overdueAmount.toDoubleOrNull()?.let { it > 0 } == true
        MetricTile(
            title = "OVERDUE AMOUNT",
            value = formatCurrency(account.overdueAmount),
            color = if (isOverdue) ErrorRed else BrandNavy,
            modifier = Modifier.weight(1f)
        )
    }
}

@Composable
private fun MetricTile(title: String, value: String, color: androidx.compose.ui.graphics.Color, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier.border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = BrandWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Text(
                title,
                fontFamily = LeagueSpartanFamily,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 0.8.sp,
                color = TextSecondary
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                value,
                fontFamily = LeagueSpartanFamily,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                color = color
            )
        }
    }
}

@Composable
private fun SectionCard(title: String, content: @Composable () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, BrandLightGray, RoundedCornerShape(12.dp)),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = BrandWhite),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                title,
                fontFamily = LeagueSpartanFamily,
                fontSize = 13.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 0.8.sp,
                color = BrandNavy
            )
            Spacer(modifier = Modifier.height(8.dp))
            content()
        }
    }
}
