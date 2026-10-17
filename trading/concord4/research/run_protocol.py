#!/usr/bin/env python3
"""Run the whole CONCORD-4 validation protocol in one command.

    python run_protocol.py --data-dir data/ --server-offset 3 --out results/

Executes, in order, refusing to continue past a data failure:

    1. data audit        every symbol, before anything is computed from it
    2. gate report       how often each gate fired and why breakouts died
    3. full sample       headline numbers + tearsheet
    4. in/out of sample  and how far the edge degrades across the split
    5. parameter sweeps  looking for a plateau, not a peak
    6. walk-forward      the only honest estimate of live performance
    7. Monte Carlo       a distribution of drawdown, not one observation
    8. spread stress     everything again at 1.5x the spread

Writes REPORT.md, the tearsheets and the underlying CSVs to ``--out``, and
exits 0 when every check passes, 1 on warnings, 2 when the data cannot
support an honest backtest.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from c4 import (
    Config, ExecConfig, Instrument, PlottingUnavailable, USD_BASKET,
    audit_bars, build_features, format_summary, load_dataset, monte_carlo,
    render_audit, run, split_is_oos, sweep, tearsheet_both_themes,
    veto_reasons, walk_forward, weighted_walk_forward,
)
from c4.audit import FAIL, WARN

SWEEPS = {
    "breakout_atr_k": [0.05, 0.10, 0.15, 0.20, 0.25, 0.30],
    "stop_min_atr": [1.0, 1.25, 1.5, 1.75, 2.0],
    "max_spread_atr": [0.04, 0.06, 0.08, 0.12, 0.20],
}


class Report:
    """Accumulates the markdown report while the console stays readable."""

    def __init__(self, title: str) -> None:
        self.lines = [f"# {title}", "",
                      f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC_", ""]
        self.warnings: list[str] = []

    def section(self, heading: str) -> None:
        self.lines += ["", f"## {heading}", ""]

    def text(self, body: str) -> None:
        self.lines += [body, ""]

    def code(self, body: str) -> None:
        self.lines += ["```", body.rstrip(), "```", ""]

    def table(self, frame: pd.DataFrame, digits: int = 3) -> None:
        """Markdown table, written by hand.

        ``DataFrame.to_markdown`` needs the optional ``tabulate`` package and
        raises if it is absent. A pipe-delimited string is not worth a
        dependency the rest of the harness does not have.
        """
        if frame.empty:
            self.lines += ["_(empty)_", ""]
            return

        def cell(value) -> str:
            if isinstance(value, float):
                return "" if not np.isfinite(value) else f"{value:.{digits}f}"
            if isinstance(value, pd.Timestamp):
                return f"{value:%Y-%m-%d}"
            return str(value)

        headers = [str(c) for c in frame.columns]
        rows = [[cell(v) for v in row] for row in frame.itertuples(index=False)]
        widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]

        self.lines.append("| " + " | ".join(h.ljust(w) for h, w in zip(headers, widths)) + " |")
        self.lines.append("|" + "|".join("-" * (w + 2) for w in widths) + "|")
        for row in rows:
            self.lines.append("| " + " | ".join(c.ljust(w) for c, w in zip(row, widths)) + " |")
        self.lines.append("")

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def write(self, path: Path) -> Path:
        if self.warnings:
            self.lines += ["", "## Warnings", ""]
            self.lines += [f"- {w}" for w in self.warnings]
        path.write_text("\n".join(self.lines) + "\n")
        return path


def both(report: Report, text: str) -> None:
    """Print to console and record in the report."""
    print(text)
    report.code(text)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="CONCORD-4 full validation protocol")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--out", type=Path, default=Path("results"))
    parser.add_argument("--server-offset", type=float, default=0.0,
                        help="broker server time minus UTC, in hours. MetaTrader "
                             "exports in server time; getting this wrong moves the "
                             "opening range and invalidates everything downstream")
    parser.add_argument("--news-csv", type=Path, default=None)
    parser.add_argument("--split", default="2022-01-01")
    parser.add_argument("--equity", type=float, default=10_000.0)
    parser.add_argument("--risk", type=float, default=0.50)
    parser.add_argument("--vol-target", type=float, default=10.0)
    parser.add_argument("--default-spread", type=float, default=0.25)
    parser.add_argument("--max-spread-atr", type=float, default=None)
    parser.add_argument("--stress-spread", type=float, default=1.5)
    parser.add_argument("--force", action="store_true",
                        help="continue even when the data audit reports a FAIL")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    report = Report(f"CONCORD-4 validation protocol - {args.symbol}")

    cfg = Config()
    if args.max_spread_atr is not None:
        cfg = cfg.replace(max_spread_atr=args.max_spread_atr)
    inst = Instrument(default_spread=args.default_spread)
    exec_cfg = ExecConfig(initial_equity=args.equity, risk_percent=args.risk,
                          vol_target_annual=args.vol_target)

    # ---- 1. data audit --------------------------------------------------
    print(f"Loading {args.symbol} and USD-basket legs from {args.data_dir} ...")
    try:
        dataset = load_dataset(args.data_dir, args.symbol,
                               server_offset_hours=args.server_offset,
                               news_csv=args.news_csv)
    except (ValueError, FileNotFoundError) as exc:
        # a misconfigured run is a user error, not a crash; a stack trace
        # buries the one line that says how to fix it
        print(f"\nCannot load the data:\n\n{exc}\n")
        return 2

    report.section("1. Data audit")
    audits = [audit_bars(dataset.m15, args.symbol, max_spread_atr=cfg.max_spread_atr,
                         role="traded")]
    for leg, frame in dataset.majors.items():
        audits.append(audit_bars(frame, leg, expected_freq="1h", role="reference"))

    rendered = render_audit(audits)
    print(rendered)
    report.code(rendered)

    for entry in audits:
        for finding in entry.findings:
            if finding.severity in (WARN, FAIL):
                report.warn(f"{entry.symbol} / {finding.check}: {finding.detail}")

    if any(not a.ok for a in audits) and not args.force:
        report.text("**Stopped**: the audit reported a FAIL. Nothing below was computed.")
        path = report.write(args.out / "REPORT.md")
        print(f"\nSTOPPED at the audit. Report: {path}")
        print("Fix the data, or pass --force to compute anyway (results will be unreliable).")
        return 2

    # ---- 2. gate report --------------------------------------------------
    report.section("2. Gate report")
    features = build_features(dataset.m15, dataset.h1, dataset.d1, dataset.usd_h1,
                              cfg, news_events=dataset.news,
                              default_spread=inst.default_spread)
    reasons = veto_reasons(features)
    breakouts = int((features["l3"] != 0).sum())

    lines = [
        f"  M15 bars                {len(features):>9,}",
        f"  in session              {int(features['in_session'].sum()):>9,}",
        f"  L0 tradability open     {int(features['l0'].sum()):>9,}",
        f"  L1 regime non-neutral   {int((features['l1'] != 0).sum()):>9,}",
        f"  L2 intermarket non-neut {int((features['l2'] != 0).sum()):>9,}",
        f"  L3 breakouts            {breakouts:>9,}",
        f"  signals (all agree)     {int((features['signal'] != 0).sum()):>9,}",
        "",
        "  breakouts rejected by:",
    ]
    for reason, count in reasons[reasons != ""].value_counts().items():
        share = 100.0 * count / breakouts if breakouts else 0.0
        lines.append(f"    {reason:<42} {count:>7,}  ({share:4.1f}%)")
    both(report, "\n".join(lines))

    if int((features["signal"] != 0).sum()) == 0:
        report.warn("no signals fired at all - read the rejection table above before "
                    "concluding anything about the strategy")

    # ---- 3. full sample ---------------------------------------------------
    report.section("3. Full sample")
    result, stats = run(dataset, cfg, exec_cfg, inst)
    both(report, format_summary(stats, "Full sample"))

    pd.DataFrame({"equity": result.equity}).to_csv(args.out / "equity.csv")
    result.trades.to_csv(args.out / "trades.csv", index=False)

    if stats["trades"] == 0:
        report.warn("the backtest produced no trades; everything below is vacuous")

    # ---- 4. in / out of sample --------------------------------------------
    report.section("4. In-sample vs out-of-sample")
    is_data, oos_data = split_is_oos(dataset, args.split)
    _, is_stats = run(is_data, cfg, exec_cfg, inst)
    _, oos_stats = run(oos_data, cfg, exec_cfg, inst)
    both(report, format_summary(is_stats, f"In-sample (to {args.split})"))
    both(report, format_summary(oos_stats, f"Out-of-sample (from {args.split})"))

    if np.isfinite(is_stats["sharpe"]) and is_stats["sharpe"] > 0:
        drop = 100 * (1 - oos_stats["sharpe"] / is_stats["sharpe"])
        both(report, f"  Sharpe degradation IS -> OOS: {drop:.0f}%")
        if drop > 50:
            report.warn(f"Sharpe degraded {drop:.0f}% out of sample - the in-sample "
                        "result was mostly fitting")
    else:
        both(report, "  Sharpe degradation: n/a - in-sample Sharpe is not positive.")
        report.warn("in-sample Sharpe is not positive; there is no edge to degrade")

    # ---- 5. parameter sweeps -----------------------------------------------
    report.section("5. Parameter sweeps")
    report.text("Read the `plateau` column, not the peak. Several rows near 1.0 is a "
                "shelf; one row near 1.0 with low neighbours is a curve fit.")
    for parameter, values in SWEEPS.items():
        table = sweep(dataset, parameter, values, cfg, exec_cfg, inst)
        table.to_csv(args.out / f"sweep_{parameter}.csv", index=False)
        print(f"\nSWEEP - {parameter}")
        print(table.to_string(index=False, float_format=lambda v: f"{v:8.3f}"))
        report.text(f"### {parameter}")
        report.table(table)

        if table["plateau"].notna().any() and table["plateau"].max() < 0.70:
            report.warn(f"{parameter}: no plateau - the metric peaks sharply, "
                        "which is the signature of a curve fit")

    # ---- 6. walk-forward -----------------------------------------------------
    report.section("6. Walk-forward (12m train / 6m test)")
    folds = walk_forward(dataset, "breakout_atr_k", SWEEPS["breakout_atr_k"],
                         cfg=cfg, exec_cfg=exec_cfg, inst=inst)
    if folds.empty:
        both(report, "  not enough history for a single fold")
        report.warn("walk-forward produced no folds; the sample is too short")
    else:
        folds.to_csv(args.out / "walkforward.csv", index=False)
        print("\nWALK-FORWARD")
        print(folds.to_string(index=False, float_format=lambda v: f"{v:8.3f}"))
        report.table(folds)
        agg = weighted_walk_forward(folds)

        lines = [
            f"  folds                     {agg['folds']}",
            f"  folds with >= 10 trades   {agg['qualifying_folds']}",
            f"  test trades in total      {agg['total_test_trades']}",
            f"  naive mean Sharpe         {agg['naive_mean']:.3f}",
            f"  mean over qualifying      "
            + (f"{agg['qualified_mean']:.3f}" if np.isfinite(agg["qualified_mean"]) else "n/a"),
        ]
        both(report, "\n".join(lines))

        if agg["qualifying_folds"] == 0:
            both(report, "  Every fold traded too little for its Sharpe to mean anything.")
            report.warn(f"no walk-forward fold reached 10 trades (total "
                        f"{agg['total_test_trades']} across {agg['folds']} folds). The naive "
                        f"mean of {agg['naive_mean']:.2f} is noise, not an edge - a fold "
                        "holding one or two trades produces a Sharpe with no information "
                        "in it.")
        elif not np.isfinite(agg["qualified_mean"]) or agg["qualified_mean"] <= 0:
            report.warn("mean walk-forward Sharpe over qualifying folds is not positive - "
                        "this is the number that matters most, and it says there is no edge")

    # ---- 7. Monte Carlo --------------------------------------------------------
    report.section("7. Monte Carlo")
    mc = monte_carlo(result.trades, iterations=5000, initial_equity=args.equity)
    if not mc:
        both(report, "  no trades to resample")
    else:
        lines = [f"  iterations                {mc['iterations']:,}",
                 f"  trades resampled          {mc['observed_trades']:,}"]
        lines += [f"  max drawdown {k:<12} {v * 100:6.2f}%"
                  for k, v in mc["max_dd_percentiles"].items()]
        lines += [f"  median final equity       {mc['median_final_equity']:,.0f}",
                  f"  P(losing overall)         {mc['prob_negative'] * 100:5.1f}%",
                  f"  P(drawdown > 10%)         {mc['prob_dd_over_10pct'] * 100:5.1f}%",
                  f"  P(drawdown > 20%)         {mc['prob_dd_over_20pct'] * 100:5.1f}%"]
        both(report, "\n".join(lines))
        if mc["max_dd_percentiles"]["p95"] > 0.10:
            report.warn(f"p95 bootstrapped drawdown is "
                        f"{mc['max_dd_percentiles']['p95'] * 100:.1f}%, past the 10% "
                        "design target - size against this, not the observed figure")

    # ---- 8. spread stress ---------------------------------------------------------
    report.section(f"8. Spread stress ({args.stress_spread}x)")
    if "spread" in dataset.m15.columns:
        stressed = dataset.slice()
        stressed.m15 = dataset.m15.assign(spread=dataset.m15["spread"] * args.stress_spread)
        _, stress_stats = run(stressed, cfg, exec_cfg, inst)
        both(report, format_summary(stress_stats, f"Spread x{args.stress_spread}"))
        if np.isfinite(stats["sharpe"]) and stats["sharpe"] > 0 and \
                np.isfinite(stress_stats["sharpe"]):
            erosion = 100 * (1 - stress_stats["sharpe"] / stats["sharpe"])
            both(report, f"  Sharpe erosion from wider spreads: {erosion:.0f}%")
            if erosion > 60:
                report.warn(f"{erosion:.0f}% of the Sharpe disappears at "
                            f"{args.stress_spread}x spread - the edge is inside the costs")
    else:
        both(report, "  skipped: this dataset carries no spread column")
        report.warn("no spread column, so the spread stress test could not run")

    # ---- tearsheets ------------------------------------------------------------------
    if not result.equity.empty:
        try:
            subtitle = (f"{dataset.m15.index[0]:%Y-%m-%d} to {dataset.m15.index[-1]:%Y-%m-%d}   "
                        f"risk {args.risk:.2f}% / trade   vol target {args.vol_target:.0f}%")
            written = tearsheet_both_themes(
                result.equity, result.trades, stats, args.out / "tearsheet.png",
                title=f"CONCORD-4 - {args.symbol}", subtitle=subtitle, monte_carlo=mc,
            )
            report.section("Tearsheet")
            report.text("![tearsheet](tearsheet.png)")
            for item in written:
                print(f"\n  tearsheet written to {item}")
        except PlottingUnavailable as exc:
            print(f"\n  {exc}")
            report.warn("matplotlib is not installed, so no tearsheet was rendered")

    path = report.write(args.out / "REPORT.md")
    print(f"\n{'=' * 72}")
    print(f"  Protocol complete. Report: {path}")
    if report.warnings:
        print(f"  {len(report.warnings)} warning(s):")
        for message in report.warnings:
            print(f"    ! {message}")
        return 1
    print("  No warnings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
