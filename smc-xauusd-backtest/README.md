# SMC XAUUSD Strategy — an RBI Study

A Smart Money Concepts (SMC) trading strategy for gold (XAU/USD), built and
evaluated with the **RBI framework — Research, Backtest, Implement**: research
a strategy idea, encode it exactly and backtest it against realistic costs,
and only implement (trade) it if the backtest earns that right.

**Verdict: rejected at the Backtest gate.** Every tested configuration lost
money over the 2-year window (June 2023 – June 2025) in which simply holding
gold returned +71%. The best variant lost −8.7% (profit factor 0.84). The
strategy as specified has no edge on XAUUSD H1 and must not be traded live.
That is the RBI framework doing its job: the backtest killed the idea before
real money did.

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

### Verdict

Naive-but-faithful SMC (structure bias + OB retest + liquidity sweeps +
discount filter + kill zones) on XAUUSD H1 is **not tradeable**: profit
factor < 1 everywhere, underwater vs both zero and buy-and-hold. Reject.

## 3. Implement

Not reached — the backtest gate failed, so no live/paper deployment. The
pre-registered promotion criteria were: profit factor > 1.3 and positive
expectancy on both IS and OOS, max drawdown < 20%, ≥ 100 OOS trades, then a
3-month demo-account forward test before any real size.

If you want to keep researching, the highest-value directions suggested by
the failure mode (low win rate at fixed 2R): displacement/FVG quality filters
on the impulse leg, targeting opposing liquidity instead of fixed R,
higher-timeframe entry zones (H4 OBs, H1 execution), volatility-regime
filters, and walk-forward optimization instead of a single split.

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
