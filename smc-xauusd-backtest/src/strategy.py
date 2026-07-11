"""SMC strategy for backtesting.py.

Trade logic (long side; shorts are mirrored):

1. HTF alignment - H4 market structure bias must be bullish (+1).
2a. Order-block entry ("ob"): when an H1 close breaks the last confirmed
    swing high (bullish BOS), the last bearish candle of the leg becomes a
    bullish order block.  A limit order is placed at the top of that zone,
    optionally only if the zone sits in the *discount* half of the current
    dealing range.  Stop goes under the zone minus an ATR buffer; target is
    a fixed R multiple.
2b. Liquidity-sweep entry ("sweep"): when a bar wicks below the last
    confirmed swing low but closes back above it (sell-side liquidity grab)
    while HTF bias is bullish, buy at market.  Stop under the sweep wick.
3. Risk per trade is a fixed fraction of equity, converted to units via the
   stop distance.  One position / one pending entry at a time.
4. Pending limit orders expire after `order_expiry` bars or when the HTF
   bias flips; open positions are closed on a bias flip (CHoCH = setup
   invalidation).
"""

from __future__ import annotations

import numpy as np
from backtesting import Strategy


class SmcStrategy(Strategy):
    # --- tunables (picked up by Backtest.optimize as well) ---
    mode = "both"            # "ob", "sweep" or "both"
    bias_tf = "h4"           # HTF used for structure bias: "d1" or "h4"
    rr = 2.0                 # take-profit in R multiples (tp_mode="rr")
    tp_mode = "rr"           # "rr" = fixed R multiple; "liquidity" = opposing pool
    min_rr = 1.5             # tp_mode="liquidity": skip trades paying less than this
    liq_lookback = 100       # bars scanned for the opposing liquidity pool
    tp_liq_buf_atr = 0.1     # exit this many ATRs in front of the pool
    require_fvg = False      # only trade OBs whose impulse left a fair value gap
    be_at_r = 0.0            # move stop to breakeven at this R multiple (0 = off)
    risk_pct = 0.01          # fraction of equity risked per trade
    sl_buf_atr = 0.25        # extra ATR under/over the invalidation level
    ob_lookback = 15         # bars scanned back for the order-block candle
    ob_max_age = 96          # bars an untouched OB zone stays valid
    order_expiry = 48        # bars a pending limit order stays working
    use_pd_filter = True     # only take OB longs in discount / shorts in premium
    exit_on_flip = True      # close position when HTF bias flips against it
    margin_frac = 0.05       # must match Backtest(margin=...); caps position size
    sessions = "9-12,15-18"  # entry hours (server time) ~ London/NY kill zones; "" = all

    def init(self):
        self._hours: set[int] | None = None
        if self.sessions:
            self._hours = set()
            for part in self.sessions.split(","):
                a, b = (int(x) for x in part.split("-"))
                self._hours.update(range(a, b + 1))
        self._bull_obs: list[dict] = []   # {"top","bot","born"}
        self._bear_obs: list[dict] = []
        self._broken_high: set[float] = set()
        self._broken_low: set[float] = set()
        self._swept: set[tuple] = set()
        self._pending_born: int | None = None

    # ---------- helpers ----------

    def _units(self, entry: float, sl: float) -> int:
        risk_cash = self.equity * self.risk_pct
        dist = abs(entry - sl)
        if dist <= 0:
            return 0
        units = int(risk_cash / dist)
        max_notional = self.equity * 0.8 / self.margin_frac
        return max(0, min(units, int(max_notional / entry)))

    def _entry_orders(self):
        return [o for o in self.orders if not o.is_contingent]

    def _has_fvg(self, j: int, i: int, bullish: bool) -> bool:
        """True if the impulse leg j..i contains a 3-candle fair value gap."""
        hi, lo = self.data.High, self.data.Low
        for m in range(max(j, 1), i):
            if bullish and lo[m + 1] > hi[m - 1]:
                return True
            if not bullish and hi[m + 1] < lo[m - 1]:
                return True
        return False

    def _target(self, entry: float, stop: float, atr_: float,
                is_long: bool) -> float | None:
        """Take-profit price, or None if the trade doesn't pay enough.

        tp_mode="rr": fixed R multiple.  tp_mode="liquidity": exit just in
        front of the opposing liquidity pool (highest high / lowest low of
        the last `liq_lookback` bars), and skip the trade entirely when that
        pool is closer than `min_rr` times the risk.
        """
        risk = abs(entry - stop)
        if self.tp_mode == "rr":
            return entry + self.rr * risk if is_long else entry - self.rr * risk
        lb = min(self.liq_lookback, len(self.data))
        if is_long:
            pool = self.data.High[-lb:].max()
            tp = pool - self.tp_liq_buf_atr * atr_
            return tp if tp - entry >= self.min_rr * risk else None
        pool = self.data.Low[-lb:].min()
        tp = pool + self.tp_liq_buf_atr * atr_
        return tp if entry - tp >= self.min_rr * risk else None

    def _last_opposite_candle(self, i: int, bearish: bool) -> int | None:
        """Bar index of the most recent bearish (or bullish) candle before i."""
        o, c = self.data.Open, self.data.Close
        for j in range(i - 1, max(-1, i - 1 - self.ob_lookback), -1):
            if bearish and c[j] < o[j]:
                return j
            if not bearish and c[j] > o[j]:
                return j
        return None

    # ---------- main loop ----------

    def next(self):
        i = len(self.data) - 1
        close = self.data.Close[-1]
        low = self.data.Low[-1]
        high = self.data.High[-1]
        atr_ = self.data.Atr[-1]
        bias = (self.data.BiasD1 if self.bias_tf == "d1"
                else self.data.BiasH4)[-1]
        sh, shid = self.data.LastSH[-1], self.data.LastSHId[-1]
        sl_, slid = self.data.LastSL[-1], self.data.LastSLId[-1]

        # --- maintain order blocks from H1 breaks of structure ---
        if not np.isnan(sh) and shid not in self._broken_high and close > sh:
            self._broken_high.add(shid)
            j = self._last_opposite_candle(i, bearish=True)
            if j is not None:
                self._bull_obs.append(
                    {"top": self.data.High[j], "bot": self.data.Low[j],
                     "born": i, "fvg": self._has_fvg(j, i, bullish=True)})
        if not np.isnan(sl_) and slid not in self._broken_low and close < sl_:
            self._broken_low.add(slid)
            j = self._last_opposite_candle(i, bearish=False)
            if j is not None:
                self._bear_obs.append(
                    {"top": self.data.High[j], "bot": self.data.Low[j],
                     "born": i, "fvg": self._has_fvg(j, i, bullish=False)})

        # expire / invalidate zones
        self._bull_obs = [z for z in self._bull_obs
                          if i - z["born"] <= self.ob_max_age and close >= z["bot"]]
        self._bear_obs = [z for z in self._bear_obs
                          if i - z["born"] <= self.ob_max_age and close <= z["top"]]

        # --- move stops to breakeven once the trade is be_at_r in profit ---
        if self.be_at_r > 0:
            for t in self.trades:
                if t.sl is None:
                    continue
                if t.is_long and t.sl < t.entry_price:
                    r = t.entry_price - t.sl
                    if high >= t.entry_price + self.be_at_r * r:
                        t.sl = t.entry_price
                elif t.is_short and t.sl > t.entry_price:
                    r = t.sl - t.entry_price
                    if low <= t.entry_price - self.be_at_r * r:
                        t.sl = t.entry_price

        # --- manage open position / pending orders on bias flip ---
        if self.exit_on_flip and self.position:
            if (self.position.is_long and bias < 0) or \
               (self.position.is_short and bias > 0):
                self.position.close()
        for o in self._entry_orders():
            expired = (self._pending_born is not None
                       and i - self._pending_born > self.order_expiry)
            wrong_side = (o.is_long and bias < 0) or (not o.is_long and bias > 0)
            if expired or wrong_side:
                o.cancel()
                self._pending_born = None

        if self.position or self._entry_orders():
            return

        # session (kill-zone) filter for new entries
        if self._hours is not None and \
                self.data.index[-1].hour not in self._hours:
            return

        mid = (sh + sl_) / 2 if not (np.isnan(sh) or np.isnan(sl_)) else np.nan

        # --- sweep entries (market) ---
        if self.mode in ("sweep", "both"):
            if bias > 0 and not np.isnan(sl_) and ("L", slid) not in self._swept \
                    and low < sl_ and close > sl_:
                self._swept.add(("L", slid))
                stop = low - self.sl_buf_atr * atr_
                units = self._units(close, stop)
                tp = self._target(close, stop, atr_, is_long=True)
                if units > 0 and tp is not None:
                    self.buy(size=units, sl=stop, tp=tp, tag="sweep")
                    self._pending_born = i
                    return
            if bias < 0 and not np.isnan(sh) and ("H", shid) not in self._swept \
                    and high > sh and close < sh:
                self._swept.add(("H", shid))
                stop = high + self.sl_buf_atr * atr_
                units = self._units(close, stop)
                tp = self._target(close, stop, atr_, is_long=False)
                if units > 0 and tp is not None:
                    self.sell(size=units, sl=stop, tp=tp, tag="sweep")
                    self._pending_born = i
                    return

        # --- order-block retest entries (limit) ---
        if self.mode in ("ob", "both"):
            if bias > 0 and self._bull_obs:
                z = self._bull_obs[-1]
                if self.require_fvg and not z["fvg"]:
                    self._bull_obs.pop()   # low-quality impulse, discard
                    return
                entry = z["top"]
                in_discount = np.isnan(mid) or entry <= mid
                if close > entry and (not self.use_pd_filter or in_discount):
                    stop = z["bot"] - self.sl_buf_atr * atr_
                    units = self._units(entry, stop)
                    tp = self._target(entry, stop, atr_, is_long=True)
                    if units > 0 and tp is not None:
                        self.buy(size=units, limit=entry, sl=stop, tp=tp,
                                 tag="ob")
                        self._pending_born = i
                        self._bull_obs.pop()
            elif bias < 0 and self._bear_obs:
                z = self._bear_obs[-1]
                if self.require_fvg and not z["fvg"]:
                    self._bear_obs.pop()   # low-quality impulse, discard
                    return
                entry = z["bot"]
                in_premium = np.isnan(mid) or entry >= mid
                if close < entry and (not self.use_pd_filter or in_premium):
                    stop = z["top"] + self.sl_buf_atr * atr_
                    units = self._units(entry, stop)
                    tp = self._target(entry, stop, atr_, is_long=False)
                    if units > 0 and tp is not None:
                        self.sell(size=units, limit=entry, sl=stop, tp=tp,
                                  tag="ob")
                        self._pending_born = i
                        self._bear_obs.pop()
