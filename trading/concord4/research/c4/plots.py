"""Tearsheet plotting: equity curve, underwater drawdown, and supporting panels.

Matplotlib is an OPTIONAL dependency. The backtest, validation and parity
code never import this module, so a harness without matplotlib still runs
everything that produces numbers - only the pictures are unavailable.

Design notes, so later edits do not quietly undo them:

* Equity and drawdown share one x axis across stacked panels rather than
  sharing one plot with two y scales. A dual-axis chart invents a
  correlation out of the arbitrary alignment of its two scales.
* Colours come from a validated palette (blue slot 1, red slot 8). The two
  only ever share a plot in the R-multiple histogram, where they encode
  polarity - and that pair clears the colourblind separation floor in both
  modes (CVD dE 21.6 light / 19.2 dark, against a floor of 8).
* Dark mode is a selected set of steps for the dark surface, not an
  automatic inversion of the light one.
* Gridlines are solid hairlines. Dashed grids read as "projection" or
  "threshold" when they are just a grid.
* Labels are selective: the endpoint, the extreme, the thresholds that carry
  a decision. A number on every point goes unread.

Because a PNG cannot carry a tooltip, the numbers behind every panel stay
reachable through the printed summary and ``--save-equity`` / ``--save-trades``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .metrics import max_drawdown


class PlottingUnavailable(RuntimeError):
    """Raised when matplotlib is not installed."""


def _require_matplotlib():
    try:
        import matplotlib
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise PlottingUnavailable(
            "matplotlib is required for plotting but is not installed.\n"
            "  pip install matplotlib\n"
            "Everything else in the harness works without it."
        ) from exc

    matplotlib.use("Agg")  # file output only; never needs a display
    import matplotlib.pyplot as plt

    return matplotlib, plt


@dataclass(frozen=True)
class Theme:
    """Chart tokens for one mode. Both modes are chosen, not flipped."""

    surface: str
    page: str
    ink_primary: str
    ink_secondary: str
    ink_muted: str
    grid: str
    axis: str
    reference: str       # in-plot reference lines (zero, starting equity)
    series: str          # categorical slot 1 - equity
    loss: str            # categorical slot 8 - drawdown and losing trades
    good_text: str
    bad_text: str


THEMES = {
    "light": Theme(
        surface="#fcfcfb", page="#f9f9f7",
        ink_primary="#0b0b0b", ink_secondary="#52514e", ink_muted="#898781",
        grid="#e1e0d9", axis="#c3c2b7", reference="#898781",
        series="#2a78d6", loss="#e34948",
        good_text="#006300", bad_text="#d03b3b",
    ),
    "dark": Theme(
        surface="#1a1a19", page="#0d0d0d",
        ink_primary="#f0efec", ink_secondary="#c3c2b7", ink_muted="#898781",
        grid="#2c2c2a", axis="#383835", reference="#898781",
        series="#3987e5", loss="#e66767",
        good_text="#0ca30c", bad_text="#e66767",
    ),
}


def drawdown_series(equity: pd.Series) -> pd.Series:
    """Fractional drawdown from the running peak, <= 0 everywhere."""
    if equity.empty:
        return equity
    return (equity - equity.cummax()) / equity.cummax()


def _naive(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Matplotlib plots tz-naive timestamps without complaint."""
    return index.tz_localize(None) if index.tz is not None else index


def _style_axes(ax, theme: Theme, *, grid_axis: str = "y") -> None:
    ax.set_facecolor(theme.surface)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(theme.axis)
        ax.spines[side].set_linewidth(0.8)

    # solid hairlines - never dashed
    ax.grid(True, axis=grid_axis, color=theme.grid, linewidth=0.8,
            linestyle="-", alpha=1.0)
    ax.set_axisbelow(True)
    ax.tick_params(colors=theme.ink_muted, labelsize=8.5, length=0)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_color(theme.ink_muted)


def _pct_formatter(span: float):
    """Percent ticks with enough decimals to be distinct over ``span``.

    A fixed "%.0f%%" turns a 1% drawdown axis into "0%, -0%, -1%, -1%, -1%".
    The number of decimals has to follow the range, not a constant.
    """
    import matplotlib.ticker as mticker

    if not np.isfinite(span) or span <= 0:
        digits = 1
    elif span >= 0.20:
        digits = 0
    elif span >= 0.04:
        digits = 1
    else:
        digits = 2
    return mticker.FuncFormatter(lambda v, _: f"{v * 100:.{digits}f}%")


