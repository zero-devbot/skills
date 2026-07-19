"""Python port of "HalfTrend Long/Short Signal Engine [BigBeluga]" (Pine v6).

Faithful bar-by-bar translation of the Pine state machine:

  - atr2      = ta.atr(100) / 2          (Wilder RMA of true range, SMA seed)
  - highPrice = highest(high, amplitude) (rolling max, current bar inclusive)
  - lowPrice  = lowest(low,  amplitude)
  - highma    = sma(high, amplitude), lowma = sma(low, amplitude)
  - trend 0 = bullish, 1 = bearish; buy on 1->0 flip, sell on 0->1 flip,
    evaluated on confirmed bar closes (no intrabar repainting).

Deviations from Pine, both confined to the warmup region:
  - Pine's `highest/lowest` return na until `amplitude` bars exist; here the
    rolling extremes use min_periods=1 so the state vars never go NaN. The
    SMAs keep min_periods=amplitude (na -> comparison False, same as Pine).
  - Signals are only emitted once ATR has a value (bar >= atr_period), which
    is stricter than Pine but avoids trading on a half-seeded state machine.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


def wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """ta.atr equivalent: RMA (Wilder) smoothing of true range, seeded with an SMA."""
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    tr.iloc[0] = high.iloc[0] - low.iloc[0]

    atr = np.full(len(tr), np.nan)
    if len(tr) >= period:
        atr[period - 1] = tr.iloc[:period].mean()
        for i in range(period, len(tr)):
            atr[i] = (atr[i - 1] * (period - 1) + tr.iloc[i]) / period
    return pd.Series(atr, index=high.index)


@dataclass
class HalfTrendResult:
    trend: pd.Series      # 0 bullish / 1 bearish
    ht_line: pd.Series    # the HalfTrend baseline (up when bull, down when bear)
    atr2: pd.Series       # ATR(atr_period) / 2, the unit for SL/TP distances
    atr_high: pd.Series   # channel bands (baseline +/- channelDeviation * atr2)
    atr_low: pd.Series
    buy_signal: pd.Series
    sell_signal: pd.Series


def halftrend(
    df: pd.DataFrame,
    amplitude: int = 20,
    channel_deviation: float = 2.0,
    atr_period: int = 100,
) -> HalfTrendResult:
    """Run the HalfTrend engine over a DataFrame with High/Low/Close columns."""
    high, low, close = df["High"], df["Low"], df["Close"]
    n = len(df)

    atr2 = wilder_atr(high, low, close, atr_period) / 2.0
    dev = channel_deviation * atr2

    high_price = high.rolling(amplitude, min_periods=1).max().to_numpy()
    low_price = low.rolling(amplitude, min_periods=1).min().to_numpy()
    highma = high.rolling(amplitude, min_periods=amplitude).mean().to_numpy()
    lowma = low.rolling(amplitude, min_periods=amplitude).mean().to_numpy()

    h, l, c = high.to_numpy(), low.to_numpy(), close.to_numpy()

    trend = np.zeros(n, dtype=int)
    ht_line = np.full(n, np.nan)
    up_arr = np.full(n, np.nan)
    down_arr = np.full(n, np.nan)

    # Pine `var` initial state (evaluated on the first bar)
    cur_trend = 0
    next_trend = 0
    max_low_price = l[0]
    min_high_price = h[0]
    up_prev = np.nan   # up[1] / down[1] are na on the first bar
    down_prev = np.nan
    trend_prev = None  # trend[1] is na on the first bar

    for i in range(n):
        prev_low = l[i - 1] if i > 0 else l[i]    # nz(low[1], low)
        prev_high = h[i - 1] if i > 0 else h[i]   # nz(high[1], high)

        if next_trend == 1:
            max_low_price = max(low_price[i], max_low_price)
            if highma[i] < max_low_price and c[i] < prev_low:  # NaN highma -> False
                cur_trend = 1
                next_trend = 0
                min_high_price = high_price[i]
        else:
            min_high_price = min(high_price[i], min_high_price)
            if lowma[i] > min_high_price and c[i] > prev_high:
                cur_trend = 0
                next_trend = 1
                max_low_price = low_price[i]

        if cur_trend == 0:
            if trend_prev is not None and trend_prev != 0:
                up = down_prev if not np.isnan(down_prev) else np.nan
            else:
                up = max_low_price if np.isnan(up_prev) else max(max_low_price, up_prev)
            up_prev, down_prev = up, down_prev
            ht_line[i] = up
        else:
            if trend_prev is not None and trend_prev != 1:
                down = up_prev if not np.isnan(up_prev) else np.nan
            else:
                down = min_high_price if np.isnan(down_prev) else min(min_high_price, down_prev)
            up_prev, down_prev = up_prev, down
            ht_line[i] = down

        trend[i] = cur_trend
        up_arr[i], down_arr[i] = up_prev, down_prev
        trend_prev = cur_trend

    trend_s = pd.Series(trend, index=df.index)
    ht_s = pd.Series(ht_line, index=df.index)
    prev = trend_s.shift(1)
    warm = ~atr2.isna()  # only trade once ATR exists

    return HalfTrendResult(
        trend=trend_s,
        ht_line=ht_s,
        atr2=atr2,
        atr_high=ht_s + dev,
        atr_low=ht_s - dev,
        buy_signal=(trend_s == 0) & (prev == 1) & warm,
        sell_signal=(trend_s == 1) & (prev == 0) & warm,
    )
