package com.tradingsignals.app.ui

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.tradingsignals.app.ui.screens.ConnectionsScreen
import com.tradingsignals.app.ui.screens.SignalsScreen
import com.tradingsignals.app.ui.screens.StrategyEditorScreen

private sealed class Tab(val route: String, val label: String) {
    data object Signals : Tab("signals", "Signals")
    data object Strategy : Tab("strategy", "Strategy")
    data object Connections : Tab("connections", "Connections")
}

private val tabs = listOf(Tab.Signals, Tab.Strategy, Tab.Connections)

@Composable
fun TradingSignalsNavHost(viewModel: AppViewModel) {
    val navController = rememberNavController()

    Scaffold(
        bottomBar = {
            NavigationBar {
                val backStackEntry by navController.currentBackStackEntryAsState()
                val currentDestination = backStackEntry?.destination

                tabs.forEach { tab ->
                    val selected = currentDestination?.hierarchy?.any { it.route == tab.route } == true
                    NavigationBarItem(
                        selected = selected,
                        onClick = {
                            navController.navigate(tab.route) {
                                popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = {
                            val icon = when (tab) {
                                Tab.Signals -> Icons.Filled.List
                                Tab.Strategy -> Icons.Filled.Star
                                Tab.Connections -> Icons.Filled.Settings
                            }
                            Icon(icon, contentDescription = tab.label)
                        },
                        label = { Text(tab.label) },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = Tab.Signals.route,
            modifier = Modifier.padding(padding),
        ) {
            composable(Tab.Signals.route) {
                val signals by viewModel.signals.collectAsState()
                SignalsScreen(signals = signals)
            }
            composable(Tab.Strategy.route) {
                val strategyCode by viewModel.strategyCode.collectAsState()
                val symbol by viewModel.symbol.collectAsState()
                val interval by viewModel.interval.collectAsState()
                val activeBroker by viewModel.activeBroker.collectAsState()
                val runState by viewModel.runState.collectAsState()
                val backgroundChecksEnabled by viewModel.backgroundChecksEnabled.collectAsState()

                StrategyEditorScreen(
                    strategyCode = strategyCode,
                    onStrategyCodeChange = viewModel::updateStrategyCode,
                    symbol = symbol,
                    onSymbolChange = viewModel::updateSymbol,
                    interval = interval,
                    onIntervalChange = viewModel::updateInterval,
                    activeBroker = activeBroker,
                    onActiveBrokerChange = viewModel::updateActiveBroker,
                    backgroundChecksEnabled = backgroundChecksEnabled,
                    onBackgroundChecksChange = viewModel::enableBackgroundChecks,
                    runState = runState,
                    onRunNow = viewModel::runStrategyNow,
                )
            }
            composable(Tab.Connections.route) {
                val bybitConfig by viewModel.bybitConfig.collectAsState()
                val metaApiConfig by viewModel.metaApiConfig.collectAsState()
                val tradingViewPort by viewModel.tradingViewPort.collectAsState()
                val tradingViewRunning by viewModel.tradingViewServerRunning.collectAsState()

                ConnectionsScreen(
                    bybitConfig = bybitConfig,
                    onBybitConfigChange = viewModel::updateBybitConfig,
                    metaApiConfig = metaApiConfig,
                    onMetaApiConfigChange = viewModel::updateMetaApiConfig,
                    tradingViewPort = tradingViewPort,
                    onTradingViewPortChange = viewModel::updateTradingViewPort,
                    tradingViewServerRunning = tradingViewRunning,
                    onStartTradingViewServer = viewModel::startTradingViewServer,
                    onStopTradingViewServer = viewModel::stopTradingViewServer,
                )
            }
        }
    }
}
