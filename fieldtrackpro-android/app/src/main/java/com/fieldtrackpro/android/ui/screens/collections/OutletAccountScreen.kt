package com.fieldtrackpro.android.ui.screens.collections

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.fieldtrackpro.android.data.model.AccountSummaryDto
import com.fieldtrackpro.android.ui.components.ErrorBanner
import com.fieldtrackpro.android.ui.components.FieldTrackTopAppBar
import com.fieldtrackpro.android.ui.components.LoadingScreen
import com.fieldtrackpro.android.ui.components.StatusBadge
import com.fieldtrackpro.android.ui.theme.ErrorRed
import com.fieldtrackpro.android.ui.theme.FieldTrackNavy
import com.fieldtrackpro.android.ui.theme.SurfaceOffWhite
import com.fieldtrackpro.android.ui.theme.SurfaceWhite
import com.fieldtrackpro.android.ui.theme.TextMuted
import com.fieldtrackpro.android.ui.theme.TextPrimary
import com.fieldtrackpro.android.ui.viewmodel.AccountState
import com.fieldtrackpro.android.ui.viewmodel.CollectionViewModel

private fun formatCurrency(value: String): String {
    val n = value.toDoubleOrNull() ?: 0.0
    return "₹${"%,.0f".format(n)}"
}

/**
 * Outlet Account panel: outstanding/due/overdue, aging, invoice + payment
 * history, brand-wise totals. Mirrors the web AccountSummaryCard - same
 * data, same fields, just the Android layout.
 */
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
            FieldTrackTopAppBar(title = "Outlet Account", onBackClick = onNavigateBack)
        }
    ) { innerPadding ->
        when (val s = state) {
            is AccountState.Loading -> LoadingScreen(message = "Loading outlet account...", modifier = Modifier.padding(innerPadding))
            is AccountState.Error -> Column(modifier = Modifier.padding(innerPadding).padding(16.dp)) {
                ErrorBanner(message = s.message)
            }
            is AccountState.Success -> {
                val account = s.account
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(SurfaceOffWhite)
                        .padding(innerPadding)
                        .padding(16.dp)
                        .verticalScroll(rememberScrollState())
                ) {
                    AccountHeader(account)
                    Spacer(modifier = Modifier.height(16.dp))
                    AccountMetrics(account)
                    Spacer(modifier = Modifier.height(16.dp))

                    Button(
                        onClick = { onNavigateToCollectPayment(visitId, customerId) },
                        modifier = Modifier.fillMaxWidth().height(48.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = FieldTrackNavy, contentColor = SurfaceWhite)
                    ) {
                        Text("COLLECT PAYMENT", fontWeight = FontWeight.Bold)
                    }
                    Spacer(modifier = Modifier.height(16.dp))

                    if (account.brandSummary.isNotEmpty()) {
                        // P2-A: brand-wise history - same fields as the web
                        // AccountSummaryCard's Brand History table, laid out
                        // as two lines per brand to fit a phone width.
                        SectionCard(title = "Brand History") {
                            account.brandSummary.forEach { b ->
                                Column(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween
                                    ) {
                                        Text(b.brand, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = TextPrimary)
                                        Text(formatCurrency(b.totalOutstanding), fontSize = 13.sp, fontWeight = FontWeight.Bold, color = FieldTrackNavy)
                                    }
                                    Text(
                                        "Invoiced ${formatCurrency(b.totalInvoiced)} · Paid ${formatCurrency(b.totalPaid)}" +
                                            if (b.overdueAmount.toDoubleOrNull() != null && b.overdueAmount.toDouble() > 0)
                                                " · Overdue ${formatCurrency(b.overdueAmount)}"
                                            else "",
                                        fontSize = 12.sp,
                                        color = if (b.overdueAmount.toDoubleOrNull()?.let { it > 0 } == true) ErrorRed else TextMuted
                                    )
                                    Text(
                                        "${b.invoiceCount} invoice${if (b.invoiceCount == 1) "" else "s"}" +
                                            (b.latestInvoiceDate?.let { " · Latest $it" } ?: ""),
                                        fontSize = 11.sp,
                                        color = TextMuted
                                    )
                                }
                            }
                        }
                        Spacer(modifier = Modifier.height(16.dp))
                    }

                    if (account.recentInvoices.isNotEmpty()) {
                        SectionCard(title = "Invoice History") {
                            account.recentInvoices.forEach { inv ->
                                Column(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                        Text(inv.invoiceNumber, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = TextPrimary)
                                        StatusBadge(status = inv.agingStatus)
                                    }
                                    Text(
                                        "${inv.invoiceDate} · Remaining ${formatCurrency(inv.remainingAmount)} · ${inv.daysOutstanding}d",
                                        fontSize = 12.sp,
                                        color = TextMuted
                                    )
                                }
                            }
                        }
                        Spacer(modifier = Modifier.height(16.dp))
                    }

                    if (account.recentPayments.isNotEmpty()) {
                        SectionCard(title = "Payment History") {
                            account.recentPayments.forEach { p ->
                                Row(
                                    modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    Column {
                                        Text(formatCurrency(p.amount), fontSize = 13.sp, fontWeight = FontWeight.Bold, color = TextPrimary)
                                        Text("${p.paymentMethod} · ${p.paymentDate}", fontSize = 12.sp, color = TextMuted)
                                    }
                                    StatusBadge(status = p.status)
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
    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Column {
            Text(account.customerName, style = MaterialTheme.typography.titleLarge, color = FieldTrackNavy, fontWeight = FontWeight.Bold)
            account.outletCode?.let {
                Text("Outlet Code: $it", fontSize = 12.sp, color = TextMuted)
            }
        }
        StatusBadge(status = account.collectionStatus)
    }
}

@Composable
private fun AccountMetrics(account: AccountSummaryDto) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            MetricBox("Outstanding", formatCurrency(account.totalOutstanding), FieldTrackNavy, Modifier.weight(1f))
            MetricBox("Paid to Date", formatCurrency(account.totalPaid), FieldTrackNavy, Modifier.weight(1f))
        }
        Spacer(modifier = Modifier.height(10.dp))
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            MetricBox(
                "Overdue",
                formatCurrency(account.overdueAmount),
                if (account.overdueAmount.toDoubleOrNull() ?: 0.0 > 0) ErrorRed else FieldTrackNavy,
                Modifier.weight(1f)
            )
            MetricBox("Days Outstanding", account.maxDaysOutstanding.toString(), FieldTrackNavy, Modifier.weight(1f))
        }
    }
}

@Composable
private fun MetricBox(label: String, value: String, valueColor: androidx.compose.ui.graphics.Color, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(10.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(label.uppercase(), fontSize = 10.sp, color = TextMuted, fontWeight = FontWeight.SemiBold)
            Spacer(modifier = Modifier.height(4.dp))
            Text(value, fontSize = 18.sp, fontWeight = FontWeight.Bold, color = valueColor)
        }
    }
}

@Composable
private fun SectionCard(title: String, content: @Composable () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceWhite)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(title, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = FieldTrackNavy)
            Spacer(modifier = Modifier.height(8.dp))
            content()
        }
    }
}
