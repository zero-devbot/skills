# HalfTrend [BigBeluga] on SOLBTC — daily backtest

Data: synthetic daily SOLBTC 2021-01-01 .. 2024-09-29 (see `build_dataset.py` for sources and construction caveats). Params: amplitude=20, channelDeviation=2.0, ATR(100)/2, baseRiskMult=6.0, fees 0.1%/side, 3-tranche scale-out at 1R/2R/3R, full-position stop at 1R, reverse on opposite flip.

## Long/short (as published)

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

## Long-only + regime filter (bull flips only above SMA100)

### In-sample (70%): 2021-01-01 .. 2023-08-15

| Metric | Value |
|---|---|
| Return [%] | -10.73 |
| Buy & Hold Return [%] | 1192.07 |
| Return (Ann.) [%] | -4.23 |
| Sharpe Ratio | -0.35 |
| Sortino Ratio | -0.47 |
| Max. Drawdown [%] | -27.08 |
| # Trades | 12 |
| Win Rate [%] | 50.00 |
| Profit Factor | 0.70 |
| Expectancy [%] | -2.65 |
| Exposure Time [%] | 6.79 |

### Out-of-sample (30%): 2023-08-16 .. 2024-09-29

| Metric | Value |
|---|---|
| Return [%] | -9.71 |
| Buy & Hold Return [%] | 211.21 |
| Return (Ann.) [%] | -8.67 |
| Sharpe Ratio | -0.73 |
| Sortino Ratio | -0.84 |
| Max. Drawdown [%] | -21.58 |
| # Trades | 12 |
| Win Rate [%] | 25.00 |
| Profit Factor | 0.70 |
| Expectancy [%] | -2.55 |
| Exposure Time [%] | 15.82 |

### Full period: 2021-01-01 .. 2024-09-29

| Metric | Value |
|---|---|
| Return [%] | -27.14 |
| Buy & Hold Return [%] | 3746.92 |
| Return (Ann.) [%] | -8.10 |
| Sharpe Ratio | -0.68 |
| Sortino Ratio | -0.82 |
| Max. Drawdown [%] | -36.37 |
| # Trades | 24 |
| Win Rate [%] | 25.00 |
| Profit Factor | 0.58 |
| Expectancy [%] | -4.43 |
| Exposure Time [%] | 9.72 |

## Robustness sweep (in-sample, long-only + regime)

Return % / Sharpe / #trades per (amplitude, baseRiskMult):

| amplitude \ riskMult | 4.0 | 6.0 | 8.0 |
|---|---|---|---|
| 10 | 22% / 0.70 / 12 | 26% / 0.60 / 12 | 33% / 0.67 / 12 |
| 15 | 21% / 0.74 / 12 | 22% / 0.52 / 12 | 23% / 0.48 / 12 |
| 20 | -13% / -0.66 / 12 | -11% / -0.35 / 12 | -15% / -0.41 / 12 |
| 25 | -21% / -1.26 / 9 | -23% / -0.82 / 9 | -30% / -1.05 / 9 |
| 30 | -11% / -0.65 / 9 | -19% / -0.66 / 9 | -26% / -0.88 / 9 |
