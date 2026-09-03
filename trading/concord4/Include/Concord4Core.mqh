//+------------------------------------------------------------------+
//|                                                 Concord4Core.mqh |
//|            Shared gate logic for the CONCORD-4 hybrid system     |
//+------------------------------------------------------------------+
//| Both Concord4.mq5 (indicator) and Concord4EA.mq5 (expert) include|
//| this file and call C4Evaluate(). Keeping one implementation is    |
//| the whole point: if the chart shows a gate open, the EA agrees.   |
//|                                                                   |
//| Four gates drawn from four different information sources,         |
//| evaluated only on closed M15 bars:                                |
//|   L0 tradability - clock / spread / calendar / vol regime         |
//|   L1 regime bias - D1 price, 50-63 day horizon                    |
//|   L2 intermarket - synthetic USD basket built from OTHER symbols  |
//|   L3 trigger     - M15 opening-range breakout + expansion         |
//|                                                                   |
//| NON-REPAINTING CONTRACT                                           |
//| Every higher-timeframe read is anchored to the decision instant   |
//| of the bar under evaluation (its close), not to the present. A    |
//| bar evaluated today and the same bar evaluated next year produce  |
//| identical output. C4ClosedShift() is what enforces this; if you   |
//| add a new data source, route it through that function too.        |
//+------------------------------------------------------------------+
#property strict

#define C4_NEUTRAL   0
#define C4_LONG      1
#define C4_SHORT    -1

//--- how the server-to-UTC offset is resolved
enum ENUM_C4_GMT_MODE
  {
   C4_GMT_AUTO,      // Auto-detect from TimeCurrent()-TimeGMT()
   C4_GMT_MANUAL     // Use the offset supplied below
  };

//+------------------------------------------------------------------+
//| Everything the caller can tune. Both the indicator and the EA    |
//| expose these as inputs and copy them into one of these structs.  |
//+------------------------------------------------------------------+
struct C4Config
  {
   string            symbol;

   //--- L0 tradability
   int               sessionAStartMin;   // London window open, minutes from 00:00 UTC
   int               sessionAEndMin;     // London window close
   int               sessionBStartMin;   // LN/NY overlap open
   int               sessionBEndMin;     // LN/NY overlap close
   double            maxSpreadAtr;       // reject if spread > this * ATR(M15)
   bool              useNewsFilter;
   int               newsPadMinutes;     // blackout half-width around high-impact events
   int               volPctLow;          // ATR(D1) percentile floor
   int               volPctHigh;         // ATR(D1) percentile ceiling
   int               volPctLookback;     // sample size for the percentile

   //--- L1 regime
   int               emaD1Period;
   int               tsmomDays;          // time-series momentum lookback

   //--- L2 intermarket
   string            symbolSuffix;       // broker suffix, e.g. ".m" - "" to auto-detect
   int               usdEmaPeriod;
   int               usdSlopeBars;

   //--- L3 trigger
   int               orStartMin;         // opening range start, minutes from 00:00 UTC
   int               orLengthMin;        // opening range duration
   double            breakoutAtrK;       // buffer beyond the OR edge
   double            minBarRangeAtr;     // expansion: bar range floor
   double            minVolMult;         // expansion: tick-volume floor vs 20-bar average
   double            maxOrWidthAdr;      // exhaustion veto
   double            maxChaseAtr;        // do not chase a breakout further than this

   //--- risk geometry (shared so the indicator can draw the same stop)
   double            stopStructBufAtr;   // buffer beyond the opposite OR edge
   double            stopMinAtr;         // never tighter than this
   double            stopMaxAtr;         // skip the trade if structure needs more

   //--- misc
   ENUM_C4_GMT_MODE  gmtMode;
   int               gmtManualOffsetHrs;
  };

