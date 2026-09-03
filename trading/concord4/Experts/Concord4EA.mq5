//+------------------------------------------------------------------+
//|                                                   Concord4EA.mq5 |
//|          CONCORD-4 hybrid breakout system - XAUUSD, M15          |
//+------------------------------------------------------------------+
//| Entry logic lives entirely in Concord4Core.mqh, shared with the   |
//| Concord4 indicator. This file is the execution and risk engine:   |
//| sizing, partials, trailing, the time stop, and the circuit        |
//| breakers that are the actual drawdown control.                    |
//|                                                                   |
//| Defaults: 0.5% risk per trade, 10% annualised volatility target,  |
//| whichever is SMALLER. Daily stop 2R, weekly 4R, -8% halves size.  |
//+------------------------------------------------------------------+
#property copyright "CONCORD-4"
#property version   "1.00"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Concord4Core.mqh>

//--- L0 tradability
input group                "L0  Tradability";
input int    InpSessionAStart   = 420;    // Session A start (min from 00:00 UTC) 420 = 07:00
input int    InpSessionAEnd     = 660;    // Session A end   (min) 660 = 11:00
input int    InpSessionBStart   = 780;    // Session B start (min) 780 = 13:00
input int    InpSessionBEnd     = 960;    // Session B end   (min) 960 = 16:00
input double InpMaxSpreadAtr    = 0.06;   // Max spread as fraction of ATR(M15)
input bool   InpUseNewsFilter   = true;   // Block around high-impact news
input int    InpNewsPadMinutes  = 15;     // News blackout half-width (minutes)
input int    InpVolPctLow       = 20;     // ATR(D1) percentile floor
input int    InpVolPctHigh      = 90;     // ATR(D1) percentile ceiling
input int    InpVolPctLookback  = 250;    // Percentile sample size (days)

//--- L1 regime
input group                "L1  Regime bias (D1)";
input int    InpEmaD1Period     = 50;     // D1 EMA period
input int    InpTsmomDays       = 63;     // Time-series momentum lookback (days)

//--- L2 intermarket
input group                "L2  Intermarket (USD basket)";
input string InpSymbolSuffix    = "";     // Broker symbol suffix ("" = auto-detect)
input int    InpUsdEmaPeriod    = 20;     // USD index EMA period (H1 bars)
input int    InpUsdSlopeBars    = 3;      // USD index slope lookback (H1 bars)

//--- L3 trigger
input group                "L3  Opening-range trigger";
input int    InpOrStartMin      = 420;    // Opening range start (min from 00:00 UTC)
input int    InpOrLengthMin     = 30;     // Opening range length (minutes)
input double InpBreakoutAtrK    = 0.15;   // Breakout buffer beyond OR edge (x ATR)
input double InpMinBarRangeAtr  = 0.80;   // Min break-bar range (x ATR)
input double InpMinVolMult      = 1.50;   // Min break-bar tick volume (x 20-bar avg)
input double InpMaxOrWidthAdr   = 1.20;   // Max OR width (x ADR20)
input double InpMaxChaseAtr     = 2.00;   // Max distance beyond OR edge (x ATR)

//--- risk geometry
input group                "Risk geometry";
input double InpStopStructBuf   = 0.10;   // Stop buffer beyond opposite OR edge (x ATR)
input double InpStopMinAtr      = 1.50;   // Minimum stop distance (x ATR)
input double InpStopMaxAtr      = 2.00;   // Maximum stop distance (x ATR) - skip if wider

//--- sizing
input group                "Position sizing";
input double InpRiskPercent     = 0.50;   // Risk per trade (% of equity)
input double InpVolTargetAnnual = 10.0;   // Annualised volatility target (%)
input bool   InpUseVolTarget    = true;   // Cap size by the volatility target

//--- exits
input group                "Exits";
input double InpPartialAtR      = 1.00;   // Take partial at this multiple of R
input double InpPartialFraction = 0.50;   // Fraction of the position to close
input double InpBeSpreadMult    = 2.00;   // Breakeven offset as a multiple of spread
input double InpChandelierAtr   = 2.80;   // Trail distance (x ATR H1)
input int    InpFlatMinuteUtc   = 1200;   // Close everything at this UTC minute (1200 = 20:00)

