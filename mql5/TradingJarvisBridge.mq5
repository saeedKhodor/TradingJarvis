// === CODE INDEX ===
// 1. Properties & Input Parameters (Line 15)
// 2. Indicator Handle Declarations & Structures (Line 38)
// 3. OnInit() - Initializes MT5 native iMA indicator handles (Line 60)
// 4. OnDeinit() - Releases indicator handles and cleans up resources (Line 125)
// 5. OnTick() - Triggered on live incoming ticks (Line 150)
// 6. OnTimer() - Periodic fallback export timer (Line 160)
// 7. UpdateAndExportIndicators() - Reads CopyBuffer and writes JSON to Common Files (Line 172)
// ===================

#property copyright "TradingJarvis AI"
#property link      "https://github.com/saeedKhodor/TradingJarvis"
#property version   "1.00"
#property description "J.A.R.V.I.S. Native MT5 Multi-Timeframe 9-EMA Indicator Bridge"

// --- Input Parameters
input group "=== Indicator Settings ==="
input int                InpEmaPeriod       = 9;              // EMA Period
input ENUM_APPLIED_PRICE InpAppliedPrice    = PRICE_CLOSE;    // Applied Price
input ENUM_MA_METHOD     InpMaMethod        = MODE_EMA;       // Moving Average Method

input group "=== Bridge Export Settings ==="
input int                InpTimerIntervalMs = 500;            // Export Timer Interval (ms)
input bool               InpVerboseLogs     = false;          // Enable Diagnostic Logging

// --- Global Indicator Handles
int h_m1  = INVALID_HANDLE;
int h_m2  = INVALID_HANDLE;
int h_m5  = INVALID_HANDLE;
int h_m10 = INVALID_HANDLE;
int h_m15 = INVALID_HANDLE;
int h_m30 = INVALID_HANDLE;
int h_h1  = INVALID_HANDLE;
int h_h4  = INVALID_HANDLE;
int h_d1  = INVALID_HANDLE;

datetime g_last_export_time = 0;
double   g_last_export_price = 0.0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("[J.A.R.V.I.S. Bridge] Initializing native MT5 Multi-Timeframe 9-EMA handles for ", _Symbol, "...");

   // Initialize native MT5 iMA handles
   h_m1  = iMA(_Symbol, PERIOD_M1,  InpEmaPeriod, 0, InpMaMethod, InpAppliedPrice);
   h_m2  = iMA(_Symbol, PERIOD_M2,  InpEmaPeriod, 0, InpMaMethod, InpAppliedPrice);
   h_m5  = iMA(_Symbol, PERIOD_M5,  InpEmaPeriod, 0, InpMaMethod, InpAppliedPrice);
   h_m10 = iMA(_Symbol, PERIOD_M10, InpEmaPeriod, 0, InpMaMethod, InpAppliedPrice);
   h_m15 = iMA(_Symbol, PERIOD_M15, InpEmaPeriod, 0, InpMaMethod, InpAppliedPrice);
   h_m30 = iMA(_Symbol, PERIOD_M30, InpEmaPeriod, 0, InpMaMethod, InpAppliedPrice);
   h_h1  = iMA(_Symbol, PERIOD_H1,  InpEmaPeriod, 0, InpMaMethod, InpAppliedPrice);
   h_h4  = iMA(_Symbol, PERIOD_H4,  InpEmaPeriod, 0, InpMaMethod, InpAppliedPrice);
   h_d1  = iMA(_Symbol, PERIOD_D1,  InpEmaPeriod, 0, InpMaMethod, InpAppliedPrice);

   if(h_m1 == INVALID_HANDLE || h_m5 == INVALID_HANDLE || h_m10 == INVALID_HANDLE ||
      h_m15 == INVALID_HANDLE || h_m30 == INVALID_HANDLE || h_h1 == INVALID_HANDLE ||
      h_h4 == INVALID_HANDLE || h_d1 == INVALID_HANDLE)
   {
      Print("[J.A.R.V.I.S. Error] Failed to create one or more native iMA indicator handles!");
      return(INIT_FAILED);
   }

   // Start timer for periodic export
   EventSetMillisecondTimer(InpTimerIntervalMs);

   // Initial export pass
   UpdateAndExportIndicators();

   Print("[J.A.R.V.I.S. Bridge] All 9 Multi-Timeframe EMA handles initialized successfully.");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();

   // Release indicator handles
   if(h_m1  != INVALID_HANDLE) IndicatorRelease(h_m1);
   if(h_m2  != INVALID_HANDLE) IndicatorRelease(h_m2);
   if(h_m5  != INVALID_HANDLE) IndicatorRelease(h_m5);
   if(h_m10 != INVALID_HANDLE) IndicatorRelease(h_m10);
   if(h_m15 != INVALID_HANDLE) IndicatorRelease(h_m15);
   if(h_m30 != INVALID_HANDLE) IndicatorRelease(h_m30);
   if(h_h1  != INVALID_HANDLE) IndicatorRelease(h_h1);
   if(h_h4  != INVALID_HANDLE) IndicatorRelease(h_h4);
   if(h_d1  != INVALID_HANDLE) IndicatorRelease(h_d1);

   Print("[J.A.R.V.I.S. Bridge] Deinitialized and released all indicator handles.");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   UpdateAndExportIndicators();
}

