package com.tradingsignals.app

import android.content.Context
import com.tradingsignals.app.data.broker.Broker
import com.tradingsignals.app.data.broker.BybitBroker
import com.tradingsignals.app.data.broker.MetaApiBroker
import com.tradingsignals.app.data.broker.TradingViewBroker
import com.tradingsignals.app.data.broker.TradingViewWebhookServer
import com.tradingsignals.app.data.model.BrokerType
import com.tradingsignals.app.data.prefs.SecureSettings
import com.tradingsignals.app.data.repo.SignalsRepository

/**
 * Small hand-rolled service locator. A DI framework (Hilt/Koin) would be reasonable to add if
 * this app grows, but for three brokers and two repositories it's not pulling its weight yet.
 */
class AppContainer(context: Context) {

    val settings = SecureSettings(context)
    val signalsRepository = SignalsRepository(context)

    var tradingViewServer: TradingViewWebhookServer? = null
        private set

    private val bybitBroker: Broker by lazy { BybitBroker { settings.bybitConfig } }
    private val metaApiBroker: Broker by lazy { MetaApiBroker { settings.metaApiConfig } }
    private val tradingViewBroker: Broker by lazy { TradingViewBroker(tradingViewServer) }

    fun startTradingViewServer(port: Int) {
        stopTradingViewServer()
        tradingViewServer = TradingViewWebhookServer(port).apply { start() }
    }

    fun stopTradingViewServer() {
        tradingViewServer?.stop()
        tradingViewServer = null
    }

    fun brokerFor(type: BrokerType): Broker = when (type) {
        BrokerType.BYBIT -> bybitBroker
        BrokerType.MT5_METAAPI -> metaApiBroker
        BrokerType.TRADINGVIEW_WEBHOOK -> TradingViewBroker(tradingViewServer)
    }

    fun activeBroker(): Broker = brokerFor(settings.activeBroker)
}
