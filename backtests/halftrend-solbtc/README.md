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

- Every configuration loses to both zero and buy & hold. Baseline params:
  **-31% in-sample / -10% out-of-sample** (Sharpe -1.20 / -0.73, win rate
  20-26%, profit factor 0.34-0.55) while SOLBTC buy & hold did +1192% / +211%.
- The robustness sweep is noise around zero (-31% .. +12%) with no stable
  region — nothing worth forward-testing, and picking the one positive cell
  (amplitude 15) would be curve-fitting.
- Structural problem: the stop sits only `1.5 × ATR(100)` from entry on a pair
  whose daily ranges routinely exceed that, so most trades stop out within days
  (exposure ~12%) before a trend can pay 1R-3R. Meanwhile the engine is flat or
  short through most of a monster SOL/BTC uptrend.
- The Pine dashboard's advertised win rate is a scoreboard, not equity: it
  counts any TP1 *touch* as a win, and when a stop-out follows a TP1 hit it
  removes one win **and** one loss from the tally. The equity-curve reality
  (this backtest, fees included) is a 20-26% win rate and negative expectancy.

Caveats: signal-close fills, no slippage/funding, ~19 flip signals over the
window (small sample), and synthetic ratio bars slightly understate intrabar
extremes (TP/SL touch modelling is conservative in both directions).
