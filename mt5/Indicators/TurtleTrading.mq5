//+------------------------------------------------------------------+
//|                                              TurtleTrading.mq5   |
//|                       Turtle Trading System - Donchian breakout  |
//+------------------------------------------------------------------+
#property copyright "Turtle Trading indicator"
#property link      ""
#property version   "1.00"
#property description "Turtle Trading System (Dennis/Eckhardt): Donchian breakout entries,"
#property description "opposite-channel exits, Wilder ATR 'N' volatility unit and 2N stops."
#property description "System 1 = 20/10 with last-breakout-was-a-winner filter."
#property description "System 2 = 55/20, every breakout taken."

#property indicator_chart_window
#property indicator_buffers 14
#property indicator_plots   8

//--- plot 1: entry channel upper
#property indicator_label1  "Entry Upper"
#property indicator_type1   DRAW_LINE
#property indicator_color1  clrDodgerBlue
#property indicator_style1  STYLE_SOLID
#property indicator_width1  2
//--- plot 2: entry channel lower
#property indicator_label2  "Entry Lower"
#property indicator_type2   DRAW_LINE
#property indicator_color2  clrDodgerBlue
#property indicator_style2  STYLE_SOLID
#property indicator_width2  2
//--- plot 3: exit channel upper
#property indicator_label3  "Exit Upper"
#property indicator_type3   DRAW_LINE
#property indicator_color3  clrSilver
#property indicator_style3  STYLE_DOT
#property indicator_width3  1
//--- plot 4: exit channel lower
#property indicator_label4  "Exit Lower"
#property indicator_type4   DRAW_LINE
#property indicator_color4  clrSilver
#property indicator_style4  STYLE_DOT
#property indicator_width4  1
//--- plot 5: long entry
#property indicator_label5  "Long Entry"
#property indicator_type5   DRAW_ARROW
#property indicator_color5  clrLime
#property indicator_width5  2
//--- plot 6: short entry
#property indicator_label6  "Short Entry"
#property indicator_type6   DRAW_ARROW
#property indicator_color6  clrRed
#property indicator_width6  2
//--- plot 7: long exit
#property indicator_label7  "Long Exit"
#property indicator_type7   DRAW_ARROW
#property indicator_color7  clrAqua
#property indicator_width7  1
//--- plot 8: short exit
#property indicator_label8  "Short Exit"
#property indicator_type8   DRAW_ARROW
#property indicator_color8  clrOrange
#property indicator_width8  1

//+------------------------------------------------------------------+
//| Enumerations                                                     |
//+------------------------------------------------------------------+
enum ENUM_TURTLE_SYSTEM
  {
   TURTLE_SYSTEM_1,           // System 1 (20/10, with winner filter)
   TURTLE_SYSTEM_2,           // System 2 (55/20, no filter)
   TURTLE_SYSTEM_CUSTOM       // Custom periods
  };

enum ENUM_TURTLE_SIGNAL
  {
   TURTLE_INTRABAR,           // Intrabar (high/low pierces the channel)
   TURTLE_CLOSE               // Close only (bar must close beyond)
  };

//+------------------------------------------------------------------+
//| Inputs                                                           |
//+------------------------------------------------------------------+
input group                "=== System ==="
input ENUM_TURTLE_SYSTEM   InpSystem       = TURTLE_SYSTEM_1;  // Turtle system
input int                  InpEntryPeriod  = 20;               // Custom: entry channel period
input int                  InpExitPeriod   = 10;               // Custom: exit channel period
input ENUM_TURTLE_SIGNAL   InpSignalMode   = TURTLE_INTRABAR;  // Breakout confirmation

input group                "=== Volatility (N) and stops ==="
input int                  InpATRPeriod    = 20;               // N period (Wilder ATR)
input double               InpStopN        = 2.0;              // Stop distance in N

input group                "=== Position sizing ==="
input bool                 InpShowPanel    = true;             // Show info panel
input double               InpRiskPercent  = 1.0;              // Risk per unit (% of equity per 1N)
input int                  InpMaxUnits     = 4;                // Max units (pyramiding)
input double               InpAddEveryN    = 0.5;              // Add a unit every ... N

input group                "=== Alerts ==="
input bool                 InpAlertPopup   = false;            // Popup alert on new signal
input bool                 InpAlertPush    = false;            // Push notification on new signal

