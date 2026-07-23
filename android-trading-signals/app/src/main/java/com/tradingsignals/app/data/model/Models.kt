package com.tradingsignals.app.data.model

/** One OHLCV bar for a symbol/timeframe. */
data class Candle(
    val timestampMillis: Long,
    val open: Double,
    val high: Double,
    val low: Double,
    val close: Double,
    val volume: Double,
)

enum class SignalAction { BUY, SELL, HOLD }

/** A signal produced either by the Python strategy or received from a TradingView webhook. */
data class TradeSignal(
    val timestampMillis: Long,
    val symbol: String,
    val action: SignalAction,
    val price: Double,
    val source: String,
    val note: String = "",
)

enum class BrokerType(val displayName: String) {
    BYBIT("Bybit"),
    MT5_METAAPI("MT5 (via MetaApi)"),
    TRADINGVIEW_WEBHOOK("TradingView (webhook)"),
}

/** Result of an order placement attempt. Brokers that can't trade return a failure explaining why. */
sealed class OrderResult {
    data class Success(val orderId: String) : OrderResult()
    data class Failure(val reason: String) : OrderResult()
}
