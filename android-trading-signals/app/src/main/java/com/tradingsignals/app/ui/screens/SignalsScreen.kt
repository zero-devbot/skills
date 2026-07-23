package com.tradingsignals.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.tradingsignals.app.data.model.SignalAction
import com.tradingsignals.app.data.model.TradeSignal
import com.tradingsignals.app.ui.theme.BuyColor
import com.tradingsignals.app.ui.theme.SellColor
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun SignalsScreen(signals: List<TradeSignal>) {
    if (signals.isEmpty()) {
        Box(Modifier.fillMaxSize()) {
            Text(
                "No signals yet. Run your strategy from the Strategy tab, or wait for the " +
                    "background check / a TradingView webhook to produce one.",
                modifier = Modifier
                    .align(Alignment.Center)
                    .padding(32.dp),
            )
        }
        return
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(signals) { signal -> SignalCard(signal) }
    }
}

@Composable
private fun SignalCard(signal: TradeSignal) {
    val actionColor = when (signal.action) {
        SignalAction.BUY -> BuyColor
        SignalAction.SELL -> SellColor
        SignalAction.HOLD -> MaterialTheme.colorScheme.onSurfaceVariant
    }
    val timeFormat = remember(signal.timestampMillis) {
        SimpleDateFormat("MMM d, HH:mm:ss", Locale.getDefault()).format(Date(signal.timestampMillis))
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    text = "${signal.action} ${signal.symbol}",
                    color = actionColor,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(text = timeFormat, style = MaterialTheme.typography.bodySmall)
            }
            Text(
                text = "${signal.source} @ ${signal.price}",
                style = MaterialTheme.typography.bodyMedium,
            )
            if (signal.note.isNotBlank()) {
                Text(text = signal.note, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
