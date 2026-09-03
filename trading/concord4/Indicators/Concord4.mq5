//+------------------------------------------------------------------+
//|                                                     Concord4.mq5 |
//|        CONCORD-4 gate visualiser - non-repainting, M15 chart     |
//+------------------------------------------------------------------+
//| Draws the opening range, the entry arrows, and a live panel of    |
//| the four gate states. Every buffer is exported so the values can  |
//| be read from another program via iCustom().                       |
//|                                                                   |
//| This shares Concord4Core.mqh with the EA, so an arrow on the      |
//| chart is by construction the same decision the EA would take.     |
//+------------------------------------------------------------------+
#property copyright "CONCORD-4"
#property version   "1.00"
#property indicator_chart_window
#property indicator_buffers 9
#property indicator_plots   4

//--- plot 0: opening range high
#property indicator_label1  "OR High"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrDodgerBlue
#property indicator_style1  STYLE_DOT
#property indicator_width1  1

//--- plot 1: opening range low
#property indicator_label2  "OR Low"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrDodgerBlue
#property indicator_style2  STYLE_DOT
#property indicator_width2  1

//--- plot 2: long signal
#property indicator_label3  "C4 Long"
#property indicator_type3   DRAW_ARROW
#property indicator_color3  clrLimeGreen
#property indicator_width3  2

//--- plot 3: short signal
#property indicator_label4  "C4 Short"
#property indicator_type4   DRAW_ARROW
#property indicator_color4  clrOrangeRed
#property indicator_width4  2

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

//--- display
input group                "Display";
input ENUM_C4_GMT_MODE InpGmtMode = C4_GMT_AUTO;  // Server-to-UTC offset mode
input int    InpGmtOffsetHours  = 0;      // Manual offset (hours, if mode = Manual)
input int    InpMaxBars         = 3000;   // Max bars to calculate
input bool   InpShowPanel       = true;   // Show gate panel

//--- plotted buffers
double BufOrHigh[];
double BufOrLow[];
double BufLong[];
double BufShort[];
//--- data-only buffers, readable via iCustom()
double BufL0[];        // 1 = tradability open, 0 = blocked
double BufL1[];        // +1 long bias, -1 short bias, 0 flat
double BufL2[];
double BufL3[];
double BufSignal[];    // non-zero only when all four agree

C4Config g_cfg;
const string PANEL_PREFIX = "C4PANEL_";

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
   if(Period() != PERIOD_M15)
      Print("CONCORD-4: designed for M15. Attach to an M15 chart for the intended behaviour.");

   SetIndexBuffer(0, BufOrHigh, INDICATOR_DATA);
   SetIndexBuffer(1, BufOrLow,  INDICATOR_DATA);
   SetIndexBuffer(2, BufLong,   INDICATOR_DATA);
   SetIndexBuffer(3, BufShort,  INDICATOR_DATA);
   SetIndexBuffer(4, BufL0,     INDICATOR_CALCULATIONS);
   SetIndexBuffer(5, BufL1,     INDICATOR_CALCULATIONS);
   SetIndexBuffer(6, BufL2,     INDICATOR_CALCULATIONS);
   SetIndexBuffer(7, BufL3,     INDICATOR_CALCULATIONS);
   SetIndexBuffer(8, BufSignal, INDICATOR_CALCULATIONS);

   PlotIndexSetInteger(2, PLOT_ARROW, 233);   // up arrow
   PlotIndexSetInteger(3, PLOT_ARROW, 234);   // down arrow

   for(int i = 0; i < 4; i++)
      PlotIndexSetDouble(i, PLOT_EMPTY_VALUE, EMPTY_VALUE);

   IndicatorSetString(INDICATOR_SHORTNAME, "CONCORD-4");
   IndicatorSetInteger(INDICATOR_DIGITS, _Digits);

   BuildConfig();
   if(!C4Init(g_cfg)) return INIT_FAILED;

   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   C4Deinit();
   ObjectsDeleteAll(0, PANEL_PREFIX);
  }

//+------------------------------------------------------------------+
void PanelLine(const int row, const string text, const color clr)
  {
   string name = PANEL_PREFIX + IntegerToString(row);
   if(ObjectFind(0, name) < 0)
     {
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 12);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 18 + row * 15);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetString (0, name, OBJPROP_FONT, "Consolas");
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
     }
   ObjectSetString (0, name, OBJPROP_TEXT,  text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
  }

color GateColor(const bool ok) { return ok ? clrLimeGreen : clrGray; }