def _fmt_pct(value: float, digits: int = 1) -> str:
    return "n/a" if value is None or not np.isfinite(value) else f"{value * 100:.{digits}f}%"


def _fmt_num(value: float, digits: int = 2) -> str:
    return "n/a" if value is None or not np.isfinite(value) else f"{value:.{digits}f}"


# --------------------------------------------------------------------------
# panels
# --------------------------------------------------------------------------

def _stat_strip(ax, stats: dict, theme: Theme) -> None:
    """Hero numbers. When the story is one figure, a tile beats a chart."""
    ax.set_facecolor(theme.surface)
    ax.axis("off")

    total = stats.get("total_return", np.nan)
    tiles = [
        ("Total return", f"{'+' if np.isfinite(total) and total >= 0 else ''}{_fmt_pct(total)}",
         theme.good_text if np.isfinite(total) and total >= 0 else theme.bad_text),
        ("CAGR", _fmt_pct(stats.get("cagr", np.nan)), theme.ink_primary),
        ("Sharpe", _fmt_num(stats.get("sharpe", np.nan)), theme.ink_primary),
        ("Max drawdown", _fmt_pct(stats.get("max_drawdown", np.nan)), theme.ink_primary),
        ("Profit factor", _fmt_num(stats.get("profit_factor", np.nan)), theme.ink_primary),
        ("Trades", f"{stats.get('trades', 0):,}", theme.ink_primary),
        ("Expectancy", f"{_fmt_num(stats.get('expectancy_r', np.nan))} R", theme.ink_primary),
    ]

    for i, (label, value, colour) in enumerate(tiles):
        x = i / len(tiles)
        ax.text(x, 0.62, value, transform=ax.transAxes, color=colour,
                fontsize=15, fontweight="bold", va="center", ha="left")
        # matplotlib has no letter-spacing, so the spacing is baked into the string
        ax.text(x, 0.16, " ".join(label.upper()), transform=ax.transAxes,
                color=theme.ink_muted, fontsize=6.5, va="center", ha="left")


def _equity_panel(ax, equity: pd.Series, stats: dict, theme: Theme,
                  log_scale: bool = False) -> None:
    """One series, so no legend box: the title names it."""
    import matplotlib.ticker as mticker

    _style_axes(ax, theme)
    x = _naive(equity.index)

    initial = stats.get("initial_equity", float(equity.iloc[0]))
    ax.axhline(initial, color=theme.reference, linewidth=0.8, zorder=1)

    depth, peak_at, trough_at = max_drawdown(equity)
    if peak_at is not None and trough_at is not None:
        # shade the worst peak-to-trough span: the extreme is worth labelling
        ax.axvspan(_naive(pd.DatetimeIndex([peak_at]))[0],
                   _naive(pd.DatetimeIndex([trough_at]))[0],
                   color=theme.loss, alpha=0.10, linewidth=0, zorder=1)

    ax.plot(x, equity.to_numpy(), color=theme.series, linewidth=1.6,
            solid_capstyle="round", zorder=3)

    if peak_at is not None and trough_at is not None:
        # placed only now: before the line is drawn the y limits are not final,
        # and an axes-fraction y keeps the label inside the panel regardless
        mid = peak_at + (trough_at - peak_at) / 2
        ax.annotate(f"max DD {_fmt_pct(-depth)}",
                    xy=(_naive(pd.DatetimeIndex([mid]))[0], 0.96),
                    xycoords=("data", "axes fraction"),
                    color=theme.loss, fontsize=8.5, ha="center", va="top", zorder=5)

    # direct-label the endpoint only
    final = float(equity.iloc[-1])
    ax.annotate(f"{final:,.0f}", xy=(x[-1], final), xytext=(6, 0),
                textcoords="offset points", color=theme.series,
                fontsize=9, fontweight="bold", va="center", zorder=5)

    if log_scale:
        ax.set_yscale("log")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_title("Equity curve, marked to market", color=theme.ink_primary,
                 fontsize=11, fontweight="bold", loc="left", pad=10)
    ax.margins(x=0.02)


