package com.tradingsignals.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val Green = Color(0xFF26C281)
private val Red = Color(0xFFE5484D)
private val DarkBackground = Color(0xFF101418)

private val DarkColors = darkColorScheme(
    primary = Green,
    secondary = Red,
    background = DarkBackground,
    surface = Color(0xFF181D24),
)

private val LightColors = lightColorScheme(
    primary = Green,
    secondary = Red,
)

@Composable
fun TradingSignalsTheme(content: @Composable () -> Unit) {
    val colors = if (isSystemInDarkTheme()) DarkColors else LightColors
    MaterialTheme(colorScheme = colors, content = content)
}

val BuyColor = Green
val SellColor = Red
