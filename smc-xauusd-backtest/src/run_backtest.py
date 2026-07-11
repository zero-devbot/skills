"""RBI backtest runner for the SMC XAUUSD strategy.

Runs, on 2 years of H1 XAUUSD data:
  1. the three entry variants (ob / sweep / both) over the full window,
  2. an in-sample (first 18 months) vs out-of-sample (last 6 months) split
     for the combined variant,
  3. a small robustness sweep over R:R and the discount filter,
and writes results/summary.md, results/trades_both.csv and equity PNGs.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from backtesting import Backtest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smc
from strategy import SmcStrategy

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "xauusd_h1_2y.csv"
RESULTS = ROOT / "results"

CASH = 100_000
COMMISSION = 0.0002   # ~ $0.6 round-trip per oz at $3000 ≈ typical spot spread
MARGIN = 0.05         # 20:1 leverage available; sizing is risk-based anyway

KEEP = ["Start", "End", "# Trades", "Return [%]", "Buy & Hold Return [%]",
        "Return (Ann.) [%]", "Max. Drawdown [%]", "Sharpe Ratio",
        "Sortino Ratio", "Win Rate [%]", "Profit Factor", "Avg. Trade [%]",
        "Expectancy [%]", "SQN"]


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA, parse_dates=["Date"], index_col="Date")
    return smc.prepare(df)


def run(df: pd.DataFrame, **params):
    bt = Backtest(df, SmcStrategy, cash=CASH, commission=COMMISSION,
                  margin=MARGIN, finalize_trades=True)
    stats = bt.run(**params)
    return bt, stats


def row(name: str, stats) -> dict:
    out = {"Variant": name}
    for k in KEEP:
        v = stats[k]
        if isinstance(v, float):
            v = round(v, 2)
        out[k] = v
    return out


def equity_png(stats, path: Path, title: str) -> None:
    eq = stats["_equity_curve"]
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 6), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]})
    ax1.plot(eq.index, eq.Equity, lw=1.2)
    ax1.set_title(title)
    ax1.set_ylabel("Equity ($)")
    ax1.grid(alpha=0.3)
    dd = eq.DrawdownPct * 100
    ax2.fill_between(eq.index, -dd, 0, alpha=0.6)
    ax2.set_ylabel("Drawdown (%)")
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> int:
    RESULTS.mkdir(exist_ok=True)
    df = load()
    print(f"H1 bars after prep: {len(df)}, {df.index[0]} -> {df.index[-1]}")

    lines = ["# SMC XAUUSD backtest results", "",
             f"Data: XAUUSD H1, {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}"
             f" ({len(df)} bars). Cash ${CASH:,}, commission {COMMISSION:.2%},"
             f" margin {MARGIN} (20:1), risk 1%/trade. Timestamps are broker"
             f" (MetaTrader) server time, assumed EET.", ""]

    # 0 --- iteration ablation: v1 (H4 bias, no BE) -> v2 (D1 bias + BE) ----
    kz = "9-12,15-18"  # ~ London & New York opens in broker (EET) server time
    ablation = [
        ("v1: H4 bias, all hours", dict(bias_tf="h4", be_at_r=0.0, sessions="")),
        ("v1 + D1 bias", dict(bias_tf="d1", be_at_r=0.0, sessions="")),
        ("v1 + breakeven@1R", dict(bias_tf="h4", be_at_r=1.0, sessions="")),
        ("v1 + D1 bias + breakeven@1R",
         dict(bias_tf="d1", be_at_r=1.0, sessions="")),
        ("v2 (best): v1 + kill zones LDN/NY",
         dict(bias_tf="h4", be_at_r=0.0, sessions=kz)),
        ("v2 + breakeven@1R", dict(bias_tf="h4", be_at_r=1.0, sessions=kz)),
    ]
    rows = []
    for name, params in ablation:
        _, stats = run(df, mode="both", **params)
        rows.append(row(name, stats))
    lines += ["## Iteration ablation (mode=both)", "",
              pd.DataFrame(rows).to_markdown(index=False), ""]

    # 0b -- iteration 3: FVG quality filter + liquidity-pool targets --------
    it3 = [
        ("v2 baseline (fixed 2R)", dict()),
        ("v2 + FVG filter", dict(require_fvg=True)),
        ("v2 + liquidity targets (min_rr=1.5, lb=100)",
         dict(tp_mode="liquidity")),
        ("v3: FVG + liquidity targets", dict(require_fvg=True,
                                             tp_mode="liquidity")),
        ("v3, min_rr=1.0", dict(require_fvg=True, tp_mode="liquidity",
                                min_rr=1.0)),
        ("v3, min_rr=2.0", dict(require_fvg=True, tp_mode="liquidity",
                                min_rr=2.0)),
        ("v3, pool lookback=48", dict(require_fvg=True, tp_mode="liquidity",
                                      liq_lookback=48)),
        ("v3, pool lookback=200", dict(require_fvg=True, tp_mode="liquidity",
                                       liq_lookback=200)),
    ]
    rows = []
    for name, params in it3:
        _, stats = run(df, mode="both", **params)
        rows.append(row(name, stats))
    lines += ["## Iteration 3: FVG filter & liquidity targets (mode=both)", "",
              pd.DataFrame(rows).to_markdown(index=False), ""]

    # 1 --- entry-mode variants, full window (v2 best-candidate params) -----
    rows = []
    for mode in ("ob", "sweep", "both"):
        bt, stats = run(df, mode=mode)
        rows.append(row(mode, stats))
        equity_png(stats, RESULTS / f"equity_{mode}.png",
                   f"SMC XAUUSD H1 — mode={mode} (H4 bias, kill zones)")
        if mode == "both":
            trades = stats["_trades"]
            trades.to_csv(RESULTS / "trades_both.csv", index=False)
    full = pd.DataFrame(rows)
    lines += ["## Entry-mode variants, v2 best-candidate params (full 2 years)",
              "", full.to_markdown(index=False), ""]

    # per-signal breakdown for the combined run
    trades = pd.read_csv(RESULTS / "trades_both.csv")
    if "Tag" in trades:
        grp = trades.groupby("Tag").agg(
            n=("PnL", "size"), win_rate=("PnL", lambda s: (s > 0).mean() * 100),
            total_pnl=("PnL", "sum"), avg_pnl=("PnL", "mean")).round(2)
        lines += ["### Combined run, by signal type", "",
                  grp.to_markdown(), ""]

    # 2 --- in-sample / out-of-sample split --------------------------------
    split = df.index[0] + pd.DateOffset(months=18)
    rows = []
    for cfg_name, cfg in (("fixed 2R", {}),
                          ("liquidity targets", {"tp_mode": "liquidity"})):
        for name, part in (("in-sample (18mo)", df.loc[:split]),
                           ("out-of-sample (6mo)", df.loc[split:])):
            _, stats = run(part, mode="both", **cfg)
            rows.append(row(f"{cfg_name}, {name}", stats))
    lines += ["## In-sample vs out-of-sample (mode=both)", "",
              pd.DataFrame(rows).to_markdown(index=False), ""]

    # equity chart + trade log for the liquidity-target variant
    _, stats = run(df, mode="both", tp_mode="liquidity")
    equity_png(stats, RESULTS / "equity_liq_targets.png",
               "SMC XAUUSD H1 — liquidity targets (H4 bias, kill zones)")
    stats["_trades"].to_csv(RESULTS / "trades_liq_targets.csv", index=False)

    # 3 --- robustness sweep ------------------------------------------------
    rows = []
    for rr in (1.5, 2.0, 2.5, 3.0):
        for pdf in (True, False):
            _, stats = run(df, mode="both", rr=rr, use_pd_filter=pdf)
            r = row(f"rr={rr}, pd_filter={pdf}", stats)
            rows.append(r)
    lines += ["## Robustness sweep (mode=both)", "",
              pd.DataFrame(rows).to_markdown(index=False), ""]

    (RESULTS / "summary.md").write_text("\n".join(lines))
    print(f"wrote {RESULTS / 'summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
