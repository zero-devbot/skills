package com.tradingsignals.app.data.python

import com.chaquo.python.Python
import com.tradingsignals.app.data.model.Candle
import com.tradingsignals.app.data.model.SignalAction
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

data class StrategyResult(val action: SignalAction, val note: String)

class StrategyExecutionException(message: String) : Exception(message)

/**
 * Thin wrapper around the `strategy_runner` Python module (app/src/main/python) that Chaquopy
 * bundles into the APK. Python.start() must already have been called (see TradingSignalsApp)
 * before this is used.
 */
object PythonStrategyEngine {

    suspend fun run(userCode: String, candles: List<Candle>): StrategyResult =
        withContext(Dispatchers.Default) {
            val candlesJson = JSONArray().apply {
                candles.forEach { c ->
                    put(
                        JSONObject().apply {
                            put("timestamp", c.timestampMillis)
                            put("open", c.open)
                            put("high", c.high)
                            put("low", c.low)
                            put("close", c.close)
                            put("volume", c.volume)
                        }
                    )
                }
            }.toString()

            val module = Python.getInstance().getModule("strategy_runner")
            val resultJson = try {
                module.callAttr("run_user_strategy", userCode, candlesJson).toString()
            } catch (e: Exception) {
                // Chaquopy wraps Python exceptions (including our StrategyError) as PyException.
                throw StrategyExecutionException(e.message ?: "Strategy execution failed")
            }

            val result = JSONObject(resultJson)
            val action = runCatching {
                SignalAction.valueOf(result.getString("action"))
            }.getOrElse { throw StrategyExecutionException("Strategy returned an unrecognized action") }

            StrategyResult(action = action, note = result.optString("note", ""))
        }
}
