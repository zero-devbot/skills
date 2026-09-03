"""Indicators reimplemented to match MetaTrader 5's built-ins.

Parity matters more than elegance here. If ``iATR`` in the terminal and
``atr`` in this module disagree, every downstream comparison between the
backtest and the live EA is meaningless, so the seeding conventions below
deliberately mirror MT5's rather than pandas' defaults.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Wilder's true range. The first element is NaN: no previous close."""
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    # pandas' max(axis=1) skips NaN, so without this the first bar would
    # quietly fall back to high-low and pull the ATR seed a bar early.
    tr[prev_close.isna()] = np.nan
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder-smoothed ATR, seeded with the SMA of the first ``period`` TRs.

    This is what MT5's ``iATR`` does. ``ewm(alpha=1/period)`` alone is not:
    it seeds from the first observation and stays biased for a long time.
    """
    tr = true_range(high, low, close)
    out = pd.Series(np.nan, index=tr.index, dtype="float64")

    valid = tr.dropna()
    if len(valid) < period:
        return out

    seed_idx = valid.index[period - 1]
    values = tr.to_numpy(dtype="float64")
    result = np.full(len(values), np.nan)

    start = tr.index.get_loc(seed_idx)
    result[start] = np.nanmean(values[start - period + 1 : start + 1])
    for i in range(start + 1, len(values)):
        if np.isnan(values[i]):
            result[i] = result[i - 1]
        else:
            result[i] = (result[i - 1] * (period - 1) + values[i]) / period

    out.iloc[:] = result
    return out


def ema(series: pd.Series, period: int) -> pd.Series:
    """EMA seeded with an SMA of the first ``period`` values, as MT5 does."""
    values = series.to_numpy(dtype="float64")
    out = np.full(len(values), np.nan)
    if len(values) < period:
        return pd.Series(out, index=series.index)

    k = 2.0 / (period + 1.0)
    out[period - 1] = values[:period].mean()
    for i in range(period, len(values)):
        out[i] = k * values[i] + (1.0 - k) * out[i - 1]
    return pd.Series(out, index=series.index)


def rolling_percentile_rank(series: pd.Series, window: int) -> pd.Series:
    """Percentile rank of each value within its own trailing window, 0-100.

    Matches ``C4PercentileRank``: ``count(x <= v) / n * 100``, with the
    current observation inside the window. So the floor is ``100/n``, never 0.
    """
    return series.rolling(window).rank(method="max", pct=True) * 100.0
