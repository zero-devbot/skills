package com.tradingsignals.app.data.broker

import com.tradingsignals.app.data.model.BrokerType
import com.tradingsignals.app.data.model.Candle
import com.tradingsignals.app.data.model.OrderResult
import com.tradingsignals.app.data.model.SignalAction

/**
 * Common surface every market connection implements, whether it's a real exchange API
 * (Bybit), a bridge to a desktop terminal (MT5 via MetaApi), or a passive receiver
 * (TradingView alerts arrive as webhooks, they aren't pulled).
 */
interface Broker {
    val type: BrokerType

    /** True once the user has entered enough config (keys/tokens) to actually call out. */
    fun isConfigured(): Boolean

    /** Recent OHLCV history for [symbol] on [interval] (e.g. "1", "5", "60", "D"), newest last. */
    suspend fun fetchCandles(symbol: String, interval: String, limit: Int): List<Candle>

    /**
     * Attempt to place a market order. Brokers with no order-placement path (e.g. the
     * TradingView webhook receiver is read-only) return [OrderResult.Failure] explaining why.
     */
    suspend fun placeOrder(symbol: String, action: SignalAction, quantity: Double): OrderResult
}
