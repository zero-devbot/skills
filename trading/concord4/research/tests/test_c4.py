"""Tests for the CONCORD-4 harness.

The one that matters most is ``test_no_lookahead``: it recomputes the gates
on a truncated dataset and asserts the values at the boundary bar are
byte-identical to the full-history run. If that ever fails, every
performance number the harness produces is fiction.

Run: ``python tests/test_c4.py``  (or ``pytest tests/test_c4.py``)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from c4 import (                                    # noqa: E402
    Config, ExecConfig, Instrument, USD_BASKET,
    build_features, resample, run_backtest, size_position, synthetic_ohlc, usd_index_h1,
)
from c4.gates import LONG, NEUTRAL, SHORT, asof_align, opening_range  # noqa: E402
from c4.indicators import atr, ema, rolling_percentile_rank           # noqa: E402
from c4.metrics import max_drawdown, summarize                        # noqa: E402


def _dataset(bars: int = 40_000, seed: int = 5):
    m15 = synthetic_ohlc("2017-01-01", bars, start_price=1300.0, seed=seed)
    majors = {}
    for i, (leg, _, _) in enumerate(USD_BASKET):
        price = 110.0 if leg == "USDJPY" else 1.15
        majors[leg] = resample(
            synthetic_ohlc("2017-01-01", bars, start_price=price, annual_vol=0.08, seed=seed + i + 1),
            "1h",
        )
    return m15, resample(m15, "1h"), resample(m15, "1D"), usd_index_h1(majors)


# ---------------------------------------------------------------- indicators

def test_atr_matches_wilder_recursion():
    frame = synthetic_ohlc("2020-01-01", 300, seed=1)
    period = 14
    computed = atr(frame.high, frame.low, frame.close, period)

    prev_close = frame.close.shift(1)
    tr = pd.concat(
        [frame.high - frame.low, (frame.high - prev_close).abs(), (frame.low - prev_close).abs()],
        axis=1,
    ).max(axis=1).to_numpy()

    expected = np.full(len(tr), np.nan)
    expected[period] = np.nanmean(tr[1 : period + 1])
    for i in range(period + 1, len(tr)):
        expected[i] = (expected[i - 1] * (period - 1) + tr[i]) / period

    got = computed.to_numpy()
    assert np.allclose(got[period + 5 :], expected[period + 5 :], rtol=1e-9), "ATR is not Wilder-smoothed"


def test_ema_seeds_with_sma():
    series = pd.Series(np.arange(1.0, 101.0))
    result = ema(series, 10)
    assert np.isnan(result.iloc[8]), "EMA should be undefined before the seed"
    assert result.iloc[9] == series.iloc[:10].mean(), "EMA must seed with an SMA, as MT5 does"
    expected = (2 / 11) * series.iloc[10] + (1 - 2 / 11) * result.iloc[9]
    assert abs(result.iloc[10] - expected) < 1e-12


def test_percentile_rank_counts_inclusive():
    series = pd.Series([5.0, 1.0, 3.0, 2.0, 4.0])
    rank = rolling_percentile_rank(series, 5)
    # last value 4.0 ranks above 1,2,3 and itself -> 4 of 5
    assert abs(rank.iloc[-1] - 80.0) < 1e-9
    assert rank.iloc[:4].isna().all(), "no rank before the window fills"


# ---------------------------------------------------------------- alignment

def test_asof_align_never_uses_an_unclosed_bar():
    h1 = pd.DataFrame(
        {"x": [1.0, 2.0, 3.0]},
        index=pd.to_datetime(["2020-01-01 06:00", "2020-01-01 07:00", "2020-01-01 08:00"], utc=True),
    )
    decisions = pd.DatetimeIndex(
        pd.to_datetime(["2020-01-01 07:30", "2020-01-01 08:00", "2020-01-01 08:15"], utc=True)
    )
    out = asof_align(decisions, h1, pd.Timedelta(hours=1), ["x"], "")

    # 07:30 -> the 07:00 bar has NOT closed, so the 06:00 bar is the newest usable
    assert out["x"].iloc[0] == 1.0
    # 08:00 -> the 07:00 bar closed exactly now and becomes usable
    assert out["x"].iloc[1] == 2.0
    assert out["x"].iloc[2] == 2.0


def test_no_lookahead():
    """Truncating the data must not change any already-computed bar."""
    m15, h1, d1, usd = _dataset()
    cfg = Config()

    full = build_features(m15, h1, d1, usd, cfg)

    cut = int(len(m15) * 0.75)
    boundary = m15.index[cut]
    m15_t = m15.loc[:boundary]
    truncated = build_features(
        m15_t, resample(m15_t, "1h"), resample(m15_t, "1D"),
        usd.loc[:boundary], cfg,
    )

    checked = ["l0", "l1", "l2", "l3", "signal", "or_high", "or_low", "risk_dist", "vol_pct"]
    tail = truncated.index[-200:]

    for column in checked:
        a = full.loc[tail, column]
        b = truncated.loc[tail, column]
        mismatches = int((a.fillna(-999) != b.fillna(-999)).sum())
        assert mismatches == 0, f"LOOK-AHEAD in '{column}': {mismatches}/200 bars changed when data was truncated"


def test_opening_range_uses_only_its_own_window():
    cfg = Config()
    m15 = synthetic_ohlc("2020-01-06", 96 * 5, seed=2)
    ranges = opening_range(m15, cfg)

    day = ranges.index[0]
    window = m15.loc[
        (m15.index.normalize() == day)
        & (m15.index.hour * 60 + m15.index.minute >= cfg.or_start_min)
        & (m15.index.hour * 60 + m15.index.minute < cfg.or_start_min + cfg.or_length_min)
    ]
    assert ranges.loc[day, "or_high"] == window.high.max()
    assert ranges.loc[day, "or_low"] == window.low.min()


def test_bars_inside_the_range_cannot_trade_it():
    m15, h1, d1, usd = _dataset(bars=20_000)
    features = build_features(m15, h1, d1, usd, Config())
    minutes = features.index.hour * 60 + features.index.minute
    inside = features.loc[minutes < Config().or_start_min + Config().or_length_min]
    assert inside["or_high"].isna().all(), "a bar that formed the range must not see it"
    assert (inside["signal"] == NEUTRAL).all()


# ---------------------------------------------------------------- sizing

def test_size_is_the_smaller_of_risk_and_vol_target():
    inst = Instrument()
    cfg = ExecConfig(risk_percent=0.5, vol_target_annual=10.0)

    # tiny stop -> risk sizing would be enormous, vol target must bind
    lots = size_position(10_000, 0.5, atr_d1=25.0, inst=inst, cfg=cfg, multiplier=1.0)
    vol_lots = (10_000 * 0.10 / np.sqrt(252)) / (25.0 * inst.contract_size)
    assert abs(lots - np.floor(vol_lots / inst.lot_step) * inst.lot_step) < 1e-9

    # wide stop -> risk sizing binds instead
    lots = size_position(10_000, 40.0, atr_d1=1.0, inst=inst, cfg=cfg, multiplier=1.0)
    risk_lots = (10_000 * 0.005) / (40.0 * inst.contract_size)
    assert abs(lots - np.floor(risk_lots / inst.lot_step) * inst.lot_step) < 1e-9


def test_size_returns_zero_rather_than_rounding_up():
    inst = Instrument(lot_min=0.10, lot_step=0.10)
    cfg = ExecConfig(risk_percent=0.5, use_vol_target=False)
    assert size_position(100, 50.0, 10.0, inst, cfg, 1.0) == 0.0


def test_breaker_multiplier_halves_size():
    inst, cfg = Instrument(), ExecConfig(use_vol_target=False)
    full = size_position(10_000, 10.0, 20.0, inst, cfg, 1.0)
    halved = size_position(10_000, 10.0, 20.0, inst, cfg, 0.5)
    assert abs(halved - full / 2) <= inst.lot_step


# ---------------------------------------------------------------- engine

def _one_trade_frame(direction: int = LONG) -> pd.DataFrame:
    """Hand-built bars: signal on bar 0, entry bar 1, stop hit on bar 2."""
    index = pd.date_range("2020-06-01 08:00", periods=4, freq="15min", tz="UTC")
    price = 1800.0
    risk = 6.0

    frame = pd.DataFrame(
        {
            "open": [price] * 4,
            "high": [price + 1] * 4,
            "low": [price - 1] * 4,
            "close": [price] * 4,
            "tick_volume": [100.0] * 4,
            "spread": [0.0] * 4,
            "atr_h1": [4.0] * 4,
            "atr_d1": [20.0] * 4,
            "signal": [direction, 0, 0, 0],
            "risk_dist": [risk, np.nan, np.nan, np.nan],
        },
        index=index,
    )
    # bar 2 runs into the stop
    frame.loc[index[2], "low"] = price - risk - 2 if direction == LONG else price - 1
    frame.loc[index[2], "high"] = price + 1 if direction == LONG else price + risk + 2
    return frame


def test_entry_fills_on_the_next_bar_open():
    result = run_backtest(_one_trade_frame(), cfg=ExecConfig(use_vol_target=False))
    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["entry_time"] == pd.Timestamp("2020-06-01 08:15", tz="UTC"), \
        "entry must be the bar AFTER the signal bar"


def test_full_stop_loses_about_one_r():
    result = run_backtest(_one_trade_frame(), cfg=ExecConfig(use_vol_target=False))
    r = result.trades.iloc[0]["r_multiple"]
    assert -1.10 < r < -0.95, f"a clean stop should lose ~1R, got {r:.3f}R"


def test_costs_make_a_round_trip_negative():
    frame = _one_trade_frame()
    frame["spread"] = 0.60                       # a wide but realistic gold spread
    frame.loc[frame.index[2], ["high", "low"]] = [1801.0, 1799.0]   # no stop, no target

    result = run_backtest(frame, cfg=ExecConfig(use_vol_target=False))
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["pnl"] < 0, "a flat round trip must lose the spread and commission"


def test_pessimistic_ordering_prefers_the_stop():
    """When one bar contains both the stop and the +1R target, take the stop."""
    frame = _one_trade_frame()
    index = frame.index
    frame.loc[index[2], "low"] = 1800.0 - 6.0 - 2
    frame.loc[index[2], "high"] = 1800.0 + 6.0 + 2      # both levels inside the bar

    pessimistic = run_backtest(frame, cfg=ExecConfig(use_vol_target=False, pessimistic_intrabar=True))
    optimistic = run_backtest(frame, cfg=ExecConfig(use_vol_target=False, pessimistic_intrabar=False))

    assert pessimistic.trades.iloc[0]["exit_reason"] == "stop"
    assert pessimistic.trades.iloc[0]["pnl"] <= optimistic.trades.iloc[0]["pnl"]


def test_daily_entry_cap_blocks_the_third_signal():
    index = pd.date_range("2020-06-01 08:00", periods=40, freq="15min", tz="UTC")
    price = 1800.0
    frame = pd.DataFrame(
        {
            "open": price, "high": price + 0.5, "low": price - 0.5, "close": price,
            "tick_volume": 100.0, "spread": 0.0, "atr_h1": 4.0, "atr_d1": 20.0,
            "signal": 0, "risk_dist": np.nan,
        },
        index=index,
    )
    # a signal every 4th bar, and an immediate stop-out after each entry
    for i in range(0, 32, 4):
        frame.iloc[i, frame.columns.get_loc("signal")] = LONG
        frame.iloc[i, frame.columns.get_loc("risk_dist")] = 6.0
        frame.iloc[i + 2, frame.columns.get_loc("low")] = price - 10

    result = run_backtest(frame, cfg=ExecConfig(use_vol_target=False, max_entries_day=2))
    assert len(result.trades) == 2, f"entry cap should hold at 2, got {len(result.trades)}"
    assert result.rejections.get("daily entry cap", 0) > 0


def test_time_stop_flattens_the_position():
    index = pd.date_range("2020-06-01 19:30", periods=6, freq="15min", tz="UTC")
    price = 1800.0
    frame = pd.DataFrame(
        {
            "open": price, "high": price + 0.5, "low": price - 0.5, "close": price,
            "tick_volume": 100.0, "spread": 0.0, "atr_h1": 4.0, "atr_d1": 20.0,
            "signal": [LONG, 0, 0, 0, 0, 0],
            "risk_dist": [30.0, np.nan, np.nan, np.nan, np.nan, np.nan],
        },
        index=index,
    )
    result = run_backtest(frame, cfg=ExecConfig(use_vol_target=False, flat_minute_utc=1200))
    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "time stop"
    assert trade["exit_time"].hour == 20 and trade["exit_time"].minute == 0


# ---------------------------------------------------------------- metrics

def test_max_drawdown():
    equity = pd.Series(
        [100.0, 120.0, 90.0, 110.0],
        index=pd.date_range("2020-01-01", periods=4, freq="1D", tz="UTC"),
    )
    depth, peak, trough = max_drawdown(equity)
    assert abs(depth - 0.25) < 1e-12          # 120 -> 90
    assert peak == equity.index[1] and trough == equity.index[2]


def test_summary_handles_no_trades():
    equity = pd.Series(
        [1000.0] * 10, index=pd.date_range("2020-01-01", periods=10, freq="1D", tz="UTC")
    )
    stats = summarize(equity, pd.DataFrame(), 1000.0)
    assert stats["trades"] == 0 and stats["max_drawdown"] == 0.0


# ---------------------------------------------------------------- runner

def _run_all() -> int:
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failures = 0
    for name, func in tests:
        try:
            func()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {name}\n          {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {name}\n          {type(exc).__name__}: {exc}")

    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_all())
