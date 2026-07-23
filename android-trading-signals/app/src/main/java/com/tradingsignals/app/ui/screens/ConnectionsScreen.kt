package com.tradingsignals.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Divider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.tradingsignals.app.data.broker.BybitConfig
import com.tradingsignals.app.data.broker.MetaApiConfig

@Composable
fun ConnectionsScreen(
    bybitConfig: BybitConfig,
    onBybitConfigChange: (BybitConfig) -> Unit,
    metaApiConfig: MetaApiConfig,
    onMetaApiConfigChange: (MetaApiConfig) -> Unit,
    tradingViewPort: Int,
    onTradingViewPortChange: (Int) -> Unit,
    tradingViewServerRunning: Boolean,
    onStartTradingViewServer: () -> Unit,
    onStopTradingViewServer: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        BybitSection(bybitConfig, onBybitConfigChange)
        Divider()
        MetaApiSection(metaApiConfig, onMetaApiConfigChange)
        Divider()
        TradingViewSection(
            port = tradingViewPort,
            onPortChange = onTradingViewPortChange,
            running = tradingViewServerRunning,
            onStart = onStartTradingViewServer,
            onStop = onStopTradingViewServer,
        )
    }
}

@Composable
private fun BybitSection(config: BybitConfig, onChange: (BybitConfig) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Bybit", style = MaterialTheme.typography.titleMedium)
        Text(
            "Public candle data works with no keys. Keys are only needed to place orders.",
            style = MaterialTheme.typography.bodySmall,
        )
        OutlinedTextField(
            value = config.apiKey,
            onValueChange = { onChange(config.copy(apiKey = it)) },
            label = { Text("API key") },
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = config.apiSecret,
            onValueChange = { onChange(config.copy(apiSecret = it)) },
            label = { Text("API secret") },
            modifier = Modifier.fillMaxWidth(),
        )
        Row(verticalAlignment = Alignment.CenterVertically) {
            Switch(
                checked = config.useTestnet,
                onCheckedChange = { onChange(config.copy(useTestnet = it)) },
            )
            Text(" Use testnet")
        }
        OutlinedTextField(
            value = config.category,
            onValueChange = { onChange(config.copy(category = it)) },
            label = { Text("Category (spot / linear / inverse)") },
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun MetaApiSection(config: MetaApiConfig, onChange: (MetaApiConfig) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("MT5 (via MetaApi)", style = MaterialTheme.typography.titleMedium)
        Text(
            "MT5 has no direct mobile API. Deploy your MT5 account to MetaApi.cloud first, then " +
                "paste the resulting account id and token below.",
            style = MaterialTheme.typography.bodySmall,
        )
        OutlinedTextField(
            value = config.token,
            onValueChange = { onChange(config.copy(token = it)) },
            label = { Text("MetaApi token") },
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = config.accountId,
            onValueChange = { onChange(config.copy(accountId = it)) },
            label = { Text("MetaApi account id") },
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = config.region,
            onValueChange = { onChange(config.copy(region = it)) },
            label = { Text("Region (e.g. new-york, london)") },
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun TradingViewSection(
    port: Int,
    onPortChange: (Int) -> Unit,
    running: Boolean,
    onStart: () -> Unit,
    onStop: () -> Unit,
) {
    var portText by remember(port) { mutableStateOf(port.toString()) }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("TradingView (webhook)", style = MaterialTheme.typography.titleMedium)
        Text(
            "TradingView pushes alerts to a URL you give it; it can't be polled. This starts a " +
                "local receiver on this device. For TradingView's servers to reach it, the phone " +
                "needs to be reachable from the internet (port forwarding, or a tunnel like " +
                "Tailscale Funnel / ngrok) -- point the TradingView alert's webhook URL at that " +
                "public address, path \"/\", with a JSON body such as " +
                "{\"symbol\":\"BTCUSDT\",\"action\":\"buy\",\"price\":65000}.",
            style = MaterialTheme.typography.bodySmall,
        )
        OutlinedTextField(
            value = portText,
            onValueChange = {
                portText = it
                it.toIntOrNull()?.let(onPortChange)
            },
            label = { Text("Local port") },
            enabled = !running,
            modifier = Modifier.fillMaxWidth(),
        )
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (running) {
                Button(onClick = onStop) { Text("Stop receiver") }
            } else {
                Button(onClick = onStart) { Text("Start receiver") }
            }
        }
        Text(
            if (running) "Receiver running on port $port." else "Receiver stopped.",
            style = MaterialTheme.typography.bodySmall,
        )
    }
}
