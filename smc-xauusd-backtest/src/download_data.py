"""Download 2 years of XAUUSD OHLC data.

Primary source (works in restricted-network environments because
raw.githubusercontent.com is usually reachable):

    https://github.com/FeziweMelvin/XAUUSD-Gold-Price
    (MetaTrader-exported XAU/USD candles, auto-updated on weekdays;
    columns: Date;Open;High;Low;Close;Volume)

If yfinance is available and the network allows it, `--source yahoo`
pulls spot gold (XAUUSD=X) instead.

Output: data/xauusd_h1_2y.csv and data/xauusd_d1_2y.csv containing the
most recent 2 years available in the source, in standard
Date,Open,High,Low,Close,Volume format expected by backtesting.py.
"""

from __future__ import annotations

import argparse
import io
import sys
import urllib.request
from pathlib import Path

import pandas as pd

GITHUB_BASE = "https://raw.githubusercontent.com/FeziweMelvin/XAUUSD-Gold-Price/main"
FILES = {"h1": "XAU_1h_data.csv", "d1": "XAU_1d_data.csv"}
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def fetch_github(tf: str) -> pd.DataFrame:
    url = f"{GITHUB_BASE}/{FILES[tf]}"
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:
        raw = resp.read().decode()
    df = pd.read_csv(io.StringIO(raw), sep=";")
    df["Date"] = pd.to_datetime(df["Date"], format="%Y.%m.%d %H:%M")
    df = df.set_index("Date").sort_index()
    df.columns = [c.capitalize() for c in df.columns]
    return df[["Open", "High", "Low", "Close", "Volume"]]


def fetch_yahoo(tf: str) -> pd.DataFrame:
    import yfinance as yf

    interval = {"h1": "1h", "d1": "1d"}[tf]
    period = {"h1": "729d", "d1": "2y"}[tf]
    df = yf.download("XAUUSD=X", period=period, interval=interval,
                     auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def validate(df: pd.DataFrame, tf: str) -> None:
    bad = df[(df.High < df.Low) | (df.High < df.Open) | (df.High < df.Close)
             | (df.Low > df.Open) | (df.Low > df.Close)]
    if len(bad):
        raise ValueError(f"{tf}: {len(bad)} rows fail OHLC sanity checks")
    if df.index.duplicated().any():
        raise ValueError(f"{tf}: duplicate timestamps")
    if (df.Close <= 0).any():
        raise ValueError(f"{tf}: non-positive prices")
    print(f"{tf}: {len(df)} rows OK, {df.index[0]} -> {df.index[-1]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["github", "yahoo"], default="github")
    ap.add_argument("--years", type=int, default=2)
    args = ap.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fetch = fetch_github if args.source == "github" else fetch_yahoo

    for tf in ("h1", "d1"):
        df = fetch(tf)
        end = df.index.max()
        start = end - pd.DateOffset(years=args.years)
        df = df.loc[start:]
        validate(df, tf)
        out = DATA_DIR / f"xauusd_{tf}_{args.years}y.csv"
        df.to_csv(out)
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