def _underwater_panel(ax, equity: pd.Series, theme: Theme) -> None:
    """Drawdown hangs below zero, which is where a reader expects to find it."""
    import matplotlib.ticker as mticker

    _style_axes(ax, theme)
    drawdown = drawdown_series(equity)
    x = _naive(drawdown.index)
    values = drawdown.to_numpy()

    ax.fill_between(x, values, 0.0, color=theme.loss, alpha=0.18, linewidth=0, zorder=2)
    ax.plot(x, values, color=theme.loss, linewidth=1.2, zorder=3)
    ax.axhline(0.0, color=theme.reference, linewidth=0.8, zorder=1)

    if len(drawdown) and np.isfinite(values).any():
        trough = int(np.nanargmin(values))
        ax.plot([x[trough]], [values[trough]], marker="o", markersize=5,
                color=theme.loss, markeredgecolor=theme.surface,
                markeredgewidth=2, zorder=4)   # 2px surface ring, not a border
        span = abs(float(np.nanmin(values)))
        digits = 0 if span >= 0.20 else (1 if span >= 0.04 else 2)
        ax.annotate(f"{values[trough] * 100:.{digits}f}%",
                    xy=(x[trough], values[trough]), xytext=(8, 3),
                    textcoords="offset points", color=theme.loss,
                    fontsize=8.5, fontweight="bold", va="bottom", zorder=5)

    floor = min(float(np.nanmin(values)) * 1.25, -0.005) if len(values) else -0.01
    top = max(0.0, float(np.nanmax(values)) if len(values) else 0.0)
    ax.set_ylim(floor, top)
    ax.yaxis.set_major_formatter(_pct_formatter(top - floor))

    ax.set_title("Underwater - distance below the running peak",
                 color=theme.ink_primary, fontsize=10, fontweight="bold",
                 loc="left", pad=8)
    ax.margins(x=0.02)


def _r_histogram(ax, trades: pd.DataFrame, stats: dict, theme: Theme) -> None:
    """Polarity, so a diverging pair: wins one pole, losses the other."""
    _style_axes(ax, theme)
    ax.set_title("R-multiple distribution", color=theme.ink_primary,
                 fontsize=10, fontweight="bold", loc="left", pad=8)

    if trades is None or trades.empty or "r_multiple" not in trades.columns:
        ax.text(0.5, 0.5, "no trades", transform=ax.transAxes, ha="center",
                va="center", color=theme.ink_muted, fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])
        return

    values = trades["r_multiple"].replace([np.inf, -np.inf], np.nan).dropna().to_numpy()
    if values.size == 0:
        ax.text(0.5, 0.5, "no R data", transform=ax.transAxes, ha="center",
                va="center", color=theme.ink_muted, fontsize=9)
        return

    span = max(abs(values.min()), abs(values.max()), 1.0)
    edges = np.linspace(-span, span, 25)
    counts, edges = np.histogram(values, bins=edges)
    centres = (edges[:-1] + edges[1:]) / 2
    width = (edges[1] - edges[0])

    colours = [theme.series if c > 0 else theme.loss for c in centres]
    # the surface-coloured edge is the 2px gap between adjacent bars
    ax.bar(centres, counts, width=width, color=colours,
           edgecolor=theme.surface, linewidth=1.4, zorder=3)

    ax.axvline(0.0, color=theme.reference, linewidth=0.8, zorder=2)

    expectancy = stats.get("expectancy_r", np.nan)
    if np.isfinite(expectancy):
        ax.axvline(expectancy, color=theme.ink_secondary, linewidth=1.2, zorder=4)
        ax.annotate(f"expectancy {expectancy:+.2f} R", xy=(expectancy, ax.get_ylim()[1]),
                    xytext=(4, -4), textcoords="offset points",
                    color=theme.ink_secondary, fontsize=8, va="top")

    ax.set_xlabel("R multiple", color=theme.ink_muted, fontsize=8.5)
    ax.set_ylabel("trades", color=theme.ink_muted, fontsize=8.5)


