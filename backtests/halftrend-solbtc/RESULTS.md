# HalfTrend [BigBeluga] on SOLBTC — daily backtest

Data: synthetic daily SOLBTC 2021-01-01 .. 2024-09-29 (see `build_dataset.py` for sources and construction caveats). Params: amplitude=20, channelDeviation=2.0, ATR(100)/2, baseRiskMult=6.0, fees 0.1%/side, 3-tranche scale-out at 1R/2R/3R, full-position stop at 1R, reverse on opposite flip.

### In-sample (70%): 2021-01-01 .. 2023-08-15

| Metric | Value |
|---|---|
| Return [%] | 18.93 |
| Buy & Hold Return [%] | 1192.07 |
| Return (Ann.) [%] | 6.84 |
| Sharpe Ratio | 0.22 |
| Sortino Ratio | 0.37 |
| Max. Drawdown [%] | -21.40 |
| # Trades | 30 |
| Win Rate [%] | 53.33 |
| Profit Factor | 1.63 |
| Expectancy [%] | 4.34 |
| Exposure Time [%] | 51.72 |

### Out-of-sample (30%): 2023-08-16 .. 2024-09-29

| Metric | Value |
|---|---|
| Return [%] | -34.60 |
| Buy & Hold Return [%] | 211.21 |
| Return (Ann.) [%] | -31.42 |
| Sharpe Ratio | -2.15 |
| Sortino Ratio | -1.77 |
| Max. Drawdown [%] | -39.20 |
| # Trades | 27 |
| Win Rate [%] | 14.81 |
| Profit Factor | 0.32 |
| Expectancy [%] | -6.68 |
| Exposure Time [%] | 36.74 |

### Full period: 2021-01-01 .. 2024-09-29

| Metric | Value |
|---|---|
| Return [%] | -29.71 |
| Buy & Hold Return [%] | 3746.92 |
| Return (Ann.) [%] | -8.98 |
| Sharpe Ratio | -0.37 |
| Sortino Ratio | -0.49 |
| Max. Drawdown [%] | -48.04 |
| # Trades | 57 |
| Win Rate [%] | 29.82 |
| Profit Factor | 0.82 |
| Expectancy [%] | -1.65 |
| Exposure Time [%] | 47.44 |

## Robustness sweep (in-sample)

Return % / Sharpe / #trades per (amplitude, baseRiskMult):

| amplitude \ riskMult | 4.0 | 6.0 | 8.0 |
|---|---|---|---|
| 10 | 1% / 0.02 / 48 | 36% / 0.33 / 48 | 64% / 0.43 / 48 |
| 15 | -16% / -0.23 / 48 | -27% / -0.37 / 48 | -12% / -0.12 / 48 |
| 20 | -9% / -0.16 / 30 | 19% / 0.22 / 30 | 10% / 0.11 / 30 |
| 25 | -28% / -0.84 / 24 | -27% / -0.48 / 24 | -1% / -0.02 / 24 |
| 30 | 5% / 0.12 / 18 | 6% / 0.09 / 18 | -18% / -0.30 / 18 |
