"""Parity harness: diff the terminal's gate output against Python's.

The MQL5 script ``Scripts/Concord4Export.mq5`` writes a self-contained CSV -
the bars the terminal used, the higher-timeframe values it derived, and the
resulting gates. This module recomputes the gates in Python from the same
bars and reports every disagreement.

Three kinds of disagreement look identical in a naive diff, so the harness
separates them with two modes:

``inject``
    The terminal's own higher-timeframe values are fed into Python via
    ``build_features(htf_override=...)``, so only the GATE LOGIC is under
    test. A mismatch here is a genuine bug in one implementation.

``recompute``
    Python derives everything from the exported M15 bars, using the
    broker's day boundaries. A mismatch here but not in ``inject`` points at
    data depth or timeframe construction, not at logic.

Run ``inject`` first. There is no point hunting a logic bug that is really a
timezone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .data import Instrument, load_csv, resample, resample_server_days, usd_index_h1, USD_BASKET
from .gates import Config, NEUTRAL, OVERRIDABLE, build_features

#: gates must agree exactly - they are small integers, not measurements
INT_COLUMNS = ["l0", "l1", "l2", "l3", "signal"]

#: measurements, compared with a tolerance
FLOAT_COLUMNS = ["or_high", "or_low", "risk_dist", "atr_m15", "atr_h1", "atr_d1", "adr", "vol_pct"]

#: the export's name -> the feature frame's name
RENAMES = {"adr20": "adr"}


@dataclass
class ColumnDiff:
    name: str
    compared: int
    mismatches: int
    max_abs_diff: float = np.nan
    exact: bool = True

    @property
    def match_rate(self) -> float:
        return 1.0 if self.compared == 0 else 1.0 - self.mismatches / self.compared


@dataclass
class ParityReport:
    mode: str
    meta: dict
    rows_export: int
    rows_compared: int
    rows_skipped: int
    diffs: list[ColumnDiff] = field(default_factory=list)
    signal_overlap: dict = field(default_factory=dict)
    indicator_check: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    examples: pd.DataFrame | None = None

    @property
    def gate_mismatches(self) -> int:
        return sum(d.mismatches for d in self.diffs if d.name in INT_COLUMNS)

    @property
    def verdict(self) -> str:
        if self.rows_compared == 0:
            return "INCONCLUSIVE"
        if self.gate_mismatches == 0:
            return "PASS"
        rate = self.gate_mismatches / (self.rows_compared * len(INT_COLUMNS))
        return "WARN" if rate < 0.01 else "FAIL"


def load_mt5_export(path: str | Path) -> tuple[pd.DataFrame, dict]:
    """Read the terminal's export, returning the frame and its metadata."""
    path = Path(path)
    meta: dict = {"path": str(path)}

    with path.open("r", errors="replace") as handle:
        for line in handle:
            if not line.startswith("#"):
                break
            for token in line.lstrip("#").strip().split():
                if "=" in token:
                    key, _, value = token.partition("=")
                    meta[key] = value

    frame = pd.read_csv(path, comment="#")
    if "time_utc" not in frame.columns:
        raise ValueError(f"{path}: not a CONCORD-4 export (no time_utc column)")

    frame["time_utc"] = pd.to_datetime(frame["time_utc"], utc=True, format="mixed")
    frame = frame.set_index("time_utc").sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    frame = frame.rename(columns=RENAMES)

    meta["gmt_offset_hours"] = float(meta.get("gmt_offset_hours", 0.0))
    meta["digits"] = int(meta.get("digits", 2))
    return frame, meta


def export_to_bars(export: pd.DataFrame, point: float | None = None) -> pd.DataFrame:
    """Extract the M15 OHLC frame the terminal used, in harness form."""
    bars = export[["open", "high", "low", "close", "tick_volume"]].copy()
    if "spread" in export.columns:
        # MT5 records the bar spread in POINTS; the harness works in price units
        bars["spread"] = export["spread"].astype("float64") * (point or 0.01)
    return bars


def load_majors(data_dir: Path | None, suffix: str = "") -> dict[str, pd.DataFrame]:
    """Load whatever USD-basket legs are on disk, resampled to H1."""
    if data_dir is None:
        return {}
    majors = {}
    for leg, _, _ in USD_BASKET:
        path = data_dir / f"{leg}{suffix}.csv"
        if path.exists():
            majors[leg] = resample(load_csv(path), "1h")
    return majors


