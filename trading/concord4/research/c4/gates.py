"""The four CONCORD-4 gates, mirroring Concord4Core.mqh.

THE NON-REPAINTING CONTRACT
Every higher-timeframe value attached to an M15 bar comes from a bar that
had FULLY CLOSED by that M15 bar's own close. ``asof_align`` is the single
place this is enforced - it is the Python twin of ``C4ClosedShift`` in the
MQL5 core. Route any new data source through it, or the backtest starts
quietly reading the future and every number after that is fiction.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

from .indicators import atr, ema, rolling_percentile_rank

LONG, SHORT, NEUTRAL = 1, -1, 0


@dataclass
class Config:
    """Mirrors ``C4Config``. Field names match the MQL5 inputs."""

    # L0 tradability
    session_a_start_min: int = 7 * 60
    session_a_end_min: int = 11 * 60
    session_b_start_min: int = 13 * 60
    session_b_end_min: int = 16 * 60
    max_spread_atr: float = 0.06
    use_news_filter: bool = True
    news_pad_minutes: int = 15
    vol_pct_low: float = 20.0
    vol_pct_high: float = 90.0
    vol_pct_lookback: int = 250

    # L1 regime
    ema_d1_period: int = 50
    tsmom_days: int = 63

    # L2 intermarket
    usd_ema_period: int = 20
    usd_slope_bars: int = 3

    # L3 trigger
    or_start_min: int = 7 * 60
    or_length_min: int = 30
    breakout_atr_k: float = 0.15
    min_bar_range_atr: float = 0.80
    min_vol_mult: float = 1.50
    max_or_width_adr: float = 1.20
    max_chase_atr: float = 2.00

    # risk geometry
    stop_struct_buf_atr: float = 0.10
    stop_min_atr: float = 1.50
    stop_max_atr: float = 2.00

    # periods
    atr_period: int = 14
    adr_days: int = 20

    def replace(self, **kwargs) -> "Config":
        merged = asdict(self)
        unknown = set(kwargs) - set(merged)
        if unknown:
            raise KeyError(f"unknown config field(s): {sorted(unknown)}")
        merged.update(kwargs)
        return Config(**merged)


def asof_align(
    decision_times: pd.DatetimeIndex,
    htf: pd.DataFrame,
    bar_duration: pd.Timedelta,
    columns: list[str],
    prefix: str,
) -> pd.DataFrame:
    """Attach higher-timeframe columns using only bars closed by each instant.

    ``htf`` is indexed by bar OPEN time, so a bar is usable once
    ``open + duration <= decision_time``. A backward as-of join on that close
    time is exactly ``iBarShift(asOf) + 1`` in the MQL5 core.
    """
    right = htf[columns].copy()
    right["_close_time"] = right.index + bar_duration
    right = right.sort_values("_close_time").reset_index(drop=True)

    left = pd.DataFrame({"_t": decision_times}).sort_values("_t").reset_index(drop=True)

    merged = pd.merge_asof(
        left, right, left_on="_t", right_on="_close_time", direction="backward"
    )
    merged.index = pd.DatetimeIndex(merged["_t"])
    merged = merged.drop(columns=["_t", "_close_time"])
    return merged.rename(columns={c: f"{prefix}{c}" for c in columns})


def _minute_of_day(index: pd.DatetimeIndex) -> np.ndarray:
    return index.hour.to_numpy() * 60 + index.minute.to_numpy()


def opening_range(m15: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Per-UTC-day opening range high/low from the M15 bars inside it."""
    minutes = _minute_of_day(m15.index)
    inside = (minutes >= cfg.or_start_min) & (minutes < cfg.or_start_min + cfg.or_length_min)

    window = m15.loc[inside]
    if window.empty:
        return pd.DataFrame(columns=["or_high", "or_low"])

    day = window.index.normalize()
    grouped = window.groupby(day)
    return pd.DataFrame({"or_high": grouped["high"].max(), "or_low": grouped["low"].min()})


def news_blackout_mask(
    decision_times: pd.DatetimeIndex, events: pd.DatetimeIndex | None, pad_minutes: int
) -> np.ndarray:
    """True where a decision instant falls within +/- pad of a listed event."""
    if events is None or len(events) == 0:
        return np.zeros(len(decision_times), dtype=bool)

    pad = pd.Timedelta(minutes=pad_minutes)
    ordered = pd.DatetimeIndex(sorted(events))
    positions = ordered.searchsorted(decision_times)

    mask = np.zeros(len(decision_times), dtype=bool)
    for offset in (-1, 0):
        neighbour = positions + offset
        valid = (neighbour >= 0) & (neighbour < len(ordered))
        if not valid.any():
            continue
        delta = np.abs(
            decision_times[valid].to_numpy()
            - ordered[neighbour[valid]].to_numpy()
        )
        mask[valid] |= delta <= pad.to_timedelta64()
    return mask


