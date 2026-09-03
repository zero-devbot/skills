# CONCORD-4

A hybrid multi-confirmation breakout system for **XAUUSD on M15**, built as an MQL5
indicator plus an Expert Advisor that share one implementation of the entry logic.

The design goal was minimum drawdown, not maximum return. Every component was chosen
because it either (a) has published evidence behind it, or (b) removes trades rather
than adding them.

---

## Why four gates, and why these four

Most retail "confluence" systems stack RSI + Stochastic + MACD + a moving average.
Those are all deterministic transforms of the same close series — they are close to
collinear, so stacking them raises the win rate a little while cutting the trade count
a lot. That is a worse Sharpe ratio, not a better one.

CONCORD-4 draws its four gates from four genuinely different information sources:

| Gate | Question | Source | Shares data with |
|------|----------|--------|------------------|
| **L0** Tradability | Is this a moment worth trading at all? | Clock, spread, economic calendar, ATR percentile | nothing |
| **L1** Regime | Which way is the instrument biased? | XAUUSD **D1**, 50–63 day horizon | L3, at ~200× the horizon |
| **L2** Intermarket | Does the dollar agree? | **Other symbols** — a synthetic USD basket | nothing |
| **L3** Trigger | Is something happening right now? | XAUUSD **M15** structure + tick volume | L1, at ~200× the horizon |

All four must agree before a trade exists. L1 and L3 are the only pair sharing a price
series, and they look at it across horizons two orders of magnitude apart.

### Evidence behind each choice

- **L3 opening-range breakout** — Zarattini & Aziz report 19.6% annualised, Sharpe 1.33
  net of costs on SPY 2007–2024, with a hit rate of only ~43%: the edge is convexity,
  not accuracy. Independently replicated on QuantConnect.
- **L1 time-series momentum** — Moskowitz, Ooi & Pedersen document it across 58 futures
  including currencies and commodities over 25+ years, performing best in extreme markets.
- **L0 session timing** — realised volatility in metals peaks at the Tokyo, London and
  New York opens, and the London–NY overlap (13:00–16:00 UTC) is the deepest liquidity
  window. The volatility clustering is documented; profitability claims built on it
  generally are not.
- **Volatility targeting in sizing** — improves Sharpe by roughly 20–30% and robustly
  reduces maximum drawdown and tail risk.
- **L2 intermarket** — gold is USD-denominated and carries a persistent negative beta to
  the dollar. This is the only gate whose data is not a transform of the traded series.

### What was deliberately left out

- **Grid / martingale** — formalised as a stochastic process, unconstrained operation
  reaches ruin with probability 1. Directly opposed to the objective here.
- **Moving-average crossovers on FX** — Neely & Weller show risk-adjusted profits fell
  from >3% in the late 1970s–80s to roughly zero by the 1990s–2000s.
- **Ichimoku** — a peer-reviewed 2003–2018 study across four indices and four majors
  found no consistently profitable currency configuration under any parameter set.
- **Order blocks / liquidity sweeps** — no rigorous public evidence, and too loosely
  defined to automate deterministically. The one replicated piece of that literature,
  order clustering at round numbers, *is* used: it is why entries carry an ATR buffer
  beyond the range edge rather than sitting on it.
- **Carry** — real academically (Sharpe ~0.6–0.8) but skewed −0.5 to −1.0, and the edge
  is largely consumed by retail swap markups.

---

## Files

```
Include/Concord4Core.mqh    all four gates, shared by both programs
Indicators/Concord4.mq5     gate visualiser + status panel, non-repainting
Experts/Concord4EA.mq5      execution and risk engine
```

The EA does not read the indicator via `iCustom`. Both `#include` the same core, so an
arrow on the chart is by construction the same decision the EA takes.

### Install

Copy into your MT5 data folder (**File → Open Data Folder**):

```
MQL5/Include/Concord4Core.mqh
MQL5/Indicators/Concord4.mq5
MQL5/Experts/Concord4EA.mq5
```

Compile both `.mq5` files in MetaEditor (F7), then attach to an **M15 XAUUSD** chart.
EURUSD, GBPUSD, USDJPY, USDCAD, USDCHF and AUDUSD must be visible in Market Watch —
the L2 basket needs at least three of them or it fails closed and no trade is taken.

---

## The rules

**L0 — tradability.** Entries only in 07:00–11:00 and 13:00–16:00 UTC. Spread must be
≤ 6% of ATR(M15). ATR(D1) must sit between the 20th and 90th percentile of its own
trailing 250-day distribution — below that, breakouts are noise; above it, stops get run.
No entries within ±15 minutes of a high-impact USD/EUR/GBP calendar event.

**L1 — regime.** Long bias requires *both* Close(D1) > EMA(D1,50) *and* a positive
63-day return. Short bias requires both to be negative. Disagreement means the day is
flat. There are no counter-trend trades. This is the single largest drawdown reducer
in the system.

**L2 — intermarket.** A log-weighted synthetic USD index (DXY-shaped weights,
renormalised over whatever legs the broker offers) computed on H1. A falling 20-period
EMA permits longs, a rising one permits shorts.

**L3 — trigger.** The opening range is 07:00–07:30 UTC. A signal needs an M15 close
beyond the range edge by 0.15 × ATR(M15), on a bar whose range is ≥ 0.8 × ATR *and*
whose tick volume is ≥ 1.5× its 20-bar average. Vetoed if the range is already wider
than 1.2 × ADR(20), or if price has run more than 2 × ATR past the edge.