//+------------------------------------------------------------------+
//| Full gate readout for one bar.                                   |
//+------------------------------------------------------------------+
struct C4State
  {
   bool              ready;        // false = insufficient data, treat as no-trade
   string            notReady;

   bool              l0Pass;
   string            l0Reason;     // why L0 blocked, for the panel and the journal

   int               l1Bias;       // C4_LONG / C4_SHORT / C4_NEUTRAL
   int               l2Bias;
   int               l3Trigger;
   int               signal;       // non-zero only when all four agree

   double            orHigh, orLow, orWidth;
   double            atrM15, atrH1, atrD1, adr20;
   double            volPct;       // ATR(D1) percentile rank, 0-100
   double            usdEma, usdEmaPrev;

   double            entry, stop, riskDist;
   string            vetoReason;   // why L3 or the risk geometry rejected a breakout
  };

//--- indicator handles, owned by this translation unit
int      g_hAtrM15 = INVALID_HANDLE;
int      g_hAtrH1  = INVALID_HANDLE;
int      g_hAtrD1  = INVALID_HANDLE;
int      g_hEmaD1  = INVALID_HANDLE;

//--- resolved USD-basket legs
string   g_usdSym[];
double   g_usdWeight[];
int      g_usdSign[];      // +1 when the symbol is quoted USDxxx, -1 for xxxUSD
int      g_usdCount = 0;

int      g_gmtOffsetSec   = 0;
bool     g_calendarOK     = true;
bool     g_calendarWarned = false;

//+------------------------------------------------------------------+
//| Default configuration - callers override from their inputs.      |
//+------------------------------------------------------------------+
void C4DefaultConfig(C4Config &c)
  {
   c.symbol             = _Symbol;

   c.sessionAStartMin   = 7*60;      // 07:00 UTC London open
   c.sessionAEndMin     = 11*60;     // 11:00 UTC
   c.sessionBStartMin   = 13*60;     // 13:00 UTC LN/NY overlap
   c.sessionBEndMin     = 16*60;     // 16:00 UTC
   c.maxSpreadAtr       = 0.06;
   c.useNewsFilter      = true;
   c.newsPadMinutes     = 15;
   c.volPctLow          = 20;
   c.volPctHigh         = 90;
   c.volPctLookback     = 250;

   c.emaD1Period        = 50;
   c.tsmomDays          = 63;

   c.symbolSuffix       = "";
   c.usdEmaPeriod       = 20;
   c.usdSlopeBars       = 3;

   c.orStartMin         = 7*60;
   c.orLengthMin        = 30;
   c.breakoutAtrK       = 0.15;
   c.minBarRangeAtr     = 0.80;
   c.minVolMult         = 1.50;
   c.maxOrWidthAdr      = 1.20;
   c.maxChaseAtr        = 2.00;

   c.stopStructBufAtr   = 0.10;
   c.stopMinAtr         = 1.50;
   c.stopMaxAtr         = 2.00;

   c.gmtMode            = C4_GMT_AUTO;
   c.gmtManualOffsetHrs = 0;
  }

//+------------------------------------------------------------------+
//| Time helpers. Broker server time is almost never UTC, and every  |
//| session boundary here is specified in UTC, so the offset is      |
//| resolved once and applied everywhere.                            |
//+------------------------------------------------------------------+
void C4ResolveGmtOffset(const C4Config &c)
  {
   if(c.gmtMode == C4_GMT_MANUAL)
     {
      g_gmtOffsetSec = c.gmtManualOffsetHrs * 3600;
      return;
     }
   long raw = (long)TimeCurrent() - (long)TimeGMT();
   // snap to the nearest half hour - brokers sit on :00 or :30 offsets
   g_gmtOffsetSec = (int)(MathRound((double)raw / 1800.0) * 1800);
  }

datetime C4ToUtc(datetime serverTime)   { return serverTime - g_gmtOffsetSec; }
datetime C4ToServer(datetime utcTime)   { return utcTime  + g_gmtOffsetSec; }

datetime C4UtcDayStart(datetime utcTime)
  {
   return (datetime)((long)utcTime - ((long)utcTime % 86400));
  }

int C4UtcMinuteOfDay(datetime serverTime)
  {
   datetime u = C4ToUtc(serverTime);
   return (int)(((long)u % 86400) / 60);
  }