//+------------------------------------------------------------------+
//| Buffers                                                          |
//+------------------------------------------------------------------+
double BufEntryUp[];       // 0  plot
double BufEntryDn[];       // 1  plot
double BufExitUp[];        // 2  plot
double BufExitDn[];        // 3  plot
double BufLongEntry[];     // 4  plot
double BufShortEntry[];    // 5  plot
double BufLongExit[];      // 6  plot
double BufShortExit[];     // 7  plot
double BufN[];             // 8  calc - Wilder ATR (the turtle "N")
double BufTRSum[];         // 9  calc - running TR sum used to seed the ATR
double BufState[];         // 10 calc - 0 flat, +/-1 real long/short, +/-2 phantom
double BufEntryPrice[];    // 11 calc - entry price of the open (or phantom) trade
double BufStop[];          // 12 calc - current 2N stop of the open trade
double BufLoser[];         // 13 calc - 1 = last completed breakout lost, 0 = it won

//+------------------------------------------------------------------+
//| Globals                                                          |
//+------------------------------------------------------------------+
int      g_entryPeriod = 20;
int      g_exitPeriod  = 10;
bool     g_useFilter   = true;
int      g_startBar    = 21;
string   g_prefix      = "TurtleTS_";
datetime g_lastAlertBar = 0;

