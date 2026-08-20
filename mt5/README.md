# Turtle Trading indicator for MetaTrader 5

`Indicators/TurtleTrading.mq5` — the Dennis/Eckhardt Turtle system drawn on a chart:
Donchian breakout entries, opposite-channel exits, the Wilder ATR "N" volatility
unit, 2N stops and N-based position sizing.

## Install

The folder layout here mirrors MT5's own, so installing is a copy.

1. In MetaTrader 5: **File → Open Data Folder**. This opens your terminal's data
   directory (`…/Terminal/<hash>/`).
2. Copy `Indicators/TurtleTrading.mq5` into `MQL5/Indicators/` inside it.
3. Back in MT5, open **MetaEditor** (F4), find `TurtleTrading.mq5` in the
   Navigator, and press **F7** to compile. You should get `0 errors, 0 warnings`
   and a `TurtleTrading.ex5` next to the source.
4. In MT5, refresh the Navigator (right-click → Refresh), then drag
   **Indicators → TurtleTrading** onto a chart.

Daily charts are what the original system was designed for.

## Inputs

| Input | Default | Meaning |
| --- | --- | --- |
| `InpSystem` | System 1 | System 1 = 20/10 with the winner filter; System 2 = 55/20, every breakout taken; Custom = use the periods below |
| `InpEntryPeriod` / `InpExitPeriod` | 20 / 10 | Channel lengths, used only when `InpSystem` is Custom |
| `InpSignalMode` | Intrabar | Intrabar: the bar's high/low piercing the channel triggers. Close: the bar must close beyond it |
| `InpATRPeriod` | 20 | Period for N (Wilder ATR) |
| `InpStopN` | 2.0 | Stop distance from entry, in N |
| `InpShowPanel` | true | Draw the info panel in the top-left |
| `InpRiskPercent` | 1.0 | Equity risked per 1N — the classic turtle unit |
| `InpMaxUnits` | 4 | Max units, shown in the panel |
| `InpAddEveryN` | 0.5 | Pyramid spacing in N, shown in the panel |
| `InpAlertPopup` / `InpAlertPush` | false | Alert once per bar on a new signal |

## What it plots

- **Entry channel** (solid blue) — the 20- or 55-bar Donchian high/low.
- **Exit channel** (dotted grey) — the 10- or 20-bar channel that closes trades.
- **Arrows** — green up / red down for entries, cyan / orange crosses for exits.
- **Panel** — N, unit size in lots for your account, position state, entry, stop,
  the next pyramid level, and whether the next breakout will be taken or skipped.

## Buffers, for `iCustom`

`0` entry upper, `1` entry lower, `2` exit upper, `3` exit lower, `4` long entry,
`5` short entry, `6` long exit, `7` short exit, `8` N, `9` TR sum (internal),
`10` state, `11` entry price, `12` stop, `13` last-trade-lost flag.

State in buffer 10: `0` flat, `±1` long/short, `±2` a *phantom* trade — a breakout
System 1 skipped, tracked only so the next filter decision is right.

## Details worth knowing

- **Channels exclude the signal bar.** The 20-day high means the high of the 20
  bars *before* the current one. Including the current bar makes a breakout
  impossible by definition; this is the most common way this indicator is got wrong.
- **The System 1 filter is fully modelled.** When a breakout is skipped because the
  last one won, the skipped trade is still tracked to its exit so the *next* filter
  decision is correct. Those phantom trades draw no arrows.
- **Exits are checked before entries**, and a bar never both enters and exits.
- **Intrabar fills are pessimistic on ordering**: if a bar hits both the 2N stop and
  the exit channel, the level that price would reach first is used.
- **Position state lives in buffers**, not globals, so any bar can be recalculated
  in place — the values never drift as new bars arrive.
- This is an **indicator, not an EA**. It signals and sizes; it places no orders.

## Tests

`tests/` holds a Python port of the indicator's logic plus its test suite. The
port mirrors `OnCalculate` line for line, so the tests exercise the real algorithm.

```bash
cd tests
python3 structcheck.py   # buffer/plot/property wiring in the .mq5
python3 test_turtle.py   # ATR, channels, state machine, filter, edge cases
python3 test_bounds.py   # array-out-of-range sweep under MQL5 indexing rules
```

`test_bounds.py` wraps every buffer in a list type that raises on a negative or
out-of-range index, the way MQL5 does and Python normally does not, then sweeps
288 parameter/data combinations.

These cover the algorithm. They are not a substitute for the MetaEditor compile in
step 3 above, which is the only thing that checks MQL5 syntax and API use.
