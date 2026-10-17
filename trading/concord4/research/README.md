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
  c4/parity.py       diff the terminal's gate output against Python's
  c4/plots.py        tearsheet: equity curve, underwater drawdown, distributions
  c4/audit.py        data quality checks, run before anything is computed
  fetch_data.py      Dukascopy downloader -> CSV
  run_protocol.py    the whole validation protocol in one command
  run_backtest.py    backtest CLI
  check_parity.py    parity CLI
  tests/test_c4.py   37 tests, including the look-ahead and parity checks
```

`numpy` and `pandas` are required. `matplotlib` is needed only for `--plot` and
`requests` only for `fetch_data.py`; everything that produces numbers runs without
either.

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
python tests/test_c4.py
python check_parity.py --self-test                 # validate the parity comparer
```

Then, once you have data:

```bash
python run_protocol.py --data-dir data/ --server-offset 3 --out results/
```

That is the whole protocol — audit, gates, full sample, in/out-of-sample, three
parameter sweeps, walk-forward, Monte Carlo, spread stress — writing `REPORT.md`,
both tearsheets and the underlying CSVs. It exits 0 when every check passes, 1 on
warnings, and **2 when the data audit fails, without computing anything downstream**.

The individual stages remain available through `run_backtest.py --mode`
(`gates`, `single`, `oos`, `sweep`, `walkforward`, `montecarlo`, `all`).

## Getting data

`fetch_data.py` pulls Dukascopy ticks, but many networks block
`datafeed.dukascopy.com`. The fallback needs no third party: **export it from
MetaTrader itself** (Tools → History Centre, or right-click a chart → Save As),
one file per symbol named `XAUUSD.csv`, `EURUSD.csv` and so on. The loader reads
that format directly — tab separated, angle-bracket headers, `<DATE>`/`<TIME>`
split across two columns.

**`--server-offset` is the argument to get right.** MetaTrader exports in the
*broker's server time*, not UTC, and every session boundary in this system is
specified in UTC. Loading a UTC+3 broker's export without saying so shifts the
opening range by three hours and silently invalidates everything downstream —
nothing in the output will look wrong. The EA prints the offset it resolved on
init; use that number. The audit's Saturday-bar check will often catch a badly
wrong offset, but it cannot catch a plausible one.

You need the traded symbol plus at least three of the six USD-basket legs
(EURUSD, USDJPY, GBPUSD, USDCAD, USDCHF, AUDUSD) or L2 fails closed and no trade
is ever taken.

## Data audit

Synthetic data is clean by construction; broker history is not. The audit runs
before anything is computed and checks OHLC integrity, index sanity, intra-week
gaps (separating a feed outage from a weekend), multi-day breaks, Saturday bars,
flat bars, bad ticks, spread sanity, and per-year coverage. A `FAIL` stops the
protocol rather than producing a confident-looking number from broken input.

It also reports **what share of bars the L0 spread gate would block on your
feed** — the single most useful line when a run comes back with no trades.

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

## Tearsheets

```bash
python run_backtest.py --data-dir data/ --plot tearsheet.png
python run_backtest.py --data-dir data/ --plot sheet.png --plot-theme both --plot-log
python run_backtest.py --data-dir data/ --save-equity equity.csv --save-trades trades.csv
```

Four panels under a strip of hero numbers:

| Panel | What it answers |
|---|---|
| **Equity curve** | marked to market, with the worst peak-to-trough span shaded and labelled |
| **Underwater** | how far below the running peak, and for how long — the drawdown *duration* a single max-DD number hides |
| **R-multiple distribution** | is the edge convexity or accuracy? Losses and wins as opposite poles |
| **Bootstrapped max drawdown** | the observed drawdown against the p95 of 2,000 reshuffled paths |

`--plot-theme both` writes `sheet.png` and `sheet-dark.png`. Dark mode is a
selected set of steps for the dark surface, not an inversion of the light one.

Some deliberate choices, so a later edit does not undo them by accident:

- **Equity and drawdown are stacked panels sharing one x axis, never one plot with
  two y scales.** A dual-axis chart invents a correlation out of the arbitrary
  alignment of its two scales.
