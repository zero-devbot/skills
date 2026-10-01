//+------------------------------------------------------------------+
//|                                              Concord4Export.mq5 |
//|      Export the terminal's gate state for the Python parity harness |
//+------------------------------------------------------------------+
//| Attach to an M15 chart of the traded symbol and run once. Writes  |
//| MQL5/Files/<InpFileName>, which research/check_parity.py diffs    |
//| against the Python implementation.                                |
//|                                                                   |
//| The export is deliberately SELF-CONTAINED: it carries the bars    |
//| the terminal used, the higher-timeframe values it derived from    |
//| them, and the resulting gates. That lets the Python side separate  |
//| three different kinds of disagreement:                             |
//|                                                                   |
//|   1. different bars      - broker history vs. your CSV            |
//|   2. different HTF values- server-time D1 boundaries vs. UTC days |
//|   3. different logic     - an actual bug in one implementation    |
//|                                                                   |
//| Without the HTF columns, (2) masquerades as (3) and the harness    |
//| sends you hunting for a bug that is really a timezone.            |
//|                                                                   |
//| Inputs must match the ones used for the Python run, and the        |
//| iCustom cross-check columns are only meaningful while they also    |
//| match the Concord4 indicator's own defaults.                       |
//+------------------------------------------------------------------+
#property copyright "CONCORD-4"
#property version   "1.00"
#property script_show_inputs

#include <Concord4Core.mqh>

input group                "Export";
input string InpFileName        = "concord4_mt5_export.csv";  // Output file (MQL5/Files)
input int    InpBars            = 3000;   // M15 bars to export (newest first)
input bool   InpCrossCheck      = true;   // Also read the Concord4 indicator via iCustom

input group                "L0  Tradability";
input int    InpSessionAStart   = 420;    // Session A start (min from 00:00 UTC)
input int    InpSessionAEnd     = 660;    // Session A end   (min)
input int    InpSessionBStart   = 780;    // Session B start (min)
input int    InpSessionBEnd     = 960;    // Session B end   (min)
input double InpMaxSpreadAtr    = 0.06;   // Max spread as fraction of ATR(M15)
input bool   InpUseNewsFilter   = false;  // OFF by default: Python has no calendar
input int    InpNewsPadMinutes  = 15;     // News blackout half-width (minutes)
input int    InpVolPctLow       = 20;     // ATR(D1) percentile floor
input int    InpVolPctHigh      = 90;     // ATR(D1) percentile ceiling
input int    InpVolPctLookback  = 250;    // Percentile sample size (days)

input group                "L1  Regime bias (D1)";
input int    InpEmaD1Period     = 50;     // D1 EMA period
input int    InpTsmomDays       = 63;     // Time-series momentum lookback (days)

input group                "L2  Intermarket (USD basket)";
input string InpSymbolSuffix    = "";     // Broker symbol suffix ("" = auto-detect)
input int    InpUsdEmaPeriod    = 20;     // USD index EMA period (H1 bars)
input int    InpUsdSlopeBars    = 3;      // USD index slope lookback (H1 bars)

input group                "L3  Opening-range trigger";
input int    InpOrStartMin      = 420;    // Opening range start (min from 00:00 UTC)
input int    InpOrLengthMin     = 30;     // Opening range length (minutes)
input double InpBreakoutAtrK    = 0.15;   // Breakout buffer beyond OR edge (x ATR)
input double InpMinBarRangeAtr  = 0.80;   // Min break-bar range (x ATR)
input double InpMinVolMult      = 1.50;   // Min break-bar tick volume (x 20-bar avg)
input double InpMaxOrWidthAdr   = 1.20;   // Max OR width (x ADR20)
input double InpMaxChaseAtr     = 2.00;   // Max distance beyond OR edge (x ATR)

input group                "Risk geometry";
input double InpStopStructBuf   = 0.10;   // Stop buffer beyond opposite OR edge (x ATR)
input double InpStopMinAtr      = 1.50;   // Minimum stop distance (x ATR)
input double InpStopMaxAtr      = 2.00;   // Maximum stop distance (x ATR)

input group                "Execution";
input ENUM_C4_GMT_MODE InpGmtMode = C4_GMT_AUTO;  // Server-to-UTC offset mode
input int    InpGmtOffsetHours  = 0;      // Manual offset (hours, if mode = Manual)

C4Config g_cfg;

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
//| CSV helpers. Unset doubles are written as "nan" so pandas parses  |
//| them as missing instead of as a real zero.                        |
//+------------------------------------------------------------------+
string Num(const double value, const int digits, const bool zero_is_unset = false)
  {
   if(!MathIsValidNumber(value)) return "nan";
   if(zero_is_unset && MathAbs(value) < 1e-12) return "nan";
   return DoubleToString(value, digits);
  }