//+------------------------------------------------------------------+
//| Custom indicator initialization function                         |
//+------------------------------------------------------------------+
int OnInit()
  {
//--- resolve the system into concrete periods
   switch(InpSystem)
     {
      case TURTLE_SYSTEM_1:
         g_entryPeriod = 20;
         g_exitPeriod  = 10;
         g_useFilter   = true;
         break;
      case TURTLE_SYSTEM_2:
         g_entryPeriod = 55;
         g_exitPeriod  = 20;
         g_useFilter   = false;
         break;
      default:
         g_entryPeriod = InpEntryPeriod;
         g_exitPeriod  = InpExitPeriod;
         g_useFilter   = false;
         break;
     }

//--- validate
   if(g_entryPeriod < 2 || g_exitPeriod < 2)
     {
      Print("TurtleTrading: entry and exit periods must be >= 2");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(InpATRPeriod < 2)
     {
      Print("TurtleTrading: N period must be >= 2");
      return(INIT_PARAMETERS_INCORRECT);
     }
   if(InpStopN <= 0.0)
     {
      Print("TurtleTrading: stop distance in N must be > 0");
      return(INIT_PARAMETERS_INCORRECT);
     }

   g_startBar = MathMax(MathMax(g_entryPeriod, g_exitPeriod), InpATRPeriod) + 1;

//--- bind buffers
   SetIndexBuffer(0,  BufEntryUp,    INDICATOR_DATA);
   SetIndexBuffer(1,  BufEntryDn,    INDICATOR_DATA);
   SetIndexBuffer(2,  BufExitUp,     INDICATOR_DATA);
   SetIndexBuffer(3,  BufExitDn,     INDICATOR_DATA);
   SetIndexBuffer(4,  BufLongEntry,  INDICATOR_DATA);
   SetIndexBuffer(5,  BufShortEntry, INDICATOR_DATA);
   SetIndexBuffer(6,  BufLongExit,   INDICATOR_DATA);
   SetIndexBuffer(7,  BufShortExit,  INDICATOR_DATA);
   SetIndexBuffer(8,  BufN,          INDICATOR_CALCULATIONS);
   SetIndexBuffer(9,  BufTRSum,      INDICATOR_CALCULATIONS);
   SetIndexBuffer(10, BufState,      INDICATOR_CALCULATIONS);
   SetIndexBuffer(11, BufEntryPrice, INDICATOR_CALCULATIONS);
   SetIndexBuffer(12, BufStop,       INDICATOR_CALCULATIONS);
   SetIndexBuffer(13, BufLoser,      INDICATOR_CALCULATIONS);

//--- all buffers are indexed oldest -> newest inside OnCalculate
   ArraySetAsSeries(BufEntryUp,    false);
   ArraySetAsSeries(BufEntryDn,    false);
   ArraySetAsSeries(BufExitUp,     false);
   ArraySetAsSeries(BufExitDn,     false);
   ArraySetAsSeries(BufLongEntry,  false);
   ArraySetAsSeries(BufShortEntry, false);
   ArraySetAsSeries(BufLongExit,   false);
   ArraySetAsSeries(BufShortExit,  false);
   ArraySetAsSeries(BufN,          false);
   ArraySetAsSeries(BufTRSum,      false);
   ArraySetAsSeries(BufState,      false);
   ArraySetAsSeries(BufEntryPrice, false);
   ArraySetAsSeries(BufStop,       false);
   ArraySetAsSeries(BufLoser,      false);

//--- plot cosmetics
   PlotIndexSetInteger(4, PLOT_ARROW, 233);   // up arrow
   PlotIndexSetInteger(5, PLOT_ARROW, 234);   // down arrow
   PlotIndexSetInteger(6, PLOT_ARROW, 251);   // cross
   PlotIndexSetInteger(7, PLOT_ARROW, 251);   // cross

   for(int p = 0; p < 8; p++)
     {
      PlotIndexSetDouble(p, PLOT_EMPTY_VALUE, EMPTY_VALUE);
      PlotIndexSetInteger(p, PLOT_DRAW_BEGIN, g_startBar);
     }

   IndicatorSetInteger(INDICATOR_DIGITS, _Digits);
   IndicatorSetString(INDICATOR_SHORTNAME,
                      StringFormat("Turtle(%d/%d, N=%d)", g_entryPeriod, g_exitPeriod, InpATRPeriod));

   if(InpShowPanel)
      PanelCreate();

   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Custom indicator deinitialization function                       |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   ObjectsDeleteAll(0, g_prefix);
   ChartRedraw();
  }

//+------------------------------------------------------------------+
//| Highest high over `period` bars ending at index `endIdx`         |
//+------------------------------------------------------------------+
double HighestHigh(const double &high[], const int endIdx, const int period)
  {
   double hh = high[endIdx];
   for(int k = 1; k < period; k++)
     {
      int idx = endIdx - k;
      if(idx < 0)
         break;
      if(high[idx] > hh)
         hh = high[idx];
     }
   return(hh);
  }

//+------------------------------------------------------------------+
//| Lowest low over `period` bars ending at index `endIdx`           |
//+------------------------------------------------------------------+
double LowestLow(const double &low[], const int endIdx, const int period)
  {
   double ll = low[endIdx];
   for(int k = 1; k < period; k++)
     {
      int idx = endIdx - k;
      if(idx < 0)
         break;
      if(low[idx] < ll)
         ll = low[idx];
     }
   return(ll);
  }

//+------------------------------------------------------------------+
//| Custom indicator iteration function                              |
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
   if(rates_total < g_startBar + 2)
      return(0);

   ArraySetAsSeries(time,   false);
   ArraySetAsSeries(open,   false);
   ArraySetAsSeries(high,   false);
   ArraySetAsSeries(low,    false);
   ArraySetAsSeries(close,  false);

   int first;
   if(prev_calculated == 0)
     {
      ArrayInitialize(BufEntryUp,    EMPTY_VALUE);
      ArrayInitialize(BufEntryDn,    EMPTY_VALUE);
      ArrayInitialize(BufExitUp,     EMPTY_VALUE);
      ArrayInitialize(BufExitDn,     EMPTY_VALUE);
      ArrayInitialize(BufLongEntry,  EMPTY_VALUE);
      ArrayInitialize(BufShortEntry, EMPTY_VALUE);
      ArrayInitialize(BufLongExit,   EMPTY_VALUE);
      ArrayInitialize(BufShortExit,  EMPTY_VALUE);
      ArrayInitialize(BufN,          0.0);
      ArrayInitialize(BufTRSum,      0.0);
      ArrayInitialize(BufState,      0.0);
      ArrayInitialize(BufEntryPrice, 0.0);
      ArrayInitialize(BufStop,       0.0);
      ArrayInitialize(BufLoser,      1.0);   // no history yet -> first breakout is taken
      first = 0;
     }
   else
      first = prev_calculated - 1;

   for(int i = first; i < rates_total; i++)
     {
      //--- true range -------------------------------------------------
      double tr;
      if(i == 0)
         tr = high[0] - low[0];
      else
         tr = MathMax(high[i] - low[i],
                      MathMax(MathAbs(high[i] - close[i - 1]),
                              MathAbs(low[i]  - close[i - 1])));

      //--- N: simple average to seed, then Wilder smoothing -----------
      if(i < InpATRPeriod - 1)
        {
         BufTRSum[i] = (i == 0 ? tr : BufTRSum[i - 1] + tr);
         BufN[i]     = 0.0;
        }
      else
         if(i == InpATRPeriod - 1)
           {
            BufTRSum[i] = BufTRSum[i - 1] + tr;
            BufN[i]     = BufTRSum[i] / InpATRPeriod;
           }
         else
           {
            BufTRSum[i] = BufTRSum[i - 1];
            BufN[i]     = (BufN[i - 1] * (InpATRPeriod - 1) + tr) / InpATRPeriod;
           }

      //--- warm-up ----------------------------------------------------
      if(i < g_startBar)
        {
         BufEntryUp[i]    = EMPTY_VALUE;
         BufEntryDn[i]    = EMPTY_VALUE;
         BufExitUp[i]     = EMPTY_VALUE;
         BufExitDn[i]     = EMPTY_VALUE;
         BufLongEntry[i]  = EMPTY_VALUE;
         BufShortEntry[i] = EMPTY_VALUE;
         BufLongExit[i]   = EMPTY_VALUE;
         BufShortExit[i]  = EMPTY_VALUE;
         BufState[i]      = 0.0;
         BufEntryPrice[i] = 0.0;
         BufStop[i]       = 0.0;
         BufLoser[i]      = 1.0;
         continue;
        }

      //--- channels are built from COMPLETED prior bars only ----------
      double upEntry = HighestHigh(high, i - 1, g_entryPeriod);
      double dnEntry = LowestLow(low,   i - 1, g_entryPeriod);
      double upExit  = HighestHigh(high, i - 1, g_exitPeriod);
      double dnExit  = LowestLow(low,   i - 1, g_exitPeriod);

      BufEntryUp[i] = upEntry;
      BufEntryDn[i] = dnEntry;
      BufExitUp[i]  = upExit;
      BufExitDn[i]  = dnExit;

      BufLongEntry[i]  = EMPTY_VALUE;
      BufShortEntry[i] = EMPTY_VALUE;
      BufLongExit[i]   = EMPTY_VALUE;
      BufShortExit[i]  = EMPTY_VALUE;

      //--- carry the state forward ------------------------------------
      int    st  = (int)BufState[i - 1];
      double ent = BufEntryPrice[i - 1];
      double stp = BufStop[i - 1];
      double lsr = BufLoser[i - 1];

      double n = BufN[i - 1];              // N as known at the open of this bar
      if(n <= 0.0)
         n = BufN[i];
      double off = (n > 0.0 ? 0.4 * n : 5 * _Point);

      bool actedThisBar = false;

      //--- exits are evaluated before entries -------------------------
      if(st != 0)
        {
         bool   isLong    = (st > 0);
         bool   isPhantom = (st == 2 || st == -2);
         bool   doExit    = false;
         double exitPrice = 0.0;

         if(isLong)
           {
            bool hitStop = (InpSignalMode == TURTLE_INTRABAR) ? (low[i]  <= stp)    : (close[i] <= stp);
            bool hitChan = (InpSignalMode == TURTLE_INTRABAR) ? (low[i]  <  dnExit) : (close[i] <  dnExit);
            if(hitStop || hitChan)
              {
               doExit = true;
               if(InpSignalMode == TURTLE_INTRABAR)
                 {
                  // falling price touches the HIGHER level first
                  double chanFill = dnExit - _Point;
                  exitPrice = hitStop ? stp : chanFill;
                  if(hitStop && hitChan)
                     exitPrice = MathMax(stp, chanFill);
                 }
               else
                  exitPrice = close[i];
              }
           }
         else
           {
            bool hitStop = (InpSignalMode == TURTLE_INTRABAR) ? (high[i] >= stp)   : (close[i] >= stp);
            bool hitChan = (InpSignalMode == TURTLE_INTRABAR) ? (high[i] >  upExit) : (close[i] >  upExit);
            if(hitStop || hitChan)
              {
               doExit = true;
               if(InpSignalMode == TURTLE_INTRABAR)
                 {
                  // rising price touches the LOWER level first
                  double chanFill = upExit + _Point;
                  exitPrice = hitStop ? stp : chanFill;
                  if(hitStop && hitChan)
                     exitPrice = MathMin(stp, chanFill);
                 }
               else
                  exitPrice = close[i];
              }
           }

         if(doExit)
           {
            bool won = isLong ? (exitPrice > ent) : (exitPrice < ent);
            lsr = won ? 0.0 : 1.0;

            if(!isPhantom)
              {
               if(isLong)
                  BufLongExit[i] = high[i] + off;
               else
                  BufShortExit[i] = low[i] - off;
              }

            st  = 0;
            ent = 0.0;
            stp = 0.0;
            actedThisBar = true;
           }
        }

      //--- entries -----------------------------------------------------
      if(st == 0 && !actedThisBar)
        {
         bool brkUp = (InpSignalMode == TURTLE_INTRABAR) ? (high[i] > upEntry) : (close[i] > upEntry);
         bool brkDn = (InpSignalMode == TURTLE_INTRABAR) ? (low[i]  < dnEntry) : (close[i] < dnEntry);

         // an outside bar can pierce both channels: follow the bar's direction
         if(brkUp && brkDn)
           {
            if(close[i] >= open[i])
               brkDn = false;
            else
               brkUp = false;
           }

         if(brkUp || brkDn)
           {
            bool take = (!g_useFilter) || (lsr > 0.5);

            if(brkUp)
              {
               ent = (InpSignalMode == TURTLE_INTRABAR) ? upEntry + _Point : close[i];
               stp = ent - InpStopN * n;
               st  = take ? 1 : 2;
               if(take)
                  BufLongEntry[i] = low[i] - off;
              }
            else
              {
               ent = (InpSignalMode == TURTLE_INTRABAR) ? dnEntry - _Point : close[i];
               stp = ent + InpStopN * n;
               st  = take ? -1 : -2;
               if(take)
                  BufShortEntry[i] = high[i] + off;
              }
           }
        }

      //--- persist the state so any bar can be recalculated in place ---
      BufState[i]      = (double)st;
      BufEntryPrice[i] = ent;
      BufStop[i]       = stp;
      BufLoser[i]      = lsr;
     }

//--- alerts and panel only make sense on the live bar ---------------
   int last = rates_total - 1;
   if((InpAlertPopup || InpAlertPush) && prev_calculated > 0)
      CheckAlerts(last, time[last]);
   if(InpShowPanel)
      PanelUpdate(last);

   return(rates_total);
  }