def _mc_panel(ax, mc: dict, observed_dd: float, theme: Theme) -> None:
    """One distribution, so one hue. Magnitude, not identity."""
    _style_axes(ax, theme)
    ax.set_title("Bootstrapped max drawdown", color=theme.ink_primary,
                 fontsize=10, fontweight="bold", loc="left", pad=8)

    samples = mc.get("samples") if mc else None
    if samples is None or len(samples) == 0:
        ax.text(0.5, 0.5, "not run", transform=ax.transAxes, ha="center",
                va="center", color=theme.ink_muted, fontsize=9)
        ax.set_xticks([]); ax.set_yticks([])
        return

    samples = np.asarray(samples, dtype="float64")
    ax.hist(samples * 100, bins=40, color=theme.series, alpha=0.75,
            edgecolor=theme.surface, linewidth=0.8, zorder=3)

    p95 = float(np.percentile(samples, 95)) * 100
    ax.axvline(p95, color=theme.loss, linewidth=1.4, zorder=5)
    ax.annotate(f"p95 {p95:.1f}%", xy=(p95, ax.get_ylim()[1]), xytext=(4, -4),
                textcoords="offset points", color=theme.loss, fontsize=8, va="top")

    if np.isfinite(observed_dd):
        ax.axvline(observed_dd * 100, color=theme.ink_secondary, linewidth=1.2, zorder=4)
        ax.annotate(f"observed {observed_dd * 100:.1f}%",
                    xy=(observed_dd * 100, ax.get_ylim()[1] * 0.80),
                    xytext=(4, 0), textcoords="offset points",
                    color=theme.ink_secondary, fontsize=8, va="top")

    ax.set_xlabel("max drawdown, % (size against p95, not the median)",
                  color=theme.ink_muted, fontsize=8.5)
    ax.set_ylabel("paths", color=theme.ink_muted, fontsize=8.5)


# --------------------------------------------------------------------------
# the tearsheet
# --------------------------------------------------------------------------

def tearsheet(
    equity: pd.Series,
    trades: pd.DataFrame,
    stats: dict,
    path: str | Path,
    title: str = "CONCORD-4",
    subtitle: str | None = None,
    theme: str = "light",
    log_scale: bool = False,
    monte_carlo: dict | None = None,
    dpi: int = 144,
) -> Path:
    """Render the tearsheet to ``path`` and return it."""
    _, plt = _require_matplotlib()

    if theme not in THEMES:
        raise ValueError(f"unknown theme '{theme}' (expected {sorted(THEMES)})")
    tokens = THEMES[theme]

    if equity is None or equity.empty:
        raise ValueError("cannot plot an empty equity curve")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with plt.rc_context({
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Segoe UI", "Helvetica", "Arial"],
        "figure.facecolor": tokens.page,
        "savefig.facecolor": tokens.page,
        "axes.unicode_minus": False,
    }):
        fig = plt.figure(figsize=(12.0, 10.6))
        grid = fig.add_gridspec(
            4, 2, height_ratios=[0.42, 2.5, 1.15, 1.7],
            hspace=0.52, wspace=0.18,
            left=0.07, right=0.955, top=0.915, bottom=0.065,
        )

        fig.text(0.07, 0.967, title, color=tokens.ink_primary,
                 fontsize=16, fontweight="bold", ha="left", va="center")
        if subtitle:
            fig.text(0.07, 0.938, subtitle, color=tokens.ink_muted,
                     fontsize=9, ha="left", va="center")

        _stat_strip(fig.add_subplot(grid[0, :]), stats, tokens)

        ax_equity = fig.add_subplot(grid[1, :])
        _equity_panel(ax_equity, equity, stats, tokens, log_scale=log_scale)

        ax_under = fig.add_subplot(grid[2, :], sharex=ax_equity)
        _underwater_panel(ax_under, equity, tokens)
        # the panels share an axis, so only the lower one carries date labels
        ax_equity.tick_params(labelbottom=False)

        _r_histogram(fig.add_subplot(grid[3, 0]), trades, stats, tokens)

        observed = stats.get("max_drawdown", np.nan)
        _mc_panel(fig.add_subplot(grid[3, 1]), monte_carlo or {}, observed, tokens)

        fig.savefig(path, dpi=dpi, facecolor=tokens.page)
        plt.close(fig)

    return path


def tearsheet_both_themes(
    equity: pd.Series,
    trades: pd.DataFrame,
    stats: dict,
    path: str | Path,
    **kwargs,
) -> list[Path]:
    """Write ``<name>.png`` and ``<name>-dark.png``."""
    path = Path(path)
    kwargs.pop("theme", None)
    light = tearsheet(equity, trades, stats, path, theme="light", **kwargs)
    dark = tearsheet(equity, trades, stats,
                     path.with_name(f"{path.stem}-dark{path.suffix}"),
                     theme="dark", **kwargs)
    return [light, dark]
