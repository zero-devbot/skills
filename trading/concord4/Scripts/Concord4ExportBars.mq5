//+------------------------------------------------------------------+
//|                                          Concord4ExportBars.mq5 |
//|        Export bars for the research harness, already in UTC      |
//+------------------------------------------------------------------+
//| Run once on any chart. Writes one CSV per symbol into            |
//| MQL5/Files/, ready for run_protocol.py with no conversion and no |
//| --server-offset flag.                                            |
//|                                                                   |
//| WHY THIS EXISTS                                                   |
//| MetaTrader stores and exports bar times in the broker's server    |
//| time. Every session boundary in CONCORD-4 is specified in UTC. A  |
//| manual export loaded without the right offset shifts the opening  |
//| range by the offset, and nothing in the results looks wrong - you |
//| simply get confident numbers for a strategy you did not test.     |
//|                                                                   |
//| This script resolves the offset with the same C4ToUtc() the EA    |
//| uses and writes UTC timestamps, so the trap cannot be stepped on. |
//| The header records the offset applied; the Python loader reads it |
//| and REFUSES a --server-offset on top, because double-applying it  |
//| would just be the same bug wearing a different hat.               |
//+------------------------------------------------------------------+
#property copyright "CONCORD-4"
#property version   "1.00"
#property script_show_inputs

#include <Concord4Core.mqh>

input group                "Range";
input datetime InpFrom          = D'2015.01.01 00:00';  // From (server time)
input datetime InpTo            = 0;                    // To (0 = now)

input group                "Symbols";
input string InpSymbol          = "XAUUSD";  // Traded symbol
input bool   InpExportBasket    = true;      // Also export the USD-basket legs
input string InpSymbolSuffix    = "";        // Broker suffix ("" = auto-detect)

input group                "Timeframes";
input ENUM_TIMEFRAMES InpTimeframe    = PERIOD_M15;  // Traded symbol timeframe
input ENUM_TIMEFRAMES InpLegTimeframe = PERIOD_H1;   // USD-basket leg timeframe

input group                "Output";
input string InpPrefix          = "";    // Filename prefix
input bool   InpOverwrite       = true;  // Overwrite existing files

input group                "Execution";
input ENUM_C4_GMT_MODE InpGmtMode = C4_GMT_AUTO;  // Server-to-UTC offset mode
input int    InpGmtOffsetHours  = 0;     // Manual offset (hours, if mode = Manual)

//+------------------------------------------------------------------+
//| Ask the terminal to load history, then wait for it to arrive.    |
//| A cold symbol returns nothing on the first call: the request is   |
//| what starts the download.                                         |
//+------------------------------------------------------------------+
bool EnsureHistory(const string symbol, const ENUM_TIMEFRAMES tf,
                   const datetime from, const datetime to)
  {
   MqlRates probe[];
   for(int attempt = 0; attempt < 50; attempt++)
     {
      if(IsStopped()) return false;
      int copied = CopyRates(symbol, tf, from, to, probe);
      if(copied > 0) return true;
      Sleep(400);
     }
   return false;
  }