//+------------------------------------------------------------------+
//| Fire an alert at most once per bar                               |
//+------------------------------------------------------------------+
void CheckAlerts(const int idx, const datetime barTime)
  {
   if(barTime == g_lastAlertBar)
      return;

   string what = "";
   if(BufLongEntry[idx]  != EMPTY_VALUE)
      what = "LONG entry";
   else
      if(BufShortEntry[idx] != EMPTY_VALUE)
         what = "SHORT entry";
      else
         if(BufLongExit[idx]   != EMPTY_VALUE)
            what = "exit LONG";
         else
            if(BufShortExit[idx]  != EMPTY_VALUE)
               what = "exit SHORT";

   if(what == "")
      return;

   g_lastAlertBar = barTime;
   string msg = StringFormat("Turtle %d/%d: %s on %s %s",
                             g_entryPeriod, g_exitPeriod, what,
                             _Symbol, EnumToString((ENUM_TIMEFRAMES)_Period));
   if(InpAlertPopup)
      Alert(msg);
   if(InpAlertPush)
      SendNotification(msg);
  }

//+------------------------------------------------------------------+
//| Turtle unit size: risk InpRiskPercent of equity per 1N           |
//+------------------------------------------------------------------+
double UnitSize(const double n)
  {
   if(n <= 0.0)
      return(0.0);

   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickValue <= 0.0 || tickSize <= 0.0)
      return(0.0);

   double riskMoney  = AccountInfoDouble(ACCOUNT_EQUITY) * InpRiskPercent / 100.0;
   double riskPerLot = (n / tickSize) * tickValue;
   if(riskPerLot <= 0.0)
      return(0.0);

   double lots = riskMoney / riskPerLot;

   double step   = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step > 0.0)
      lots = MathFloor(lots / step) * step;
   if(lots < minLot)
      lots = 0.0;                 // account is too small for one unit
   if(maxLot > 0.0 && lots > maxLot)
      lots = maxLot;

   return(lots);
  }