**Stop.** Structural first — just beyond the opposite range edge — but never tighter
than 1.5 × ATR and never wider than 2.0 × ATR. If structure demands more than the cap,
the trade is skipped rather than sized down.

**Size.** The smaller of 0.5% equity at the stop and a 10% annualised volatility target.
Taking the smaller is what makes position size shrink automatically as gold's ATR
expands.

**Exits.** 50% off at +1R, stop to breakeven plus costs, then a Chandelier trail at
2.8 × ATR(H1) on the remainder. Everything is flat by 20:00 UTC — this sleeve does not
hold overnight, which removes gap risk entirely.

**Circuit breakers.** Max 2 entries per UTC day. Halt for the day at −2R realised, for
the rolling week at −4R. An 8% equity drawdown from peak halves position size until a
new equity high. These anchors persist in terminal global variables, so restarting the
EA does not silently reset a breaker that has already tripped.

---

## Expected profile — read this before backtesting

Win rate **40–48%**, average win/loss **1.8–2.5R**, profit factor **1.3–1.6**, net
Sharpe **0.8–1.3**, max drawdown target **<10%** at 0.5% risk, roughly **1.5–4 trades
per week**.

If your backtest returns a 75% win rate and a profit factor above 3, treat it as a bug
report, not a result. The most likely causes are an unrealistic spread model, a broken
GMT offset, or missing tick data.

---

## Validation protocol

1. **Data.** M1 from 2015 onward. Ideally cross-check broker history against a second
   source (Dukascopy ticks) — broker-specific artifacts are common in gold.
2. **Costs.** Variable spread (gold widens sharply at 07:00 and around news),
   commission, and slippage of roughly 0.3 × spread on market orders.
3. **Split.** In-sample 2015–2021. Touch the 2022-onward out-of-sample window *once*.
4. **Robustness.** Sweep `InpBreakoutAtrK`, `InpStopMinAtr` and `InpOrLengthMin`. You are
   looking for a **plateau**. A spike is a curve fit — reject it.
5. **Walk-forward.** 12 months train, 6 months test, rolling.
6. **Monte Carlo.** Reshuffle the trade sequence to get a *distribution* of maximum
   drawdown. A single backtest's max DD is one draw from that distribution, not the truth.
7. **Tester settings.** "Every tick based on real ticks", check the model quality, then
   re-run everything with spread × 1.5.

Run with `InpDryRun = true` first: it logs every signal and every rejection reason
without sending orders.

---

## Known limitations — all of them

- **Not yet compiled or backtested.** This code was written without access to MetaEditor
  or a terminal. It is structurally checked but unverified: compile it, fix whatever
  MetaEditor reports, and run it in the tester before it sees an order.
- **GMT offset is the biggest silent failure mode.** Every session boundary is specified
  in UTC and converted using the broker's offset. Auto-detection snaps
  `TimeCurrent() - TimeGMT()` to the nearest half hour, which is unreliable across
  historical DST transitions in the tester. Check the offset the EA prints on init
  against your broker's actual server time, and set `InpGmtMode = Manual` if it is wrong.
  A one-hour error moves the entire opening range and invalidates the results.
- **Calendar in the tester.** If `CalendarValueHistory` is unavailable, the news filter
  disables itself and says so loudly in the journal. A backtest without it is not the
  same system as the live one — check for that warning before trusting any result.
- **Tick volume is a proxy** for real volume. It correlates well with true volume in FX
  and metals, but it is broker-specific, so the 1.5× threshold may need re-fitting per
  broker.
- **ATR(D1) stands in for daily sigma** in the volatility target, overstating it by
  roughly 20–40%. Realised volatility therefore lands *below* the nominal 10% target —
  deliberately the conservative direction, but it means the number is not literal.
- **Single symbol.** The correlation cap described in the design matters only once a
  second instrument is added; today the EA holds at most one position.
- **The mean-reversion sleeve is not built.** Deferred to v2 by design.

---

## Sources

- [Zarattini & Aziz — A Profitable Day Trading Strategy For The U.S. Equity Market](https://concretumgroup.com/a-profitable-day-trading-strategy-for-the-u-s-equity-market/)
- [QuantConnect — Opening Range Breakout for Stocks in Play](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/)
- [Moskowitz, Ooi & Pedersen — Time Series Momentum](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf)
- [Neely & Weller — Technical Analysis in the Foreign Exchange Market](https://files.stlouisfed.org/files/htdocs/wp/2011/2011-001.pdf)
- [The profitability of Ichimoku Kinkohyo based trading rules](https://econpapers.repec.org/RePEc:wly:ijfiec:v:26:y:2021:i:4:p:5321-5336)
- [Brunnermeier, Nagel & Pedersen — Carry Trades and Currency Crashes](https://www.princeton.edu/~markus/research/papers/carry_trades_currency_crashes_old.pdf)
- [Intraday seasonality in efficiency, liquidity, volatility and volume (metals)](https://www.sciencedirect.com/science/article/abs/pii/S2405851318300102)
- [Alpha Architect — Volatility Targeting Improves Risk-Adjusted Returns](https://alphaarchitect.com/volatility-targeting-improves-risk-adjusted-returns/)
- [Building a Research-Grounded Grid EA in MQL5 (ruin analysis)](https://www.mql5.com/en/articles/21833)

---

## Disclaimer

Research and engineering material, not financial advice. Trading leveraged instruments
risks loss of capital. Forward-test on a demo account before risking real money.
