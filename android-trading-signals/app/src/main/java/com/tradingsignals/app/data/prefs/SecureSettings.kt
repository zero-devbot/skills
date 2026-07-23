package com.tradingsignals.app.data.prefs

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.tradingsignals.app.data.broker.BybitConfig
import com.tradingsignals.app.data.broker.MetaApiConfig
import com.tradingsignals.app.data.model.BrokerType

/**
 * API keys and tokens are sensitive, so they're stored in EncryptedSharedPreferences (backed by
 * the Android Keystore) rather than plain SharedPreferences, a plaintext file, or a database.
 */
class SecureSettings(context: Context) {

    private val prefs: SharedPreferences = run {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        EncryptedSharedPreferences.create(
            context,
            "trading_signals_secure_prefs",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    var activeBroker: BrokerType
        get() = BrokerType.entries.firstOrNull { it.name == prefs.getString(KEY_ACTIVE_BROKER, null) }
            ?: BrokerType.BYBIT
        set(value) = prefs.edit().putString(KEY_ACTIVE_BROKER, value.name).apply()

    var symbol: String
        get() = prefs.getString(KEY_SYMBOL, "BTCUSDT") ?: "BTCUSDT"
        set(value) = prefs.edit().putString(KEY_SYMBOL, value).apply()

    var interval: String
        get() = prefs.getString(KEY_INTERVAL, "60") ?: "60"
        set(value) = prefs.edit().putString(KEY_INTERVAL, value).apply()

    var strategyCode: String
        get() = prefs.getString(KEY_STRATEGY_CODE, null) ?: DEFAULT_STRATEGY_CODE
        set(value) = prefs.edit().putString(KEY_STRATEGY_CODE, value).apply()

    var bybitConfig: BybitConfig
        get() = BybitConfig(
            apiKey = prefs.getString(KEY_BYBIT_API_KEY, "") ?: "",
            apiSecret = prefs.getString(KEY_BYBIT_API_SECRET, "") ?: "",
            useTestnet = prefs.getBoolean(KEY_BYBIT_TESTNET, true),
            category = prefs.getString(KEY_BYBIT_CATEGORY, "linear") ?: "linear",
        )
        set(value) = prefs.edit()
            .putString(KEY_BYBIT_API_KEY, value.apiKey)
            .putString(KEY_BYBIT_API_SECRET, value.apiSecret)
            .putBoolean(KEY_BYBIT_TESTNET, value.useTestnet)
            .putString(KEY_BYBIT_CATEGORY, value.category)
            .apply()

    var metaApiConfig: MetaApiConfig
        get() = MetaApiConfig(
            token = prefs.getString(KEY_METAAPI_TOKEN, "") ?: "",
            accountId = prefs.getString(KEY_METAAPI_ACCOUNT_ID, "") ?: "",
            region = prefs.getString(KEY_METAAPI_REGION, "new-york") ?: "new-york",
        )
        set(value) = prefs.edit()
            .putString(KEY_METAAPI_TOKEN, value.token)
            .putString(KEY_METAAPI_ACCOUNT_ID, value.accountId)
            .putString(KEY_METAAPI_REGION, value.region)
            .apply()

    var tradingViewPort: Int
        get() = prefs.getInt(KEY_TRADINGVIEW_PORT, 8080)
        set(value) = prefs.edit().putInt(KEY_TRADINGVIEW_PORT, value).apply()

    var backgroundChecksEnabled: Boolean
        get() = prefs.getBoolean(KEY_BACKGROUND_CHECKS, false)
        set(value) = prefs.edit().putBoolean(KEY_BACKGROUND_CHECKS, value).apply()

    companion object {
        private const val KEY_ACTIVE_BROKER = "active_broker"
        private const val KEY_SYMBOL = "symbol"
        private const val KEY_INTERVAL = "interval"
        private const val KEY_STRATEGY_CODE = "strategy_code"

        private const val KEY_BYBIT_API_KEY = "bybit_api_key"
        private const val KEY_BYBIT_API_SECRET = "bybit_api_secret"
        private const val KEY_BYBIT_TESTNET = "bybit_testnet"
        private const val KEY_BYBIT_CATEGORY = "bybit_category"

        private const val KEY_METAAPI_TOKEN = "metaapi_token"
        private const val KEY_METAAPI_ACCOUNT_ID = "metaapi_account_id"
        private const val KEY_METAAPI_REGION = "metaapi_region"

        private const val KEY_TRADINGVIEW_PORT = "tradingview_port"
        private const val KEY_BACKGROUND_CHECKS = "background_checks_enabled"

        val DEFAULT_STRATEGY_CODE = """
            def strategy(candles):
                closes = [c["close"] for c in candles]
                if len(closes) < 20:
                    return {"action": "HOLD", "note": "not enough candles yet (need 20)"}

                fast = sum(closes[-5:]) / 5
                slow = sum(closes[-20:]) / 20

                if fast > slow:
                    return {"action": "BUY", "note": f"fast MA {fast:.4f} > slow MA {slow:.4f}"}
                if fast < slow:
                    return {"action": "SELL", "note": f"fast MA {fast:.4f} < slow MA {slow:.4f}"}
                return {"action": "HOLD", "note": "fast MA == slow MA"}
        """.trimIndent()
    }
}
