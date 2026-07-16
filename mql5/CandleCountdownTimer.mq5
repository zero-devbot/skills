//+------------------------------------------------------------------+
//|                                        CandleCountdownTimer.mq5  |
//|                    Candle close countdown timer (TradingView-like)|
//+------------------------------------------------------------------+
#property copyright "Candle Countdown Timer"
#property version   "1.00"
#property indicator_chart_window
#property indicator_plots 0
#property strict

//--- inputs
input int              InpFontSize   = 12;                    // Font Size
input color             InpFontColor  = clrWhite;               // Font Color
input string            InpFontName   = "Arial";                // Font Type
input ENUM_BASE_CORNER  InpCorner     = CORNER_RIGHT_LOWER;      // Chart Corner
input int               InpXOffset    = 20;                     // X Offset
input int               InpYOffset    = 20;                     // Y Offset

//--- object name (unique per chart)
string g_labelName;

//+------------------------------------------------------------------+
//| Build the label text for the given number of seconds remaining   |
//+------------------------------------------------------------------+
string FormatCountdown(long secondsLeft, int periodSeconds)
  {
   if(secondsLeft < 0)
      secondsLeft = 0;

   int hours   = (int)(secondsLeft / 3600);
   int minutes = (int)((secondsLeft % 3600) / 60);
   int seconds = (int)(secondsLeft % 60);

   if(periodSeconds >= 3600)
      return StringFormat("%02d:%02d:%02d", hours, minutes, seconds);

   return StringFormat("%02d:%02d", minutes, seconds);
  }

//+------------------------------------------------------------------+
//| Create (or reuse) the countdown label object                     |
//+------------------------------------------------------------------+
void CreateLabel()
  {
   if(ObjectFind(0, g_labelName) < 0)
     {
      ObjectCreate(0, g_labelName, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, g_labelName, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, g_labelName, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, g_labelName, OBJPROP_BACK, false);
     }

   ObjectSetInteger(0, g_labelName, OBJPROP_CORNER, InpCorner);
   ObjectSetInteger(0, g_labelName, OBJPROP_XDISTANCE, InpXOffset);
   ObjectSetInteger(0, g_labelName, OBJPROP_YDISTANCE, InpYOffset);
   ObjectSetInteger(0, g_labelName, OBJPROP_COLOR, InpFontColor);
   ObjectSetInteger(0, g_labelName, OBJPROP_FONTSIZE, InpFontSize);
   ObjectSetString(0, g_labelName, OBJPROP_FONT, InpFontName);
  }

//+------------------------------------------------------------------+
//| Recompute remaining time and refresh the label text               |
//+------------------------------------------------------------------+
void UpdateCountdown()
  {
   int periodSeconds = PeriodSeconds(PERIOD_CURRENT);
   if(periodSeconds <= 0)
      return;

   datetime barOpenTime  = iTime(_Symbol, PERIOD_CURRENT, 0);
   datetime barCloseTime = barOpenTime + periodSeconds;
   long     secondsLeft  = (long)barCloseTime - (long)TimeCurrent();

   ObjectSetString(0, g_labelName, OBJPROP_TEXT, FormatCountdown(secondsLeft, periodSeconds));
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Custom indicator initialization function                         |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_labelName = "CandleCountdownTimer_" + IntegerToString((int)ChartID());

   CreateLabel();
   UpdateCountdown();

   EventSetTimer(1);

   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Custom indicator deinitialization function                       |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();

   ObjectDelete(0, g_labelName);
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Timer function - ticks every second regardless of price activity |
//+------------------------------------------------------------------+
void OnTimer()
  {
   UpdateCountdown();
  }

//+------------------------------------------------------------------+
//| Custom indicator iteration function                               |
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
   UpdateCountdown();
   return(rates_total);
  }
//+------------------------------------------------------------------+
