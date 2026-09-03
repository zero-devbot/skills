"""Data loading, resampling and a Dukascopy tick fetcher.

The harness never invents prices. Every function here either reads real
data from disk, downloads it, or - in ``synthetic_ohlc`` - produces
explicitly labelled fake data for smoke-testing the engine. Synthetic data
is for proving the plumbing works, never for judging the strategy.
"""

from __future__ import annotations

import lzma
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

OHLC_COLUMNS = ["open", "high", "low", "close", "tick_volume"]

# Legs of the synthetic USD basket, with DXY-shaped weights. ``sign`` is +1
# when the pair is quoted USDxxx and -1 for xxxUSD, so every leg contributes
# in the same direction: up means a stronger dollar.
USD_BASKET = [
    ("EURUSD", 0.576, -1),
    ("USDJPY", 0.136, +1),
    ("GBPUSD", 0.119, -1),
    ("USDCAD", 0.091, +1),
    ("USDCHF", 0.036, +1),
    ("AUDUSD", 0.042, -1),
]


@dataclass(frozen=True)
class Instrument:
    """Contract specification. Defaults are a typical XAUUSD CFD."""

    symbol: str = "XAUUSD"
    contract_size: float = 100.0        # ounces per lot
    lot_step: float = 0.01
    lot_min: float = 0.01
    lot_max: float = 50.0
    digits: int = 2
    commission_per_lot_rt: float = 7.0  # account currency, round turn
    default_spread: float = 0.25        # price units, used only if data has none


