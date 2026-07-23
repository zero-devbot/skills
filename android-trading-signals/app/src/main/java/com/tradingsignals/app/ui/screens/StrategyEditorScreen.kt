package com.tradingsignals.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.tradingsignals.app.data.model.BrokerType
import com.tradingsignals.app.ui.RunState

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun StrategyEditorScreen(
    strategyCode: String,
    onStrategyCodeChange: (String) -> Unit,
    symbol: String,
    onSymbolChange: (String) -> Unit,
    interval: String,
    onIntervalChange: (String) -> Unit,
    activeBroker: BrokerType,
    onActiveBrokerChange: (BrokerType) -> Unit,
    backgroundChecksEnabled: Boolean,
    onBackgroundChecksChange: (Boolean) -> Unit,
    runState: RunState,
    onRunNow: () -> Unit,
) {
    var brokerMenuExpanded by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Broker & market", style = MaterialTheme.typography.titleMedium)

        ExposedDropdownMenuBox(
            expanded = brokerMenuExpanded,
            onExpandedChange = { brokerMenuExpanded = it },
        ) {
            OutlinedTextField(
                value = activeBroker.displayName,
                onValueChange = {},
                readOnly = true,
                label = { Text("Active broker") },
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor(),
            )
            androidx.compose.material3.ExposedDropdownMenu(
                expanded = brokerMenuExpanded,
                onDismissRequest = { brokerMenuExpanded = false },
            ) {
                BrokerType.entries.forEach { type ->
                    androidx.compose.material3.DropdownMenuItem(
                        text = { Text(type.displayName) },
                        onClick = {
                            onActiveBrokerChange(type)
                            brokerMenuExpanded = false
                        },
                    )
                }
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = symbol,
                onValueChange = onSymbolChange,
                label = { Text("Symbol") },
                modifier = Modifier.weight(1f),
            )
            OutlinedTextField(
                value = interval,
                onValueChange = onIntervalChange,
                label = { Text("Interval") },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
                modifier = Modifier.weight(1f),
            )
        }
        Text(
            "Interval uses Bybit-style tokens (1, 5, 15, 60, 240, D) which are mapped to MetaApi " +
                "timeframes automatically when MT5 is the active broker.",
            style = MaterialTheme.typography.bodySmall,
        )

        Text("Strategy code (Python)", style = MaterialTheme.typography.titleMedium)
        Text(
            "Must define a function `strategy(candles)` returning " +
                "{\"action\": \"BUY\"|\"SELL\"|\"HOLD\", \"note\": \"...\"}.",
            style = MaterialTheme.typography.bodySmall,
        )
        OutlinedTextField(
            value = strategyCode,
            onValueChange = onStrategyCodeChange,
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = 4.dp),
            textStyle = TextStyle(fontFamily = FontFamily.Monospace, fontSize = MaterialTheme.typography.bodySmall.fontSize),
            minLines = 12,
        )

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Button(onClick = onRunNow, enabled = runState !is RunState.Running) {
                Text("Run strategy now")
            }
            if (runState is RunState.Running) {
                CircularProgressIndicator(modifier = Modifier.padding(start = 8.dp))
            }
        }

        when (runState) {
            is RunState.Done -> Text(
                "Last run: ${runState.signal.action} @ ${runState.signal.price} - ${runState.signal.note}",
                style = MaterialTheme.typography.bodyMedium,
            )
            is RunState.Error -> Text(
                "Error: ${runState.message}",
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodyMedium,
            )
            else -> {}
        }

        Text("Background checks", style = MaterialTheme.typography.titleMedium)
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            androidx.compose.material3.Switch(
                checked = backgroundChecksEnabled,
                onCheckedChange = onBackgroundChecksChange,
            )
            Text(
                " Run this strategy automatically every 15 minutes and notify on new BUY/SELL signals.",
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}
