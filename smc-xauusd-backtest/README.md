# SMC XAUUSD Strategy — an RBI Study

A Smart Money Concepts (SMC) trading strategy for gold (XAU/USD), built and
evaluated with the **RBI framework — Research, Backtest, Implement**: research
a strategy idea, encode it exactly and backtest it against realistic costs,
and only implement (trade) it if the backtest earns that right.

**Verdict: rejected at the Backtest gate.** Across three iterations, no
configuration shows a real edge over the 2-year window (June 2023 – June
2025) in which simply holding gold returned +71%. Fixed-R exits lose −19% to
−71%; the best refinement (liquidity-pool targets, iteration 3) reaches
+12% over the full window but the gain is entirely in-sample (+15.8% IS,
−3.0% OOS, profit factor ≈ 1, −32% max drawdown, and it flips negative if
the pool lookback changes). The strategy as specified must not be traded
live. That is the RBI framework doing its job: the backtest killed the idea
before real money did.

---

## 1. Research

### Hypothesis

Institutional order flow leaves footprints on price: impulsive breaks of
structure originate from zones of resting orders (order blocks), and moves
often begin by sweeping obvious liquidity (stops under swing lows / above
swing highs). Trading retests of those zones in the direction of
higher-timeframe structure, during London/New York opens, should produce
asymmetric R:R entries.

### Concepts encoded (all causally, no lookahead)

| Concept | Definition used |
|---|---|
| Swing high/low | Strict local extreme with k=3 bars each side (H1); only usable k bars after it prints |
| Break of structure (BOS) / CHoCH | H1/H4/D1 close through the last confirmed swing high (bullish) or low (bearish) |
| HTF bias | Direction of the last BOS/CHoCH on H4 (or D1), applied to H1 bars only after the HTF candle closes |
| Order block (OB) | Last opposing candle before a BOS impulse; entry = limit at zone edge on retest |
| Liquidity sweep | Bar wicks through the last confirmed swing low/high but closes back inside; entry at market |
| Premium/discount | OB longs only below the 50% level of the current dealing range (shorts mirrored) |
| Kill zones | New entries only during London/NY opens (server hours 9–12 and 15–18, EET) |
| Fair value gap (FVG) | 3-candle gap (`low[m+1] > high[m-1]`) inside the BOS impulse; optional OB quality filter |
| Liquidity target | Optional TP just in front of the opposing pool (highest high / lowest low of last 100 bars), skipping trades paying < 1.5R |

Risk model: 1% of equity per trade, stop beyond the invalidation level plus a
0.25×ATR buffer, fixed take-profit in R multiples (default 2R), pending
orders expire after 48 bars, positions close if the HTF bias flips (CHoCH).

## 2. Backtest

### Data