//+------------------------------------------------------------------+
//| Shift of the last bar on `tf` that had FULLY CLOSED at `asOf`.   |
//| This is the non-repainting contract in one function: iBarShift   |
//| returns the bar containing asOf, whose close still lies in the   |
//| future at that instant, so we step one further back.             |
//| Returns -1 when the symbol has no usable history.                |
//+------------------------------------------------------------------+
int C4ClosedShift(const string sym, const ENUM_TIMEFRAMES tf, const datetime asOf)
  {
   int sh = iBarShift(sym, tf, asOf, false);
   if(sh < 0) return -1;
   return sh + 1;
  }

//+------------------------------------------------------------------+
//| Resolve a base symbol against the broker's naming. Tries the     |
//| explicit suffix first, then scans for a prefix match so          |
//| "EURUSD" finds "EURUSD.pro" without configuration.               |
//+------------------------------------------------------------------+
bool C4ResolveSymbol(const string base, const string suffix, string &out)
  {
   if(suffix != "")
     {
      string candidate = base + suffix;
      if(SymbolSelect(candidate, true)) { out = candidate; return true; }
     }
   if(SymbolSelect(base, true)) { out = base; return true; }

   int total = SymbolsTotal(false);
   for(int i = 0; i < total; i++)
     {
      string name = SymbolName(i, false);
      if(StringFind(name, base) == 0 && SymbolSelect(name, true))
        { out = name; return true; }
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Build the USD basket. Weights follow the DXY shape, renormalised |
//| over whatever legs the broker actually offers, so a missing      |
//| USDCHF degrades the index rather than disabling the gate.        |
//+------------------------------------------------------------------+
bool C4BuildUsdBasket(const C4Config &c)
  {
   string bases[6]  = {"EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDCHF", "AUDUSD"};
   double wts[6]    = {0.576,    0.136,    0.119,    0.091,    0.036,    0.042};
   int    signs[6]  = {-1,       +1,       -1,       +1,       +1,       -1};

   ArrayResize(g_usdSym, 0);
   ArrayResize(g_usdWeight, 0);
   ArrayResize(g_usdSign, 0);
   g_usdCount = 0;

   double weightSum = 0.0;
   for(int i = 0; i < 6; i++)
     {
      string resolved;
      if(!C4ResolveSymbol(bases[i], c.symbolSuffix, resolved))
         continue;
      ArrayResize(g_usdSym,    g_usdCount + 1);
      ArrayResize(g_usdWeight, g_usdCount + 1);
      ArrayResize(g_usdSign,   g_usdCount + 1);
      g_usdSym[g_usdCount]    = resolved;
      g_usdWeight[g_usdCount] = wts[i];
      g_usdSign[g_usdCount]   = signs[i];
      weightSum += wts[i];
      g_usdCount++;
     }

   if(g_usdCount < 3 || weightSum <= 0.0)
     {
      PrintFormat("CONCORD-4: USD basket needs at least 3 legs, resolved %d. L2 fails closed.", g_usdCount);
      return false;
     }
   for(int i = 0; i < g_usdCount; i++)
      g_usdWeight[i] /= weightSum;

   string legs = "";
   for(int i = 0; i < g_usdCount; i++)
      legs += StringFormat("%s(%.3f) ", g_usdSym[i], g_usdWeight[i]);
   PrintFormat("CONCORD-4: USD basket = %s", legs);
   return true;
  }

//+------------------------------------------------------------------+
//| Create indicator handles. Call once from OnInit.                 |
//+------------------------------------------------------------------+
bool C4Init(const C4Config &c)
  {
   C4ResolveGmtOffset(c);
   PrintFormat("CONCORD-4: server-to-UTC offset resolved to %+.1f h (server %s / GMT %s)",
               g_gmtOffsetSec / 3600.0,
               TimeToString(TimeCurrent(), TIME_DATE|TIME_MINUTES),
               TimeToString(TimeGMT(),     TIME_DATE|TIME_MINUTES));

   g_hAtrM15 = iATR(c.symbol, PERIOD_M15, 14);
   g_hAtrH1  = iATR(c.symbol, PERIOD_H1,  14);
   g_hAtrD1  = iATR(c.symbol, PERIOD_D1,  14);
   g_hEmaD1  = iMA (c.symbol, PERIOD_D1, c.emaD1Period, 0, MODE_EMA, PRICE_CLOSE);

   if(g_hAtrM15 == INVALID_HANDLE || g_hAtrH1 == INVALID_HANDLE ||
      g_hAtrD1  == INVALID_HANDLE || g_hEmaD1 == INVALID_HANDLE)
     {
      Print("CONCORD-4: failed to create indicator handles.");
      return false;
     }

   C4BuildUsdBasket(c);
   return true;
  }

void C4Deinit()
  {
   if(g_hAtrM15 != INVALID_HANDLE) IndicatorRelease(g_hAtrM15);
   if(g_hAtrH1  != INVALID_HANDLE) IndicatorRelease(g_hAtrH1);
   if(g_hAtrD1  != INVALID_HANDLE) IndicatorRelease(g_hAtrD1);
   if(g_hEmaD1  != INVALID_HANDLE) IndicatorRelease(g_hEmaD1);
   g_hAtrM15 = g_hAtrH1 = g_hAtrD1 = g_hEmaD1 = INVALID_HANDLE;
  }

//+------------------------------------------------------------------+
//| Percentile rank of v within the first n elements of arr, 0-100.  |
//+------------------------------------------------------------------+
double C4PercentileRank(const double &arr[], const int n, const double v)
  {
   if(n <= 0) return -1.0;
   int below = 0;
   for(int i = 0; i < n; i++)
      if(arr[i] <= v) below++;
   return 100.0 * (double)below / (double)n;
  }

//+------------------------------------------------------------------+
//| L2 - synthetic USD index over `count` H1 bars closed as of       |
//| `asOf`, newest at index 0. Geometric (log-weighted) so the legs  |
//| compose correctly. Returns false if any leg is short of history: |
//| the gate then fails closed rather than guessing.                 |
//+------------------------------------------------------------------+
bool C4BuildUsdSeries(const int count, const datetime asOf, double &series[])
  {
   if(g_usdCount < 3) return false;

   ArrayResize(series, count);
   ArrayInitialize(series, 0.0);

   for(int leg = 0; leg < g_usdCount; leg++)
     {
      int sh = C4ClosedShift(g_usdSym[leg], PERIOD_H1, asOf);
      if(sh < 0) return false;

      double closes[];
      ArraySetAsSeries(closes, true);
      if(CopyClose(g_usdSym[leg], PERIOD_H1, sh, count, closes) < count)
         return false;

      for(int i = 0; i < count; i++)
        {
         if(closes[i] <= 0.0) return false;
         series[i] += g_usdWeight[leg] * g_usdSign[leg] * MathLog(closes[i]);
        }
     }
   return true;
  }

//+------------------------------------------------------------------+
//| High-impact calendar blackout around `serverTime`.               |
//| Degrades gracefully: if the terminal refuses calendar access the |
//| filter disables itself and says so once, loudly, because a       |
//| backtest without it is not the same system.                      |
//+------------------------------------------------------------------+
bool C4InNewsBlackout(const datetime serverTime, const int padMinutes)
  {
   if(!g_calendarOK) return false;

   string currencies[3] = {"USD", "EUR", "GBP"};
   datetime from = serverTime - padMinutes * 60;
   datetime to   = serverTime + padMinutes * 60;

   for(int c = 0; c < 3; c++)
     {
      MqlCalendarValue values[];
      ResetLastError();
      int n = CalendarValueHistory(values, from, to, NULL, currencies[c]);
      if(n <= 0)
        {
         int err = GetLastError();
         if(err != 0)   // 4014 = function not permitted here
           {
            g_calendarOK = false;
            if(!g_calendarWarned)
              {
               PrintFormat("CONCORD-4: calendar unavailable (error %d) - news filter DISABLED. "
                           "These results do not include the news blackout.", err);
               g_calendarWarned = true;
              }
            return false;
           }
         continue;   // genuinely no events in the window
        }
      for(int i = 0; i < n; i++)
        {
         MqlCalendarEvent ev;
         if(!CalendarEventById(values[i].event_id, ev)) continue;
         if(ev.importance == CALENDAR_IMPORTANCE_HIGH) return true;
        }
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Opening range for the UTC day containing `barOpenTime`.          |
//| Deliberately keyed to the bar's OPEN: a bar that opens before    |
//| the range has closed is part of the range and cannot trade it.   |
//+------------------------------------------------------------------+
bool C4OpeningRange(const C4Config &c, const datetime barOpenTime,
                    double &orHigh, double &orLow)
  {
   datetime utc      = C4ToUtc(barOpenTime);
   datetime dayStart = C4UtcDayStart(utc);

   datetime orFromUtc = dayStart + c.orStartMin * 60;
   datetime orToUtc   = orFromUtc + c.orLengthMin * 60;

   if(utc < orToUtc) return false;

   MqlRates rates[];
   int n = CopyRates(c.symbol, PERIOD_M15,
                     C4ToServer(orFromUtc),
                     C4ToServer(orToUtc) - 1,
                     rates);
   if(n <= 0) return false;

   orHigh = -DBL_MAX;
   orLow  =  DBL_MAX;
   for(int i = 0; i < n; i++)
     {
      orHigh = MathMax(orHigh, rates[i].high);
      orLow  = MathMin(orLow,  rates[i].low);
     }
   return (orHigh > orLow);
  }

//+------------------------------------------------------------------+
//| Average daily range over `bars` D1 bars closed as of `asOf`.     |
//+------------------------------------------------------------------+
double C4Adr(const string symbol, const int bars, const datetime asOf)
  {
   int sh = C4ClosedShift(symbol, PERIOD_D1, asOf);
   if(sh < 0) return 0.0;

   MqlRates r[];
   ArraySetAsSeries(r, true);
   if(CopyRates(symbol, PERIOD_D1, sh, bars, r) < bars) return 0.0;

   double sum = 0.0;
   for(int i = 0; i < bars; i++) sum += (r[i].high - r[i].low);
   return sum / bars;
  }

//+------------------------------------------------------------------+
//| Evaluate every gate for the M15 bar at `shift`.                  |
//| shift must be >= 1: the forming bar is never used.               |
//+------------------------------------------------------------------+
bool C4Evaluate(const C4Config &c, const int shift, C4State &st)
  {
   st.ready      = false;
   st.notReady   = "";
   st.l0Pass     = false;
   st.l0Reason   = "";
   st.l1Bias     = C4_NEUTRAL;
   st.l2Bias     = C4_NEUTRAL;
   st.l3Trigger  = C4_NEUTRAL;
   st.signal     = C4_NEUTRAL;
   st.vetoReason = "";
   st.orHigh = st.orLow = st.orWidth = 0.0;
   st.entry  = st.stop  = st.riskDist = 0.0;
   st.volPct = -1.0;

   if(shift < 1) { st.notReady = "shift<1 (forming bar)"; return false; }

   //--- M15 context -------------------------------------------------
   // window copy: index 0 is the bar under evaluation, 1..20 are the
   // bars behind it for the volume average. O(1) per bar, so painting a
   // long chart history stays linear.
   MqlRates m15[];
   ArraySetAsSeries(m15, true);
   if(CopyRates(c.symbol, PERIOD_M15, shift, 21, m15) < 21)
     { st.notReady = "M15 history"; return false; }

   datetime barTime = m15[0].time;
   // the instant the decision could actually have been made
   datetime asOf    = barTime + PeriodSeconds(PERIOD_M15);

   int shH1 = C4ClosedShift(c.symbol, PERIOD_H1, asOf);
   int shD1 = C4ClosedShift(c.symbol, PERIOD_D1, asOf);
   if(shH1 < 0 || shD1 < 0) { st.notReady = "HTF bar alignment"; return false; }

   double atrM15[], atrH1[], atrD1[], emaD1[];
   ArraySetAsSeries(atrM15, true);
   ArraySetAsSeries(atrH1,  true);
   ArraySetAsSeries(atrD1,  true);
   ArraySetAsSeries(emaD1,  true);

   if(CopyBuffer(g_hAtrM15, 0, shift, 1, atrM15) < 1) { st.notReady = "ATR M15"; return false; }
   if(CopyBuffer(g_hAtrH1,  0, shH1,  1, atrH1)  < 1) { st.notReady = "ATR H1";  return false; }
   if(CopyBuffer(g_hAtrD1,  0, shD1, c.volPctLookback, atrD1) < c.volPctLookback)
     { st.notReady = "ATR D1 percentile history"; return false; }
   if(CopyBuffer(g_hEmaD1,  0, shD1, 1, emaD1) < 1)  { st.notReady = "EMA D1"; return false; }

   st.atrM15 = atrM15[0];
   st.atrH1  = atrH1[0];
   st.atrD1  = atrD1[0];
   if(st.atrM15 <= 0.0 || st.atrD1 <= 0.0) { st.notReady = "zero ATR"; return false; }

   st.adr20 = C4Adr(c.symbol, 20, asOf);
   if(st.adr20 <= 0.0) { st.notReady = "ADR(20)"; return false; }

   st.ready = true;

   //--- L1 regime bias: D1 trend AND time-series momentum must agree
   MqlRates d1[];
   ArraySetAsSeries(d1, true);
   int needD1 = c.tsmomDays + 2;
   if(CopyRates(c.symbol, PERIOD_D1, shD1, needD1, d1) < needD1)
     { st.ready = false; st.notReady = "D1 history for TSMOM"; return false; }

   double lastD1Close = d1[0].close;
   double tsmomRef    = d1[c.tsmomDays].close;
   bool   trendUp     = (lastD1Close > emaD1[0]);
   bool   momUp       = (tsmomRef > 0.0 && lastD1Close > tsmomRef);

   if(trendUp && momUp)        st.l1Bias = C4_LONG;
   else if(!trendUp && !momUp) st.l1Bias = C4_SHORT;
   else                        st.l1Bias = C4_NEUTRAL;   // disagreement = flat day

   //--- L0 clock first: it is free, and it short-circuits the two
   //--- expensive gates (multi-symbol history and the calendar) on the
   //--- ~85% of bars that fall outside the trading windows.
   int minOfDay = C4UtcMinuteOfDay(barTime);
   bool inSessionA = (minOfDay >= c.sessionAStartMin && minOfDay < c.sessionAEndMin);
   bool inSessionB = (minOfDay >= c.sessionBStartMin && minOfDay < c.sessionBEndMin);
   bool inSession  = (inSessionA || inSessionB);
   if(!inSession)
      st.l0Reason = StringFormat("outside session (%02d:%02d UTC)", minOfDay/60, minOfDay%60);

   //--- L2 intermarket: USD basket slope, from other symbols entirely
   int needUsd = c.usdEmaPeriod * 5 + c.usdSlopeBars + 5;
   double usdRaw[];
   if(!inSession)
     {
      st.l2Bias = C4_NEUTRAL;   // not evaluated - the clock already blocks
     }
   else if(C4BuildUsdSeries(needUsd, asOf, usdRaw))
     {
      // seed at the oldest sample and walk forward to the newest
      double k   = 2.0 / (c.usdEmaPeriod + 1.0);
      double ema = usdRaw[needUsd - 1];
      double emaAtSlopeBar = ema;
      for(int i = needUsd - 2; i >= 0; i--)
        {
         ema = k * usdRaw[i] + (1.0 - k) * ema;
         if(i == c.usdSlopeBars) emaAtSlopeBar = ema;
        }
      st.usdEma     = ema;
      st.usdEmaPrev = emaAtSlopeBar;

      if(st.usdEma < st.usdEmaPrev)      st.l2Bias = C4_LONG;    // USD falling -> gold long
      else if(st.usdEma > st.usdEmaPrev) st.l2Bias = C4_SHORT;
      else                               st.l2Bias = C4_NEUTRAL;
     }
   else
     {
      st.l2Bias     = C4_NEUTRAL;                                // fail closed
      st.vetoReason = "L2 data unavailable";
     }

   //--- L0 tradability (clock already applied above) -----------------
   st.volPct = C4PercentileRank(atrD1, c.volPctLookback, st.atrD1);
   if(st.l0Reason == "" && (st.volPct < c.volPctLow || st.volPct > c.volPctHigh))
      st.l0Reason = StringFormat("vol regime %.0f%% outside [%d,%d]",
                                 st.volPct, c.volPctLow, c.volPctHigh);

   // the bar carries its own recorded spread; using it keeps the
   // indicator's history honest instead of judging last month's bars
   // by today's spread. Live, the two agree.
   double spreadPts = (double)m15[0].spread;
   if(spreadPts <= 0.0) spreadPts = (double)SymbolInfoInteger(c.symbol, SYMBOL_SPREAD);
   double spreadAbs = spreadPts * SymbolInfoDouble(c.symbol, SYMBOL_POINT);
   if(st.l0Reason == "" && spreadAbs > c.maxSpreadAtr * st.atrM15)
      st.l0Reason = StringFormat("spread %.0f pts above %.0f%% of ATR",
                                 spreadPts, c.maxSpreadAtr * 100.0);

   if(st.l0Reason == "" && c.useNewsFilter && C4InNewsBlackout(asOf, c.newsPadMinutes))
      st.l0Reason = "high-impact news blackout";

   st.l0Pass = (st.l0Reason == "");

   //--- L3 trigger ---------------------------------------------------
   if(!C4OpeningRange(c, barTime, st.orHigh, st.orLow))
     {
      if(st.vetoReason == "") st.vetoReason = "opening range not closed";
      return true;
     }
   st.orWidth = st.orHigh - st.orLow;

   if(st.orWidth > c.maxOrWidthAdr * st.adr20)
     {
      st.vetoReason = StringFormat("OR width %.0f%% of ADR - range already spent",
                                   100.0 * st.orWidth / st.adr20);
      return true;
     }

   double close  = m15[0].close;
   double range  = m15[0].high - m15[0].low;
   double buffer = c.breakoutAtrK * st.atrM15;

   int dir = C4_NEUTRAL;
   if(close > st.orHigh + buffer)      dir = C4_LONG;
   else if(close < st.orLow - buffer)  dir = C4_SHORT;
   if(dir == C4_NEUTRAL) return true;

   //--- expansion confirmation: a real break, not a drift-through
   if(range < c.minBarRangeAtr * st.atrM15)
     { st.vetoReason = "no range expansion on the break bar"; return true; }

   double volSum = 0.0;
   for(int i = 1; i <= 20; i++) volSum += (double)m15[i].tick_volume;
   double volAvg = volSum / 20.0;
   if(volAvg <= 0.0 || (double)m15[0].tick_volume < c.minVolMult * volAvg)
     { st.vetoReason = "tick volume below expansion threshold"; return true; }

   //--- do not chase a break that has already run
   double edge = (dir == C4_LONG) ? st.orHigh : st.orLow;
   if(MathAbs(close - edge) > c.maxChaseAtr * st.atrM15)
     { st.vetoReason = "breakout extended beyond chase limit"; return true; }

   st.l3Trigger = dir;

   //--- risk geometry: structure first, ATR as floor and hard cap
   double structStop = (dir == C4_LONG)
                       ? st.orLow  - c.stopStructBufAtr * st.atrM15
                       : st.orHigh + c.stopStructBufAtr * st.atrM15;
   double dist = MathMax(MathAbs(close - structStop), c.stopMinAtr * st.atrM15);

   if(dist > c.stopMaxAtr * st.atrM15)
     {
      st.vetoReason = StringFormat("stop needs %.2f ATR, cap is %.2f",
                                   dist / st.atrM15, c.stopMaxAtr);
      return true;
     }

   st.entry    = close;
   st.riskDist = dist;
   st.stop     = (dir == C4_LONG) ? close - dist : close + dist;

   //--- all four gates must agree before anything becomes a signal
   if(st.l0Pass && st.l1Bias == dir && st.l2Bias == dir)
      st.signal = dir;
   else
     {
      if(!st.l0Pass)            st.vetoReason = "L0: " + st.l0Reason;
      else if(st.l1Bias != dir) st.vetoReason = "L1 regime disagrees";
      else if(st.l2Bias != dir) st.vetoReason = "L2 intermarket disagrees";
     }

   return true;
  }

//+------------------------------------------------------------------+
//| Human-readable bias for the journal and the chart panel.         |
//+------------------------------------------------------------------+
string C4BiasText(const int bias)
  {
   if(bias == C4_LONG)  return "LONG";
   if(bias == C4_SHORT) return "SHORT";
   return "-";
  }
