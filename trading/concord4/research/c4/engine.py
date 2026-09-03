"""Event-driven backtester for CONCORD-4.

Deliberately not ``backtesting.py``: the L2 gate needs six extra symbols,
positions close in two legs, and every higher-timeframe read has to respect
the as-of contract in ``gates.py``. A purpose-built loop keeps the backtest
and the MQL5 EA structurally comparable, which is the only reason this
harness exists.

Conventions, all chosen to err against the strategy:
  * Signals are computed on a closed M15 bar; the fill is the NEXT bar's
    open, which is where the EA's first post-close tick actually lands.
  * Prices in the data are treated as mid. Every fill pays half the spread
    plus slippage, adversely, on both entry and exit.
  * When a bar's range contains both the stop and the profit target, the
    stop is assumed to have come first.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

from .data import Instrument
from .gates import LONG, SHORT, NEUTRAL


@dataclass
class ExecConfig:
    """Execution, sizing and circuit-breaker settings. Mirrors the EA inputs."""

    initial_equity: float = 10_000.0

    risk_percent: float = 0.50
    vol_target_annual: float = 10.0
    use_vol_target: bool = True

    partial_at_r: float = 1.00
    partial_fraction: float = 0.50
    be_spread_mult: float = 2.00
    chandelier_atr: float = 2.80
    flat_minute_utc: int = 1200

    daily_loss_r: float = 2.00
    weekly_loss_r: float = 4.00
    max_entries_day: int = 2
    breaker_dd_pct: float = 8.00
    breaker_size_mult: float = 0.50

    slippage_frac_of_spread: float = 0.30
    pessimistic_intrabar: bool = True

    def replace(self, **kwargs) -> "ExecConfig":
        merged = asdict(self)
        unknown = set(kwargs) - set(merged)
        if unknown:
            raise KeyError(f"unknown exec field(s): {sorted(unknown)}")
        merged.update(kwargs)
        return ExecConfig(**merged)


@dataclass
class Position:
    direction: int
    entry_time: pd.Timestamp
    entry_price: float
    lots: float
    initial_lots: float
    stop: float
    risk_dist: float
    r_money: float
    partial_done: bool = False
    extreme: float = 0.0
    realized: float = 0.0
    legs: list = field(default_factory=list)


@dataclass
class Result:
    trades: pd.DataFrame
    equity: pd.Series
    rejections: pd.Series
    config: dict


def _normalize_lots(raw: float, inst: Instrument) -> float:
    lots = np.floor(raw / inst.lot_step) * inst.lot_step
    lots = min(lots, inst.lot_max)
    if lots < inst.lot_min - 1e-12:
        return 0.0
    return round(lots, 8)


def size_position(
    equity: float,
    risk_dist: float,
    atr_d1: float,
    inst: Instrument,
    cfg: ExecConfig,
    multiplier: float,
) -> float:
    """min(fixed-fractional risk, volatility target), then broker rounding."""
    if risk_dist <= 0 or not np.isfinite(risk_dist):
        return 0.0

    risk_lots = (equity * cfg.risk_percent / 100.0 * multiplier) / (risk_dist * inst.contract_size)
    lots = risk_lots

    if cfg.use_vol_target and np.isfinite(atr_d1) and atr_d1 > 0:
        # ATR(D1) proxies daily sigma and overstates it by roughly 20-40%,
        # so realised vol lands under the nominal target - the conservative side.
        target_daily = equity * (cfg.vol_target_annual / 100.0) / np.sqrt(252.0)
        vol_lots = target_daily / (atr_d1 * inst.contract_size) * multiplier
        lots = min(risk_lots, vol_lots)

    return _normalize_lots(lots, inst)


def run_backtest(
    features: pd.DataFrame,
    inst: Instrument | None = None,
    cfg: ExecConfig | None = None,
) -> Result:
    """Run the strategy over pre-computed gate features."""
    inst = inst or Instrument()
    cfg = cfg or ExecConfig()

    frame = features.dropna(subset=["open", "high", "low", "close"]).copy()
    times = frame.index
    minutes = times.hour.to_numpy() * 60 + times.minute.to_numpy()
    days = times.normalize()

    col = {name: frame[name].to_numpy() for name in
           ("open", "high", "low", "close", "atr_h1", "atr_d1", "spread", "signal", "risk_dist")}

    equity = cfg.initial_equity
    peak_equity = equity
    position: Position | None = None

    day_start_equity = equity
    current_day = days[0] if len(days) else None
    realized_today = 0.0
    entries_today = 0
    daily_realized: dict[pd.Timestamp, float] = {}

    equity_curve = np.empty(len(frame))
    trades: list[dict] = []
    rejections: dict[str, int] = {}

    def reject(reason: str) -> None:
        rejections[reason] = rejections.get(reason, 0) + 1

    def close_leg(pos: Position, lots: float, price: float, when, reason: str) -> float:
        gross = (price - pos.entry_price) * pos.direction * lots * inst.contract_size
        commission = inst.commission_per_lot_rt * lots
        net = gross - commission
        pos.realized += net
        pos.legs.append({"time": when, "lots": lots, "price": price, "pnl": net, "reason": reason})
        return net

    def finish(pos: Position, when) -> None:
        trades.append(
            {
                "entry_time": pos.entry_time,
                "exit_time": when,
                "direction": "long" if pos.direction == LONG else "short",
                "entry_price": pos.entry_price,
                "lots": pos.initial_lots,
                "risk_dist": pos.risk_dist,
                "r_money": pos.r_money,
                "pnl": pos.realized,
                "r_multiple": pos.realized / pos.r_money if pos.r_money > 0 else np.nan,
                "exit_reason": pos.legs[-1]["reason"] if pos.legs else "unknown",
                "legs": len(pos.legs),
            }
        )

    for i in range(len(frame)):
        bar_time = times[i]
        day = days[i]

        # ---- roll the day anchors --------------------------------------
        if day != current_day:
            daily_realized[current_day] = realized_today
            current_day = day
            day_start_equity = equity
            realized_today = 0.0
            entries_today = 0

        half_spread = float(col["spread"][i]) / 2.0
        if not np.isfinite(half_spread):
            half_spread = inst.default_spread / 2.0
        slip = half_spread * 2.0 * cfg.slippage_frac_of_spread
        cost = half_spread + slip

        high, low, open_, close = (float(col[c][i]) for c in ("high", "low", "open", "close"))

        # ---- manage an open position ------------------------------------
        if position is not None:
            pos = position

            if minutes[i] >= cfg.flat_minute_utc:
                fill = open_ - cost * pos.direction
                equity += close_leg(pos, pos.lots, fill, bar_time, "time stop")
                realized_today += pos.legs[-1]["pnl"]
                finish(pos, bar_time)
                position = None
            else:
                stop_hit = (low <= pos.stop) if pos.direction == LONG else (high >= pos.stop)

                target = (
                    pos.entry_price + pos.direction * cfg.partial_at_r * pos.risk_dist
                    if not pos.partial_done else None
                )
                target_hit = (
                    target is not None
                    and ((high >= target) if pos.direction == LONG else (low <= target))
                )

                # pessimistic ordering: adverse level first
                if stop_hit and (cfg.pessimistic_intrabar or not target_hit):
                    fill = pos.stop - cost * pos.direction
                    equity += close_leg(pos, pos.lots, fill, bar_time, "stop")
                    realized_today += pos.legs[-1]["pnl"]
                    finish(pos, bar_time)
                    position = None

                elif target_hit:
                    part = _normalize_lots(pos.lots * cfg.partial_fraction, inst)
                    remainder = round(pos.lots - part, 8)
                    if part >= inst.lot_min and remainder >= inst.lot_min:
                        fill = target - cost * pos.direction
                        equity += close_leg(pos, part, fill, bar_time, "partial +1R")
                        realized_today += pos.legs[-1]["pnl"]
                        pos.lots = remainder

                    pos.partial_done = True
                    be_offset = half_spread * cfg.be_spread_mult
                    pos.stop = pos.entry_price + pos.direction * be_offset

                    # the freshly-moved stop can still be taken out this bar
                    if (low <= pos.stop) if pos.direction == LONG else (high >= pos.stop):
                        fill = pos.stop - cost * pos.direction
                        equity += close_leg(pos, pos.lots, fill, bar_time, "breakeven stop")
                        realized_today += pos.legs[-1]["pnl"]
                        finish(pos, bar_time)
                        position = None

                if position is not None:
                    pos.extreme = max(pos.extreme, high) if pos.direction == LONG else min(pos.extreme, low)

                    if pos.partial_done:
                        atr_h1 = float(col["atr_h1"][i])
                        if np.isfinite(atr_h1) and atr_h1 > 0:
                            trail = pos.extreme - pos.direction * cfg.chandelier_atr * atr_h1
                            improves = trail > pos.stop if pos.direction == LONG else trail < pos.stop
                            if improves:
                                pos.stop = trail

        # ---- entry, from the previous bar's signal -----------------------
        if position is None and i > 0:
            signal = int(col["signal"][i - 1])
            if signal != NEUTRAL:
                risk_dist = float(col["risk_dist"][i - 1])
                r_money_day = day_start_equity * cfg.risk_percent / 100.0

                week_start = day - pd.Timedelta(days=6)
                week_realized = realized_today + sum(
                    v for k, v in daily_realized.items() if k is not None and k >= week_start
                )

                blocked = None
                if entries_today >= cfg.max_entries_day:
                    blocked = "daily entry cap"
                elif realized_today <= -cfg.daily_loss_r * r_money_day:
                    blocked = "daily loss cap"
                elif week_realized <= -cfg.weekly_loss_r * r_money_day:
                    blocked = "weekly loss cap"

                if blocked:
                    reject(blocked)
                else:
                    dd_pct = 100.0 * (peak_equity - equity) / peak_equity if peak_equity > 0 else 0.0
                    multiplier = cfg.breaker_size_mult if dd_pct >= cfg.breaker_dd_pct else 1.0

                    lots = size_position(
                        equity, risk_dist, float(col["atr_d1"][i]), inst, cfg, multiplier
                    )
                    if lots <= 0:
                        reject("size below broker minimum")
                    else:
                        entry = open_ + cost * signal
                        stop = entry - signal * risk_dist
                        position = Position(
                            direction=signal,
                            entry_time=bar_time,
                            entry_price=entry,
                            lots=lots,
                            initial_lots=lots,
                            stop=stop,
                            risk_dist=risk_dist,
                            r_money=risk_dist * lots * inst.contract_size,
                            extreme=high if signal == LONG else low,
                        )
                        entries_today += 1

        # ---- mark to market ----------------------------------------------
        open_pnl = 0.0
        if position is not None:
            open_pnl = (
                (close - position.entry_price)
                * position.direction
                * position.lots
                * inst.contract_size
            )
        equity_curve[i] = equity + open_pnl
        peak_equity = max(peak_equity, equity_curve[i])

    if position is not None:                       # flatten at the end of data
        last_close = float(col["close"][-1])
        equity += close_leg(position, position.lots, last_close, times[-1], "end of data")
        finish(position, times[-1])
        equity_curve[-1] = equity

    return Result(
        trades=pd.DataFrame(trades),
        equity=pd.Series(equity_curve, index=times, name="equity"),
        rejections=pd.Series(rejections, dtype="int64").sort_values(ascending=False),
        config={"exec": asdict(cfg), "instrument": asdict(inst)},
    )
