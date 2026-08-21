//+------------------------------------------------------------------+
//|                               AnalyzeYesterdayPositions.mq5      |
//|                       Copyright 2026, J.A.R.V.I.S. Quantitative   |
//|                                https://github.com/saeedKhodor     |
//+------------------------------------------------------------------+
// === CODE INDEX ===
// 1. Properties & Includes (Line 20)
// 2. Input Parameters & Date Filters (Line 30)
// 3. Global Handles (Line 45)
// 4. OnInit() - Handle Setup & History Analysis (Line 60)
// 5. RunAnalysis() - Scans yesterday's bars with native MT5 CopyBuffer() EMAs (Line 100)
// 6. OnDeinit() - Cleanup (Line 190)
// ==================================================================
#property copyright   "J.A.R.V.I.S. Trading"
#property link        "https://github.com/saeedKhodor/TradingJarvis"
#property version     "1.00"
#property script_show_inputs

#include <Trade\SymbolInfo.mqh>

input string   InpSymbol        = "US500.cash";
input datetime InpTargetDate    = D'2026.08.20 00:00';

int h_m5_ema9   = INVALID_HANDLE;
int h_m15_ema9  = INVALID_HANDLE;
int h_m30_ema9  = INVALID_HANDLE;
int h_h1_ema9   = INVALID_HANDLE;
int h_h1_ema21  = INVALID_HANDLE;
int h_h1_ema50  = INVALID_HANDLE;
int h_d1_ema9   = INVALID_HANDLE;