//--- circuit breakers
input group                "Circuit breakers";
input double InpDailyLossR      = 2.00;   // Halt for the day after losing this many R
input double InpWeeklyLossR     = 4.00;   // Halt for the week after losing this many R
input int    InpMaxEntriesDay   = 2;      // Max entries per UTC day
input double InpBreakerDdPct    = 8.00;   // Equity drawdown that halves size (%)
input double InpBreakerSizeMult = 0.50;   // Size multiplier while the breaker is on

//--- plumbing
input group                "Execution";
input ENUM_C4_GMT_MODE InpGmtMode = C4_GMT_AUTO;  // Server-to-UTC offset mode
input int    InpGmtOffsetHours  = 0;      // Manual offset (hours, if mode = Manual)
input long   InpMagic           = 40412;  // Magic number
input int    InpSlippagePoints  = 30;     // Max deviation (points)
input bool   InpDryRun          = false;  // Log signals without sending orders

//--- forward declarations: OnInit uses these before their definitions
void   SaveAnchors();
void   LoadAnchors();
double SizeMultiplier();
double NormalizeVolume(const double raw);

CTrade        g_trade;
CPositionInfo g_pos;
C4Config      g_cfg;

datetime g_lastBarTime  = 0;
datetime g_lastDayStart = 0;
double   g_dayStartEquity = 0.0;
double   g_peakEquity     = 0.0;

//+------------------------------------------------------------------+
//| Per-position bookkeeping lives in terminal globals keyed by       |
//| ticket, so a restart mid-trade does not lose the initial R or     |
//| forget that a partial was already taken.                          |
//+------------------------------------------------------------------+
string GvName(const ulong ticket, const string field)
  { return StringFormat("C4_%d_%I64u_%s", (int)InpMagic, ticket, field); }

void   GvSet(const ulong t, const string f, const double v) { GlobalVariableSet(GvName(t, f), v); }
double GvGet(const ulong t, const string f, const double def = 0.0)
  {
   double v;
   if(GlobalVariableGet(GvName(t, f), v)) return v;
   return def;
  }
void GvClear(const ulong t)
  {
   string fields[3] = {"R", "V0", "PART"};
   for(int i = 0; i < 3; i++) GlobalVariableDel(GvName(t, fields[i]));
  }

//+------------------------------------------------------------------+
void BuildConfig()
  {
   C4DefaultConfig(g_cfg);
   g_cfg.symbol             = _Symbol;
   g_cfg.sessionAStartMin   = InpSessionAStart;
   g_cfg.sessionAEndMin     = InpSessionAEnd;
   g_cfg.sessionBStartMin   = InpSessionBStart;
   g_cfg.sessionBEndMin     = InpSessionBEnd;
   g_cfg.maxSpreadAtr       = InpMaxSpreadAtr;
   g_cfg.useNewsFilter      = InpUseNewsFilter;
   g_cfg.newsPadMinutes     = InpNewsPadMinutes;
   g_cfg.volPctLow          = InpVolPctLow;
   g_cfg.volPctHigh         = InpVolPctHigh;
   g_cfg.volPctLookback     = InpVolPctLookback;
   g_cfg.emaD1Period        = InpEmaD1Period;
   g_cfg.tsmomDays          = InpTsmomDays;
   g_cfg.symbolSuffix       = InpSymbolSuffix;
   g_cfg.usdEmaPeriod       = InpUsdEmaPeriod;
   g_cfg.usdSlopeBars       = InpUsdSlopeBars;
   g_cfg.orStartMin         = InpOrStartMin;
   g_cfg.orLengthMin        = InpOrLengthMin;
   g_cfg.breakoutAtrK       = InpBreakoutAtrK;
   g_cfg.minBarRangeAtr     = InpMinBarRangeAtr;
   g_cfg.minVolMult         = InpMinVolMult;
   g_cfg.maxOrWidthAdr      = InpMaxOrWidthAdr;
   g_cfg.maxChaseAtr        = InpMaxChaseAtr;
   g_cfg.stopStructBufAtr   = InpStopStructBuf;
   g_cfg.stopMinAtr         = InpStopMinAtr;
   g_cfg.stopMaxAtr         = InpStopMaxAtr;
   g_cfg.gmtMode            = InpGmtMode;
   g_cfg.gmtManualOffsetHrs = InpGmtOffsetHours;
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   BuildConfig();
   if(!C4Init(g_cfg)) return INIT_FAILED;

   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpSlippagePoints);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   g_trade.SetAsyncMode(false);

   LoadAnchors();

   if(Period() != PERIOD_M15)
      Print("CONCORD-4: designed for M15. Signals are evaluated on M15 regardless of chart period.");
   if(InpDryRun)
      Print("CONCORD-4: DRY RUN - signals will be logged, no orders sent.");

   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason) { C4Deinit(); }

