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
import org.json.JSONObject
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

data class BybitConfig(
    val apiKey: String = "",
    val apiSecret: String = "",
    val useTestnet: Boolean = true,
    val category: String = "linear", // spot | linear | inverse
)

/**
 * Bybit is the only one of the three connections that exposes a real, documented, mobile-friendly
 * REST API (v5), which is why it's the fully-worked-out example. Public market data needs no
 * auth; order placement is signed per Bybit's HMAC-SHA256 v5 auth scheme.
 *
 * Docs: https://bybit-exchange.github.io/docs/v5/market/kline
 *       https://bybit-exchange.github.io/docs/v5/order/create-order
 */
class BybitBroker(private val configProvider: () -> BybitConfig) : Broker {

    override val type = BrokerType.BYBIT

    private val client = OkHttpClient()
    private val json = "application/json; charset=utf-8".toMediaType()

    private fun baseUrl(cfg: BybitConfig) =
        if (cfg.useTestnet) "https://api-testnet.bybit.com" else "https://api.bybit.com"

    override fun isConfigured(): Boolean {
        // Reading candles doesn't require keys; trading does. The screen surfaces both states.
        return true
    }

    override suspend fun fetchCandles(symbol: String, interval: String, limit: Int): List<Candle> =
        withContext(Dispatchers.IO) {
            val cfg = configProvider()
            val url = "${baseUrl(cfg)}/v5/market/kline"
                .toHttpUrl()
                .newBuilder()
                .addQueryParameter("category", cfg.category)
                .addQueryParameter("symbol", symbol)
                .addQueryParameter("interval", interval)
                .addQueryParameter("limit", limit.toString())
                .build()

            val request = Request.Builder().url(url).get().build()
            client.newCall(request).execute().use { response ->
                val bodyString = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    throw BrokerException("Bybit kline request failed: HTTP ${response.code} $bodyString")
                }
                val root = JSONObject(bodyString)
                if (root.optInt("retCode", -1) != 0) {
                    throw BrokerException("Bybit error: ${root.optString("retMsg")}")
                }
                val list = root.getJSONObject("result").getJSONArray("list")
                val candles = mutableListOf<Candle>()
                // Bybit returns newest-first; reverse so index 0 is oldest, matching strategy expectations.
                for (i in list.length() - 1 downTo 0) {
                    val row = list.getJSONArray(i)
                    candles += Candle(
                        timestampMillis = row.getString(0).toLong(),
                        open = row.getString(1).toDouble(),
                        high = row.getString(2).toDouble(),
                        low = row.getString(3).toDouble(),
                        close = row.getString(4).toDouble(),
                        volume = row.getString(5).toDouble(),
                    )
                }
                candles
            }
        }

    override suspend fun placeOrder(symbol: String, action: SignalAction, quantity: Double): OrderResult =
        withContext(Dispatchers.IO) {
            val cfg = configProvider()
            if (cfg.apiKey.isBlank() || cfg.apiSecret.isBlank()) {
                return@withContext OrderResult.Failure("Bybit API key/secret not set in Connections.")
            }
            if (action == SignalAction.HOLD) {
                return@withContext OrderResult.Failure("HOLD signals are not sent as orders.")
            }

            val bodyJson = JSONObject().apply {
                put("category", cfg.category)
                put("symbol", symbol)
                put("side", if (action == SignalAction.BUY) "Buy" else "Sell")
                put("orderType", "Market")
                put("qty", quantity.toString())
            }.toString()

            val timestamp = System.currentTimeMillis().toString()
            val recvWindow = "5000"
            val signaturePayload = timestamp + cfg.apiKey + recvWindow + bodyJson
            val signature = hmacSha256Hex(cfg.apiSecret, signaturePayload)

            val request = Request.Builder()
                .url("${baseUrl(cfg)}/v5/order/create")
                .post(bodyJson.toRequestBody(json))
                .addHeader("X-BAPI-API-KEY", cfg.apiKey)
                .addHeader("X-BAPI-TIMESTAMP", timestamp)
                .addHeader("X-BAPI-RECV-WINDOW", recvWindow)
                .addHeader("X-BAPI-SIGN", signature)
                .build()

            client.newCall(request).execute().use { response ->
                val bodyString = response.body?.string().orEmpty()
                val root = runCatching { JSONObject(bodyString) }.getOrNull()
                val retCode = root?.optInt("retCode", -1) ?: -1
                if (response.isSuccessful && retCode == 0) {
                    val orderId = root?.getJSONObject("result")?.optString("orderId").orEmpty()
                    OrderResult.Success(orderId)
                } else {
                    OrderResult.Failure(root?.optString("retMsg") ?: "HTTP ${response.code}: $bodyString")
                }
            }
        }

    private fun hmacSha256Hex(secret: String, payload: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(secret.toByteArray(), "HmacSHA256"))
        val bytes = mac.doFinal(payload.toByteArray())
        val hex = StringBuilder(bytes.size * 2)
        for (b in bytes) hex.append(String.format("%02x", b))
        return hex.toString()
    }
}

class BrokerException(message: String) : Exception(message)
