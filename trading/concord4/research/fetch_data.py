#!/usr/bin/env python3
"""Download Dukascopy tick data and write the CSVs the harness expects.

    python fetch_data.py --start 2015-01-01 --end 2026-01-01 --out data/

One CSV per symbol, aggregated to M15 with a real average spread per bar -
which matters, because gold's spread is not a constant and the L0 gate is
measured against it.

Downloading a decade of XAUUSD ticks is tens of thousands of hourly files.
Expect it to take hours, and re-run it: existing symbol files are skipped
unless --force is passed.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from c4.data import USD_BASKET, fetch_dukascopy, ticks_to_bars

# Dukascopy stores prices as integers scaled by the instrument's digit count.
POINT_VALUE = {
    "XAUUSD": 1e-3,
    "EURUSD": 1e-5,
    "GBPUSD": 1e-5,
    "AUDUSD": 1e-5,
    "USDCAD": 1e-5,
    "USDCHF": 1e-5,
    "USDJPY": 1e-3,
}


def download(symbol: str, start: datetime, end: datetime, out_dir: Path, rule: str) -> bool:
    point = POINT_VALUE.get(symbol)
    if point is None:
        print(f"  {symbol}: unknown point value, pass --point-value to override")
        return False

    print(f"  {symbol}: fetching {start:%Y-%m-%d} -> {end:%Y-%m-%d} ...")
    ticks = fetch_dukascopy(symbol, start, end, point_value=point)
    if ticks.empty:
        print(f"  {symbol}: no data returned")
        return False

    bars = ticks_to_bars(ticks, rule)
    if bars.empty:
        print(f"  {symbol}: ticks decoded but produced no bars")
        return False

    path = out_dir / f"{symbol}.csv"
    bars.index.name = "time"
    bars.to_csv(path)

    span = f"{bars.index[0]:%Y-%m-%d} -> {bars.index[-1]:%Y-%m-%d}"
    print(f"  {symbol}: {len(bars):,} bars  {span}  ({len(ticks):,} ticks)  -> {path}")
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Dukascopy downloader for CONCORD-4")
    parser.add_argument("--start", required=True, help="UTC date, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="UTC date, YYYY-MM-DD (exclusive)")
    parser.add_argument("--out", type=Path, default=Path("data"))
    parser.add_argument("--symbol", default="XAUUSD", help="the traded instrument")
    parser.add_argument("--rule", default="15min", help="bar size to aggregate to")
    parser.add_argument("--skip-majors", action="store_true",
                        help="skip the USD-basket legs (L2 will then fail closed)")
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args(argv)

    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    if end <= start:
        raise SystemExit("--end must be after --start")

    args.out.mkdir(parents=True, exist_ok=True)

    symbols = [args.symbol]
    if not args.skip_majors:
        symbols += [leg for leg, _, _ in USD_BASKET if leg != args.symbol]

    print(f"Dukascopy -> {args.out}  ({len(symbols)} symbols)")
    failed = []
    for symbol in symbols:
        path = args.out / f"{symbol}.csv"
        if path.exists() and not args.force:
            print(f"  {symbol}: already present, skipping (use --force to refresh)")
            continue
        if not download(symbol, start, end, args.out, args.rule):
            failed.append(symbol)

    if failed:
        print(f"\nfailed: {failed}")
        print("Check network access to datafeed.dukascopy.com. Corporate proxies and "
              "sandboxes commonly block it; in that case export the same CSVs from "
              "MT5 (History Centre) or another vendor instead.")
        return 1

    print("\ndone. Next: python run_backtest.py --data-dir", args.out, "--mode all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
