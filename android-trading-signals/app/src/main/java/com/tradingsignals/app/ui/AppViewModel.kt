package com.tradingsignals.app.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.tradingsignals.app.AppContainer
import com.tradingsignals.app.TradingSignalsApp
import com.tradingsignals.app.data.broker.BybitConfig
import com.tradingsignals.app.data.broker.MetaApiConfig
import com.tradingsignals.app.data.model.BrokerType
import com.tradingsignals.app.data.model.TradeSignal
import com.tradingsignals.app.data.python.PythonStrategyEngine
import com.tradingsignals.app.service.SignalScheduler
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class RunState {
    data object Idle : RunState()
    data object Running : RunState()
    data class Done(val signal: TradeSignal) : RunState()
    data class Error(val message: String) : RunState()
}

class AppViewModel(application: Application) : AndroidViewModel(application) {

    private val container: AppContainer
        get() = (getApplication<Application>() as TradingSignalsApp).container

    val signals: StateFlow<List<TradeSignal>> get() = container.signalsRepository.signals

    private val _runState = MutableStateFlow<RunState>(RunState.Idle)
    val runState: StateFlow<RunState> = _runState.asStateFlow()

    private val _strategyCode = MutableStateFlow(container.settings.strategyCode)
    val strategyCode: StateFlow<String> = _strategyCode.asStateFlow()

    private val _symbol = MutableStateFlow(container.settings.symbol)
    val symbol: StateFlow<String> = _symbol.asStateFlow()

    private val _interval = MutableStateFlow(container.settings.interval)
    val interval: StateFlow<String> = _interval.asStateFlow()

    private val _activeBroker = MutableStateFlow(container.settings.activeBroker)
    val activeBroker: StateFlow<BrokerType> = _activeBroker.asStateFlow()

    private val _bybitConfig = MutableStateFlow(container.settings.bybitConfig)
    val bybitConfig: StateFlow<BybitConfig> = _bybitConfig.asStateFlow()

    private val _metaApiConfig = MutableStateFlow(container.settings.metaApiConfig)
    val metaApiConfig: StateFlow<MetaApiConfig> = _metaApiConfig.asStateFlow()

    private val _tradingViewPort = MutableStateFlow(container.settings.tradingViewPort)
    val tradingViewPort: StateFlow<Int> = _tradingViewPort.asStateFlow()

    private val _tradingViewServerRunning = MutableStateFlow(false)
    val tradingViewServerRunning: StateFlow<Boolean> = _tradingViewServerRunning.asStateFlow()

    private val _backgroundChecksEnabled = MutableStateFlow(container.settings.backgroundChecksEnabled)
    val backgroundChecksEnabled: StateFlow<Boolean> = _backgroundChecksEnabled.asStateFlow()

    fun updateStrategyCode(code: String) {
        _strategyCode.value = code
        container.settings.strategyCode = code
    }

    fun updateSymbol(value: String) {
        _symbol.value = value
        container.settings.symbol = value
    }

    fun updateInterval(value: String) {
        _interval.value = value
        container.settings.interval = value
    }

    fun updateActiveBroker(type: BrokerType) {
        _activeBroker.value = type
        container.settings.activeBroker = type
    }

    fun updateBybitConfig(config: BybitConfig) {
        _bybitConfig.value = config
        container.settings.bybitConfig = config
    }

    fun updateMetaApiConfig(config: MetaApiConfig) {
        _metaApiConfig.value = config
        container.settings.metaApiConfig = config
    }

    fun updateTradingViewPort(port: Int) {
        _tradingViewPort.value = port
        container.settings.tradingViewPort = port
    }

    fun startTradingViewServer() {
        container.startTradingViewServer(tradingViewPort.value)
        _tradingViewServerRunning.value = true
        viewModelScope.launch {
            container.tradingViewServer?.alerts?.collect { signal ->
                container.signalsRepository.add(signal)
            }
        }
    }

    fun stopTradingViewServer() {
        container.stopTradingViewServer()
        _tradingViewServerRunning.value = false
    }

    fun runStrategyNow() {
        viewModelScope.launch {
            _runState.value = RunState.Running
            try {
                val broker = container.brokerFor(activeBroker.value)
                val candles = broker.fetchCandles(symbol.value, interval.value, limit = 200)
                if (candles.isEmpty()) {
                    _runState.value = RunState.Error("No candles returned for ${symbol.value}.")
                    return@launch
                }
                val result = PythonStrategyEngine.run(strategyCode.value, candles)
                val signal = TradeSignal(
                    timestampMillis = System.currentTimeMillis(),
                    symbol = symbol.value,
                    action = result.action,
                    price = candles.last().close,
                    source = broker.type.displayName,
                    note = result.note,
                )
                container.signalsRepository.add(signal)
                _runState.value = RunState.Done(signal)
            } catch (e: Exception) {
                _runState.value = RunState.Error(e.message ?: "Unknown error")
            }
        }
    }

    fun enableBackgroundChecks(enabled: Boolean) {
        _backgroundChecksEnabled.value = enabled
        container.settings.backgroundChecksEnabled = enabled
        if (enabled) {
            SignalScheduler.start(getApplication())
        } else {
            SignalScheduler.stop(getApplication())
        }
    }
}