//+------------------------------------------------------------------+
//| Realised P&L and entry count for this EA since `fromServer`.     |
//+------------------------------------------------------------------+
double RealizedSince(const datetime fromServer, int &entryCount)
  {
   entryCount = 0;
   double pnl = 0.0;
   if(!HistorySelect(fromServer, TimeCurrent() + 60)) return 0.0;

   int total = HistoryDealsTotal();
   for(int i = 0; i < total; i++)
     {
      ulong t = HistoryDealGetTicket(i);
      if(t == 0) continue;
      if(HistoryDealGetInteger(t, DEAL_MAGIC) != InpMagic)   continue;
      if(HistoryDealGetString (t, DEAL_SYMBOL) != _Symbol)   continue;

      if(HistoryDealGetInteger(t, DEAL_ENTRY) == DEAL_ENTRY_IN) entryCount++;

      pnl += HistoryDealGetDouble(t, DEAL_PROFIT)
           + HistoryDealGetDouble(t, DEAL_SWAP)
           + HistoryDealGetDouble(t, DEAL_COMMISSION);
     }
   return pnl;
  }

//+------------------------------------------------------------------+
//| Breaker anchors survive a restart. Without persistence, stopping |
//| and restarting the EA would silently reset a hit daily loss cap  |
//| and the equity peak - the exact failure mode that turns a bad    |
//| day into a bad week.                                             |
//+------------------------------------------------------------------+
string AnchorName(const string field)
  { return StringFormat("C4_%d_ANCHOR_%s", (int)InpMagic, field); }

void SaveAnchors()
  {
   GlobalVariableSet(AnchorName("DAYSTART"), (double)g_lastDayStart);
   GlobalVariableSet(AnchorName("DAYEQ"),    g_dayStartEquity);
   GlobalVariableSet(AnchorName("PEAKEQ"),   g_peakEquity);
  }

void LoadAnchors()
  {
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double v  = 0.0;

   g_lastDayStart   = GlobalVariableGet(AnchorName("DAYSTART"), v) ? (datetime)v
                                                                  : C4UtcDayStart(C4ToUtc(TimeCurrent()));
   g_dayStartEquity = GlobalVariableGet(AnchorName("DAYEQ"),  v) && v > 0.0 ? v  : eq;
   g_peakEquity     = GlobalVariableGet(AnchorName("PEAKEQ"), v) && v > 0.0 ? v  : eq;

   // a stale anchor from a previous day is worse than none
   datetime today = C4UtcDayStart(C4ToUtc(TimeCurrent()));
   if(g_lastDayStart != today) { g_lastDayStart = today; g_dayStartEquity = eq; }

   if(g_peakEquity < eq) g_peakEquity = eq;
   SaveAnchors();
   PrintFormat("CONCORD-4: anchors - day equity %.2f, peak equity %.2f, size multiplier %.2f",
               g_dayStartEquity, g_peakEquity, SizeMultiplier());
  }

//+------------------------------------------------------------------+
//| Roll the day anchor and the equity peak.                         |
//+------------------------------------------------------------------+
void UpdateAnchors()
  {
   bool dirty = false;
   datetime dayStart = C4UtcDayStart(C4ToUtc(TimeCurrent()));
   if(dayStart != g_lastDayStart)
     {
      g_lastDayStart   = dayStart;
      g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
      dirty = true;
     }
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   if(eq > g_peakEquity) { g_peakEquity = eq; dirty = true; }
   if(dirty) SaveAnchors();
  }