//+------------------------------------------------------------------+
//| Expert timer function                                            |
//+------------------------------------------------------------------+
void OnTimer()
{
   UpdateAndExportIndicators();
}

//+------------------------------------------------------------------+
//| Helper to read single indicator buffer value                    |
//+------------------------------------------------------------------+
double GetEmaVal(int handle, int shift=0)
{
   if(handle == INVALID_HANDLE) return(0.0);
   double buf[1];
   if(CopyBuffer(handle, 0, shift, 1, buf) > 0)
   {
      return(buf[0]);
   }
   return(0.0);
}

//+------------------------------------------------------------------+
//| Reads native MT5 buffers and exports JSON to Common Files       |
//+------------------------------------------------------------------+
void UpdateAndExportIndicators()
{
   MqlTick last_tick;
   if(!SymbolInfoTick(_Symbol, last_tick)) return;

   // Read exact buffer values (shift 0 = current live bar, shift 1 = closed bar)
   double ema_m1  = GetEmaVal(h_m1, 0);
   double ema_m2  = GetEmaVal(h_m2, 0);
   double ema_m5  = GetEmaVal(h_m5, 0);
   double ema_m10 = GetEmaVal(h_m10, 0);
   double ema_m15 = GetEmaVal(h_m15, 0);
   double ema_m30 = GetEmaVal(h_m30, 0);
   double ema_h1  = GetEmaVal(h_h1, 0);
   double ema_h4  = GetEmaVal(h_h4, 0);
   double ema_d1  = GetEmaVal(h_d1, 0);

   // Avoid writing identical data if price and time haven't changed
   if(last_tick.time == g_last_export_time && last_tick.bid == g_last_export_price)
   {
      return;
   }

   g_last_export_time  = last_tick.time;
   g_last_export_price = last_tick.bid;

   // Build JSON payload
   string json = "{\n";
   json += "  \"symbol\": \"" + _Symbol + "\",\n";
   json += "  \"time\": " + IntegerToString((long)last_tick.time) + ",\n";
   json += "  \"time_str\": \"" + TimeToString(last_tick.time, TIME_DATE|TIME_SECONDS) + "\",\n";
   json += "  \"bid\": " + DoubleToString(last_tick.bid, _Digits) + ",\n";
   json += "  \"ask\": " + DoubleToString(last_tick.ask, _Digits) + ",\n";
   json += "  \"period\": " + IntegerToString(InpEmaPeriod) + ",\n";
   json += "  \"source\": \"MT5_NATIVE_INDICATOR_ENGINE\",\n";
   json += "  \"emas\": {\n";
   json += "    \"M1\": "  + DoubleToString(ema_m1, _Digits) + ",\n";
   json += "    \"M2\": "  + DoubleToString(ema_m2, _Digits) + ",\n";
   json += "    \"M5\": "  + DoubleToString(ema_m5, _Digits) + ",\n";
   json += "    \"M10\": " + DoubleToString(ema_m10, _Digits) + ",\n";
   json += "    \"M15\": " + DoubleToString(ema_m15, _Digits) + ",\n";
   json += "    \"M30\": " + DoubleToString(ema_m30, _Digits) + ",\n";
   json += "    \"H1\": "  + DoubleToString(ema_h1, _Digits) + ",\n";
   json += "    \"H4\": "  + DoubleToString(ema_h4, _Digits) + ",\n";
   json += "    \"D1\": "  + DoubleToString(ema_d1, _Digits) + "\n";
   json += "  }\n";
   json += "}\n";

   // Write to Common Files directory for ultra-fast shared access
   string filename = "jarvis_indicators_" + _Symbol + ".json";
   int file_handle = FileOpen(filename, FILE_WRITE|FILE_TXT|FILE_COMMON|FILE_ANSI);
   if(file_handle != INVALID_HANDLE)
   {
      FileWriteString(file_handle, json);
      FileClose(file_handle);
   }

   // Also write default jarvis_indicators.json
   int def_handle = FileOpen("jarvis_indicators.json", FILE_WRITE|FILE_TXT|FILE_COMMON|FILE_ANSI);
   if(def_handle != INVALID_HANDLE)
   {
      FileWriteString(def_handle, json);
      FileClose(def_handle);
   }

   if(InpVerboseLogs)
   {
      Print("[J.A.R.V.I.S. Bridge] Exported 9-EMA telemetry: M5=", DoubleToString(ema_m5, 2), " M10=", DoubleToString(ema_m10, 2), " H1=", DoubleToString(ema_h1, 2));
   }
}