//+------------------------------------------------------------------+
//| Script program start function                                    |
//+------------------------------------------------------------------+
void OnStart()
{
   PrintFormat("[*] Starting Native MT5 Indicator Extraction for %s on %s...", InpSymbol, TimeToString(InpTargetDate, TIME_DATE));

   // Create native MT5 indicator handles
   h_m5_ema9   = iMA(InpSymbol, PERIOD_M5,  9, 0, MODE_EMA, PRICE_CLOSE);
   h_m15_ema9  = iMA(InpSymbol, PERIOD_M15, 9, 0, MODE_EMA, PRICE_CLOSE);
   h_m30_ema9  = iMA(InpSymbol, PERIOD_M30, 9, 0, MODE_EMA, PRICE_CLOSE);
   h_h1_ema9   = iMA(InpSymbol, PERIOD_H1,  9, 0, MODE_EMA, PRICE_CLOSE);
   h_h1_ema21  = iMA(InpSymbol, PERIOD_H1, 21, 0, MODE_EMA, PRICE_CLOSE);
   h_h1_ema50  = iMA(InpSymbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   h_d1_ema9   = iMA(InpSymbol, PERIOD_D1,  9, 0, MODE_EMA, PRICE_CLOSE);

   if(h_m5_ema9 == INVALID_HANDLE || h_m15_ema9 == INVALID_HANDLE ||
      h_m30_ema9 == INVALID_HANDLE || h_h1_ema9 == INVALID_HANDLE ||
      h_h1_ema21 == INVALID_HANDLE || h_h1_ema50 == INVALID_HANDLE ||
      h_d1_ema9 == INVALID_HANDLE)
   {
      Print("[!] Error creating native MT5 indicator handles.");
      return;
   }

   Sleep(1000); // Allow MT5 to calculate buffer values

   datetime start_time = InpTargetDate;
   datetime end_time   = InpTargetDate + 86400; // 24 hours

   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   int bar_count = CopyRates(InpSymbol, PERIOD_M5, start_time, end_time, rates);

   if(bar_count <= 0)
   {
      PrintFormat("[!] No M5 bars found for %s between %s and %s", InpSymbol, TimeToString(start_time), TimeToString(end_time));
      return;
   }

   PrintFormat("[+] Retrieved %d M5 bars from MT5 for yesterday.", bar_count);

   // Open CSV in Common Files
   string filename = "yesterday_analysis_20260820.csv";
   int file_handle = FileOpen(filename, FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI, ",");
   if(file_handle == INVALID_HANDLE)
   {
      Print("[!] Failed to create CSV file in Common Files.");
      return;
   }

   // Write Header
   FileWrite(file_handle, "Time", "Open", "High", "Low", "Close", 
             "MT5_M5_EMA9", "MT5_M15_EMA9", "MT5_M30_EMA9", 
             "MT5_H1_EMA9", "MT5_H1_EMA21", "MT5_H1_EMA50", "MT5_D1_EMA9",
             "Cascade_Active", "Bull_Alignment", "Golden_Pocket_Short", "Pullback_Long");

   for(int i = 0; i < bar_count; i++)
   {
      datetime bar_dt = rates[i].time;
      double o = rates[i].open;
      double h = rates[i].high;
      double l = rates[i].low;
      double c = rates[i].close;

      // Extract native MT5 EMA buffer values at exact bar timestamp
      double buf_m5_9[1], buf_m15_9[1], buf_m30_9[1], buf_h1_9[1], buf_h1_21[1], buf_h1_50[1], buf_d1_9[1];
      CopyBuffer(h_m5_ema9,  0, bar_dt, 1, buf_m5_9);
      CopyBuffer(h_m15_ema9, 0, bar_dt, 1, buf_m15_9);
      CopyBuffer(h_m30_ema9, 0, bar_dt, 1, buf_m30_9);
      CopyBuffer(h_h1_ema9,  0, bar_dt, 1, buf_h1_9);
      CopyBuffer(h_h1_ema21, 0, bar_dt, 1, buf_h1_21);
      CopyBuffer(h_h1_ema50, 0, bar_dt, 1, buf_h1_50);
      CopyBuffer(h_d1_ema9,  0, bar_dt, 1, buf_d1_9);

      double m5_9   = buf_m5_9[0];
      double m15_9  = buf_m15_9[0];
      double m30_9  = buf_m30_9[0];
      double h1_9   = buf_h1_9[0];
      double h1_21  = buf_h1_21[0];
      double h1_50  = buf_h1_50[0];
      double d1_9   = buf_d1_9[0];

      // Strategy Conditions evaluated directly on native MT5 buffers
      bool is_cascade = (c < h1_9 && h1_9 < h1_21 && h1_21 < h1_50);
      bool is_bull_align = (c > m15_9 && m15_9 > h1_9 && c > d1_9);

      // Golden Pocket Short Check
      bool touches_ema = (h >= (h1_9 - 2.5) && h <= (h1_21 + 2.5)) || (h >= (m30_9 - 2.5) && h <= (h1_9 + 2.5));
      bool is_bear_candle = (c < o);
      double range = h - l;
      double upper_wick = h - MathMax(o, c);
      bool is_rejection = (range > 0.0) && ((upper_wick / range) >= 0.25);
      bool golden_pocket_short = is_cascade && touches_ema && (is_bear_candle || is_rejection);

      // Pullback Long Check
      bool pullback_dip = (l <= (m15_9 + 2.5) && c >= m15_9);
      double lower_wick = MathMin(o, c) - l;
      bool is_bull_rejection = (range > 0.0) && ((lower_wick / range) >= 0.25);
      bool pullback_long = is_bull_align && pullback_dip && (c > o || is_bull_rejection);

      FileWrite(file_handle, 
                TimeToString(bar_dt, TIME_DATE|TIME_MINUTES),
                DoubleToString(o, 2), DoubleToString(h, 2), DoubleToString(l, 2), DoubleToString(c, 2),
                DoubleToString(m5_9, 2), DoubleToString(m15_9, 2), DoubleToString(m30_9, 2),
                DoubleToString(h1_9, 2), DoubleToString(h1_21, 2), DoubleToString(h1_50, 2), DoubleToString(d1_9, 2),
                is_cascade ? "1" : "0",
                is_bull_align ? "1" : "0",
                golden_pocket_short ? "1" : "0",
                pullback_long ? "1" : "0");
   }

   FileClose(file_handle);
   PrintFormat("[+] Successfully exported yesterday's data to Common Files\\%s", filename);

   // Cleanup handles
   IndicatorRelease(h_m5_ema9);
   IndicatorRelease(h_m15_ema9);
   IndicatorRelease(h_m30_ema9);
   IndicatorRelease(h_h1_ema9);
   IndicatorRelease(h_h1_ema21);
   IndicatorRelease(h_h1_ema50);
   IndicatorRelease(h_d1_ema9);
}
