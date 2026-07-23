package com.tradingsignals.app.data.repo

import android.content.Context
import com.tradingsignals.app.data.model.SignalAction
import com.tradingsignals.app.data.model.TradeSignal
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

private const val MAX_STORED_SIGNALS = 200

/**
 * Keeps the signal history in memory (for the UI) and mirrors it to a small JSON file so it
 * survives process death. A full database was overkill for a list this small.
 */
class SignalsRepository(context: Context) {

    private val storeFile = File(context.filesDir, "signals.json")

    private val _signals = MutableStateFlow(loadFromDisk())
    val signals: StateFlow<List<TradeSignal>> = _signals.asStateFlow()

    fun add(signal: TradeSignal) {
        val updated = (listOf(signal) + _signals.value).take(MAX_STORED_SIGNALS)
        _signals.value = updated
        saveToDisk(updated)
    }

    private fun loadFromDisk(): List<TradeSignal> {
        if (!storeFile.exists()) return emptyList()
        return runCatching {
            val array = JSONArray(storeFile.readText())
            (0 until array.length()).map { i ->
                val obj = array.getJSONObject(i)
                TradeSignal(
                    timestampMillis = obj.getLong("timestampMillis"),
                    symbol = obj.getString("symbol"),
                    action = SignalAction.valueOf(obj.getString("action")),
                    price = obj.getDouble("price"),
                    source = obj.getString("source"),
                    note = obj.optString("note", ""),
                )
            }
        }.getOrElse { emptyList() }
    }

    private fun saveToDisk(signals: List<TradeSignal>) {
        val array = JSONArray()
        signals.forEach { s ->
            array.put(
                JSONObject().apply {
                    put("timestampMillis", s.timestampMillis)
                    put("symbol", s.symbol)
                    put("action", s.action.name)
                    put("price", s.price)
                    put("source", s.source)
                    put("note", s.note)
                }
            )
        }
        runCatching { storeFile.writeText(array.toString()) }
    }
}
