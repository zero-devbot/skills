# HalfTrend [BigBeluga] on SOLBTC — daily backtest

Data: synthetic daily SOLBTC 2021-01-01 .. 2024-09-29 (see `build_dataset.py` for sources and construction caveats). Params: amplitude=20, channelDeviation=2.0, ATR(100)/2, baseRiskMult=3.0, fees 0.1%/side, 3-tranche scale-out at 1R/2R/3R, full-position stop at 1R, reverse on opposite flip.

### In-sample (70%): 2021-01-01 .. 2023-08-15

| Metric | Value |
|---|---|
| Return [%] | -31.39 |
| Buy & Hold Return [%] | 1192.07 |
| Return (Ann.) [%] | -13.38 |
| Sharpe Ratio | -1.20 |
| Sortino Ratio | -1.26 |
| Max. Drawdown [%] | -36.59 |
| # Trades | 30 |
| Win Rate [%] | 20.00 |
| Profit Factor | 0.34 |
| Expectancy [%] | -5.06 |
| Exposure Time [%] | 7.73 |

### Out-of-sample (30%): 2023-08-16 .. 2024-09-29

| Metric | Value |
|---|---|
| Return [%] | -10.35 |
| Buy & Hold Return [%] | 211.21 |
| Return (Ann.) [%] | -9.25 |
| Sharpe Ratio | -0.73 |
| Sortino Ratio | -0.87 |
| Max. Drawdown [%] | -16.66 |
| # Trades | 27 |
| Win Rate [%] | 25.93 |
| Profit Factor | 0.55 |
| Expectancy [%] | -2.01 |
| Exposure Time [%] | 21.65 |

### Full period: 2021-01-01 .. 2024-09-29

| Metric | Value |
|---|---|
| Return [%] | -38.49 |
| Buy & Hold Return [%] | 3746.92 |
| Return (Ann.) [%] | -12.16 |
| Sharpe Ratio | -1.05 |
| Sortino Ratio | -1.14 |
| Max. Drawdown [%] | -43.74 |
| # Trades | 57 |
| Win Rate [%] | 22.81 |
| Profit Factor | 0.42 |
| Expectancy [%] | -3.62 |
| Exposure Time [%] | 11.92 |

## Robustness sweep (in-sample)

Return % / Sharpe / #trades per (amplitude, baseRiskMult):

| amplitude \ riskMult | 2.0 | 3.0 | 4.0 |
|---|---|---|---|
| 10 | -1% / -0.04 / 48 | -11% / -0.21 / 48 | 1% / 0.02 / 48 |
| 15 | 9% / 0.21 / 48 | 12% / 0.21 / 48 | -16% / -0.23 / 48 |
| 20 | -22% / -1.01 / 30 | -31% / -1.20 / 30 | -9% / -0.16 / 30 |
| 25 | -5% / -0.24 / 24 | -18% / -0.67 / 24 | -28% / -0.84 / 24 |
| 30 | 6% / 0.29 / 18 | -5% / -0.20 / 18 | 5% / 0.12 / 18 |
