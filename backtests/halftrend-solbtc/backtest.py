"""Backtest the HalfTrend Long/Short engine on daily SOLBTC.

Trade rules, translated from the Pine script's tracker into a real strategy:
  - Long on bullish flip, short on bearish flip, entry at the signal bar's
    close (Pine sets entryPx := close on the confirmed signal bar).
  - dist = baseRiskMult * atr2 (atr2 = ATR(100)/2 at the signal bar).
  - Stop for the whole position at entry -/+ dist.
  - Three equal tranches take profit at 1x / 2x / 3x dist (the Pine version
    checks TPs sequentially one-per-bar; independent limit orders are the
    honest equivalent).
  - An opposite flip closes whatever remains and reverses.
  - Fees: 0.1% per side (Binance spot taker). Exits start the bar after
    entry, same as the Pine tracker.

Runs in-sample (first 70%) and out-of-sample (last 30%) with the indicator
computed causally over the full history (no leakage), then a parameter
robustness sweep on the in-sample slice. Writes RESULTS.md.
"""

import pathlib

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy

from halftrend import halftrend

HERE = pathlib.Path(__file__).resolve().parent

AMPLITUDE = 20
CHANNEL_DEV = 2.0
ATR_PERIOD = 100
BASE_RISK_MULT = 6.0  # dist = 6 * ATR/2 = 3 x ATR; TPs scale with it (1R/2R/3R)
COMMISSION = 0.001
CASH = 10.0  # account denominated in BTC
TRANCHE = 0.3  # 3 tranches x 30% of equity


class HalfTrendStrategy(Strategy):
    risk_mult = BASE_RISK_MULT

    def init(self):
        pass  # signals precomputed on the full series, carried in as data columns

    def next(self):
        price = self.data.Close[-1]
        atr2 = self.data.Atr2[-1]
        if np.isnan(atr2):
            return
        dist = self.risk_mult * atr2

        # A non-positive SL/TP level can never be touched (Pine keeps such
        # levels forever-unfilled); the equivalent here is omitting the level.
        if self.data.Buy[-1]:
            if self.position.is_short:
                self.position.close()
            if not self.position.is_long:
                sl = price - dist
                for k in (1, 2, 3):
                    self.buy(size=TRANCHE, sl=sl if sl > 0 else None, tp=price + k * dist)
        elif self.data.Sell[-1]:
            if self.position.is_long:
                self.position.close()
            if not self.position.is_short:
                sl = price + dist
                for k in (1, 2, 3):
                    tp = price - k * dist
                    self.sell(size=TRANCHE, sl=sl, tp=tp if tp > 0 else None)


def attach_signals(df: pd.DataFrame, amplitude=AMPLITUDE) -> pd.DataFrame:
    # channelDeviation is cosmetic in the Pine script (bands only) — signals
    # depend solely on amplitude; SL/TP distances on atr2 * risk_mult.
    ht = halftrend(df, amplitude=amplitude, channel_deviation=CHANNEL_DEV, atr_period=ATR_PERIOD)
    out = df.copy()
    out["Atr2"] = ht.atr2
    out["Buy"] = ht.buy_signal.astype(int)
    out["Sell"] = ht.sell_signal.astype(int)
    return out


def run(data: pd.DataFrame, **params):
    bt = Backtest(
        data,
        HalfTrendStrategy,
        cash=CASH,
        commission=COMMISSION,
        trade_on_close=True,
        exclusive_orders=False,
        finalize_trades=True,
    )
    return bt.run(**params)


KEEP = [
    "Return [%]",
    "Buy & Hold Return [%]",
    "Return (Ann.) [%]",
    "Sharpe Ratio",
    "Sortino Ratio",
    "Max. Drawdown [%]",
    "# Trades",
    "Win Rate [%]",
    "Profit Factor",
    "Expectancy [%]",
    "Exposure Time [%]",
]


def fmt_stats(name: str, stats) -> str:
    lines = [f"### {name}", "", "| Metric | Value |", "|---|---|"]
    for k in KEEP:
        v = stats[k]
        lines.append(f"| {k} | {v:.2f} |" if isinstance(v, float) else f"| {k} | {v} |")
    lines.append("")
    return "\n".join(lines)


def main():
    raw = pd.read_csv(HERE / "data" / "solbtc_1d.csv", index_col="time", parse_dates=True)
    full = attach_signals(raw)

    split = int(len(full) * 0.7)
    is_df, oos_df = full.iloc[:split], full.iloc[split:]
    n_sig = int(full["Buy"].sum() + full["Sell"].sum())
    print(f"{len(full)} bars, {n_sig} signals | IS: {is_df.index[0].date()}..{is_df.index[-1].date()}"
          f" | OOS: {oos_df.index[0].date()}..{oos_df.index[-1].date()}")

    report = [
        "# HalfTrend [BigBeluga] on SOLBTC — daily backtest",
        "",
        f"Data: synthetic daily SOLBTC {full.index[0].date()} .. {full.index[-1].date()} "
        "(see `build_dataset.py` for sources and construction caveats). "
        f"Params: amplitude={AMPLITUDE}, channelDeviation={CHANNEL_DEV}, ATR({ATR_PERIOD})/2, "
        f"baseRiskMult={BASE_RISK_MULT}, fees {COMMISSION*100:.1f}%/side, "
        "3-tranche scale-out at 1R/2R/3R, full-position stop at 1R, reverse on opposite flip.",
        "",
    ]

    for name, df in (
        (f"In-sample (70%): {is_df.index[0].date()} .. {is_df.index[-1].date()}", is_df),
        (f"Out-of-sample (30%): {oos_df.index[0].date()} .. {oos_df.index[-1].date()}", oos_df),
        (f"Full period: {full.index[0].date()} .. {full.index[-1].date()}", full),
    ):
        stats = run(df)
        report.append(fmt_stats(name, stats))
        print(f"\n== {name}\n{stats[KEEP].to_string()}")

    # Parameter robustness sweep on the in-sample slice only
    report += ["## Robustness sweep (in-sample)", "",
               "Return % / Sharpe / #trades per (amplitude, baseRiskMult):", "",
               "| amplitude \\ riskMult | 4.0 | 6.0 | 8.0 |", "|---|---|---|---|"]
    print("\n== Robustness sweep (IS): amplitude x baseRiskMult")
    for amp in (10, 15, 20, 25, 30):
        row = [f"| {amp} |"]
        sweep = attach_signals(raw, amplitude=amp).iloc[:split]
        for rm in (4.0, 6.0, 8.0):
            s = run(sweep, risk_mult=rm)
            cell = f"{s['Return [%]']:.0f}% / {s['Sharpe Ratio']:.2f} / {s['# Trades']}"
            row.append(f" {cell} |")
            print(f"  amp={amp} riskMult={rm}: {cell}")
        report.append("".join(row))
    report.append("")

    (HERE / "RESULTS.md").write_text("\n".join(report))
    print(f"\nWrote {HERE / 'RESULTS.md'}")


if __name__ == "__main__":
    main()