double SizeMultiplier()
  {
   if(g_peakEquity <= 0.0) return 1.0;
   double ddPct = 100.0 * (g_peakEquity - AccountInfoDouble(ACCOUNT_EQUITY)) / g_peakEquity;
   return (ddPct >= InpBreakerDdPct) ? InpBreakerSizeMult : 1.0;
  }

//+------------------------------------------------------------------+
//| Circuit breakers. Returns false when the day is closed for       |
//| business, with the reason in `why`.                              |
//+------------------------------------------------------------------+
bool TradingAllowed(string &why)
  {
   why = "";
   double rMoney = g_dayStartEquity * InpRiskPercent / 100.0;
   if(rMoney <= 0.0) { why = "no equity anchor"; return false; }

   int entriesToday = 0;
   datetime dayStartServer = C4ToServer(g_lastDayStart);
   double dayPnl = RealizedSince(dayStartServer, entriesToday);

   if(entriesToday >= InpMaxEntriesDay)
     { why = StringFormat("daily entry cap reached (%d)", entriesToday); return false; }

   if(dayPnl <= -InpDailyLossR * rMoney)
     { why = StringFormat("daily loss cap hit (%.2f)", dayPnl); return false; }

   int dummy = 0;
   datetime weekStartServer = C4ToServer(g_lastDayStart - 6 * 86400);
   double weekPnl = RealizedSince(weekStartServer, dummy);
   if(weekPnl <= -InpWeeklyLossR * rMoney)
     { why = StringFormat("weekly loss cap hit (%.2f)", weekPnl); return false; }

   return true;
  }

//+------------------------------------------------------------------+
//| Volume normalisation to the symbol's step and bounds.            |
//+------------------------------------------------------------------+
double NormalizeVolume(const double raw)
  {
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0.0) step = 0.01;

   double v = MathFloor(raw / step) * step;
   if(v > vmax) v = vmax;
   if(v < vmin) return 0.0;             // too small to trade: skip, never round up

   int digits = 0;                      // derive rounding from the step itself
   double probe = step;
   while(digits < 8 && MathAbs(probe - MathRound(probe)) > 1e-9) { probe *= 10.0; digits++; }
   return NormalizeDouble(v, digits);
  }

//+------------------------------------------------------------------+
//| Size = min(fixed-fractional risk, volatility target). Taking the |
//| smaller is what keeps size falling as gold's ATR expands, which  |
//| is the main drawdown lever in the whole system.                  |
//+------------------------------------------------------------------+
double CalcLots(const double riskDist, const double atrD1, string &detail)
  {
   detail = "";
   double tickVal  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tickVal <= 0.0) tickVal = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickVal <= 0.0 || tickSize <= 0.0 || riskDist <= 0.0)
     { detail = "bad tick metrics"; return 0.0; }

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double mult   = SizeMultiplier();

   double lossPerLot = (riskDist / tickSize) * tickVal;
   if(lossPerLot <= 0.0) { detail = "zero loss per lot"; return 0.0; }
   double riskLots = (equity * InpRiskPercent / 100.0 * mult) / lossPerLot;

   double lots = riskLots;
   if(InpUseVolTarget && atrD1 > 0.0)
     {
      // ATR(D1) stands in for the daily sigma. It overstates sigma by
      // roughly 20-40%, so the realised vol target lands under the
      // nominal figure - deliberately the conservative direction.
      double targetDaily     = equity * (InpVolTargetAnnual / 100.0) / MathSqrt(252.0);
      double dailyMovePerLot = (atrD1 / tickSize) * tickVal;
      if(dailyMovePerLot > 0.0)
        {
         double volLots = targetDaily / dailyMovePerLot * mult;
         lots = MathMin(riskLots, volLots);
        }
     }

   double norm = NormalizeVolume(lots);
   if(norm <= 0.0)
     {
      detail = StringFormat("size %.4f below broker minimum", lots);
      return 0.0;
     }

   //--- margin sanity: never commit more than half of free margin
   double price  = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double margin = 0.0;
   if(OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, norm, price, margin))
     {
      double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
      if(margin > freeMargin * 0.5)
        {
         detail = StringFormat("margin %.2f exceeds half of free margin %.2f", margin, freeMargin);
         return 0.0;
        }
     }

   detail = StringFormat("risk-cap %.2f / chosen %.2f -> %.2f lots (breaker mult %.2f)",
                         riskLots, lots, norm, mult);
   return norm;
  }