def python_side(
    export: pd.DataFrame,
    meta: dict,
    cfg: Config,
    mode: str = "inject",
    majors_dir: Path | None = None,
    inst: Instrument | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Recompute the gates in Python from the exported bars."""
    inst = inst or Instrument()
    warnings: list[str] = []

    point = 10.0 ** -meta["digits"]
    bars = export_to_bars(export, point)

    h1 = resample(bars, "1h")
    d1 = resample_server_days(bars, meta["gmt_offset_hours"])

    majors = load_majors(majors_dir)
    usd = usd_index_h1(majors) if majors else pd.Series(dtype="float64")

    override = None
    if mode == "inject":
        available = [c for c in OVERRIDABLE if c in export.columns]
        override = export[available].astype("float64")
        missing = [c for c in OVERRIDABLE if c not in available]
        if missing:
            warnings.append(f"inject mode: export lacks {missing}; Python derived them instead")
    elif mode == "recompute":
        if not majors:
            warnings.append(
                "recompute mode without --majors-dir: Python cannot build the USD basket, "
                "so L2 is NEUTRAL everywhere and no Python signal can fire. "
                "Supply the basket CSVs or use --mode inject."
            )
        if len(bars) < cfg.vol_pct_lookback * 96:
            warnings.append(
                f"recompute mode: the export holds {len(bars):,} M15 bars, under the "
                f"~{cfg.vol_pct_lookback * 96:,} needed to fill the {cfg.vol_pct_lookback}-day "
                "volatility percentile. Early bars will differ purely from warmup depth."
            )
    else:
        raise ValueError(f"unknown mode '{mode}' (expected 'inject' or 'recompute')")

    features = build_features(
        bars, h1, d1, usd, cfg,
        news_events=None,
        default_spread=inst.default_spread,
        htf_override=override,
    )
    return features, warnings


def compare(
    export: pd.DataFrame,
    features: pd.DataFrame,
    meta: dict,
    mode: str,
    max_examples: int = 12,
    skip_not_ready: bool = True,
) -> ParityReport:
    """Diff the two sides and build the report."""
    warnings: list[str] = []
    common = export.index.intersection(features.index)

    mt5 = export.loc[common]
    py = features.loc[common]

    mask = pd.Series(True, index=common)
    if skip_not_ready and "ready" in mt5.columns:
        mask &= mt5["ready"].fillna(0).astype(int) == 1
    # Python's own warmup: no ATR means no decision was possible
    mask &= py["atr_m15"].notna() & py["atr_d1"].notna()

    mt5, py = mt5.loc[mask], py.loc[mask]
    skipped = int(len(common) - mask.sum())

    diffs: list[ColumnDiff] = []
    mismatch_index = pd.DatetimeIndex([])

    for name in INT_COLUMNS:
        if name not in mt5.columns:
            continue
        left = mt5[name].astype("float64")
        right = py[name].astype("float64")
        usable = left.notna() & right.notna()
        bad = usable & (left != right)

        diffs.append(ColumnDiff(name, int(usable.sum()), int(bad.sum()), exact=True))
        mismatch_index = mismatch_index.union(bad[bad].index)

    price_tol = 2.0 * 10.0 ** -meta["digits"]
    for name in FLOAT_COLUMNS:
        if name not in mt5.columns or name not in py.columns:
            continue
        left = mt5[name].astype("float64")
        right = py[name].astype("float64")

        usable = left.notna() & right.notna()
        if not usable.any():
            diffs.append(ColumnDiff(name, 0, 0, exact=False))
            continue

        tol = price_tol if name in ("or_high", "or_low", "risk_dist") else 1e-6
        close = np.isclose(left[usable], right[usable], rtol=1e-6, atol=tol)
        delta = float(np.max(np.abs(left[usable] - right[usable]))) if usable.any() else np.nan

        diffs.append(
            ColumnDiff(name, int(usable.sum()), int((~close).sum()), delta, exact=False)
        )

        # a one-sided NaN is itself a disagreement worth naming
        one_sided = int((left.notna() ^ right.notna()).sum())
        if one_sided:
            warnings.append(f"'{name}': {one_sided} bar(s) present on one side only")

    # ---- what actually matters: do the same bars produce signals? --------
    mt5_sig = set(mt5.index[mt5["signal"].fillna(0).astype(int) != NEUTRAL]) if "signal" in mt5 else set()
    py_sig = set(py.index[py["signal"].astype(int) != NEUTRAL])
    signal_overlap = {
        "mt5": len(mt5_sig),
        "python": len(py_sig),
        "both": len(mt5_sig & py_sig),
        "mt5_only": sorted(mt5_sig - py_sig),
        "python_only": sorted(py_sig - mt5_sig),
    }

    # ---- indicator vs core, inside the terminal --------------------------
    indicator_check: dict = {}
    if "ic_signal" in mt5.columns:
        have = mt5["ic_signal"].notna()
        if have.any():
            disagree = int(
                (mt5.loc[have, "ic_signal"].astype(int) != mt5.loc[have, "signal"].astype(int)).sum()
            )
            indicator_check = {"compared": int(have.sum()), "mismatches": disagree}

    # ---- sanity checks ---------------------------------------------------
    if "or_high" in mt5.columns:
        first_or = mt5.index[mt5["or_high"].notna()]
        if len(first_or):
            minutes = first_or.hour * 60 + first_or.minute
            earliest = int(minutes.min())
            expected = Config().or_start_min + Config().or_length_min
            if earliest < expected:
                warnings.append(
                    f"opening range first appears at {earliest // 60:02d}:{earliest % 60:02d} UTC, "
                    f"before the expected {expected // 60:02d}:{expected % 60:02d}. "
                    "The server-to-UTC offset in the export is probably wrong."
                )

    offset = meta["gmt_offset_hours"]
    if abs(offset) > 12:
        warnings.append(f"implausible gmt_offset_hours={offset} in the export")

    # ---- worked examples -------------------------------------------------
    examples = None
    if len(mismatch_index):
        picked = mismatch_index.sort_values()[:max_examples]
        context = ["l0", "l1", "l2", "l3", "signal", "or_high", "or_low", "risk_dist"]
        frames = {}
        for name in context:
            if name in mt5.columns:
                frames[f"mt5_{name}"] = mt5.loc[picked, name]
            if name in py.columns:
                column = py.loc[picked, name]
                # l0 is boolean on the Python side; show it as 0/1 so the two
                # columns line up visually next to each other
                frames[f"py_{name}"] = column.astype(int) if column.dtype == bool else column
        examples = pd.DataFrame(frames)

    return ParityReport(
        mode=mode,
        meta=meta,
        rows_export=int(len(export)),
        rows_compared=int(len(mt5)),
        rows_skipped=skipped,
        diffs=diffs,
        signal_overlap=signal_overlap,
        indicator_check=indicator_check,
        warnings=warnings,
        examples=examples,
    )


def render(report: ParityReport) -> str:
    """Console report."""
    meta = report.meta
    lines = [
        "",
        f"PARITY CHECK - mode '{report.mode}'",
        "=" * 72,
        f"  export            {meta.get('path')}",
        f"  symbol            {meta.get('symbol', '?')}  (digits {meta.get('digits')})",
        f"  broker / server   {meta.get('broker', '?')} / {meta.get('server', '?')}",
        f"  server-to-UTC     {meta.get('gmt_offset_hours'):+.2f} h",
        f"  news filter       {meta.get('news_filter', '?')} "
        f"(calendar available: {meta.get('calendar_ok', '?')})",
        f"  rows in export    {report.rows_export:,}",
        f"  rows compared     {report.rows_compared:,}   (skipped {report.rows_skipped:,} warmup / not-ready)",
        "",
        "  GATES - must agree exactly",
        "  " + "-" * 70,
        f"  {'column':<14}{'compared':>10}{'mismatch':>10}{'match rate':>13}",
    ]

    for diff in report.diffs:
        if diff.name not in INT_COLUMNS:
            continue
        lines.append(
            f"  {diff.name:<14}{diff.compared:>10,}{diff.mismatches:>10,}"
            f"{diff.match_rate * 100:>12.3f}%"
        )

    float_diffs = [d for d in report.diffs if d.name not in INT_COLUMNS]
    if float_diffs:
        lines += [
            "",
            "  MEASUREMENTS - compared with tolerance",
            "  " + "-" * 70,
            f"  {'column':<14}{'compared':>10}{'outside tol':>13}{'max abs diff':>16}",
        ]
        for diff in float_diffs:
            delta = "n/a" if not np.isfinite(diff.max_abs_diff) else f"{diff.max_abs_diff:.3e}"
            lines.append(
                f"  {diff.name:<14}{diff.compared:>10,}{diff.mismatches:>13,}{delta:>16}"
            )

    overlap = report.signal_overlap
    if overlap:
        lines += [
            "",
            "  SIGNALS - the part that actually trades",
            "  " + "-" * 70,
            f"  terminal          {overlap['mt5']:,}",
            f"  python            {overlap['python']:,}",
            f"  agreed            {overlap['both']:,}",
            f"  terminal only     {len(overlap['mt5_only']):,}",
            f"  python only       {len(overlap['python_only']):,}",
        ]
        for label, key in (("terminal only", "mt5_only"), ("python only", "python_only")):
            if overlap[key]:
                shown = ", ".join(str(t) for t in overlap[key][:5])
                more = "" if len(overlap[key]) <= 5 else f"  (+{len(overlap[key]) - 5} more)"
                lines.append(f"    {label}: {shown}{more}")

    if report.indicator_check:
        check = report.indicator_check
        status = "AGREE" if check["mismatches"] == 0 else f"DISAGREE on {check['mismatches']:,}"
        lines += [
            "",
            f"  INDICATOR vs CORE inside the terminal: {status} "
            f"({check['compared']:,} bars via iCustom)",
        ]

    if report.examples is not None and not report.examples.empty:
        lines += ["", "  FIRST DISAGREEMENTS", "  " + "-" * 70]
        table = report.examples.to_string(float_format=lambda v: f"{v:.4f}")
        lines += ["  " + row for row in table.splitlines()]

    if report.warnings:
        lines += ["", "  WARNINGS", "  " + "-" * 70]
        lines += [f"  ! {w}" for w in report.warnings]

    verdict = report.verdict
    note = {
        "PASS": "every gate agrees on every compared bar.",
        "WARN": "a handful of bars disagree - inspect them before trusting either side.",
        "FAIL": "the implementations diverge materially. Do not trade this.",
        "INCONCLUSIVE": "nothing could be compared. Check the export and the overlap window.",
    }[verdict]

    lines += ["", "=" * 72, f"  VERDICT: {verdict} - {note}"]

    if verdict != "PASS" and report.mode == "inject":
        lines.append("  Inject mode isolates logic, so this is a real bug in one implementation.")
    elif verdict != "PASS" and report.mode == "recompute":
        lines.append("  Re-run with --mode inject: if that passes, the cause is data or")
        lines.append("  timeframe construction, not gate logic.")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# Synthetic export - lets the comparer be tested without a terminal
# --------------------------------------------------------------------------

EXPORT_COLUMNS = [
    "time_server", "time_utc", "open", "high", "low", "close", "tick_volume", "spread",
    "atr_m15", "atr_h1", "atr_d1", "adr20", "vol_pct",
    "close_d1", "ema_d1", "tsmom_ref", "usd_ema", "usd_ema_prev",
    "l0", "l1", "l2", "l3", "signal", "or_high", "or_low", "risk_dist", "stop",
    "ic_l0", "ic_l1", "ic_l2", "ic_l3", "ic_signal", "ready", "l0_reason", "veto_reason",
]


def write_synthetic_export(
    features: pd.DataFrame,
    path: str | Path,
    digits: int = 2,
    gmt_offset_hours: float = 0.0,
    symbol: str = "XAUUSD",
) -> Path:
    """Write a feature frame in the terminal's export format.

    This is how the comparer gets tested without MetaTrader: a Python run is
    dressed up as a terminal export, so a clean round trip MUST report PASS.
    If it does not, the comparer is broken - not the strategy.
    """
    path = Path(path)
    point = 10.0 ** -digits
    frame = features.copy()

    out = pd.DataFrame(index=frame.index)
    shift = pd.Timedelta(hours=gmt_offset_hours)
    out["time_server"] = (frame.index + shift).strftime("%Y.%m.%d %H:%M:%S")
    out["time_utc"] = frame.index.strftime("%Y.%m.%d %H:%M:%S")

    for name in ("open", "high", "low", "close"):
        out[name] = frame[name].round(digits)
    out["tick_volume"] = frame["tick_volume"].round(0).astype("int64")
    out["spread"] = (frame["spread"] / point).round(0).astype("int64")

    out["atr_m15"] = frame["atr_m15"]
    out["atr_h1"] = frame["atr_h1"]
    out["atr_d1"] = frame["atr_d1"]
    out["adr20"] = frame["adr"]
    out["vol_pct"] = frame["vol_pct"]
    for name in ("close_d1", "ema_d1", "tsmom_ref", "usd_ema", "usd_ema_prev"):
        out[name] = frame[name] if name in frame.columns else np.nan

    out["l0"] = frame["l0"].astype(int)
    for name in ("l1", "l2", "l3", "signal"):
        out[name] = frame[name].astype(int)

    out["or_high"] = frame["or_high"]
    out["or_low"] = frame["or_low"]
    out["risk_dist"] = frame["risk_dist"]
    out["stop"] = np.where(
        frame["signal"].astype(int) == 0, np.nan,
        frame["close"] - frame["signal"].astype(int) * frame["risk_dist"],
    )

    for name in ("l0", "l1", "l2", "l3", "signal"):
        out[f"ic_{name}"] = out[name]

    out["ready"] = frame["atr_m15"].notna().astype(int)
    out["l0_reason"] = ""
    out["veto_reason"] = ""

    header = [
        "# concord4_export v1 (SYNTHETIC - generated by write_synthetic_export)",
        f"# symbol={symbol} digits={digits} point={point:.10f}",
        "# broker=synthetic server=synthetic",
        f"# gmt_offset_hours={gmt_offset_hours:.2f}",
        f"# exported_utc=synthetic bars={len(out)}",
        "# news_filter=off calendar_ok=no",
    ]
    with path.open("w") as handle:
        handle.write("\n".join(header) + "\n")
        out[EXPORT_COLUMNS].to_csv(handle, index=False)
    return path
