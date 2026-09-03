"""Performance metrics.

Everything is computed from the mark-to-market equity curve and the trade
list, so drawdown reflects open positions rather than only closed ones.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252.0


def max_drawdown(equity: pd.Series) -> tuple[float, pd.Timestamp | None, pd.Timestamp | None]:
    """Peak-to-trough drawdown as a fraction, with the dates that bracket it."""
    if equity.empty:
        return 0.0, None, None

    running_peak = equity.cummax()
    drawdown = (equity - running_peak) / running_peak
    trough = drawdown.idxmin()
    depth = float(-drawdown.min())
    if depth <= 0:
        return 0.0, None, None

    peak = equity.loc[:trough].idxmax()
    return depth, peak, trough


def summarize(equity: pd.Series, trades: pd.DataFrame, initial_equity: float | None = None) -> dict:
    """Headline statistics. Sharpe is computed on daily equity returns."""
    initial = initial_equity if initial_equity is not None else (
        float(equity.iloc[0]) if len(equity) else 0.0
    )
    final = float(equity.iloc[-1]) if len(equity) else initial

    daily = equity.resample("1D").last().dropna()
    returns = daily.pct_change().dropna()

    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9) if len(equity) > 1 else 0.0
    cagr = (final / initial) ** (1 / years) - 1 if years > 0 and initial > 0 and final > 0 else np.nan

    sharpe = np.nan
    sortino = np.nan
    if len(returns) > 2 and returns.std() > 0:
        sharpe = float(returns.mean() / returns.std() * np.sqrt(TRADING_DAYS))
        downside = returns[returns < 0]
        if len(downside) > 1 and downside.std() > 0:
            sortino = float(returns.mean() / downside.std() * np.sqrt(TRADING_DAYS))

    depth, peak_at, trough_at = max_drawdown(equity)

    stats = {
        "start": equity.index[0] if len(equity) else None,
        "end": equity.index[-1] if len(equity) else None,
        "initial_equity": initial,
        "final_equity": final,
        "total_return": (final / initial - 1) if initial else np.nan,
        "cagr": cagr,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": depth,
        "max_dd_peak": peak_at,
        "max_dd_trough": trough_at,
        "calmar": (cagr / depth) if depth > 0 and np.isfinite(cagr) else np.nan,
    }
    stats.update(trade_stats(trades))

    if np.isfinite(stats["max_drawdown"]) and stats["max_drawdown"] > 0:
        stats["return_over_maxdd"] = stats["total_return"] / stats["max_drawdown"]
    else:
        stats["return_over_maxdd"] = np.nan
    return stats


def trade_stats(trades: pd.DataFrame) -> dict:
    """Win rate, profit factor and R-multiple statistics."""
    empty = {
        "trades": 0, "win_rate": np.nan, "profit_factor": np.nan,
        "expectancy_r": np.nan, "avg_win_r": np.nan, "avg_loss_r": np.nan,
        "payoff_ratio": np.nan, "gross_profit": 0.0, "gross_loss": 0.0,
        "largest_loss_r": np.nan, "max_consecutive_losses": 0,
    }
    if trades is None or trades.empty:
        return empty

    pnl = trades["pnl"]
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    gross_profit, gross_loss = float(wins.sum()), float(-losses.sum())

    r = trades["r_multiple"].replace([np.inf, -np.inf], np.nan).dropna()
    win_r, loss_r = r[r > 0], r[r <= 0]

    streak = best = 0
    for value in pnl:
        streak = streak + 1 if value < 0 else 0
        best = max(best, streak)

    return {
        "trades": int(len(trades)),
        "win_rate": float(len(wins) / len(pnl)) if len(pnl) else np.nan,
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else np.inf,
        "expectancy_r": float(r.mean()) if len(r) else np.nan,
        "avg_win_r": float(win_r.mean()) if len(win_r) else np.nan,
        "avg_loss_r": float(loss_r.mean()) if len(loss_r) else np.nan,
        "payoff_ratio": (
            float(win_r.mean() / abs(loss_r.mean()))
            if len(win_r) and len(loss_r) and loss_r.mean() != 0 else np.nan
        ),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "largest_loss_r": float(r.min()) if len(r) else np.nan,
        "max_consecutive_losses": int(best),
    }


def format_summary(stats: dict, title: str = "CONCORD-4") -> str:
    """Console report."""
    def pct(x):
        return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:6.2f}%"

    def num(x, fmt="8.2f"):
        return "n/a" if x is None or not np.isfinite(x) else format(x, fmt)

    lines = [
        f"\n{title}",
        "=" * max(len(title), 58),
        f"  period            {stats['start']}  ->  {stats['end']}",
        f"  equity            {stats['initial_equity']:,.0f}  ->  {stats['final_equity']:,.0f}",
        f"  total return      {pct(stats['total_return'])}",
        f"  CAGR              {pct(stats['cagr'])}",
        f"  Sharpe            {num(stats['sharpe'])}",
        f"  Sortino           {num(stats['sortino'])}",
        f"  max drawdown      {pct(stats['max_drawdown'])}",
        f"  Calmar            {num(stats['calmar'])}",
        f"  return / max DD   {num(stats['return_over_maxdd'])}",
        "-" * 58,
        f"  trades            {stats['trades']}",
        f"  win rate          {pct(stats['win_rate'])}",
        f"  profit factor     {num(stats['profit_factor'])}",
        f"  expectancy        {num(stats['expectancy_r'])} R",
        f"  avg win / loss    {num(stats['avg_win_r'], '5.2f')} R / {num(stats['avg_loss_r'], '5.2f')} R",
        f"  payoff ratio      {num(stats['payoff_ratio'])}",
        f"  worst trade       {num(stats['largest_loss_r'])} R",
        f"  max losing streak {stats['max_consecutive_losses']}",
    ]
    return "\n".join(lines)
