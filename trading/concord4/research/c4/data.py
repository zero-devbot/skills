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


def _infer_point(prices: pd.Series) -> float:
    """Smallest price increment, from the decimals actually present."""
    text = prices.dropna().astype("str").head(500)
    decimals = text.str.split(".").str[-1].str.len().where(text.str.contains("."), 0)
    return 10.0 ** -int(decimals.max()) if len(decimals) else 0.01


def load_csv(
    path: str | Path,
    server_offset_hours: float = 0.0,
    spread_units: str = "auto",
    point: float | None = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """Load an OHLC file indexed by bar open time in UTC.

    Accepts the plain ``time,open,high,low,close`` form and MetaTrader's own
    History Centre export, which is tab separated with angle-bracket headers
    and splits the timestamp over ``<DATE>`` and ``<TIME>``::

        <DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>
        2024.01.02\t07:00:00\t2063.05\t2064.12\t2062.88\t2063.44\t412\t0\t21

    ``server_offset_hours`` is the one argument worth getting right. **MetaTrader
    exports in the broker's server time, not UTC**, and every session boundary
    in this system is specified in UTC. Loading a UTC+3 broker's export without
    saying so shifts the opening range by three hours and silently invalidates
    everything downstream. Pass the broker's offset; the EA prints it on init.

    Files written by ``Scripts/Concord4ExportBars.mq5`` carry a
    ``# timezone=UTC`` header and need no offset at all; passing one anyway
    raises rather than silently double-shifting the data.

    ``spread_units`` converts MetaTrader's integer point spreads into price
    units. "auto" treats an all-integer column as points.
    """
    # Concord4ExportBars.mq5 writes a "# key=value" preamble; read it before
    # pandas skips over it, because it decides whether the offset below is
    # allowed at all.
    meta: dict[str, str] = {}
    with Path(path).open("r", errors="replace") as handle:
        for line in handle:
            if not line.startswith("#"):
                break
            for token in line.lstrip("#").strip().split():
                if "=" in token:
                    key, _, value = token.partition("=")
                    meta[key] = value

    if meta.get("timezone", "").upper() == "UTC" and server_offset_hours:
        raise ValueError(
            f"{Path(path).name} was exported by Concord4ExportBars.mq5 and its "
            f"timestamps are ALREADY UTC (the script applied a "
            f"{meta.get('server_offset_hours', '?')}h offset itself), but "
            f"server_offset_hours={server_offset_hours} was passed as well.\n"
            "Applying it twice would shift the opening range exactly as badly as "
            "not applying it at all. Drop --server-offset for these files."
        )

    frame = pd.read_csv(path, sep=None, engine="python", skipinitialspace=True,
                        comment="#")

    # MetaTrader wraps its headers in angle brackets
    frame.columns = [str(c).strip().strip("<>").lower() for c in frame.columns]
    # MetaTrader exports BOTH <TICKVOL> and <VOL>, so these cannot be renamed
    # blindly: collapsing them to one name produces duplicate columns, and
    # frame["tick_volume"] then returns a DataFrame. Tick volume wins, because
    # <VOL> is real volume and reads 0 on virtually every retail FX feed.
    if "tickvol" in frame.columns:
        frame = frame.drop(columns=[c for c in ("volume", "vol") if c in frame.columns])
        frame = frame.rename(columns={"tickvol": "tick_volume"})
    else:
        for source in ("volume", "vol"):
            if source in frame.columns:
                frame = frame.rename(columns={source: "tick_volume"})
                break

    if "date" in frame.columns and "time" in frame.columns:
        stamps = frame["date"].astype(str).str.strip() + " " + frame["time"].astype(str).str.strip()
        frame = frame.drop(columns=["date", "time"])
        frame["time"] = stamps
    else:
        time_col = next(
            (c for c in ("time", "datetime", "date", "timestamp") if c in frame.columns), None
        )
        if time_col is None:
            raise ValueError(f"{path}: no recognisable time column in {list(frame.columns)}")
        frame = frame.rename(columns={time_col: "time"})

    # MetaTrader writes 2024.01.02; pandas needs the dots normalised
    stamps = frame["time"].astype(str).str.strip().str.replace(".", "-", regex=False)
    frame["time"] = pd.to_datetime(stamps, utc=True, format="mixed")

    if server_offset_hours:
        frame["time"] = frame["time"] - pd.Timedelta(hours=float(server_offset_hours))

    frame = frame.set_index("time").sort_index()

    missing = {"open", "high", "low", "close"} - set(frame.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")

    for column in ("open", "high", "low", "close", "tick_volume", "spread"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    if "tick_volume" not in frame.columns:
        frame["tick_volume"] = 1.0
    # MetaTrader's <VOL> is real volume and is 0 on most FX feeds; <TICKVOL> is
    # the usable one, and the rename above already preferred it when both exist
    frame["tick_volume"] = frame["tick_volume"].fillna(0.0)

    if "spread" in frame.columns:
        values = frame["spread"].dropna()
        is_points = (
            spread_units == "points"
            or (spread_units == "auto" and len(values) > 0
                and bool(np.all(np.isclose(values, values.round()))) and values.max() > 1.0)
        )
        if is_points:
            tick = point if point is not None else _infer_point(frame["close"])
            frame["spread"] = frame["spread"] * tick
            if verbose:
                print(f"  {Path(path).name}: spread read as points, converted at {tick:g}/point")

    keep = OHLC_COLUMNS + (["spread"] if "spread" in frame.columns else [])
    frame = frame[keep].dropna(subset=["open", "high", "low", "close"])
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


def resample_server_days(frame: pd.DataFrame, gmt_offset_hours: float) -> pd.DataFrame:
    """Resample to D1 bars that start at the BROKER's midnight, not UTC's.

    MT5's daily bars begin at the server's midnight. On a UTC+3 server that
    is 21:00 UTC the previous day, so plain ``resample("1D")`` produces
    different bars from the ones the terminal used - different ATR(D1),
    different percentile, different regime bias. The parity harness needs
    the terminal's boundaries to compare like with like.
    """
    offset = pd.Timedelta(hours=-float(gmt_offset_hours))
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "tick_volume": "sum"}
    if "spread" in frame.columns:
        agg["spread"] = "mean"

    # "24h", not "1D": pandas silently ignores `offset` for calendar-day
    # frequencies, so "1D" would hand back UTC days while claiming to be
    # server days - a no-op that the parity harness would then blame on logic.
    out = frame.resample("24h", label="left", closed="left", offset=offset).agg(agg)
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