void DrawPanel(const C4State &st)
  {
   if(!InpShowPanel) return;

   if(!st.ready)
     {
      PanelLine(0, "CONCORD-4  NOT READY: " + st.notReady, clrOrangeRed);
      for(int i = 1; i <= 6; i++) PanelLine(i, "", clrGray);
      return;
     }

   PanelLine(0, StringFormat("CONCORD-4  %s  vol %.0f%%  ATR(M15) %.*f",
                             _Symbol, st.volPct, _Digits, st.atrM15), clrWhite);
   PanelLine(1, "L0 tradability : " + (st.l0Pass ? "OPEN" : "BLOCKED - " + st.l0Reason),
             GateColor(st.l0Pass));
   PanelLine(2, "L1 regime      : " + C4BiasText(st.l1Bias), GateColor(st.l1Bias != C4_NEUTRAL));
   PanelLine(3, "L2 intermarket : " + C4BiasText(st.l2Bias), GateColor(st.l2Bias != C4_NEUTRAL));
   PanelLine(4, "L3 trigger     : " + C4BiasText(st.l3Trigger), GateColor(st.l3Trigger != C4_NEUTRAL));

   if(st.signal != C4_NEUTRAL)
      PanelLine(5, StringFormat(">>> SIGNAL %s  entry %.*f  stop %.*f  risk %.*f",
                                C4BiasText(st.signal), _Digits, st.entry,
                                _Digits, st.stop, _Digits, st.riskDist),
                st.signal == C4_LONG ? clrLimeGreen : clrOrangeRed);
   else
      PanelLine(5, "no signal" + (st.vetoReason == "" ? "" : " - " + st.vetoReason), clrSilver);

   PanelLine(6, StringFormat("OR %.*f / %.*f   width %.0f%% of ADR20",
                             _Digits, st.orHigh, _Digits, st.orLow,
                             st.adr20 > 0.0 ? 100.0 * st.orWidth / st.adr20 : 0.0), clrSilver);
  }

//+------------------------------------------------------------------+
int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
  {
   if(rates_total < 100) return 0;

   //--- bars older than InpMaxBars are never evaluated, so blank them
   //--- explicitly - MQL5 zero-fills new buffer elements, and a zero
   //--- would otherwise be drawn as a line at price 0.
   if(prev_calculated == 0)
     {
      ArrayInitialize(BufOrHigh, EMPTY_VALUE);
      ArrayInitialize(BufOrLow,  EMPTY_VALUE);
      ArrayInitialize(BufLong,   EMPTY_VALUE);
      ArrayInitialize(BufShort,  EMPTY_VALUE);
      ArrayInitialize(BufL0,     0.0);
      ArrayInitialize(BufL1,     0.0);
      ArrayInitialize(BufL2,     0.0);
      ArrayInitialize(BufL3,     0.0);
      ArrayInitialize(BufSignal, 0.0);
     }

   int limit = (prev_calculated > 1) ? rates_total - prev_calculated + 1 : InpMaxBars;
   limit = MathMin(limit, MathMin(InpMaxBars, rates_total - 2));
   if(limit < 1) limit = 1;

   C4State st;

   // shift 1 is the newest CLOSED bar; the forming bar is never evaluated
   for(int shift = limit; shift >= 1; shift--)
     {
      int idx = rates_total - 1 - shift;         // series shift -> buffer index
      if(idx < 0 || idx >= rates_total) continue;

      BufOrHigh[idx] = EMPTY_VALUE;
      BufOrLow[idx]  = EMPTY_VALUE;
      BufLong[idx]   = EMPTY_VALUE;
      BufShort[idx]  = EMPTY_VALUE;
      BufL0[idx]     = 0.0;
      BufL1[idx]     = 0.0;
      BufL2[idx]     = 0.0;
      BufL3[idx]     = 0.0;
      BufSignal[idx] = 0.0;

      if(!C4Evaluate(g_cfg, shift, st)) continue;

      BufL0[idx]     = st.l0Pass ? 1.0 : 0.0;
      BufL1[idx]     = (double)st.l1Bias;
      BufL2[idx]     = (double)st.l2Bias;
      BufL3[idx]     = (double)st.l3Trigger;
      BufSignal[idx] = (double)st.signal;

      if(st.orHigh > 0.0 && st.orLow > 0.0)
        {
         BufOrHigh[idx] = st.orHigh;
         BufOrLow[idx]  = st.orLow;
        }

      if(st.signal == C4_LONG)  BufLong[idx]  = low[idx]  - 0.5 * st.atrM15;
      if(st.signal == C4_SHORT) BufShort[idx] = high[idx] + 0.5 * st.atrM15;
     }

   //--- panel always reflects the newest closed bar
   C4Evaluate(g_cfg, 1, st);
   DrawPanel(st);

   //--- forming bar carries no values
   int last = rates_total - 1;
   BufOrHigh[last] = EMPTY_VALUE;
   BufOrLow[last]  = EMPTY_VALUE;
   BufLong[last]   = EMPTY_VALUE;
   BufShort[last]  = EMPTY_VALUE;

   return rates_total;
  }