def build_features(
    m15: pd.DataFrame,
    h1: pd.DataFrame,
    d1: pd.DataFrame,
    usd_h1: pd.Series,
    cfg: Config,
    news_events: pd.DatetimeIndex | None = None,
    default_spread: float = 0.25,
) -> pd.DataFrame:
    """Compute every gate for every M15 bar. Index is the M15 bar OPEN time."""
    out = m15.copy()
    decision_times = out.index + pd.Timedelta(minutes=15)

    # ---- own-timeframe context -----------------------------------------
    out["atr_m15"] = atr(out.high, out.low, out.close, cfg.atr_period)

    # ---- H1 and D1, as-of aligned --------------------------------------
    h1_feat = pd.DataFrame(index=h1.index)
    h1_feat["atr_h1"] = atr(h1.high, h1.low, h1.close, cfg.atr_period)

    d1_feat = pd.DataFrame(index=d1.index)
    d1_feat["atr_d1"] = atr(d1.high, d1.low, d1.close, cfg.atr_period)
    d1_feat["vol_pct"] = rolling_percentile_rank(d1_feat["atr_d1"], cfg.vol_pct_lookback)
    d1_feat["adr"] = (d1.high - d1.low).rolling(cfg.adr_days).mean()
    d1_feat["ema_d1"] = ema(d1.close, cfg.ema_d1_period)
    d1_feat["close_d1"] = d1.close
    d1_feat["tsmom_ref"] = d1.close.shift(cfg.tsmom_days)

    out = out.join(asof_align(decision_times, h1_feat, pd.Timedelta(hours=1), ["atr_h1"], ""))
    out = out.join(
        asof_align(
            decision_times,
            d1_feat,
            pd.Timedelta(days=1),
            ["atr_d1", "vol_pct", "adr", "ema_d1", "close_d1", "tsmom_ref"],
            "",
        )
    )

    # ---- L1 regime: trend AND momentum must agree ----------------------
    trend_up = out["close_d1"] > out["ema_d1"]
    mom_up = out["close_d1"] > out["tsmom_ref"]
    known = out[["close_d1", "ema_d1", "tsmom_ref"]].notna().all(axis=1)

    out["l1"] = np.where(
        known & trend_up & mom_up, LONG,
        np.where(known & ~trend_up & ~mom_up, SHORT, NEUTRAL),
    )

    # ---- L0 clock ------------------------------------------------------
    minutes = _minute_of_day(out.index)
    in_session = (
        (minutes >= cfg.session_a_start_min) & (minutes < cfg.session_a_end_min)
    ) | ((minutes >= cfg.session_b_start_min) & (minutes < cfg.session_b_end_min))
    out["in_session"] = in_session

    # ---- L2 intermarket: USD basket slope ------------------------------
    if usd_h1 is None or usd_h1.empty:
        out["l2"] = NEUTRAL
        out["usd_slope"] = np.nan
    else:
        usd_feat = pd.DataFrame(index=usd_h1.index)
        usd_ema = ema(usd_h1, cfg.usd_ema_period)
        usd_feat["usd_ema"] = usd_ema
        usd_feat["usd_ema_prev"] = usd_ema.shift(cfg.usd_slope_bars)

        out = out.join(
            asof_align(
                decision_times, usd_feat, pd.Timedelta(hours=1),
                ["usd_ema", "usd_ema_prev"], "",
            )
        )
        slope = out["usd_ema"] - out["usd_ema_prev"]
        out["usd_slope"] = slope
        out["l2"] = np.where(slope < 0, LONG, np.where(slope > 0, SHORT, NEUTRAL))
        out.loc[slope.isna(), "l2"] = NEUTRAL

    # L2 is not evaluated outside the session, exactly as the EA skips it
    out.loc[~out["in_session"], "l2"] = NEUTRAL

    # ---- L0 remaining checks -------------------------------------------
    if "spread" not in out.columns:
        out["spread"] = default_spread
    out["spread"] = out["spread"].fillna(default_spread)

    vol_ok = (out["vol_pct"] >= cfg.vol_pct_low) & (out["vol_pct"] <= cfg.vol_pct_high)
    spread_ok = out["spread"] <= cfg.max_spread_atr * out["atr_m15"]

    blackout = (
        news_blackout_mask(decision_times, news_events, cfg.news_pad_minutes)
        if cfg.use_news_filter
        else np.zeros(len(out), dtype=bool)
    )
    out["news_blackout"] = blackout
    out["vol_ok"] = vol_ok.fillna(False)
    out["spread_ok"] = spread_ok.fillna(False)
    out["l0"] = out["in_session"] & out["vol_ok"] & out["spread_ok"] & ~blackout

    # ---- L3 trigger -----------------------------------------------------
    ranges = opening_range(m15, cfg)
    day = out.index.normalize()
    out["or_high"] = ranges["or_high"].reindex(day).to_numpy()
    out["or_low"] = ranges["or_low"].reindex(day).to_numpy()

    # a bar that opens before the range closes is part of it and cannot trade it
    or_end = cfg.or_start_min + cfg.or_length_min
    out.loc[minutes < or_end, ["or_high", "or_low"]] = np.nan
    out["or_width"] = out["or_high"] - out["or_low"]

    buffer = cfg.breakout_atr_k * out["atr_m15"]
    broke_up = out["close"] > out["or_high"] + buffer
    broke_dn = out["close"] < out["or_low"] - buffer
    direction = np.where(broke_up, LONG, np.where(broke_dn, SHORT, NEUTRAL))

    bar_range = out["high"] - out["low"]
    expansion = bar_range >= cfg.min_bar_range_atr * out["atr_m15"]
    vol_avg = out["tick_volume"].shift(1).rolling(20).mean()
    vol_ok_bar = out["tick_volume"] >= cfg.min_vol_mult * vol_avg

    edge = np.where(direction == LONG, out["or_high"], out["or_low"])
    chase_ok = np.abs(out["close"] - edge) <= cfg.max_chase_atr * out["atr_m15"]
    width_ok = out["or_width"] <= cfg.max_or_width_adr * out["adr"]

    valid = (
        (direction != NEUTRAL)
        & expansion.fillna(False).to_numpy()
        & vol_ok_bar.fillna(False).to_numpy()
        & pd.Series(chase_ok, index=out.index).fillna(False).to_numpy()
        & width_ok.fillna(False).to_numpy()
    )
    out["l3"] = np.where(valid, direction, NEUTRAL)

    # ---- risk geometry --------------------------------------------------
    struct_stop = np.where(
        out["l3"] == LONG,
        out["or_low"] - cfg.stop_struct_buf_atr * out["atr_m15"],
        out["or_high"] + cfg.stop_struct_buf_atr * out["atr_m15"],
    )
    dist = np.maximum(np.abs(out["close"] - struct_stop), cfg.stop_min_atr * out["atr_m15"])
    within_cap = dist <= cfg.stop_max_atr * out["atr_m15"]

    out["risk_dist"] = np.where((out["l3"] != NEUTRAL) & within_cap, dist, np.nan)

    # ---- composite ------------------------------------------------------
    agree = (out["l3"] != NEUTRAL) & (out["l1"] == out["l3"]) & (out["l2"] == out["l3"])
    out["signal"] = np.where(
        agree & out["l0"] & out["risk_dist"].notna(), out["l3"], NEUTRAL
    )
    return out


def veto_reasons(features: pd.DataFrame) -> pd.Series:
    """Why each breakout was rejected. Drives the dry-run rejection report."""
    reasons = pd.Series("", index=features.index, dtype="object")
    broke = features["l3"] != NEUTRAL

    reasons[broke & ~features["in_session"]] = "outside session"
    remaining = broke & features["in_session"]

    checks = [
        (features["news_blackout"], "L0 news blackout"),
        (~features["vol_ok"] & features["vol_pct"].isna(), "L0 vol regime (warmup, no history yet)"),
        (~features["vol_ok"], "L0 vol regime outside percentile band"),
        (~features["spread_ok"], "L0 spread too wide vs ATR"),
        (features["risk_dist"].isna(), "stop wider than cap"),
        (features["l1"] != features["l3"], "L1 regime disagrees"),
        (features["l2"] != features["l3"], "L2 intermarket disagrees"),
    ]
    for mask, label in checks:
        target = remaining & mask & (reasons == "")
        reasons[target] = label
    return reasons