- XAUUSD H1 candles, 2023-06-06 → 2025-06-06 (11,853 bars), MetaTrader
  export from the auto-updated
  [FeziweMelvin/XAUUSD-Gold-Price](https://github.com/FeziweMelvin/XAUUSD-Gold-Price)
  dataset (columns validated for OHLC sanity; see `src/download_data.py`).
- This is the most recent 2-year window that dataset provides (its updates
  stop at 2025-06-06). Live sources (Yahoo Finance, Stooq, Binance, etc.)
  were unreachable from this build environment's network policy, so the
  window ends there rather than at today's date. `src/download_data.py
  --source yahoo` re-pulls a current window when run somewhere with open
  network access.
- Engine: [backtesting.py](https://kernc.github.io/backtesting.py/), cash
  $100k, commission 0.02% per side (≈ spot spread), 20:1 margin available,
  risk-based position sizing.

### Results (full window, mode = OB + sweeps unless noted)

| Configuration | Trades | Return | Win rate | Profit factor | Max DD |
|---|---|---|---|---|---|
| v1: H4 bias, all hours | 261 | −40.8% | 33.7% | 0.81 | −42.0% |
| v1 + D1 bias | 309 | −71.0% | 27.2% | 0.58 | −71.2% |
| v1 + breakeven @1R | 281 | −36.8% | 24.9% | 0.84 | −36.8% |
| **v2: v1 + kill zones** | 233 | **−19.4%** | 37.3% | 0.86 | −24.9% |
| v2, OB entries only | 163 | −8.7% | 39.9% | 0.84 | −17.6% |
| v2 + FVG filter (iter. 3) | 217 | −23.2% | 36.9% | 0.83 | −32.3% |
| v2 + liquidity targets (iter. 3) | 199 | +12.3% | 28.1% | 0.98 | −31.8% |
| v3: FVG + liquidity targets | 187 | −15.3% | 26.7% | 0.86 | −46.5% |
| Buy & hold | — | **+71.6%** | — | — | — |

Full tables — entry-mode variants, in-sample (18 mo) vs out-of-sample (6 mo)
split, and a robustness sweep over R:R × discount filter — are in
[`results/summary.md`](results/summary.md); equity/drawdown charts in
`results/equity_*.png`, full trade log in `results/trades_both.csv`.

### What the iteration showed

- **Kill zones were the only change that materially helped** (−41% → −19%):
  off-session OB retests and Asian-session sweeps were mostly noise fills.
- **Slower (D1) bias made things worse**, not better — it kept the system
  shorting corrections inside a bull market for weeks at a time, and removed
  the H4 CHoCH exit that had been cutting losers early.
- **The discount/premium filter consistently helped** across the whole
  R:R sweep; requiring entries at favorable range position is real, just not
  sufficient.
- **Mechanics were validated, edge was not.** Losses cluster at −1.1R
  (−1R plus costs; worst ≈ −1.9R from same-bar gaps through sweep stops,
  which is honest market behavior), wins cap at ≈ +1.8R net. That payoff
  needs a ~39% win rate to break even; the entries deliver 26–37%. Even
  long-only trades during the strongest bull leg (Jan–Apr 2025) summed to
  −1.8R over 38 trades — the entry signal adds nothing over noise there.
- The out-of-sample slice (58 trades, PF 1.13) is the only positive cell and
  is far too small to outweigh everything else.

Iteration 3 (requested follow-up) tested the two directions flagged above:

- **FVG quality filter: rejected.** Requiring a fair value gap inside the
  OB's impulse leg made every combination worse (v2 −19.4% → −23.2%; with
  liquidity targets +12.3% → −15.3%). On H1 gold, most structure breaks
  print an FVG anyway, so the filter mainly discards decent zones from
  steadier legs while keeping the same losers.
- **Liquidity-pool targets: the most promising change so far, but not an
  edge.** Targeting the opposing pool instead of a fixed 2R (median planned
  payoff ≈ 4R in this trending market) is the only configuration that goes
  positive over the full window (+12.3%). It does not survive scrutiny:
  the profit is entirely in-sample (+15.8% IS vs −3.0% OOS on 52 trades),
  profit factor stays ≈ 1, max drawdown deepens to −32% (28% win rate means
  long losing streaks), and shrinking the pool lookback from 100 to 48 bars
  flips it to −25.4%. Two positive cells surrounded by deep negatives is
  the signature of noise, not signal.

### Verdict

Naive-but-faithful SMC (structure bias + OB retest + liquidity sweeps +
discount filter + kill zones) on XAUUSD H1 is **not tradeable**, with fixed-R
or liquidity-based exits alike: no configuration shows an edge that survives
out-of-sample validation and parameter perturbation. Reject.

## 3. Implement

Not reached — the backtest gate failed, so no live/paper deployment. The
pre-registered promotion criteria were: profit factor > 1.3 and positive
expectancy on both IS and OOS, max drawdown < 20%, ≥ 100 OOS trades, then a
3-month demo-account forward test before any real size.

If you want to keep researching: FVG filters and liquidity targets have now
been tested (iteration 3 — the former rejected, the latter promising but
unconfirmed). The remaining untested directions are higher-timeframe entry
zones (H4 OBs with H1 execution), volatility-regime filters, walk-forward
optimization instead of a single split, and — most importantly for the
liquidity-target variant — more data: regime diversity beyond one strong
bull market is what this 2-year window fundamentally lacks.

## Repository layout / how to run

```
smc-xauusd-backtest/
├── data/                 # committed 2-year H1 + D1 CSVs (reproducible runs)
├── results/              # summary.md, equity PNGs, trade log
└── src/
    ├── download_data.py  # fetch + validate + slice the dataset
    ├── smc.py            # causal SMC primitives (swings, structure bias, ATR)
    ├── strategy.py       # backtesting.py Strategy (OB / sweep / both)
    └── run_backtest.py   # full RBI suite -> results/
```

```bash
pip install -r requirements.txt
python src/download_data.py     # optional; data/ is already committed
python src/run_backtest.py
```

## Disclaimer

Educational backtest only — not financial advice. Past (simulated)
performance does not predict future results; the simulation ignores swap,
variable spreads, and slippage beyond the fixed commission.
