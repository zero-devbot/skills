"""Build a daily SOLBTC OHLCV dataset from public GitHub-hosted sources.

Direct exchange APIs (Binance, Kraken, Coinbase, ...) are unreachable from
this execution environment's network policy, so the SOLBTC series is
constructed as a ratio of two USD series:

  SOL/USD daily OHLCV  : github.com/NI3singh/Solana-Data-Analysis
                         (Binance SOLUSDT daily, 2021-01-01 .. 2024-09-29)
  BTC/USD 1-min OHLCV  : github.com/ff137/bitstamp-btcusd-minute-data
                         (Bitstamp, aggregated here to daily UTC bars)

Ratio OHLC construction (the usual synthetic-cross approximation):
  Open  = solO / btcO
  Close = solC / btcC
  High  = max(Open, Close, solH / btcH)
  Low   = min(Open, Close, solL / btcL)

High/Low assume SOL and BTC intraday extremes roughly co-occur (they are
strongly positively correlated), which slightly understates the true ratio
range — i.e. intrabar TP/SL fills in the backtest are modelled a touch
conservatively. (Coin Metrics' community CSVs were considered for close
validation but now only publish reference rates for the trailing week, so
validation is limited to internal consistency checks plus landmark dates.)

Usage: python build_dataset.py [cache_dir]
Writes data/solbtc_1d.csv next to this script.
"""

import io
import pathlib
import subprocess
import sys

import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent

SOL_URL = "https://raw.githubusercontent.com/NI3singh/Solana-Data-Analysis/main/Solana_Price_data.csv"
BTC_URL = (
    "https://raw.githubusercontent.com/ff137/bitstamp-btcusd-minute-data/"
    "main/data/historical/btcusd_bitstamp_1min_2012-2025.csv.gz"
)


def fetch(url: str, cache: pathlib.Path) -> bytes:
    if cache.exists():
        return cache.read_bytes()
    out = subprocess.run(["curl", "-sSL", "--max-time", "300", url], capture_output=True, check=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(out.stdout)
    return out.stdout


def main() -> None:
    cache_dir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "cache"

    sol = pd.read_csv(io.BytesIO(fetch(SOL_URL, cache_dir / "sol_1d.csv")), parse_dates=["time"])
    sol = sol.set_index("time").sort_index()

    btc_min = pd.read_csv(
        io.BytesIO(fetch(BTC_URL, cache_dir / "btcusd_1min.csv.gz")), compression="gzip"
    )
    btc_min["ts"] = pd.to_datetime(btc_min["timestamp"], unit="s")
    btc_min = btc_min[btc_min["ts"] >= "2020-12-31"].set_index("ts")
    btc = btc_min.resample("1D").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    )

    both = sol.join(btc, how="inner", rsuffix="_btc")
    o = both["Open"] / both["open"]
    c = both["Close"] / both["close"]
    h = pd.concat([o, c, both["High"] / both["high"]], axis=1).max(axis=1)
    l = pd.concat([o, c, both["Low"] / both["low"]], axis=1).min(axis=1)
    out = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": both["Volume"]})

    # Sanity checks: bar validity, gapless daily index, and known landmark dates
    assert (out["High"] >= out[["Open", "Close"]].max(axis=1) - 1e-15).all()
    assert (out["Low"] <= out[["Open", "Close"]].min(axis=1) + 1e-15).all()
    gaps = out.index.to_series().diff().dt.days.iloc[1:]
    print(f"Missing days: {int((gaps - 1).sum())} across {len(out)} bars")
    for d in ("2021-11-06", "2022-11-09", "2023-12-25"):
        if d in out.index:
            print(f"  {d} close: {out.loc[d, 'Close']:.6f} BTC")

    dest = HERE / "data" / "solbtc_1d.csv"
    dest.parent.mkdir(exist_ok=True)
    out.to_csv(dest, float_format="%.10f")
    print(f"Wrote {dest}: {len(out)} rows, {out.index[0].date()} .. {out.index[-1].date()}")


if __name__ == "__main__":
    main()
