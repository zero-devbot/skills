package com.tradingsignals.app.service

import android.Manifest
import android.app.NotificationManager
import android.content.Context
import android.content.pm.PackageManager
import android.util.Log
import androidx.core.app.ActivityCompat
import androidx.core.app.NotificationCompat
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.tradingsignals.app.R
import com.tradingsignals.app.TradingSignalsApp
import com.tradingsignals.app.data.model.SignalAction
import com.tradingsignals.app.data.model.TradeSignal
import com.tradingsignals.app.data.python.PythonStrategyEngine

private const val TAG = "SignalWorker"

/**
 * Periodic background job: pull fresh candles from whichever broker is active, run the saved
 * Python strategy against them, and notify the user if the resulting action differs from the
 * previous signal for this symbol (so it doesn't spam a notification every single run on HOLD).
 */
class SignalWorker(appContext: Context, params: WorkerParameters) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result {
        val app = applicationContext as TradingSignalsApp
        val container = app.container
        val settings = container.settings

        val broker = container.activeBroker()
        if (!broker.isConfigured()) {
            Log.w(TAG, "Active broker (${broker.type}) is not configured; skipping this run.")
            return Result.success()
        }

        return try {
            val candles = broker.fetchCandles(settings.symbol, settings.interval, limit = 200)
            if (candles.isEmpty()) {
                Log.w(TAG, "No candles returned; skipping this run.")
                return Result.success()
            }

            val strategyResult = PythonStrategyEngine.run(settings.strategyCode, candles)
            val lastPrice = candles.last().close

            val previousAction = container.signalsRepository.signals.value.firstOrNull {
                it.symbol == settings.symbol
            }?.action

            val signal = TradeSignal(
                timestampMillis = System.currentTimeMillis(),
                symbol = settings.symbol,
                action = strategyResult.action,
                price = lastPrice,
                source = broker.type.displayName,
                note = strategyResult.note,
            )
            container.signalsRepository.add(signal)

            if (strategyResult.action != SignalAction.HOLD && strategyResult.action != previousAction) {
                notifyNewSignal(signal)
            }

            Result.success()
        } catch (e: Exception) {
            Log.e(TAG, "Signal run failed", e)
            Result.retry()
        }
    }

    private fun notifyNewSignal(signal: TradeSignal) {
        val context = applicationContext
        if (android.os.Build.VERSION.SDK_INT >= 33 &&
            ActivityCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        ) {
            return
        }

        val notification = NotificationCompat.Builder(context, TradingSignalsApp.SIGNAL_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_launcher)
            .setContentTitle("${signal.action} ${signal.symbol}")
            .setContentText("${signal.source} @ ${signal.price}  ${signal.note}")
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .build()

        val manager = context.getSystemService(NotificationManager::class.java)
        manager.notify(signal.symbol.hashCode(), notification)
    }
}
