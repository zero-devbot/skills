#!/usr/bin/env python3
"""CONCORD-4 backtest CLI - RBI stage 2.

    python run_backtest.py --data-dir data/                 # single run
    python run_backtest.py --data-dir data/ --mode all      # full protocol
    python run_backtest.py --synthetic --mode all           # plumbing check

Expects one CSV per symbol in ``--data-dir``, named ``XAUUSD.csv``,
``EURUSD.csv`` and so on, with columns ``time,open,high,low,close`` plus
optional ``tick_volume`` and ``spread``. Times must be UTC.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from c4 import (
    Config, Dataset, ExecConfig, Instrument, USD_BASKET,
    format_summary, load_csv, monte_carlo, resample, run, split_is_oos,
    summarize, sweep, synthetic_ohlc, usd_index_h1, veto_reasons, walk_forward,
)
from c4.gates import build_features


def load_dataset(data_dir: Path, symbol: str, news_csv: Path | None) -> Dataset:
    """Load the traded symbol plus every USD-basket leg the folder has."""
    main_path = data_dir / f"{symbol}.csv"
    if not main_path.exists():
        raise SystemExit(f"missing {main_path}")

    raw = load_csv(main_path)
    m15 = raw if _infer_freq(raw) <= pd.Timedelta(minutes=15) else raw
    if _infer_freq(raw) < pd.Timedelta(minutes=15):
        m15 = resample(raw, "15min")

    majors = {}
    for leg, _, _ in USD_BASKET:
        path = data_dir / f"{leg}.csv"
        if path.exists():
            majors[leg] = resample(load_csv(path), "1h")

    if len(majors) < 3:
        print(f"WARNING: only {len(majors)} USD-basket legs found. "
              f"L2 fails closed and NO trades will be taken. "
              f"Add {[s for s, _, _ in USD_BASKET]} to {data_dir}.")

    news = None
    if news_csv and news_csv.exists():
        events = pd.read_csv(news_csv)
        col = next(c for c in events.columns if c.lower() in ("time", "datetime", "date"))
        news = pd.DatetimeIndex(pd.to_datetime(events[col], utc=True, format="mixed"))
        print(f"news calendar: {len(news)} high-impact events")

    return Dataset(
        m15=m15,
        h1=resample(m15, "1h"),
        d1=resample(m15, "1D"),
        usd_h1=usd_index_h1(majors),
        news=news,
    )


def _infer_freq(frame: pd.DataFrame) -> pd.Timedelta:
    if len(frame) < 3:
        return pd.Timedelta(minutes=15)
    return pd.Series(frame.index).diff().median()


def synthetic_dataset(bars: int, seed: int) -> Dataset:
    """Fake data for checking the plumbing. Produces no edge, proves nothing."""
    print("SYNTHETIC DATA: this validates the engine, not the strategy.\n")
    m15 = synthetic_ohlc("2016-01-01", bars, start_price=1300.0, annual_vol=0.16, seed=seed)

    majors = {}
    for i, (leg, _, _) in enumerate(USD_BASKET):
        price = 110.0 if leg == "USDJPY" else 1.15
        majors[leg] = resample(
            synthetic_ohlc("2016-01-01", bars, start_price=price, annual_vol=0.08, seed=seed + i + 1),
            "1h",
        )

    return Dataset(
        m15=m15, h1=resample(m15, "1h"), d1=resample(m15, "1D"),
        usd_h1=usd_index_h1(majors), news=None,
    )


def report_gates(dataset: Dataset, cfg: Config, inst: Instrument) -> None:
    """Dry-run report: how often each gate blocked, and why."""
    features = build_features(
        dataset.m15, dataset.h1, dataset.d1, dataset.usd_h1, cfg,
        news_events=dataset.news, default_spread=inst.default_spread,
    )
    reasons = veto_reasons(features)
    breakouts = int((features["l3"] != 0).sum())

    print("\nGATE REPORT")
    print("=" * 58)
    print(f"  M15 bars                {len(features):>8,}")
    print(f"  in session              {int(features['in_session'].sum()):>8,}")
    print(f"  L0 tradability open     {int(features['l0'].sum()):>8,}")
    print(f"  L1 regime non-neutral   {int((features['l1'] != 0).sum()):>8,}")
    print(f"  L2 intermarket non-neut {int((features['l2'] != 0).sum()):>8,}")
    print(f"  L3 breakouts            {breakouts:>8,}")
    print(f"  signals (all agree)     {int((features['signal'] != 0).sum()):>8,}")

    rejected = reasons[reasons != ""].value_counts()
    if not rejected.empty:
        print("\n  breakouts rejected by:")
        for reason, count in rejected.items():
            share = 100.0 * count / breakouts if breakouts else 0.0
            print(f"    {reason:<38} {count:>6,}  ({share:4.1f}%)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CONCORD-4 backtest harness")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--news-csv", type=Path, default=None)
    parser.add_argument("--synthetic", action="store_true", help="run on generated data")
    parser.add_argument("--synthetic-bars", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--mode", default="single",
        choices=["single", "gates", "sweep", "walkforward", "montecarlo", "oos", "all"],
    )
    parser.add_argument("--split", default="2022-01-01", help="in-sample / out-of-sample boundary")
    parser.add_argument("--equity", type=float, default=10_000.0)
    parser.add_argument("--risk", type=float, default=0.50, help="risk per trade, %%")
    parser.add_argument("--vol-target", type=float, default=10.0, help="annualised vol target, %%")
    parser.add_argument("--spread-mult", type=float, default=1.0, help="stress-test spreads")
    parser.add_argument("--default-spread", type=float, default=None,
                        help="spread in price units when the data has no spread column")
    parser.add_argument("--max-spread-atr", type=float, default=None,
                        help="override the L0 spread gate (fraction of ATR(M15))")
    parser.add_argument("--sweep-param", default="breakout_atr_k")
    parser.add_argument("--sweep-values", default="0.05,0.10,0.15,0.20,0.25,0.30")
    args = parser.parse_args(argv)

    dataset = (
        synthetic_dataset(args.synthetic_bars, args.seed)
        if args.synthetic
        else load_dataset(args.data_dir, args.symbol, args.news_csv)
    )

    if args.spread_mult != 1.0 and "spread" in dataset.m15.columns:
        dataset.m15 = dataset.m15.assign(spread=dataset.m15["spread"] * args.spread_mult)
        print(f"spread stress: x{args.spread_mult}")

    cfg = Config()
    if args.max_spread_atr is not None:
        cfg = cfg.replace(max_spread_atr=args.max_spread_atr)
    inst = Instrument()
    if args.default_spread is not None:
        inst = Instrument(default_spread=args.default_spread)
    exec_cfg = ExecConfig(
        initial_equity=args.equity,
        risk_percent=args.risk,
        vol_target_annual=args.vol_target,
    )

    coverage = f"{dataset.m15.index[0]} -> {dataset.m15.index[-1]}  ({len(dataset.m15):,} M15 bars)"
    print(f"data: {coverage}")

    if args.mode in ("gates", "all"):
        report_gates(dataset, cfg, inst)

    result = None
    if args.mode in ("single", "montecarlo", "all"):
        result, stats = run(dataset, cfg, exec_cfg, inst)
        print(format_summary(stats, "CONCORD-4 - full sample"))
        if not result.rejections.empty:
            print("\n  signals blocked by circuit breakers:")
            for reason, count in result.rejections.items():
                print(f"    {reason:<38} {count:>6,}")

    if args.mode in ("oos", "all"):
        is_data, oos_data = split_is_oos(dataset, args.split)
        _, is_stats = run(is_data, cfg, exec_cfg, inst)
        _, oos_stats = run(oos_data, cfg, exec_cfg, inst)
        print(format_summary(is_stats, f"IN-SAMPLE  (to {args.split})"))
        print(format_summary(oos_stats, f"OUT-OF-SAMPLE  (from {args.split})"))

        if not np.isfinite(is_stats["sharpe"]) or is_stats["sharpe"] <= 0:
            print("\n  Sharpe degradation IS -> OOS: n/a - in-sample Sharpe is not positive,")
            print("  so there is nothing to degrade. The strategy failed in-sample.")
        else:
            drop = 100 * (1 - oos_stats["sharpe"] / is_stats["sharpe"])
            print(f"\n  Sharpe degradation IS -> OOS: {drop:.0f}%")
            print("  Anything past ~50% means the in-sample result was mostly fitting.")

    if args.mode in ("sweep", "all"):
        values = [float(v) for v in args.sweep_values.split(",")]
        table = sweep(dataset, args.sweep_param, values, cfg, exec_cfg, inst)
        print(f"\nPARAMETER SWEEP - {args.sweep_param}")
        print("=" * 58)
        print(table.to_string(index=False, float_format=lambda v: f"{v:8.3f}"))
        if table["plateau"].isna().all():
            print("  plateau score withheld: no parameter value reached a positive metric,")
            print("  so there is no good region to be on a shelf of.")
        else:
            print("  Read the plateau column, not the peak. Several rows near 1.0 is a shelf;")
            print("  one row near 1.0 with low neighbours is a curve fit.")

    if args.mode in ("walkforward", "all"):
        values = [float(v) for v in args.sweep_values.split(",")]
        folds = walk_forward(dataset, args.sweep_param, values, cfg=cfg, exec_cfg=exec_cfg, inst=inst)
        print("\nWALK-FORWARD  (12m train / 6m test)")
        print("=" * 58)
        if folds.empty:
            print("  not enough history for a single fold")
        else:
            print(folds.to_string(index=False, float_format=lambda v: f"{v:8.3f}"))
            test_col = next(c for c in folds.columns if c.startswith("test_") and c.endswith("sharpe"))
            print(f"\n  mean out-of-sample Sharpe across folds: {folds[test_col].mean():.3f}")

    if args.mode in ("montecarlo", "all") and result is not None:
        mc = monte_carlo(result.trades, initial_equity=args.equity, seed=args.seed)
        print("\nMONTE CARLO  (bootstrapped trade order)")
        print("=" * 58)
        if not mc:
            print("  no trades to resample")
        else:
            print(f"  iterations                {mc['iterations']:,}")
            print(f"  trades resampled          {mc['observed_trades']:,}")
            for key, value in mc["max_dd_percentiles"].items():
                print(f"  max drawdown {key:<12} {value * 100:6.2f}%")
            print(f"  median final equity       {mc['median_final_equity']:,.0f}")
            print(f"  P(losing overall)         {mc['prob_negative'] * 100:5.1f}%")
            print(f"  P(drawdown > 10%)         {mc['prob_dd_over_10pct'] * 100:5.1f}%")
            print(f"  P(drawdown > 20%)         {mc['prob_dd_over_20pct'] * 100:5.1f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