//+------------------------------------------------------------------+
//| Info panel                                                       |
//+------------------------------------------------------------------+
void PanelCreate()
  {
   for(int r = 0; r < 8; r++)
     {
      string name = g_prefix + "row" + IntegerToString(r);
      if(ObjectFind(0, name) >= 0)
         continue;
      ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, name, OBJPROP_CORNER,    CORNER_LEFT_UPPER);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 12);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 20 + r * 16);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE,  9);
      ObjectSetString(0,  name, OBJPROP_FONT,      "Consolas");
      ObjectSetInteger(0, name, OBJPROP_COLOR,     clrGainsboro);
      ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, name, OBJPROP_HIDDEN,    true);
      ObjectSetInteger(0, name, OBJPROP_BACK,      false);
     }
  }

//+------------------------------------------------------------------+
void PanelSet(const int row, const string text, const color clr)
  {
   string name = g_prefix + "row" + IntegerToString(row);
   ObjectSetString(0,  name, OBJPROP_TEXT,  text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
  }

//+------------------------------------------------------------------+
void PanelUpdate(const int idx)
  {
   if(idx < g_startBar)
      return;

   double n     = BufN[idx];
   int    st    = (int)BufState[idx];
   double ent   = BufEntryPrice[idx];
   double stp   = BufStop[idx];
   bool   phant = (st == 2 || st == -2);
   double lots  = UnitSize(n);

   string sState;
   color  cState;
   if(st == 0)
     {
      sState = "FLAT";
      cState = clrGainsboro;
     }
   else
      if(st > 0)
        {
         sState = phant ? "LONG (skipped/phantom)" : "LONG";
         cState = phant ? clrGray : clrLime;
        }
      else
        {
         sState = phant ? "SHORT (skipped/phantom)" : "SHORT";
         cState = phant ? clrGray : clrTomato;
        }

   PanelSet(0, StringFormat("Turtle System %s  %d/%d",
                            (InpSystem == TURTLE_SYSTEM_1 ? "1" :
                             (InpSystem == TURTLE_SYSTEM_2 ? "2" : "C")),
                            g_entryPeriod, g_exitPeriod), clrDodgerBlue);
   PanelSet(1, StringFormat("N (ATR%d)      %s", InpATRPeriod, DoubleToString(n, _Digits)), clrGainsboro);
   PanelSet(2, StringFormat("Unit size      %s lots (%.2f%% per 1N)",
                            DoubleToString(lots, 2), InpRiskPercent), clrGainsboro);
   PanelSet(3, StringFormat("Risk at stop   %.2f%% of equity per unit",
                            InpRiskPercent * InpStopN), clrGainsboro);
   PanelSet(4, StringFormat("Position       %s", sState), cState);

   if(st == 0)
     {
      PanelSet(5, StringFormat("Buy stop      %s", DoubleToString(BufEntryUp[idx], _Digits)), clrLime);
      PanelSet(6, StringFormat("Sell stop     %s", DoubleToString(BufEntryDn[idx], _Digits)), clrTomato);
      PanelSet(7, g_useFilter
               ? StringFormat("Filter         next breakout %s",
                              (BufLoser[idx] > 0.5 ? "TAKEN" : "SKIPPED (last one won)"))
               : "Filter         off", clrGainsboro);
     }
   else
     {
      bool   isLong = (st > 0);
      double nextAdd = isLong ? ent + InpAddEveryN * n : ent - InpAddEveryN * n;
      PanelSet(5, StringFormat("Entry / Stop   %s / %s",
                               DoubleToString(ent, _Digits), DoubleToString(stp, _Digits)), clrGainsboro);
      PanelSet(6, StringFormat("Next add (%.1fN) %s   [max %d units]",
                               InpAddEveryN, DoubleToString(nextAdd, _Digits), InpMaxUnits), clrGainsboro);
      PanelSet(7, StringFormat("Exit channel   %s",
                               DoubleToString(isLong ? BufExitDn[idx] : BufExitUp[idx], _Digits)), clrAqua);
     }

   ChartRedraw();
  }
//+------------------------------------------------------------------+