//+------------------------------------------------------------------+
//| Respect the broker's minimum stop distance.                      |
//+------------------------------------------------------------------+
double ClampStop(const int dir, const double price, const double stop)
  {
   double point   = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   long   lvlPts  = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double minDist = (double)lvlPts * point;
   if(minDist <= 0.0) return stop;

   if(dir == C4_LONG  && (price - stop) < minDist) return price - minDist;
   if(dir == C4_SHORT && (stop - price) < minDist) return price + minDist;
   return stop;
  }

//+------------------------------------------------------------------+
bool SelectOwnPosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(!g_pos.SelectByIndex(i)) continue;
      if(g_pos.Magic() == InpMagic && g_pos.Symbol() == _Symbol) return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Highest high / lowest low on H1 since the position opened,       |
//| for the Chandelier trail.                                        |
//+------------------------------------------------------------------+
bool ExtremeSinceEntry(const datetime entryTime, const int dir, double &extreme)
  {
   MqlRates r[];
   int n = CopyRates(_Symbol, PERIOD_H1, entryTime, TimeCurrent(), r);
   if(n <= 0) return false;

   extreme = (dir == C4_LONG) ? -DBL_MAX : DBL_MAX;
   for(int i = 0; i < n; i++)
     {
      if(dir == C4_LONG) extreme = MathMax(extreme, r[i].high);
      else               extreme = MathMin(extreme, r[i].low);
     }
   return (extreme != -DBL_MAX && extreme != DBL_MAX);
  }

//+------------------------------------------------------------------+
//| Manage the open position: time stop, partial, breakeven, trail.  |
//+------------------------------------------------------------------+
void ManagePosition()
  {
   if(!SelectOwnPosition()) return;

   ulong  ticket = g_pos.Ticket();
   int    dir    = (g_pos.PositionType() == POSITION_TYPE_BUY) ? C4_LONG : C4_SHORT;
   double open   = g_pos.PriceOpen();
   double vol    = g_pos.Volume();
   double sl     = g_pos.StopLoss();
   double bid    = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask    = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double price  = (dir == C4_LONG) ? bid : ask;

   double rDist  = GvGet(ticket, "R", 0.0);
   bool   partialDone = (GvGet(ticket, "PART", 0.0) > 0.5);

   //--- time stop: this sleeve does not hold overnight
   if(C4UtcMinuteOfDay(TimeCurrent()) >= InpFlatMinuteUtc)
     {
      PrintFormat("CONCORD-4: time stop, flattening ticket %I64u", ticket);
      if(!InpDryRun && g_trade.PositionClose(ticket)) GvClear(ticket);
      return;
     }

   if(rDist <= 0.0) return;   // unknown geometry - leave the broker stop in place

   //--- partial at +1R, then breakeven plus costs
   if(!partialDone)
     {
      double target = (dir == C4_LONG) ? open + InpPartialAtR * rDist
                                       : open - InpPartialAtR * rDist;
      bool reached = (dir == C4_LONG) ? (price >= target) : (price <= target);
      if(reached)
        {
         double vmin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
         double part  = NormalizeVolume(vol * InpPartialFraction);
         bool   split = (part >= vmin && (vol - part) >= vmin);

         if(split && !InpDryRun) g_trade.PositionClosePartial(ticket, part);
         else if(split)          PrintFormat("CONCORD-4: [dry] partial %.2f lots", part);

         double spreadAbs = (ask - bid);
         double beOffset  = spreadAbs * InpBeSpreadMult;
         double be = (dir == C4_LONG) ? open + beOffset : open - beOffset;
         be = ClampStop(dir, price, be);

         if(!InpDryRun) g_trade.PositionModify(ticket, be, g_pos.TakeProfit());
         GvSet(ticket, "PART", 1.0);
         PrintFormat("CONCORD-4: +1R reached on %I64u - partial %s, stop to breakeven %.*f",
                     ticket, split ? "taken" : "skipped (min lot)", _Digits, be);
         return;
        }
     }

   //--- Chandelier trail on the remainder
   if(partialDone)
     {
      double atrH1[];
      ArraySetAsSeries(atrH1, true);
      if(CopyBuffer(g_hAtrH1, 0, 1, 1, atrH1) < 1) return;

      double extreme = 0.0;
      if(!ExtremeSinceEntry((datetime)g_pos.Time(), dir, extreme)) return;

      double newSl = (dir == C4_LONG) ? extreme - InpChandelierAtr * atrH1[0]
                                      : extreme + InpChandelierAtr * atrH1[0];
      newSl = ClampStop(dir, price, newSl);

      //--- only ever move the stop in the favourable direction
      bool improves = (dir == C4_LONG) ? (newSl > sl) : (newSl < sl);
      if(improves && !InpDryRun)
         g_trade.PositionModify(ticket, NormalizeDouble(newSl, _Digits), g_pos.TakeProfit());
     }
  }

