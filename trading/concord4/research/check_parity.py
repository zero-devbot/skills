#!/usr/bin/env python3
"""Diff the terminal's CONCORD-4 gate output against the Python implementation.

    # 1. in MT5: attach Scripts/Concord4Export.mq5 to an M15 XAUUSD chart, run it
    # 2. copy MQL5/Files/concord4_mt5_export.csv here
    python check_parity.py --mt5-csv concord4_mt5_export.csv

    python check_parity.py --mt5-csv export.csv --mode recompute --majors-dir data/
    python check_parity.py --self-test          # validate the comparer itself

Modes:
  inject     (default) feed the terminal's higher-timeframe values into Python,
             so only the GATE LOGIC is under test. Run this first.
  recompute  Python derives everything from the exported bars. A mismatch here
             but not in inject means data depth or timeframe construction.

Exits 0 on PASS, 1 on WARN or FAIL, 2 if nothing could be compared - so it can
gate a commit.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import pandas as pd

from c4 import Config, Instrument, USD_BASKET, resample, synthetic_ohlc, usd_index_h1
from c4.gates import build_features
from c4.parity import (
    compare, load_mt5_export, python_side, render, write_synthetic_export,
)


def _synthetic_features(bars: int, seed: int, digits: int = 2) -> pd.DataFrame:
    m15 = synthetic_ohlc("2016-01-01", bars, start_price=1300.0, seed=seed)

    # Round to the instrument's precision BEFORE deriving anything. A terminal
    # computes its opening range from bars that are already 2-decimal, so a
    # generator that derives levels from full-precision prices and then rounds
    # the bars produces an internally inconsistent export - and flips the odd
    # borderline breakout. The same hazard applies to real data: a CSV carrying
    # more precision than the broker's bars will not reproduce its decisions.
    m15 = m15.round(digits).assign(spread=0.08)

    majors = {}
    for i, (leg, _, _) in enumerate(USD_BASKET):
        price = 110.0 if leg == "USDJPY" else 1.15
        majors[leg] = resample(
            synthetic_ohlc("2016-01-01", bars, start_price=price, annual_vol=0.08, seed=seed + i + 1),
            "1h",
        )

    return build_features(
        m15, resample(m15, "1h"), resample(m15, "1D"),
        usd_index_h1(majors), Config(), default_spread=0.08,
    )


def self_test(bars: int, seed: int) -> int:
    """Round-trip a Python run through the export format and back.

    A clean round trip must be PASS, and a deliberately corrupted one must not
    be. If either expectation fails, the comparer cannot be trusted to judge
    the real thing.
    """
    print("SELF-TEST: dressing a Python run up as a terminal export.\n"
          "This validates the comparer, not the strategy.\n")

    features = _synthetic_features(bars, seed)
    cfg, inst = Config(), Instrument(default_spread=0.08)

    with tempfile.TemporaryDirectory() as tmp:
        clean = write_synthetic_export(features, Path(tmp) / "clean.csv", digits=2)

        export, meta = load_mt5_export(clean)
        py, warnings = python_side(export, meta, cfg, mode="inject", inst=inst)
        report = compare(export, py, meta, "inject")
        report.warnings.extend(warnings)
        print(render(report))

        if report.verdict != "PASS":
            print("\nSELF-TEST FAILED: a clean round trip should be PASS.")
            return 1

        # now corrupt a few gate values and confirm the comparer notices
        corrupted = export.copy()
        flips = corrupted.index[corrupted["l1"] != 0][:25]
        if len(flips) == 0:
            print("\nSELF-TEST INCONCLUSIVE: no non-neutral L1 bars to corrupt.")
            return 1
        corrupted.loc[flips, "l1"] = -corrupted.loc[flips, "l1"]

        detected = compare(corrupted, py, meta, "inject")
        print(f"\n  corruption probe: flipped L1 on {len(flips)} bar(s) -> "
              f"verdict {detected.verdict}, {detected.gate_mismatches} gate mismatch(es)")

        if detected.gate_mismatches < len(flips):
            print("SELF-TEST FAILED: the comparer missed injected corruption.")
            return 1

        # a handful of edge bars is WARN; systematic divergence must be FAIL,
        # otherwise the verdict thresholds are not doing their job
        systematic = export.copy()
        systematic["signal"] = -systematic["signal"]
        systematic["l1"] = -systematic["l1"]
        broken = compare(systematic, py, meta, "inject")
        print(f"  systematic probe: inverted every L1 and signal -> "
              f"verdict {broken.verdict}, {broken.gate_mismatches} gate mismatch(es)")

        if broken.verdict != "FAIL":
            print(f"SELF-TEST FAILED: systematic divergence graded {broken.verdict}, "
                  "expected FAIL.")
            return 1

    print("\nSELF-TEST PASSED: clean round trip is PASS, a few bad bars are WARN, "
          "systematic divergence is FAIL.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CONCORD-4 MT5/Python parity check")
    parser.add_argument("--mt5-csv", type=Path, help="export from Scripts/Concord4Export.mq5")
    parser.add_argument("--mode", default="inject", choices=["inject", "recompute"])
    parser.add_argument("--majors-dir", type=Path, default=None,
                        help="folder of USD-basket CSVs, for --mode recompute")
    parser.add_argument("--max-examples", type=int, default=12)
    parser.add_argument("--default-spread", type=float, default=0.25)
    parser.add_argument("--max-spread-atr", type=float, default=None,
                        help="must match the value used for the export")
    parser.add_argument("--include-warmup", action="store_true",
                        help="also compare bars the terminal reported as not ready")
    parser.add_argument("--self-test", action="store_true", help="validate the comparer itself")
    parser.add_argument("--self-test-bars", type=int, default=60_000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--save-diff", type=Path, default=None,
                        help="write the full per-bar comparison to CSV")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test(args.self_test_bars, args.seed)

    if not args.mt5_csv:
        parser.error("--mt5-csv is required (or use --self-test)")
    if not args.mt5_csv.exists():
        raise SystemExit(f"missing {args.mt5_csv}")

    cfg = Config()
    if args.max_spread_atr is not None:
        cfg = cfg.replace(max_spread_atr=args.max_spread_atr)
    inst = Instrument(default_spread=args.default_spread)

    export, meta = load_mt5_export(args.mt5_csv)
    py, warnings = python_side(export, meta, cfg, mode=args.mode,
                               majors_dir=args.majors_dir, inst=inst)

    report = compare(export, py, meta, args.mode,
                     max_examples=args.max_examples,
                     skip_not_ready=not args.include_warmup)
    report.warnings.extend(warnings)
    print(render(report))

    if args.save_diff:
        common = export.index.intersection(py.index)
        gates = ["l0", "l1", "l2", "l3", "signal", "or_high", "or_low", "risk_dist"]
        frames = {}
        for name in gates:
            if name in export.columns:
                frames[f"mt5_{name}"] = export.loc[common, name]
            if name in py.columns:
                frames[f"py_{name}"] = py.loc[common, name]
        pd.DataFrame(frames).to_csv(args.save_diff)
        print(f"\n  full comparison written to {args.save_diff}")

    return {"PASS": 0, "WARN": 1, "FAIL": 1, "INCONCLUSIVE": 2}[report.verdict]


if __name__ == "__main__":
    sys.exit(main())
