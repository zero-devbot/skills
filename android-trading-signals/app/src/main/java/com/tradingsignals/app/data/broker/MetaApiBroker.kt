package com.tradingsignals.app.data.broker

import com.tradingsignals.app.data.model.BrokerType
import com.tradingsignals.app.data.model.Candle
import com.tradingsignals.app.data.model.OrderResult
import com.tradingsignals.app.data.model.SignalAction
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject

data class MetaApiConfig(
    val token: String = "",
    val accountId: String = "",
    val region: String = "new-york",
)

/**
 * MT5 has no public mobile/REST API of its own -- the terminal is a Windows desktop app that only
 * speaks its own wire protocol. The standard way to reach an MT5 account from a phone or server is
 * through a hosted bridge; MetaApi (https://metaapi.cloud) is the most widely used one, and this
 * class talks to its client REST API. You need a MetaApi account with your MT5 login already
 * deployed to a MetaApi cloud account, which gives you the `accountId` and `token` this class needs.
 *
 * If you'd rather self-host the bridge: MetaQuotes' own `MetaTrader5` Python package can expose an
 * MT5 terminal running on Windows over your own HTTP API, but that box has to run Windows with MT5
 * installed and always-on -- there is no way around a bridge of some kind existing somewhere.
 *
 * Docs: https://metaapi.cloud/docs/client/restApi/api/readTradingTerminalState/readHistoricalCandles/
 */
class MetaApiBroker(private val configProvider: () -> MetaApiConfig) : Broker {

    override val type = BrokerType.MT5_METAAPI

    private val client = OkHttpClient()
    private val json = "application/json; charset=utf-8".toMediaType()

    private fun baseUrl(cfg: MetaApiConfig) = "https://mt-client-api-v1.${cfg.region}.agiliumtrade.ai"

    override fun isConfigured(): Boolean {
        val cfg = configProvider()
        return cfg.token.isNotBlank() && cfg.accountId.isNotBlank()
    }

    /** Maps generic interval strings ("1","5","60","D") to MetaApi timeframe tokens. */
    private fun toMetaApiTimeframe(interval: String): String = when (interval) {
        "1" -> "1m"; "5" -> "5m"; "15" -> "15m"; "30" -> "30m"
        "60" -> "1h"; "240" -> "4h"; "D", "1440" -> "1d"; "W" -> "1w"
        else -> interval // allow passing MetaApi tokens straight through
    }

    override suspend fun fetchCandles(symbol: String, interval: String, limit: Int): List<Candle> =
        withContext(Dispatchers.IO) {
            val cfg = configProvider()
            if (!isConfigured()) {
                throw BrokerException("MetaApi token/accountId not set in Connections.")
            }
            val timeframe = toMetaApiTimeframe(interval)
            val url = "${baseUrl(cfg)}/users/current/accounts/${cfg.accountId}/historical-market-data/symbols/$symbol/timeframes/$timeframe/candles"
                .toHttpUrl()
                .newBuilder()
                .addQueryParameter("limit", limit.toString())
                .build()

            val request = Request.Builder()
                .url(url)
                .addHeader("auth-token", cfg.token)
                .get()
                .build()

            client.newCall(request).execute().use { response ->
                val bodyString = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    throw BrokerException("MetaApi candle request failed: HTTP ${response.code} $bodyString")
                }
                val array = JSONArray(bodyString)
                val candles = mutableListOf<Candle>()
                for (i in 0 until array.length()) {
                    val row = array.getJSONObject(i)
                    candles += Candle(
                        timestampMillis = parseIsoTimeToMillis(row.optString("time")),
                        open = row.getDouble("open"),
                        high = row.getDouble("high"),
                        low = row.getDouble("low"),
                        close = row.getDouble("close"),
                        volume = row.optDouble("tickVolume", row.optDouble("volume", 0.0)),
                    )
                }
                candles
            }
        }

    override suspend fun placeOrder(symbol: String, action: SignalAction, quantity: Double): OrderResult =
        withContext(Dispatchers.IO) {
            val cfg = configProvider()
            if (!isConfigured()) {
                return@withContext OrderResult.Failure("MetaApi token/accountId not set in Connections.")
            }
            if (action == SignalAction.HOLD) {
                return@withContext OrderResult.Failure("HOLD signals are not sent as orders.")
            }

            val bodyJson = JSONObject().apply {
                put("actionType", if (action == SignalAction.BUY) "ORDER_TYPE_BUY" else "ORDER_TYPE_SELL")
                put("symbol", symbol)
                put("volume", quantity)
            }.toString()

            val request = Request.Builder()
                .url("${baseUrl(cfg)}/users/current/accounts/${cfg.accountId}/trade")
                .addHeader("auth-token", cfg.token)
                .post(bodyJson.toRequestBody(json))
                .build()

            client.newCall(request).execute().use { response ->
                val bodyString = response.body?.string().orEmpty()
                val root = runCatching { JSONObject(bodyString) }.getOrNull()
                if (response.isSuccessful) {
                    OrderResult.Success(root?.optString("orderId") ?: root?.optString("positionId").orEmpty())
                } else {
                    OrderResult.Failure(root?.optString("message") ?: "HTTP ${response.code}: $bodyString")
                }
            }
        }

    private fun parseIsoTimeToMillis(iso: String): Long {
        return runCatching {
            java.time.Instant.parse(iso).toEpochMilli()
        }.getOrElse { System.currentTimeMillis() }
    }
}
