package com.tradingsignals.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import com.tradingsignals.app.ui.AppViewModel
import com.tradingsignals.app.ui.TradingSignalsNavHost
import com.tradingsignals.app.ui.theme.TradingSignalsTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            TradingSignalsTheme {
                val viewModel: AppViewModel = viewModel(
                    factory = ViewModelProvider.AndroidViewModelFactory.getInstance(application),
                )
                TradingSignalsNavHost(viewModel)
            }
        }
    }
}