//+------------------------------------------------------------------+
//| Drop bookkeeping for tickets that no longer have a position.     |
//+------------------------------------------------------------------+
void PruneGlobals()
  {
   string prefix = StringFormat("C4_%d_", (int)InpMagic);
   for(int i = GlobalVariablesTotal() - 1; i >= 0; i--)
     {
      string name = GlobalVariableName(i);
      if(StringFind(name, prefix) != 0) continue;

      string parts[];
      if(StringSplit(name, StringGetCharacter("_", 0), parts) < 4) continue;
      ulong ticket = (ulong)StringToInteger(parts[2]);
      if(ticket != 0 && !PositionSelectByTicket(ticket))
         GlobalVariableDel(name);
     }
  }

//+------------------------------------------------------------------+
//| Entry on the close of a confirmed M15 bar.                       |
//+------------------------------------------------------------------+
void TryEntry()
  {
   if(SelectOwnPosition()) return;          // one position at a time on this symbol

   string why;
   if(!TradingAllowed(why))
     {
      static string lastWhy = "";
      if(why != lastWhy) { PrintFormat("CONCORD-4: standing down - %s", why); lastWhy = why; }
      return;
     }

   C4State st;
   if(!C4Evaluate(g_cfg, 1, st))
     {
      PrintFormat("CONCORD-4: not ready - %s", st.notReady);
      return;
     }
   if(st.signal == C4_NEUTRAL) return;

   //--- price and stop first: the broker's stop level can widen the
   //--- distance, and sizing must reflect the risk we actually take
   double price = (st.signal == C4_LONG) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                         : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double stop  = ClampStop(st.signal, price,
                            (st.signal == C4_LONG) ? price - st.riskDist
                                                   : price + st.riskDist);
   stop = NormalizeDouble(stop, _Digits);
   double actualRisk = MathAbs(price - stop);

   string detail;
   double lots = CalcLots(actualRisk, st.atrD1, detail);
   if(lots <= 0.0)
     {
      PrintFormat("CONCORD-4: signal %s skipped - %s", C4BiasText(st.signal), detail);
      return;
     }

   PrintFormat("CONCORD-4: %s %.2f lots @ %.*f  stop %.*f  R %.*f  volPct %.0f  [%s]",
               C4BiasText(st.signal), lots, _Digits, price, _Digits, stop,
               _Digits, actualRisk, st.volPct, detail);

   if(InpDryRun) return;

   bool ok = (st.signal == C4_LONG)
             ? g_trade.Buy (lots, _Symbol, 0.0, stop, 0.0, "C4")
             : g_trade.Sell(lots, _Symbol, 0.0, stop, 0.0, "C4");

   if(!ok)
     {
      PrintFormat("CONCORD-4: order rejected - retcode %d (%s)",
                  g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
      return;
     }

   if(SelectOwnPosition())
     {
      ulong ticket = g_pos.Ticket();
      GvSet(ticket, "R",  MathAbs(g_pos.PriceOpen() - stop));
      GvSet(ticket, "V0", g_pos.Volume());
      GvSet(ticket, "PART", 0.0);
     }
  }

//+------------------------------------------------------------------+
void OnTick()
  {
   UpdateAnchors();
   ManagePosition();          // stops and the time stop are checked every tick

   //--- signals are evaluated once per closed M15 bar, never intrabar
   datetime barTime = iTime(_Symbol, PERIOD_M15, 0);
   if(barTime == g_lastBarTime) return;
   g_lastBarTime = barTime;

   PruneGlobals();
   TryEntry();
  }
