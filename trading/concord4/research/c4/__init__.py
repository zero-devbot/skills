"""CONCORD-4 research harness - RBI stage 2.

Mirrors the MQL5 implementation in ``../Include/Concord4Core.mqh`` closely
enough that a disagreement between the two is a bug worth chasing, not a
platform quirk to shrug at.
"""

from .data import Instrument, USD_BASKET, load_csv, resample, usd_index_h1, synthetic_ohlc
from .gates import Config, LONG, SHORT, NEUTRAL, build_features, veto_reasons
from .engine import ExecConfig, Result, run_backtest, size_position
from .metrics import summarize, format_summary, max_drawdown
from .validate import Dataset, run, split_is_oos, sweep, walk_forward, monte_carlo

__all__ = [
    "Instrument", "USD_BASKET", "load_csv", "resample", "usd_index_h1", "synthetic_ohlc",
    "Config", "LONG", "SHORT", "NEUTRAL", "build_features", "veto_reasons",
    "ExecConfig", "Result", "run_backtest", "size_position",
    "summarize", "format_summary", "max_drawdown",
    "Dataset", "run", "split_is_oos", "sweep", "walk_forward", "monte_carlo",
]
