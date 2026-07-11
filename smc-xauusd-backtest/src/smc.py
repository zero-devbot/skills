"""Smart Money Concepts primitives, implemented causally.

Everything here is computed so that a value attached to bar *i* uses only
information available at (or before) the close of bar *i*:

- A swing high/low with strength ``k`` is a strict local extreme with ``k``
  bars on each side; it is only *confirmed* k bars after it prints, so the
  ``Last*`` columns update with that delay.
- Higher-timeframe bias comes from H4 market structure (break of structure /
  change of character) and is only applied to H1 bars that open at or after
  the H4 candle close that produced the signal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def confirmed_swings(df: pd.DataFrame, k: int) -> pd.DataFrame:
    """Track the most recently *confirmed* swing high/low at each bar.

    Returns a DataFrame aligned to ``df`` with columns:
    LastSH, LastSHId, LastSL, LastSLId  (Id = integer bar position of the
    swing candle, NaN until the first swing confirms).
    """
    high = df.High.values
    low = df.Low.values
    n = len(df)

    last_sh = np.full(n, np.nan)
    last_sh_id = np.full(n, np.nan)
    last_sl = np.full(n, np.nan)
    last_sl_id = np.full(n, np.nan)

    cur_sh = cur_sh_id = cur_sl = cur_sl_id = np.nan
    for i in range(n):
        s = i - k  # candidate swing centre confirmed at bar i
        if s - k >= 0:
            win_h = high[s - k: s + k + 1]
            if high[s] == win_h.max() and (win_h == high[s]).sum() == 1:
                cur_sh, cur_sh_id = high[s], s
            win_l = low[s - k: s + k + 1]
            if low[s] == win_l.min() and (win_l == low[s]).sum() == 1:
                cur_sl, cur_sl_id = low[s], s
        last_sh[i], last_sh_id[i] = cur_sh, cur_sh_id
        last_sl[i], last_sl_id[i] = cur_sl, cur_sl_id

    return pd.DataFrame(
        {"LastSH": last_sh, "LastSHId": last_sh_id,
         "LastSL": last_sl, "LastSLId": last_sl_id},
        index=df.index,
    )


def structure_bias(df: pd.DataFrame, k: int) -> pd.DataFrame:
    """Market-structure bias from BOS/CHoCH on the given timeframe.

    Bias flips to +1 when a close breaks the last confirmed swing high
    (bullish break of structure) and to -1 on a close through the last
    confirmed swing low.  Each swing can only be broken once.

    Returns DataFrame with columns ``avail`` (timestamp from which the bias
    may be used on a lower timeframe, i.e. this candle's close time) and
    ``bias`` (+1 / -1 / 0 before the first break).
    """
    sw = confirmed_swings(df, k)
    close = df.Close.values
    n = len(df)
    tf = df.index.to_series().diff().median() if n > 1 else pd.Timedelta(0)

    bias = np.zeros(n)
    cur = 0
    broken_high: set[float] = set()
    broken_low: set[float] = set()
    for i in range(n):
        sh, shid = sw.LastSH.iloc[i], sw.LastSHId.iloc[i]
        sl, slid = sw.LastSL.iloc[i], sw.LastSLId.iloc[i]
        if not np.isnan(sh) and shid not in broken_high and close[i] > sh:
            cur = 1
            broken_high.add(shid)
        if not np.isnan(sl) and slid not in broken_low and close[i] < sl:
            cur = -1
            broken_low.add(slid)
        bias[i] = cur

    return pd.DataFrame({"avail": df.index + tf, "bias": bias})


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df.Close.shift(1)
    tr = pd.concat(
        [df.High - df.Low,
         (df.High - prev_close).abs(),
         (df.Low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def _map_bias(target_index: pd.DatetimeIndex, hb: pd.DataFrame) -> np.ndarray:
    """Forward-fill a bias series onto a lower-timeframe index.

    A bias value from a HTF candle applies to LTF bars opening at/after that
    candle's close time.
    """
    merged = pd.merge_asof(
        pd.DataFrame(index=target_index).reset_index(names="t"),
        hb.rename(columns={"avail": "t"}).sort_values("t"),
        on="t", direction="backward",
    )
    return merged["bias"].fillna(0).values


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return (df.resample(rule)
              .agg({"Open": "first", "High": "max", "Low": "min",
                    "Close": "last", "Volume": "sum"})
              .dropna(subset=["Open"]))


def prepare(h1: pd.DataFrame, k_ltf: int = 3, k_htf: int = 2,
            atr_period: int = 14) -> pd.DataFrame:
    """Attach all pre-computed SMC columns to the H1 frame.

    Adds: LastSH, LastSHId, LastSL, LastSLId, BiasH4, BiasD1, Atr.
    Rows before the indicators warm up are dropped.
    """
    out = h1.copy()
    out = out.join(confirmed_swings(out, k_ltf))
    out["Atr"] = atr(out, atr_period)

    out["BiasH4"] = _map_bias(out.index,
                              structure_bias(resample_ohlc(h1, "4h"), k_htf))
    out["BiasD1"] = _map_bias(out.index,
                              structure_bias(resample_ohlc(h1, "1D"), k_htf))

    return out.dropna(subset=["Atr", "LastSH", "LastSL"])