//+------------------------------------------------------------------+
//| Export one symbol. Returns the number of bars written, or -1.    |
//+------------------------------------------------------------------+
long ExportSymbol(const string resolved, const string outName,
                  const ENUM_TIMEFRAMES tf, const datetime from, const datetime to)
  {
   if(!EnsureHistory(resolved, tf, from, to))
     {
      PrintFormat("CONCORD-4 export: %s has no %s history in that range. "
                  "Open a chart on it and scroll back, or raise "
                  "Tools > Options > Charts > Max bars in chart.",
                  resolved, EnumToString(tf));
      return -1;
     }

   if(!InpOverwrite && FileIsExist(outName))
     {
      PrintFormat("CONCORD-4 export: %s already exists, skipping.", outName);
      return 0;
     }

   int file = FileOpen(outName, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(file == INVALID_HANDLE)
     {
      PrintFormat("CONCORD-4 export: cannot open %s (error %d)", outName, GetLastError());
      return -1;
     }

   int digits = (int)SymbolInfoInteger(resolved, SYMBOL_DIGITS);
   double point = SymbolInfoDouble(resolved, SYMBOL_POINT);

   //--- the header is the contract with the Python loader
   FileWriteString(file, "# concord4_bars v1\n");
   FileWriteString(file, "# timezone=UTC\n");
   FileWriteString(file, StringFormat("# server_offset_hours=%.2f\n", g_gmtOffsetSec / 3600.0));
   FileWriteString(file, StringFormat("# symbol=%s timeframe=%s digits=%d point=%.10f\n",
                                      resolved, EnumToString(tf), digits, point));
   FileWriteString(file, StringFormat("# broker=%s server=%s\n",
                                      AccountInfoString(ACCOUNT_COMPANY),
                                      AccountInfoString(ACCOUNT_SERVER)));
   FileWriteString(file, "time,open,high,low,close,tick_volume,spread\n");

   long written = 0;
   datetime cursor = from;
   MqlRates rates[];

   //--- year-sized chunks: a decade of M15 in one array is needlessly large,
   //--- and chunking gives the user progress on a long export
   while(cursor < to)
     {
      if(IsStopped()) break;
      datetime chunkEnd = cursor + 365 * 86400;
      if(chunkEnd > to) chunkEnd = to;

      int copied = CopyRates(resolved, tf, cursor, chunkEnd, rates);
      for(int i = 0; i < copied; i++)
        {
         if(rates[i].open <= 0.0 || rates[i].high < rates[i].low) continue;

         datetime utc = C4ToUtc(rates[i].time);
         MqlDateTime parts;
         TimeToStruct(utc, parts);

         string row = StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ,",
                                   parts.year, parts.mon, parts.day,
                                   parts.hour, parts.min, parts.sec);
         row += DoubleToString(rates[i].open,  digits) + ",";
         row += DoubleToString(rates[i].high,  digits) + ",";
         row += DoubleToString(rates[i].low,   digits) + ",";
         row += DoubleToString(rates[i].close, digits) + ",";
         row += StringFormat("%I64d,", rates[i].tick_volume);
         //--- spread in PRICE units, so nothing downstream has to guess
         row += DoubleToString((double)rates[i].spread * point, digits + 1) + "\n";

         FileWriteString(file, row);
         written++;
        }

      cursor = chunkEnd;
      if(written > 0 && written % 50000 < copied)
         PrintFormat("CONCORD-4 export: %s ... %I64d bars", resolved, written);
     }

   FileClose(file);
   return written;
  }

//+------------------------------------------------------------------+
void OnStart()
  {
   C4Config cfg;
   C4DefaultConfig(cfg);
   cfg.symbol             = InpSymbol;
   cfg.symbolSuffix       = InpSymbolSuffix;
   cfg.gmtMode            = InpGmtMode;
   cfg.gmtManualOffsetHrs = InpGmtOffsetHours;

   C4ResolveGmtOffset(cfg);
   PrintFormat("CONCORD-4 export: server-to-UTC offset %+.1f h "
               "(server %s / GMT %s). Bars will be written in UTC.",
               g_gmtOffsetSec / 3600.0,
               TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES),
               TimeToString(TimeGMT(), TIME_DATE | TIME_MINUTES));

   datetime to = (InpTo == 0) ? TimeCurrent() : InpTo;
   if(to <= InpFrom)
     {
      Print("CONCORD-4 export: 'To' must be after 'From'. Aborting.");
      return;
     }

   string bases[7];
   ENUM_TIMEFRAMES frames[7];
   int count = 0;

   bases[count] = InpSymbol; frames[count] = InpTimeframe; count++;
   if(InpExportBasket)
     {
      string legs[6] = {"EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDCHF", "AUDUSD"};
      for(int i = 0; i < 6; i++)
        {
         if(legs[i] == InpSymbol) continue;
         bases[count] = legs[i]; frames[count] = InpLegTimeframe; count++;
        }
     }

   long total = 0;
   int exported = 0, failed = 0;

   for(int i = 0; i < count; i++)
     {
      if(IsStopped()) break;

      string resolved;
      if(!C4ResolveSymbol(bases[i], InpSymbolSuffix, resolved))
        {
         PrintFormat("CONCORD-4 export: %s not found at this broker, skipping.", bases[i]);
         failed++;
         continue;
        }

      //--- named for the BASE symbol: the harness looks for XAUUSD.csv,
      //--- not XAUUSD.m.csv, whatever the broker calls it internally
      string outName = InpPrefix + bases[i] + ".csv";
      long written = ExportSymbol(resolved, outName, frames[i], InpFrom, to);

      if(written < 0) { failed++; continue; }
      PrintFormat("CONCORD-4 export: %-10s %8I64d bars  %s -> MQL5/Files/%s",
                  resolved, written, EnumToString(frames[i]), outName);
      total += written;
      exported++;
     }

   PrintFormat("CONCORD-4 export: %d file(s), %I64d bars total, %d failure(s).",
               exported, total, failed);

   if(exported < 4 && InpExportBasket)
      Print("CONCORD-4 export: the L2 gate needs the traded symbol plus at least "
            "THREE basket legs, or it fails closed and no trade is ever taken.");

   Print("CONCORD-4 export: copy MQL5/Files/*.csv into the harness's data/ folder, then run");
   Print("  python3 run_protocol.py --data-dir data/ --out results/");
   Print("CONCORD-4 export: do NOT pass --server-offset - these files are already UTC.");
  }
