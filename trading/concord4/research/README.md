# CONCORD-4 research harness (RBI stage 2)

Backtest and validation for the CONCORD-4 system before it touches a live account.
Mirrors the MQL5 implementation in `../Include/Concord4Core.mqh` closely enough that a
disagreement between the two is a bug worth chasing, not a platform quirk to shrug at.

```
research/
  c4/indicators.py   Wilder ATR and SMA-seeded EMA, matched to MT5's built-ins
  c4/data.py         CSV loading, resampling, Dukascopy ticks, synthetic generator
  c4/gates.py        the four gates - the as-of contract lives here
  c4/engine.py       event-driven execution, sizing, exits, circuit breakers
  c4/metrics.py      Sharpe, profit factor, R-multiples, drawdown
  c4/validate.py     IS/OOS, walk-forward, parameter sweeps, Monte Carlo
  fetch_data.py      Dukascopy downloader -> CSV
  run_backtest.py    CLI
  tests/test_c4.py   18 tests, including the look-ahead check
```

## Why not `backtesting.py`

The L2 gate needs six additional symbols, positions close in two legs, and every
higher-timeframe read has to respect the as-of contract below. A single-asset
vectorised framework fights all three. Parity with the EA is the only reason this
harness exists, so the engine is a plain event loop that can be read side by side
with `Concord4EA.mq5`.

## Quick start

```bash
pip install -r requirements.txt

python run_backtest.py --synthetic --mode all      # prove the plumbing works
python fetch_data.py --start 2015-01-01 --end 2026-01-01 --out data/
python run_backtest.py --data-dir data/ --mode all --split 2022-01-01
python tests/test_c4.py
```

`--mode` selects `gates`, `single`, `oos`, `sweep`, `walkforward`, `montecarlo`, or `all`.

## The as-of contract

This is the part that makes or breaks a backtest of a multi-timeframe system.

Every higher-timeframe value attached to an M15 bar comes from a bar that had **fully
closed** by that M15 bar's own close. `gates.asof_align` is the single place this is
enforced — the Python twin of `C4ClosedShift` in the MQL5 core. It joins on the
higher-timeframe bar's *close* time, not its open, so a decision at 07:30 sees the H1
bar that closed at 07:00 and not the one still forming.

`test_no_lookahead` recomputes every gate on a dataset truncated at 75% and asserts the
last 200 bars are byte-identical to the full-history run. If that test ever fails, every
number this harness produces is fiction. Route any new data source through `asof_align`.

## What the engine assumes, and which way it errs

All of these are chosen to err against the strategy:

- Signals compute on a closed M15 bar; the fill is the **next bar's open**, which is
  where the EA's first post-close tick actually lands.
- Prices are treated as mid. Every fill pays **half the spread plus slippage**,
  adversely, on entry and exit — a round turn costs one full spread plus two slippages.
- When one bar contains both the stop and the +1R target, the **stop is assumed first**.
  `--pessimistic-intrabar` is on by default; `test_pessimistic_ordering_prefers_the_stop`
  pins the behaviour.
- A partial that moves the stop to breakeven can still be stopped out **in the same bar**.
- Position size is the smaller of fixed-fractional risk and the volatility target, then
  floored to the broker's lot step. If that lands below the minimum lot, the trade is
  **skipped rather than rounded up**.
- Drawdown is measured on **mark-to-market** equity, so open positions count.

## Reading the output

**Gate report.** Every rejection reason is broken out separately. If a real dataset
produces no trades, this tells you which gate to look at rather than leaving you
guessing.

**Sweep.** Read the `plateau` column, not the peak. Several rows near 1.0 is a shelf; one
row near 1.0 with low neighbours is a curve fit. When no parameter value reaches a
positive metric the score is withheld rather than printed as noise — there is no good
region to be on a shelf of.

**Walk-forward.** Each fold picks the best parameter on 12 months of training and reports
what that choice earned on the untouched 6-month test window. The mean of the *test*
column is the only honest estimate of live performance here.

**Monte Carlo.** The backtest's max drawdown is one sample. Bootstrapping the trade order
5,000 times shows what else that same edge could plausibly have done — usually a good
deal worse than the single path you happened to observe. Size against the p95, not the p50.

## Sanity check the harness passes

Run on synthetic geometric Brownian motion — which has no edge by construction — the
engine returns roughly **−0.1R expectancy**, a profit factor slightly under 1, and a
Sharpe near zero. That is exactly what a random walk minus costs should produce. A
harness that manufactured an edge from random data would be worthless, so this is the
first thing to re-check after any change to the engine.

## A finding from building this

The L0 spread gate (`max_spread_atr = 0.06`) may be **too tight for real XAUUSD on a
standard account**. Gold's M15 ATR runs around 2.5–3.5 price units at current levels, so
the gate permits roughly 0.15–0.20 of spread. Raw/ECN gold spreads (0.10–0.20) pass;
standard-account spreads (0.25–0.40) would be blocked almost permanently and the system
would simply never trade.

Check the gate report before concluding the strategy is broken, and sweep the threshold
against your own broker's spreads:

```bash
python run_backtest.py --data-dir data/ --mode gates
python run_backtest.py --data-dir data/ --mode sweep --sweep-param max_spread_atr \
    --sweep-values 0.04,0.06,0.08,0.10,0.15
```

Loosening it is a real trade-off, not a free win: the gate exists to keep the system out
of the illiquid moments where breakouts fail and slippage is worst.

## Limitations

- **The Dukascopy fetcher is unverified against live data.** The sandbox this was written
  in blocks `datafeed.dukascopy.com` at the proxy (403), so the download path has never
  run end to end. The bi5 decoder follows the documented 20-byte record format
  (`>IIIff`: millisecond offset, ask, bid, ask volume, bid volume) but treat the first
  download as something to verify, not trust. If it fails, export the same CSVs from
  MT5's History Centre instead — the harness only needs `time,open,high,low,close` plus
  optional `tick_volume` and `spread`.
- **The news filter needs a calendar you supply.** Pass `--news-csv` with a `time` column
  of high-impact events. Without it the filter is inert, and the backtest is then *not*
  the same system as the EA, which reads MT5's built-in calendar.
- **M15 bars, not ticks.** Intrabar fills are modelled by the rules above rather than
  simulated. For a breakout system whose stop and target can share a bar, that
  assumption matters — which is why it defaults to the pessimistic branch.
- **Single symbol.** The correlation cap in the design applies once a second instrument
  is added; today the engine holds at most one position.
- **Synthetic data proves plumbing, never edge.** Any performance figure computed from
  `--synthetic` describes the random number generator.
