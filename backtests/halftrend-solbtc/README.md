# HalfTrend [BigBeluga] → Python port + SOLBTC backtest

Python translation of the TradingView Pine v6 indicator "HalfTrend Long/Short
Signal Engine [BigBeluga]" and a daily SOLBTC backtest of its long/short
flip signals with the script's own risk model (SL at `baseRiskMult * ATR(100)/2`
from entry, three scale-out TPs at 1R/2R/3R, reverse on opposite flip).

## Files

- `halftrend.py` — faithful port of the indicator state machine (trend flips,
  baseline, ATR bands, buy/sell signals).
- `build_dataset.py` — constructs `data/solbtc_1d.csv` (2021-01-01 .. 2024-09-29)
  from public GitHub-hosted SOL/USD and BTC/USD data; direct exchange APIs are
  not reachable from this environment. See the module docstring for sources and
  the ratio-OHLC approximation caveat.
- `backtest.py` — runs the strategy with `backtesting.py` (0.1%/side fees,
  70/30 in-sample/out-of-sample split, indicator computed causally over the
  full series) plus an amplitude × riskMult robustness sweep. Writes `RESULTS.md`.
- `RESULTS.md` — generated results.

Run: `pip install backtesting pandas numpy && python build_dataset.py && python backtest.py`

## Verdict: no edge on SOLBTC daily — rejected

- With the script's default `baseRiskMult=3` (stop 1.5×ATR), every
  configuration lost money: -31% in-sample / -10% out-of-sample, Sharpe
  -1.20 / -0.73, win rate 20-26%. The stop sits closer than typical daily
  ranges, so ~77% of trades stopped out within days (exposure ~12%).
- Widening to `baseRiskMult=6` (stop 3×ATR, the committed baseline) fixes the
  stop-out churn (win rate 53% IS, exposure ~52%) and turns in-sample positive
  (**+18.9%**, Sharpe 0.22, PF 1.63) — but out-of-sample collapses to
  **-34.6%** (Sharpe -2.15, win rate 15%, PF 0.32). In-sample gains that
  evaporate OOS are the signature of curve-fitting, not edge.
- The robustness sweep spans -28% .. +64% with adjacent cells flipping sign —
  no stable parameter region. Either way, buy & hold (+1192% IS / +211% OOS)
  crushes every cell.
- A long-only variant with a regime filter (bull flips only above the 100-day
  SMA, bearish flips just exit) was also tested. It cuts full-period drawdown
  (-36% vs -48%) by not shorting a structural uptrend, but stays negative at
  default params: -10.7% IS / -9.7% OOS. Its in-sample sweep shows a
  positive-looking pocket at amplitude 10-15 (+21..+33%), but validating that
  pocket out-of-sample gives -7.5% .. +8.6% (best cell Sharpe 0.43 on 12
  trades) — noise, not a transferable edge.
- The Pine dashboard's advertised win rate is a scoreboard, not equity: it
  counts any TP1 *touch* as a win, and when a stop-out follows a TP1 hit it
  removes one win **and** one loss from the tally. The equity-curve reality
  (this backtest, fees included) is a 20-26% win rate and negative expectancy.

Caveats: signal-close fills, no slippage/funding, ~19 flip signals over the
window (small sample), and synthetic ratio bars slightly understate intrabar
extremes (TP/SL touch modelling is conservative in both directions).