string Quoted(string text)
  {
   StringReplace(text, "\"", "'");
   return "\"" + text + "\"";
  }

//+------------------------------------------------------------------+
//| Wait for the iCustom handle to finish its first calculation.      |
//+------------------------------------------------------------------+
bool WaitForIndicator(const int handle, const int needed)
  {
   if(handle == INVALID_HANDLE) return false;
   for(int attempt = 0; attempt < 100; attempt++)
     {
      int calculated = BarsCalculated(handle);
      if(calculated >= needed) return true;
      if(IsStopped()) return false;
      Sleep(200);
     }
   PrintFormat("CONCORD-4 export: indicator calculated only %d of %d bars - "
               "iCustom columns will be incomplete. Raise the indicator's InpMaxBars.",
               BarsCalculated(handle), needed);
   return BarsCalculated(handle) > 0;
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   if(Period() != PERIOD_M15)
     {
      Print("CONCORD-4 export: attach to an M15 chart. Aborting.");
      return;
     }

   BuildConfig();
   if(!C4Init(g_cfg))
     {
      Print("CONCORD-4 export: C4Init failed. Aborting.");
      return;
     }

   int available = Bars(_Symbol, PERIOD_M15);
   int count = MathMin(InpBars, available - 2);
   if(count < 10)
     {
      PrintFormat("CONCORD-4 export: only %d M15 bars available. Aborting.", available);
      C4Deinit();
      return;
     }

   int icHandle = INVALID_HANDLE;
   bool icReady = false;
   if(InpCrossCheck)
     {
      icHandle = iCustom(_Symbol, PERIOD_M15, "Concord4");
      icReady = WaitForIndicator(icHandle, count + 1);
      if(!icReady)
         Print("CONCORD-4 export: iCustom cross-check unavailable - "
               "columns ic_* will be nan. Is Concord4.ex5 compiled?");
      else
         Print("CONCORD-4 export: iCustom cross-check active. NOTE - it is only "
               "valid while this script's inputs match the indicator's defaults.");
     }

   int file = FileOpen(InpFileName, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(file == INVALID_HANDLE)
     {
      PrintFormat("CONCORD-4 export: cannot open %s (error %d)", InpFileName, GetLastError());
      C4Deinit();
      return;
     }

   //--- metadata: everything the Python side needs to reproduce the run
   FileWriteString(file, "# concord4_export v1\n");
   FileWriteString(file, StringFormat("# symbol=%s digits=%d point=%.10f\n",
                                      _Symbol, _Digits, SymbolInfoDouble(_Symbol, SYMBOL_POINT)));
   FileWriteString(file, StringFormat("# broker=%s server=%s\n",
                                      AccountInfoString(ACCOUNT_COMPANY),
                                      AccountInfoString(ACCOUNT_SERVER)));
   FileWriteString(file, StringFormat("# gmt_offset_hours=%.2f\n", g_gmtOffsetSec / 3600.0));
   FileWriteString(file, StringFormat("# exported_utc=%s bars=%d\n",
                                      TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS), count));
   FileWriteString(file, StringFormat("# news_filter=%s calendar_ok=%s\n",
                                      InpUseNewsFilter ? "on" : "off",
                                      g_calendarOK ? "yes" : "no"));
   FileWriteString(file, StringFormat(
      "# cfg session_a=%d-%d session_b=%d-%d max_spread_atr=%.4f vol_pct=%d-%d lookback=%d\n",
      InpSessionAStart, InpSessionAEnd, InpSessionBStart, InpSessionBEnd,
      InpMaxSpreadAtr, InpVolPctLow, InpVolPctHigh, InpVolPctLookback));
   FileWriteString(file, StringFormat(
      "# cfg ema_d1=%d tsmom=%d usd_ema=%d usd_slope=%d or=%d+%d k=%.4f "
      "min_range=%.4f min_vol=%.4f max_or_adr=%.4f max_chase=%.4f\n",
      InpEmaD1Period, InpTsmomDays, InpUsdEmaPeriod, InpUsdSlopeBars,
      InpOrStartMin, InpOrLengthMin, InpBreakoutAtrK, InpMinBarRangeAtr,
      InpMinVolMult, InpMaxOrWidthAdr, InpMaxChaseAtr));
   FileWriteString(file, StringFormat(
      "# cfg stop_struct=%.4f stop_min=%.4f stop_max=%.4f\n",
      InpStopStructBuf, InpStopMinAtr, InpStopMaxAtr));

   FileWriteString(file,
      "time_server,time_utc,open,high,low,close,tick_volume,spread,"
      "atr_m15,atr_h1,atr_d1,adr20,vol_pct,"
      "close_d1,ema_d1,tsmom_ref,usd_ema,usd_ema_prev,"
      "l0,l1,l2,l3,signal,or_high,or_low,risk_dist,stop,"
      "ic_l0,ic_l1,ic_l2,ic_l3,ic_signal,ready,l0_reason,veto_reason\n");

   MqlRates bar[];
   ArraySetAsSeries(bar, true);
   C4State st;
   int written = 0, signals = 0, icMismatch = 0;

   //--- oldest first, so the CSV reads chronologically
   for(int shift = count; shift >= 1; shift--)
     {
      if(IsStopped()) break;
      if(CopyRates(_Symbol, PERIOD_M15, shift, 1, bar) < 1) continue;

      C4Evaluate(g_cfg, shift, st);

      double icL0 = 0.0, icL1 = 0.0, icL2 = 0.0, icL3 = 0.0, icSignal = 0.0;
      bool icHave = false;
      if(icReady)
        {
         double buf[];
         ArraySetAsSeries(buf, true);
         bool ok = true;
         ok = ok && CopyBuffer(icHandle, 4, shift, 1, buf) == 1; if(ok) icL0     = buf[0];
         ok = ok && CopyBuffer(icHandle, 5, shift, 1, buf) == 1; if(ok) icL1     = buf[0];
         ok = ok && CopyBuffer(icHandle, 6, shift, 1, buf) == 1; if(ok) icL2     = buf[0];
         ok = ok && CopyBuffer(icHandle, 7, shift, 1, buf) == 1; if(ok) icL3     = buf[0];
         ok = ok && CopyBuffer(icHandle, 8, shift, 1, buf) == 1; if(ok) icSignal = buf[0];
         icHave = ok;

         if(icHave && (int)icSignal != st.signal) icMismatch++;
        }

      string row = StringFormat("%s,%s,", TimeToString(bar[0].time, TIME_DATE | TIME_SECONDS),
                                TimeToString(C4ToUtc(bar[0].time), TIME_DATE | TIME_SECONDS));
      row += Num(bar[0].open,  _Digits) + "," + Num(bar[0].high, _Digits) + ",";
      row += Num(bar[0].low,   _Digits) + "," + Num(bar[0].close, _Digits) + ",";
      row += StringFormat("%I64d,%d,", bar[0].tick_volume, bar[0].spread);
      row += Num(st.atrM15, 8) + "," + Num(st.atrH1, 8) + "," + Num(st.atrD1, 8) + ",";
      row += Num(st.adr20, 8) + "," + Num(st.volPct, 6, true) + ",";
      row += Num(st.closeD1, 8, true) + "," + Num(st.emaD1, 8, true) + "," + Num(st.tsmomRef, 8, true) + ",";
      row += Num(st.usdEma, 10, true) + "," + Num(st.usdEmaPrev, 10, true) + ",";
      row += StringFormat("%d,%d,%d,%d,%d,", st.l0Pass ? 1 : 0, st.l1Bias, st.l2Bias,
                          st.l3Trigger, st.signal);
      row += Num(st.orHigh, _Digits, true) + "," + Num(st.orLow, _Digits, true) + ",";
      row += Num(st.riskDist, 8, true) + "," + Num(st.stop, _Digits, true) + ",";

      if(icHave)
         row += StringFormat("%d,%d,%d,%d,%d,", (int)icL0, (int)icL1, (int)icL2,
                             (int)icL3, (int)icSignal);
      else
         row += "nan,nan,nan,nan,nan,";

      row += StringFormat("%d,", st.ready ? 1 : 0);
      row += Quoted(st.l0Reason) + "," + Quoted(st.vetoReason) + "\n";

      FileWriteString(file, row);
      written++;
      if(st.signal != C4_NEUTRAL) signals++;

      if(written % 1000 == 0)
         PrintFormat("CONCORD-4 export: %d / %d bars", written, count);
     }

   FileClose(file);
   if(icHandle != INVALID_HANDLE) IndicatorRelease(icHandle);
   C4Deinit();

   PrintFormat("CONCORD-4 export: wrote %d bars (%d signals) to MQL5/Files/%s",
               written, signals, InpFileName);
   if(icReady)
     {
      if(icMismatch == 0)
         Print("CONCORD-4 export: iCustom cross-check AGREES on every bar - "
               "the indicator's buffers match the shared core.");
      else
         PrintFormat("CONCORD-4 export: iCustom cross-check DISAGREES on %d bar(s). "
                     "Either the script's inputs differ from the indicator's defaults, "
                     "or the indicator's buffer wiring is wrong.", icMismatch);
     }
   Print("CONCORD-4 export: next, run  python check_parity.py --mt5-csv <file>");
  }
