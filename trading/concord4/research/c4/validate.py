"""Validation: in-sample/out-of-sample, walk-forward, sweeps, Monte Carlo.

A single backtest number is one draw from a distribution. These routines
exist to ask whether the number survives being moved, re-parameterised, and
reshuffled - which is the only question that matters before risking money.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import ExecConfig, Result, run_backtest
from .data import Instrument
from .gates import Config, build_features
from .metrics import summarize

# below this, the best metric is too close to zero for a ratio to mean anything
PLATEAU_MIN_PEAK = 0.10


@dataclass
class Dataset:
    """Everything a run needs, so a window can be re-sliced cheaply."""

    m15: pd.DataFrame
    h1: pd.DataFrame
    d1: pd.DataFrame
    usd_h1: pd.Series
    news: pd.DatetimeIndex | None = None

    def slice(self, start=None, end=None) -> "Dataset":
        """Slice the M15 window while KEEPING the higher-timeframe warmup.

        Trimming D1 to the same window would strip the 250-day percentile
        history and silently disable the volatility-regime gate.
        """
        m15 = self.m15.loc[start:end]
        return Dataset(m15=m15, h1=self.h1, d1=self.d1, usd_h1=self.usd_h1, news=self.news)


def run(
    dataset: Dataset,
    cfg: Config | None = None,
    exec_cfg: ExecConfig | None = None,
    inst: Instrument | None = None,
) -> tuple[Result, dict]:
    """Build features and run one backtest, returning the result and stats."""
    cfg = cfg or Config()
    exec_cfg = exec_cfg or ExecConfig()
    inst = inst or Instrument()

    features = build_features(
        dataset.m15, dataset.h1, dataset.d1, dataset.usd_h1, cfg,
        news_events=dataset.news, default_spread=inst.default_spread,
    )
    result = run_backtest(features, inst=inst, cfg=exec_cfg)
    stats = summarize(result.equity, result.trades, exec_cfg.initial_equity)
    return result, stats


def split_is_oos(dataset: Dataset, split: str) -> tuple[Dataset, Dataset]:
    """Split at a date. Touch the OOS half once, at the very end."""
    boundary = pd.Timestamp(split, tz="UTC")
    return dataset.slice(end=boundary), dataset.slice(start=boundary)


def sweep(
    dataset: Dataset,
    parameter: str,
    values,
    cfg: Config | None = None,
    exec_cfg: ExecConfig | None = None,
    inst: Instrument | None = None,
    metric: str = "sharpe",
) -> pd.DataFrame:
    """Vary one parameter and report the metric surface.

    Read the ``plateau`` column, not the peak. A parameter whose best value
    towers over its neighbours is a curve fit; one sitting on a broad shelf
    is a finding.
    """
    cfg = cfg or Config()
    rows = []
    for value in values:
        candidate = cfg.replace(**{parameter: value})
        _, stats = run(dataset, candidate, exec_cfg, inst)
        rows.append({parameter: value, **{k: stats.get(k) for k in
                     (metric, "trades", "max_drawdown", "profit_factor", "win_rate")}})

    frame = pd.DataFrame(rows)
    series = frame[metric].astype("float64")

    # plateau score: each point against the mean of its immediate neighbours,
    # normalised by the best value. Near 1.0 across several rows is a shelf;
    # a single row near 1.0 with low neighbours is a curve fit.
    neighbours = series.rolling(3, center=True, min_periods=2).mean()
    peak = series.max()

    # Normalising by a peak that is itself ~0 produces meaningless ratios, so
    # the score is withheld rather than printed as noise. No positive peak
    # means there is no shelf to stand on: the parameter has no good region.
    if np.isfinite(peak) and peak > PLATEAU_MIN_PEAK:
        frame["plateau"] = neighbours / peak
    else:
        frame["plateau"] = np.nan
    return frame


def walk_forward(
    dataset: Dataset,
    parameter: str,
    values,
    train_months: int = 12,
    test_months: int = 6,
    cfg: Config | None = None,
    exec_cfg: ExecConfig | None = None,
    inst: Instrument | None = None,
    metric: str = "sharpe",
) -> pd.DataFrame:
    """Rolling anchored walk-forward over one parameter.

    Each fold picks the best value on the training window and reports what
    that choice earned on the untouched test window. The aggregate of the
    TEST columns is the only honest estimate of live performance here.
    """
    cfg = cfg or Config()
    start = dataset.m15.index.min()
    end = dataset.m15.index.max()

    folds = []
    train_start = start
    while True:
        train_end = train_start + pd.DateOffset(months=train_months)
        test_end = train_end + pd.DateOffset(months=test_months)
        if train_end >= end:
            break

        train = dataset.slice(train_start, train_end)
        test = dataset.slice(train_end, min(test_end, end))
        if len(test.m15) < 100:
            break

        best_value, best_score = None, -np.inf
        for value in values:
            _, stats = run(train, cfg.replace(**{parameter: value}), exec_cfg, inst)
            score = stats.get(metric)
            if score is not None and np.isfinite(score) and score > best_score:
                best_value, best_score = value, score

        if best_value is None:
            train_start = train_start + pd.DateOffset(months=test_months)
            continue

        _, test_stats = run(test, cfg.replace(**{parameter: best_value}), exec_cfg, inst)
        folds.append(
            {
                "train_start": train_start,
                "train_end": train_end,
                "test_end": min(test_end, end),
                f"best_{parameter}": best_value,
                f"train_{metric}": best_score,
                f"test_{metric}": test_stats.get(metric),
                "test_trades": test_stats.get("trades"),
                "test_return": test_stats.get("total_return"),
                "test_max_dd": test_stats.get("max_drawdown"),
            }
        )
        train_start = train_start + pd.DateOffset(months=test_months)

    return pd.DataFrame(folds)


def monte_carlo(
    trades: pd.DataFrame,
    iterations: int = 5000,
    initial_equity: float = 10_000.0,
    seed: int = 0,
) -> dict:
    """Bootstrap the trade sequence to get a DISTRIBUTION of max drawdown.

    The backtest's max drawdown is one sample. Resampling the same trades in
    a different order shows what else that edge could plausibly have done -
    usually a good deal worse than the single path you happened to observe.
    """
    if trades is None or trades.empty:
        return {}

    pnl = trades["pnl"].to_numpy(dtype="float64")
    rng = np.random.default_rng(seed)

    depths = np.empty(iterations)
    finals = np.empty(iterations)
    for i in range(iterations):
        path = initial_equity + np.cumsum(rng.choice(pnl, size=len(pnl), replace=True))
        peaks = np.maximum.accumulate(np.concatenate([[initial_equity], path]))
        depths[i] = float(np.max((peaks[1:] - path) / peaks[1:]))
        finals[i] = path[-1]

    quantiles = [50, 75, 90, 95, 99]
    return {
        "iterations": iterations,
        "observed_trades": int(len(pnl)),
        "max_dd_percentiles": {f"p{q}": float(np.percentile(depths, q)) for q in quantiles},
        "median_final_equity": float(np.median(finals)),
        "prob_negative": float((finals < initial_equity).mean()),
        "prob_dd_over_10pct": float((depths > 0.10).mean()),
        "prob_dd_over_20pct": float((depths > 0.20).mean()),
    }
