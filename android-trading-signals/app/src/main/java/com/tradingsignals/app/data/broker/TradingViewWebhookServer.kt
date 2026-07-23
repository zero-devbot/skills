package com.tradingsignals.app.data.broker

import com.tradingsignals.app.data.model.BrokerType
import com.tradingsignals.app.data.model.Candle
import com.tradingsignals.app.data.model.OrderResult
import com.tradingsignals.app.data.model.SignalAction
import com.tradingsignals.app.data.model.TradeSignal
import fi.iki.elonen.NanoHTTPD
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import org.json.JSONObject

/**
 * TradingView doesn't offer an API you can poll from a phone -- its "outgoing" integration is a
 * webhook: you set an alert in TradingView's UI with a JSON message body and a target URL, and
 * TradingView's servers POST to that URL when the alert fires. That means the *phone* has to be
 * reachable from the internet, which a phone normally isn't. Practical ways to make this work:
 *   1. Run this server on a device that has a public IP or port-forwarding (e.g. behind a home
 *      router with forwarding configured), or
 *   2. Tunnel it (Tailscale Funnel, ngrok, Cloudflare Tunnel) and put the tunnel's public URL into
 *      the TradingView alert's webhook field.
 * This class is only the receiving half: a tiny embedded HTTP server that accepts TradingView's
 * POSTed alert JSON (expects a body like {"symbol":"BTCUSDT","action":"buy","price":65000}) and
 * turns it into a TradeSignal the rest of the app already knows how to display.
 */
class TradingViewWebhookServer(port: Int) : NanoHTTPD(port) {

    private val _alerts = MutableSharedFlow<TradeSignal>(extraBufferCapacity = 64)
    val alerts: SharedFlow<TradeSignal> = _alerts.asSharedFlow()

    override fun serve(session: IHTTPSession): Response {
        if (session.method != Method.POST) {
            return newFixedLengthResponse(Response.Status.METHOD_NOT_ALLOWED, MIME_PLAINTEXT, "Only POST is accepted")
        }
        return try {
            val files = HashMap<String, String>()
            session.parseBody(files)
            val body = files["postData"].orEmpty()
            val payload = JSONObject(body)

            val symbol = payload.optString("symbol", "UNKNOWN")
            val action = runCatching {
                SignalAction.valueOf(payload.optString("action", "hold").uppercase())
            }.getOrDefault(SignalAction.HOLD)
            val price = payload.optDouble("price", 0.0)
            val note = payload.optString("note", "")

            _alerts.tryEmit(
                TradeSignal(
                    timestampMillis = System.currentTimeMillis(),
                    symbol = symbol,
                    action = action,
                    price = price,
                    source = "TradingView",
                    note = note,
                )
            )
            newFixedLengthResponse(Response.Status.OK, MIME_PLAINTEXT, "ok")
        } catch (e: Exception) {
            newFixedLengthResponse(Response.Status.BAD_REQUEST, MIME_PLAINTEXT, "Invalid alert payload: ${e.message}")
        }
    }
}

/**
 * Adapts [TradingViewWebhookServer] to the [Broker] interface used elsewhere in the app. It is
 * push-only: fetchCandles and placeOrder both fail clearly rather than pretending to support a
 * pull/trade model TradingView doesn't offer to third-party apps.
 */
class TradingViewBroker(private val server: TradingViewWebhookServer?) : Broker {

    override val type = BrokerType.TRADINGVIEW_WEBHOOK

    override fun isConfigured(): Boolean = server?.isAlive == true

    override suspend fun fetchCandles(symbol: String, interval: String, limit: Int): List<Candle> {
        throw BrokerException(
            "TradingView has no pull API. Start the webhook receiver in Connections and point a " +
                "TradingView alert at it -- signals will arrive there, not through fetchCandles."
        )
    }

    override suspend fun placeOrder(symbol: String, action: SignalAction, quantity: Double): OrderResult =
        OrderResult.Failure("The TradingView webhook receiver is read-only; it cannot place orders.")
}
