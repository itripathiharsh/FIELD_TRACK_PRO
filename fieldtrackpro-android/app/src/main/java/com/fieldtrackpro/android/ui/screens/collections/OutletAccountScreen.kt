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
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Payments
import androidx.compose.material.icons.filled.ReceiptLong
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
            FieldTrackTopAppBar(title = "Financial Overview & Ledger", onBackClick = onNavigateBack)
        }
    ) { innerPadding ->
        when (val s = state) {
            is AccountState.Loading -> LoadingScreen(message = "Retrieving financial ledger...", modifier = Modifier.padding(innerPadding))
            is AccountState.Error -> Column(modifier = Modifier.padding(innerPadding).padding(16.dp)) {
                ErrorBanner(message = s.message)
                Spacer(modifier = Modifier.height(16.dp))
                Button(
                    onClick = { viewModel.loadAccount(customerId) },
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(containerColor = BrandNavy, contentColor = BrandWhite)
                ) {
                    Text("Retry", fontFamily = LeagueSpartanFamily, fontWeight = FontWeight.Bold)
                }
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

                    // Prominent Quick Action Button
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

                    // Zero Balance Banner if settled
                    val totalOutstandingNum = account.totalOutstanding.toDoubleOrNull() ?: 0.0
                    if (totalOutstandingNum <= 0.0) {
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .border(1.dp, SuccessGreen.copy(alpha = 0.4f), RoundedCornerShape(12.dp)),
                            shape = RoundedCornerShape(12.dp),
                            colors = CardDefaults.cardColors(containerColor = SuccessGreen.copy(alpha = 0.08f))
                        ) {
                            Row(
                                modifier = Modifier.padding(14.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Icon(
                                    imageVector = Icons.Default.CheckCircle,
                                    contentDescription = null,
                                    tint = SuccessGreen,
                                    modifier = Modifier.size(22.dp)
                                )
                                Spacer(modifier = Modifier.width(10.dp))
                                Column {
                                    Text(
                                        "No Outstanding Balance",
                                        fontFamily = LeagueSpartanFamily,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 14.sp,
                                        color = BrandNavy
                                    )
                                    Text(
                                        "This customer currently has no outstanding balance.",
                                        fontFamily = LibreBaskervilleFamily,
                                        fontSize = 12.sp,
                                        color = TextSecondary
                                    )
                                }
                            }
                        }
                        Spacer(modifier = Modifier.height(16.dp))
                    }

                    // Brand-Wise Outstanding Section
                    if (account.brandSummary.isNotEmpty()) {
                        SectionCard(title = "BRAND-WISE OUTSTANDING") {
                            account.brandSummary.forEach { b ->
                                Card(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(vertical = 4.dp),
                                    shape = RoundedCornerShape(8.dp),
                                    colors = CardDefaults.cardColors(containerColor = SurfaceSecondary),
                                    border = androidx.compose.foundation.BorderStroke(1.dp, BrandLightGray)
                                ) {
                                    Column(modifier = Modifier.fillMaxWidth().padding(12.dp)) {
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.SpaceBetween,
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Text(
                                                b.brand,
                                                fontFamily = LeagueSpartanFamily,
                                                fontSize = 15.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = BrandNavy
                                            )
                                            Text(
                                                formatCurrency(b.totalOutstanding),
                                                fontFamily = LeagueSpartanFamily,
                                                fontSize = 15.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = BrandGold
                                            )
                                        }
                                        Spacer(modifier = Modifier.height(4.dp))
                                        val isBrandOverdue = b.overdueAmount.toDoubleOrNull()?.let { it > 0 } == true
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.SpaceBetween
                                        ) {
                                            Text(
                                                "Invoiced: ${formatCurrency(b.totalInvoiced)} · Paid: ${formatCurrency(b.totalPaid)}",
                                                fontFamily = LibreBaskervilleFamily,
                                                fontSize = 11.sp,
                                                color = TextSecondary
                                            )
                                            if (isBrandOverdue) {
                                                Text(
                                                    "Overdue: ${formatCurrency(b.overdueAmount)}",
                                                    fontFamily = LeagueSpartanFamily,
                                                    fontSize = 11.sp,
                                                    fontWeight = FontWeight.Bold,
                                                    color = ErrorRed
                                                )
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        Spacer(modifier = Modifier.height(16.dp))
                    }

                    // Outstanding Ageing Breakdown Section
                    val agingBuckets = account.agingBuckets
                    SectionCard(title = "OUTSTANDING AGEING") {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            AgeingBucketTile(
                                label = "0–30 Days",
                                amount = agingBuckets?.get("0-30") ?: "0",
                                modifier = Modifier.weight(1f)
                            )
                            AgeingBucketTile(
                                label = "31–60 Days",
                                amount = agingBuckets?.get("31-60") ?: "0",
                                modifier = Modifier.weight(1f)
                            )
                        }
                        Spacer(modifier = Modifier.height(8.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            AgeingBucketTile(
                                label = "61–90 Days",
                                amount = agingBuckets?.get("61-90") ?: "0",
                                modifier = Modifier.weight(1f)
                            )
                            AgeingBucketTile(
                                label = "90+ Days",
                                amount = agingBuckets?.get("90+") ?: "0",
                                isCritical = true,
                                modifier = Modifier.weight(1f)
                            )
                        }
                    }
                    Spacer(modifier = Modifier.height(16.dp))

                    // Recent Payment History Section
                    if (account.recentPayments.isNotEmpty()) {
                        SectionCard(title = "RECENT PAYMENT HISTORY") {
                            account.recentPayments.forEach { p ->
                                Card(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(vertical = 4.dp),
                                    shape = RoundedCornerShape(8.dp),
                                    colors = CardDefaults.cardColors(containerColor = SurfaceSecondary),
                                    border = androidx.compose.foundation.BorderStroke(1.dp, BrandLightGray)
                                ) {
                                    Column(modifier = Modifier.fillMaxWidth().padding(12.dp)) {
                                        Row(
                                            modifier = Modifier.fillMaxWidth(),
                                            horizontalArrangement = Arrangement.SpaceBetween,
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Text(
                                                formatCurrency(p.amount),
                                                fontFamily = LeagueSpartanFamily,
                                                fontSize = 16.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = SuccessGreen
                                            )
                                            StatusBadge(status = p.status)
                                        }
                                        Spacer(modifier = Modifier.height(3.dp))
                                        Text(
                                            "${p.paymentMethod} · ${p.paymentDate}" +
                                                (if (!p.utrReference.isNullOrBlank()) " · UTR ${p.utrReference}" else "") +
                                                (if (!p.chequeNumber.isNullOrBlank()) " · Chq ${p.chequeNumber}" else ""),
                                            fontFamily = LibreBaskervilleFamily,
                                            fontSize = 12.sp,
                                            color = TextSecondary
                                        )

                                        // Brand allocation breakdown pills
                                        if (p.allocations.isNotEmpty()) {
                                            Spacer(modifier = Modifier.height(6.dp))
                                            Row(
                                                modifier = Modifier.fillMaxWidth(),
                                                horizontalArrangement = Arrangement.spacedBy(6.dp)
                                            ) {
                                                p.allocations.forEach { alloc ->
                                                    Box(
                                                        modifier = Modifier
                                                            .clip(RoundedCornerShape(4.dp))
                                                            .background(BrandNavy.copy(alpha = 0.08f))
                                                            .padding(horizontal = 6.dp, vertical = 2.dp)
                                                    ) {
                                                        Text(
                                                            "${alloc.brand}: ${formatCurrency(alloc.allocatedAmount)}",
                                                            fontFamily = LeagueSpartanFamily,
                                                            fontWeight = FontWeight.Bold,
                                                            fontSize = 11.sp,
                                                            color = BrandNavy
                                                        )
                                                    }
                                                }
                                            }
                                        }

                                        // Proof indicator
                                        if (p.proofs.isNotEmpty()) {
                                            Spacer(modifier = Modifier.height(4.dp))
                                            Text(
                                                "📷 Payment receipt attached",
                                                fontFamily = LibreBaskervilleFamily,
                                                fontSize = 11.sp,
                                                color = SuccessGreen
                                            )
                                        }
                                    }
                                }
                            }
                        }
                        Spacer(modifier = Modifier.height(16.dp))
                    } else {
                        SectionCard(title = "RECENT PAYMENT HISTORY") {
                            Text(
                                "No payments recorded for this outlet yet.",
                                fontFamily = LibreBaskervilleFamily,
                                fontSize = 12.sp,
                                color = TextSecondary,
                                modifier = Modifier.padding(vertical = 6.dp)
                            )
                        }
                        Spacer(modifier = Modifier.height(16.dp))
                    }

                    // Recent Invoices Section
                    if (account.recentInvoices.isNotEmpty()) {
                        SectionCard(title = "RECENT INVOICES") {
                            account.recentInvoices.forEach { inv ->
                                Column(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
                                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                        Text(
                                            inv.invoiceNumber + (if (!inv.brand.isNullOrBlank()) " (${inv.brand})" else ""),
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
                                            "Billed: ${formatCurrency(inv.amount)} · ${inv.invoiceDate}",
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
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
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
                            "DMS Code: $outletCode",
                            fontFamily = LibreBaskervilleFamily,
                            fontSize = 12.sp,
                            color = TextSecondary
                        )
                    }
                }
                StatusBadge(status = account.collectionStatus)
            }

            Spacer(modifier = Modifier.height(10.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = if (account.mostRecentPayment != null)
                        "Last Paid: ${formatCurrency(account.mostRecentPayment.amount)} (${account.mostRecentPayment.paymentDate})"
                    else
                        "No prior payments",
                    fontFamily = LibreBaskervilleFamily,
                    fontSize = 11.sp,
                    color = TextSecondary
                )
            }
        }
    }
}

@Composable
private fun AccountMetrics(account: AccountSummaryDto) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
        MetricTile(
            title = "TOTAL DUE",
            value = formatCurrency(account.totalOutstanding),
            color = BrandNavy,
            modifier = Modifier.weight(1f)
        )
        val isOverdue = account.overdueAmount.toDoubleOrNull()?.let { it > 0 } == true
        MetricTile(
            title = "OVERDUE",
            value = formatCurrency(account.overdueAmount),
            color = if (isOverdue) ErrorRed else BrandNavy,
            modifier = Modifier.weight(1f)
        )
        MetricTile(
            title = "OLDEST DUE",
            value = "${account.maxDaysOutstanding} d",
            color = if (account.maxDaysOutstanding > 25) ErrorRed else BrandNavy,
            modifier = Modifier.weight(0.9f)
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
        Column(modifier = Modifier.padding(12.dp)) {
            Text(
                title,
                fontFamily = LeagueSpartanFamily,
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 0.8.sp,
                color = TextSecondary
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                value,
                fontFamily = LeagueSpartanFamily,
                fontSize = 17.sp,
                fontWeight = FontWeight.Bold,
                color = color
            )
        }
    }
}

@Composable
private fun AgeingBucketTile(
    label: String,
    amount: String,
    isCritical: Boolean = false,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (isCritical && (amount.toDoubleOrNull() ?: 0.0) > 0)
                ErrorRed.copy(alpha = 0.08f)
            else
                SurfaceSecondary
        ),
        border = androidx.compose.foundation.BorderStroke(1.dp, BrandLightGray)
    ) {
        Column(modifier = Modifier.padding(10.dp)) {
            Text(
                text = label,
                fontFamily = LeagueSpartanFamily,
                fontSize = 11.sp,
                fontWeight = FontWeight.SemiBold,
                color = TextSecondary
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = formatCurrency(amount),
                fontFamily = LeagueSpartanFamily,
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
                color = if (isCritical && (amount.toDoubleOrNull() ?: 0.0) > 0) ErrorRed else BrandNavy
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
                fontSize = 12.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 0.8.sp,
                color = BrandNavy
            )
            Spacer(modifier = Modifier.height(10.dp))
            content()
        }
    }
}