def load_csv(path: str | Path, tz: str = "UTC") -> pd.DataFrame:
    """Load an OHLC CSV indexed by bar open time.

    Expected columns: ``time,open,high,low,close`` plus optional
    ``tick_volume`` / ``volume`` and ``spread``. Times must be UTC.
    """
    frame = pd.read_csv(path)
    lower = {c.lower(): c for c in frame.columns}

    time_col = next((lower[c] for c in ("time", "datetime", "date", "timestamp") if c in lower), None)
    if time_col is None:
        raise ValueError(f"{path}: no recognisable time column in {list(frame.columns)}")

    frame = frame.rename(columns={time_col: "time"})
    frame["time"] = pd.to_datetime(frame["time"], utc=True, format="mixed")
    frame = frame.set_index("time").sort_index()

    for src, dst in (("volume", "tick_volume"), ("vol", "tick_volume")):
        if src in lower and "tick_volume" not in frame.columns:
            frame = frame.rename(columns={lower[src]: dst})

    frame.columns = [c.lower() for c in frame.columns]
    missing = {"open", "high", "low", "close"} - set(frame.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")

    if "tick_volume" not in frame.columns:
        frame["tick_volume"] = 1.0

    keep = OHLC_COLUMNS + (["spread"] if "spread" in frame.columns else [])
    frame = frame[keep]
    return frame[~frame.index.duplicated(keep="last")]


def resample(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample OHLC upward. Bars are labelled by their OPEN time."""
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "tick_volume": "sum",
    }
    if "spread" in frame.columns:
        agg["spread"] = "mean"

    out = frame.resample(rule, label="left", closed="left").agg(agg)
    return out.dropna(subset=["open", "high", "low", "close"])


def usd_index_h1(majors: dict[str, pd.DataFrame]) -> pd.Series:
    """Log-weighted synthetic USD index on H1, mirroring ``C4BuildUsdSeries``.

    Weights are renormalised over whatever legs are present, so a missing
    USDCHF degrades the index instead of disabling the gate. Fewer than
    three legs returns an empty series and the gate fails closed.
    """
    legs = [(s, w, sign) for s, w, sign in USD_BASKET if s in majors and not majors[s].empty]
    if len(legs) < 3:
        return pd.Series(dtype="float64")

    total = sum(w for _, w, _ in legs)
    index = None
    for symbol, weight, sign in legs:
        closes = majors[symbol]["close"]
        contribution = (weight / total) * sign * np.log(closes)
        index = contribution if index is None else index.add(contribution, fill_value=np.nan)

    return index.dropna()


# --------------------------------------------------------------------------
# Dukascopy
# --------------------------------------------------------------------------

_DUKA_URL = "https://datafeed.dukascopy.com/datafeed/{sym}/{y:04d}/{m:02d}/{d:02d}/{h:02d}h_ticks.bi5"
_TICK_STRUCT = struct.Struct(">IIIff")


def _decode_bi5(payload: bytes, hour_start: datetime, point_value: float) -> pd.DataFrame:
    """Decode one LZMA-compressed Dukascopy hour file into a tick frame."""
    if not payload:
        return pd.DataFrame(columns=["ask", "bid"])

    raw = lzma.LZMADecompressor().decompress(payload)
    rows = []
    for offset in range(0, len(raw) - _TICK_STRUCT.size + 1, _TICK_STRUCT.size):
        ms, ask, bid, _, _ = _TICK_STRUCT.unpack_from(raw, offset)
        rows.append((hour_start + timedelta(milliseconds=ms), ask * point_value, bid * point_value))

    if not rows:
        return pd.DataFrame(columns=["ask", "bid"])

    frame = pd.DataFrame(rows, columns=["time", "ask", "bid"]).set_index("time")
    return frame


def fetch_dukascopy(
    symbol: str,
    start: datetime,
    end: datetime,
    point_value: float = 0.001,
    session=None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Download Dukascopy ticks for ``[start, end)`` and return bid/ask ticks.

    Hours with no file (weekends, holidays) are skipped silently. Network
    failures are reported and skipped rather than aborting a long download,
    so a partial dataset is still usable - check the returned coverage
    before trusting a backtest built on it.
    """
    import requests

    session = session or requests.Session()
    frames: list[pd.DataFrame] = []
    cursor = start.replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    end = end.replace(tzinfo=timezone.utc)
    failures = 0

    while cursor < end:
        url = _DUKA_URL.format(
            sym=symbol, y=cursor.year, m=cursor.month - 1, d=cursor.day, h=cursor.hour
        )
        try:
            response = session.get(url, timeout=30)
            if response.status_code == 200 and response.content:
                frames.append(_decode_bi5(response.content, cursor, point_value))
            elif response.status_code not in (404, 410):
                failures += 1
        except Exception as exc:  # network, TLS, proxy - keep going
            failures += 1
            if verbose and failures <= 5:
                print(f"  fetch failed {cursor:%Y-%m-%d %H}h: {exc}")

        cursor += timedelta(hours=1)

    if failures and verbose:
        print(f"  {failures} hour(s) failed to download - dataset is incomplete")

    if not frames:
        return pd.DataFrame(columns=["ask", "bid"])
    return pd.concat(frames).sort_index()


def ticks_to_bars(ticks: pd.DataFrame, rule: str = "15min") -> pd.DataFrame:
    """Aggregate bid/ask ticks into OHLC bars with a real average spread."""
    if ticks.empty:
        return pd.DataFrame(columns=OHLC_COLUMNS + ["spread"])

    mid = (ticks["ask"] + ticks["bid"]) / 2.0
    grouped = mid.resample(rule, label="left", closed="left")

    bars = pd.DataFrame(
        {
            "open": grouped.first(),
            "high": grouped.max(),
            "low": grouped.min(),
            "close": grouped.last(),
            "tick_volume": grouped.count().astype("float64"),
            "spread": (ticks["ask"] - ticks["bid"]).resample(rule, label="left", closed="left").mean(),
        }
    )
    return bars.dropna(subset=["open", "high", "low", "close"])


# --------------------------------------------------------------------------
# Synthetic data - plumbing tests only
# --------------------------------------------------------------------------

def synthetic_ohlc(
    start: str,
    periods: int,
    freq: str = "15min",
    start_price: float = 2000.0,
    annual_vol: float = 0.16,
    drift: float = 0.05,
    seed: int = 0,
    session_vol_profile: bool = True,
) -> pd.DataFrame:
    """Generate FAKE bars for smoke-testing the engine.

    Returns a GBM path with an optional intraday volatility profile that
    peaks around the London and New York opens, so session-gated logic has
    something structurally plausible to chew on.

    This produces no edge and is not evidence of one. Any performance number
    computed from it describes the random number generator, nothing else.
    """
    rng = np.random.default_rng(seed)
    index = pd.date_range(start=start, periods=periods, freq=freq, tz="UTC")

    bars_per_year = pd.Timedelta(days=365) / pd.Timedelta(freq)
    sigma = annual_vol / np.sqrt(bars_per_year)
    mu = drift / bars_per_year

    scale = np.ones(periods)
    if session_vol_profile:
        hours = index.hour + index.minute / 60.0
        scale = 0.45 + 1.25 * np.exp(-((hours - 8.0) ** 2) / 6.0) + 1.4 * np.exp(
            -((hours - 14.0) ** 2) / 6.0
        )
        weekend = index.dayofweek >= 5
        scale = np.where(weekend, 0.0, scale)

    returns = mu + sigma * scale * rng.standard_normal(periods)
    close = start_price * np.exp(np.cumsum(returns))
    open_ = np.concatenate([[start_price], close[:-1]])

    wick = np.abs(sigma * scale * rng.standard_normal(periods)) * close
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    volume = 400.0 * scale * (1.0 + 0.3 * rng.standard_normal(periods))

    frame = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "tick_volume": np.clip(volume, 1.0, None),
        },
        index=index,
    )
    return frame[scale > 0]