- **Colours come from a validated palette** (blue slot 1 for equity, red slot 8 for
  loss). The two only share a plot in the R histogram, where they encode polarity;
  that pair clears the colourblind separation floor in both modes (CVD ΔE 21.6
  light / 19.2 dark against a floor of 8), so the split is readable without relying
  on hue.
- **In-plot reference lines use muted ink, not the axis token.** A spine may recede
  at the edge of a plot; a line *inside* it carrying meaning — zero drawdown,
  starting equity, zero R — may not. A test pins the contrast in both themes.
- **Labels are selective**: the endpoint, the extreme, the thresholds that carry a
  decision. A number on every point goes unread.

A PNG cannot carry a tooltip, so the numbers behind every panel stay reachable:
`--save-equity` writes the equity and drawdown series, `--save-trades` the trade
list.

## Parity harness

Two implementations of the same gates will drift apart. This finds it.

```
# 1. in MT5: attach Scripts/Concord4Export.mq5 to an M15 XAUUSD chart, run it
# 2. copy MQL5/Files/concord4_mt5_export.csv next to this README
python check_parity.py --mt5-csv concord4_mt5_export.csv
python check_parity.py --mt5-csv concord4_mt5_export.csv --mode recompute --majors-dir data/
```

The export is **self-contained**: the bars the terminal used, the
higher-timeframe values it derived from them, and the resulting gates. That
matters, because three different problems look identical in a naive diff:

| | cause | which mode exposes it |
|---|---|---|
| 1 | different bars — broker history vs. your CSV | `recompute` only |
| 2 | different HTF values — server-time D1 boundaries vs. UTC days | `recompute` only |
| 3 | different logic — a real bug in one implementation | **both** |

- **`inject` (default)** feeds the terminal's own higher-timeframe values into
  Python through `build_features(htf_override=...)`, so only the gate **logic** is
  under test. A mismatch here is a genuine bug.
- **`recompute`** derives everything from the exported bars, using the broker's day
  boundaries (`resample_server_days`). A mismatch here but not in `inject` points at
  data depth or timeframe construction.

Run `inject` first. There is no point hunting a logic bug that is really a timezone.

Crucially, inject mode exercises *the same* `build_features` the backtest uses — the
override replaces inputs, not logic. A parity harness that reimplemented the gates
would only prove two copies agree.

The report gives per-gate match rates, float deviations with tolerances, a
signal-set comparison (which bars actually traded, and which side was alone), the
terminal's own indicator-vs-core cross-check read back via `iCustom`, and the first
dozen disagreements with the values that drove them. It exits 0 on PASS, 1 on
WARN/FAIL and 2 if nothing could be compared, so it can gate a commit.

`--self-test` needs no terminal: it dresses a Python run up as an export and asserts
a clean round trip is PASS, that 25 flipped gate values are caught, and that
inverting every gate grades FAIL. If that fails, the comparer cannot be trusted to
judge the real thing.

### Precision is part of parity

MT5 computes its opening range from bars already rounded to the instrument's digits.
A CSV carrying more precision than the broker's bars will not reproduce its
decisions — a sub-cent difference in the OR edge flips any breakout sitting on the
threshold. Round your data to the instrument's precision before deriving anything.
This is not hypothetical: it is what the parity self-test caught on its first run.

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
what that choice earned on the untouched 6-month test window.

Read the **mean over qualifying folds**, not the naive mean. A fold holding one or two
trades produces a Sharpe with no information in it, and a handful of those will happily
report a strong average on data with no edge at all — on the synthetic fixture the naive
mean came out at **0.97** while every single fold was below the 10-trade threshold. The
`qualifies` column marks which folds carry any weight, and the protocol warns when none
of them do.

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
- **The parity harness has never seen a real MT5 export.** No terminal was available
  here, so it has only been validated against its own synthetic round trip. The export
  format and the comparer agree with each other by construction; whether
  `Concord4Export.mq5` compiles and produces that format is the first thing to check.
- **The `iCustom` cross-check assumes indicator defaults.** `Concord4Export.mq5` calls
  `iCustom(_Symbol, PERIOD_M15, "Concord4")` with no parameter overrides, so the `ic_*`
  columns are only meaningful while the script's inputs match the indicator's own
  defaults. Change one and that column compares two different configurations.
- **Synthetic data proves plumbing, never edge.** Any performance figure computed from
  `--synthetic` describes the random number generator.
