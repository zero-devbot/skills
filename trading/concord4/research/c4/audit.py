"""Data quality audit.

Synthetic data is clean by construction. Real vendor and broker history is
not: it has holes where the feed dropped, bars stamped on a Saturday,
flat bars where nothing traded, the odd bad tick, and a spread column that
may or may not mean what you think. None of that announces itself - it just
quietly changes the backtest.

Run this before trusting any number computed from a new dataset. Every check
returns a severity so the protocol runner can refuse to continue on a FAIL
rather than produce a confident-looking result from broken input.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

INFO, WARN, FAIL = "INFO", "WARN", "FAIL"
_RANK = {INFO: 0, WARN: 1, FAIL: 2}


@dataclass
class Finding:
    severity: str
    check: str
    detail: str


@dataclass
class AuditReport:
    symbol: str
    bars: int
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    years: float
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def worst(self) -> str:
        return max((f.severity for f in self.findings), key=lambda s: _RANK[s], default=INFO)

    @property
    def ok(self) -> bool:
        return self.worst != FAIL


def _add(report: AuditReport, severity: str, check: str, detail: str) -> None:
    report.findings.append(Finding(severity, check, detail))


def audit_bars(
    frame: pd.DataFrame,
    symbol: str = "?",
    expected_freq: str = "15min",
    min_years_hard: float = 1.5,
    min_years_soft: float = 4.0,
    max_spread_atr: float = 0.06,
    role: str = "traded",
) -> AuditReport:
    """Audit one OHLC frame. Index must be a UTC DatetimeIndex of bar opens.

    ``role`` is "traded" for the instrument the strategy trades and
    "reference" for a USD-basket leg. Reference feeds skip the checks that
    are specific to the traded symbol: the strategy's warmup requirement, and
    the L0 spread gate, which never looks at their spreads. Reporting "the L0
    gate would block 93% of bars" for USDCHF is just noise.
    """
    is_traded = role == "traded"
    report = AuditReport(symbol=symbol, bars=len(frame), start=None, end=None, years=0.0)

    if frame.empty:
        _add(report, FAIL, "empty", "no bars at all")
        return report

    report.start, report.end = frame.index[0], frame.index[-1]
    report.years = (report.end - report.start).days / 365.25

    # ---- index -------------------------------------------------------
    if not frame.index.is_monotonic_increasing:
        _add(report, FAIL, "index", "timestamps are not sorted ascending")
    duplicates = int(frame.index.duplicated().sum())
    if duplicates:
        _add(report, FAIL, "index", f"{duplicates:,} duplicate timestamps")
    if getattr(frame.index, "tz", None) is None:
        _add(report, FAIL, "index", "index is timezone-naive; UTC is required")

    # ---- span --------------------------------------------------------
    if not is_traded:
        _add(report, INFO, "span", f"{report.years:.1f} years, {len(frame):,} bars")
    elif report.years < min_years_hard:
        _add(report, FAIL, "span",
             f"{report.years:.1f} years is below the {min_years_hard} needed to fill "
             "the 250-day volatility percentile and the 63-day momentum lookback")
    elif report.years < min_years_soft:
        _add(report, WARN, "span",
             f"{report.years:.1f} years leaves little room for an out-of-sample split "
             f"after the ~1 year of warmup ({min_years_soft}+ preferred)")
    else:
        _add(report, INFO, "span", f"{report.years:.1f} years, {len(frame):,} bars")

    # ---- OHLC integrity ----------------------------------------------
    high, low = frame["high"], frame["low"]
    broken = int((high < low).sum())
    outside = int(
        ((frame["close"] > high) | (frame["close"] < low)
         | (frame["open"] > high) | (frame["open"] < low)).sum()
    )
    nonpositive = int((frame[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())

    if broken:
        _add(report, FAIL, "ohlc", f"{broken:,} bars with high < low")
    if outside:
        _add(report, FAIL, "ohlc", f"{outside:,} bars with open/close outside the high-low range")
    if nonpositive:
        _add(report, FAIL, "ohlc", f"{nonpositive:,} bars with a non-positive price")
    if not (broken or outside or nonpositive):
        _add(report, INFO, "ohlc", "every bar is internally consistent")

    # ---- gaps ---------------------------------------------------------
    step = pd.Timedelta(expected_freq)
    deltas = frame.index.to_series().diff()
    gaps = deltas[deltas > step]

    # Classifying by duration AND landing day. An earlier version accepted any
    # gap of 40h+ ending on a Monday as "the weekend", which swallowed a
    # six-day hole whole. A weekend is 40-80h; longer is something else, and
    # nothing can tell a Christmas closure from a feed outage except the date,
    # so extended breaks are listed rather than silently absorbed.
    ends_on = gaps.index.dayofweek
    is_weekend = (
        (gaps >= pd.Timedelta(hours=40)) & (gaps <= pd.Timedelta(hours=80))
        & pd.Series(np.isin(ends_on, [6, 0]), index=gaps.index)
    )
    is_extended = gaps > pd.Timedelta(hours=80)
    is_holiday = (~is_weekend) & (~is_extended) & (gaps >= pd.Timedelta(hours=20))
    intraweek = gaps[~(is_weekend | is_extended | is_holiday)]

    missing = int(((intraweek - step) / step).sum())
    expected = len(frame) + missing
    report.stats["missing_bars"] = missing
    report.stats["gap_count"] = int(len(intraweek))

    share = missing / expected if expected else 0.0
    severity = FAIL if share > 0.10 else (WARN if share > 0.02 else INFO)
    _add(report, severity, "gaps",
         f"{missing:,} bars missing inside trading weeks across {len(intraweek):,} gaps "
         f"({share * 100:.2f}% of expected)")

    if len(intraweek):
        worst = intraweek.sort_values(ascending=False).head(3)
        rendered = ", ".join(
            f"{ts:%Y-%m-%d %H:%M} after {delta.total_seconds() / 3600:.1f}h"
            for ts, delta in worst.items()
        )
        _add(report, INFO, "gaps", f"largest intra-week: {rendered}")

    extended = gaps[is_extended]
    if len(extended):
        shown = ", ".join(
            f"{ts:%Y-%m-%d} ({delta.total_seconds() / 86400:.1f}d)"
            for ts, delta in extended.sort_values(ascending=False).head(4).items()
        )
        more = "" if len(extended) <= 4 else f" (+{len(extended) - 4} more)"
        _add(report, WARN if len(extended) > 3 else INFO, "long breaks",
             f"{len(extended):,} break(s) over 80h - a holiday closure or a feed "
             f"outage, only the date tells you which: {shown}{more}")
    if len(gaps[is_holiday]):
        _add(report, INFO, "gaps", f"{int(is_holiday.sum()):,} holiday-sized breaks (expected)")

    # ---- weekend bars --------------------------------------------------
    # Saturday is the only truly dead day: the week opens late Sunday UTC.
    saturday = int((frame.index.dayofweek == 5).sum())
    if saturday:
        _add(report, WARN, "calendar",
             f"{saturday:,} bars stamped on a Saturday - check the server offset")
    else:
        _add(report, INFO, "calendar", "no Saturday bars")

    # ---- flat bars ------------------------------------------------------
    flat = int(
        ((frame["open"] == frame["high"]) & (frame["high"] == frame["low"])
         & (frame["low"] == frame["close"])).sum()
    )
    flat_share = flat / len(frame)
    report.stats["flat_share"] = flat_share
    _add(report, WARN if flat_share > 0.05 else INFO, "flat bars",
         f"{flat:,} bars with no range at all ({flat_share * 100:.2f}%)")

    # ---- suspicious jumps ------------------------------------------------
    returns = np.log(frame["close"]).diff()
    sigma = returns.rolling(500, min_periods=100).std()
    jumps = int((returns.abs() > 12 * sigma).sum())
    report.stats["jumps"] = jumps
    if jumps:
        _add(report, WARN, "jumps",
             f"{jumps:,} bar-to-bar moves beyond 12 sigma - likely bad ticks, "
             "and a breakout system will trade them")
    else:
        _add(report, INFO, "jumps", "no extreme bar-to-bar moves")

    # ---- spread ----------------------------------------------------------
    if "spread" in frame.columns and frame["spread"].notna().any():
        spread = frame["spread"].dropna()
        zero = int((spread <= 0).sum())
        report.stats.update({
            "spread_median": float(spread.median()),
            "spread_p95": float(spread.quantile(0.95)),
            "spread_max": float(spread.max()),
        })
        _add(report, INFO, "spread",
             f"median {spread.median():.3f}, p95 {spread.quantile(0.95):.3f}, "
             f"max {spread.max():.3f} (price units)")
        if zero:
            _add(report, WARN, "spread", f"{zero:,} bars report a zero or negative spread")

        # the L0 gate measures spread against ATR(M15) on the TRADED symbol
        # only; if it blocks nearly everything the backtest shows no trades
        # and looks like a bug rather than a configuration mismatch
        if not is_traded:
            return report
        true_range = pd.concat([
            frame["high"] - frame["low"],
            (frame["high"] - frame["close"].shift()).abs(),
            (frame["low"] - frame["close"].shift()).abs(),
        ], axis=1).max(axis=1)
        atr = true_range.ewm(alpha=1 / 14, adjust=False).mean()
        blocked = float((spread > max_spread_atr * atr.reindex(spread.index)).mean())
        report.stats["spread_gate_blocked"] = blocked
        _add(report, WARN if blocked > 0.80 else INFO, "spread gate",
             f"the L0 gate at {max_spread_atr:.0%} of ATR would block "
             f"{blocked * 100:.1f}% of bars on this feed")
    else:
        _add(report, WARN, "spread",
             "no spread column; the backtest will fall back to a flat assumed spread")

    # ---- per-year coverage ------------------------------------------------
    per_year = frame.groupby(frame.index.year).size()
    report.stats["bars_per_year"] = per_year.to_dict()
    if len(per_year) > 2:
        full = per_year.iloc[1:-1]            # ignore partial first and last years
        if len(full) and full.min() < 0.70 * full.median():
            thin = full[full < 0.70 * full.median()]
            _add(report, WARN, "coverage",
                 f"thin years: {', '.join(f'{y} ({n:,})' for y, n in thin.items())}")

    return report


def render(report: AuditReport) -> str:
    lines = [
        f"  {report.symbol}  {report.bars:,} bars  "
        f"{report.start:%Y-%m-%d} -> {report.end:%Y-%m-%d}"
        if report.start is not None else f"  {report.symbol}  EMPTY",
    ]
    for finding in report.findings:
        mark = {INFO: " ", WARN: "!", FAIL: "x"}[finding.severity]
        lines.append(f"    {mark} {finding.check:<12} {finding.detail}")
    return "\n".join(lines)


def render_all(reports: list[AuditReport]) -> str:
    out = ["", "DATA AUDIT", "=" * 72]
    for report in reports:
        out.append(render(report))
        out.append("")
    worst = max((r.worst for r in reports), key=lambda s: _RANK[s], default=INFO)
    out.append(f"  worst severity: {worst}")
    if worst == FAIL:
        out.append("  A FAIL means the data cannot support an honest backtest. Fix it first.")
    return "\n".join(out)
