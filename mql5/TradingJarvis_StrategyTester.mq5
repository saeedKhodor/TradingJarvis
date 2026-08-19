//+------------------------------------------------------------------+
//|                                TradingJarvis_StrategyTester.mq5   |
//|                       Copyright 2026, J.A.R.V.I.S. Quantitative   |
//|                                https://github.com/saeedKhodor     |
//+------------------------------------------------------------------+
// === CODE INDEX ===
// 1. Properties & Trade Library Includes (Line 20)
// 2. Input Parameters (Risk, R:R, Sessions, Safety Lock) (Line 30)
// 3. Global Variables & Indicator Handles (Line 60)
// 4. OnInit() - Handle Initialization & Validation (Line 75)
// 5. OnDeinit() - Handle Release & Cleanup (Line 130)
// 6. OnTick() - Bar-Close Synchronization & Signal Engine (Line 150)
// 7. CheckSafetyLock() - H1 Bearish Cascade Evaluator (Line 205)
// 8. ExecuteBuySetup() - Bullish Pullback Order Placement (Line 230)
// 9. CalculateLotSize() - Account-Risk Based Volume Sizing (Line 265)
// ==================================================================
#property copyright   "J.A.R.V.I.S. Trading"
#property link        "https://github.com/saeedKhodor/TradingJarvis"
#property version     "1.00"
#property description "J.A.R.V.I.S. Multi-Timeframe Trend Alignment & Safety Lock Strategy for MT5 Strategy Tester"

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>
#include <Trade\PositionInfo.mqh>

//--- Input Parameters
input group "=== Risk & Money Management ==="
input double   InpRiskPercent          = 1.0;        // Risk per trade (% of Balance)
input double   InpFixedLot             = 0.0;        // Fixed Lot (0.0 = Use Risk %)
input double   InpTargetRR             = 2.0;        // Target Reward-to-Risk (R:R Ratio)
input double   InpStopLossBufferPts    = 1.5;        // Stop Loss Buffer (Points below wick)
input ulong    InpMagicNumber          = 108801;     // EA Magic Number

input group "=== Trend Alignment & Pullback Filters ==="
input bool     InpUseDailyMacroFilter  = true;       // Require Price > D1 9-EMA
input double   InpPullbackTolerancePts = 2.0;        // Max distance from M15 9-EMA for pullback (Pts)
input double   InpMinWickPercent       = 0.35;       // Min lower wick ratio (0.35 = 35% pinbar)

input group "=== Safety Lock (Bearish Cascade) ==="
input bool     InpUseSafetyLock        = true;       // Enforce Safety Lock (Veto longs during cascade)
input bool     InpTradeCascadeShorts   = false;      // Trade Short on H1 9-EMA retests during cascade

input group "=== Session Filters (UTC) ==="
input bool     InpUseSessionFilter     = true;       // Enable Session Time Filter
input int      InpSessionStartHour     = 7;          // Session Start Hour (UTC)
input int      InpSessionEndHour       = 20;         // Session End Hour (UTC)

//--- Global Objects & Handles
CTrade         m_trade;
CSymbolInfo    m_symbol;
CPositionInfo  m_position;

int            h_m15_ema9   = INVALID_HANDLE;
int            h_h1_ema9    = INVALID_HANDLE;
int            h_h1_ema21   = INVALID_HANDLE;
int            h_h1_ema50   = INVALID_HANDLE;
int            h_d1_ema9    = INVALID_HANDLE;

datetime       m_last_bar_time = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   // Initialize Symbol Info
   if(!m_symbol.Name(_Symbol))
   {
      Print("[!] Error: Failed to initialize CSymbolInfo for ", _Symbol);
      return INIT_FAILED;
   }
   m_symbol.Refresh();

   // Initialize CTrade
   m_trade.SetExpertMagicNumber(InpMagicNumber);
   m_trade.SetDeviationInPoints(20);
   m_trade.SetTypeFilling(ORDER_FILLING_FOK);

   // 1. Create M15 9-EMA Handle
   h_m15_ema9 = iMA(_Symbol, PERIOD_M15, 9, 0, MODE_EMA, PRICE_CLOSE);
   if(h_m15_ema9 == INVALID_HANDLE)
   {
      Print("[!] Error creating M15 9-EMA handle.");
      return INIT_FAILED;
   }

   // 2. Create H1 9-EMA Handle
   h_h1_ema9 = iMA(_Symbol, PERIOD_H1, 9, 0, MODE_EMA, PRICE_CLOSE);
   if(h_h1_ema9 == INVALID_HANDLE)
   {
      Print("[!] Error creating H1 9-EMA handle.");
      return INIT_FAILED;
   }

   // 3. Create H1 21-EMA Handle
   h_h1_ema21 = iMA(_Symbol, PERIOD_H1, 21, 0, MODE_EMA, PRICE_CLOSE);
   if(h_h1_ema21 == INVALID_HANDLE)
   {
      Print("[!] Error creating H1 21-EMA handle.");
      return INIT_FAILED;
   }

   // 4. Create H1 50-EMA Handle
   h_h1_ema50 = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   if(h_h1_ema50 == INVALID_HANDLE)
   {
      Print("[!] Error creating H1 50-EMA handle.");
      return INIT_FAILED;
   }

   // 5. Create D1 9-EMA Handle
   h_d1_ema9 = iMA(_Symbol, PERIOD_D1, 9, 0, MODE_EMA, PRICE_CLOSE);
   if(h_d1_ema9 == INVALID_HANDLE)
   {
      Print("[!] Error creating D1 9-EMA handle.");
      return INIT_FAILED;
   }

   Print("[+] J.A.R.V.I.S. Strategy Tester EA Initialized Successfully on ", _Symbol);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   IndicatorRelease(h_m15_ema9);
   IndicatorRelease(h_h1_ema9);
   IndicatorRelease(h_h1_ema21);
   IndicatorRelease(h_h1_ema50);
   IndicatorRelease(h_d1_ema9);
   Print("[*] J.A.R.V.I.S. Strategy Tester EA Released.");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // Check for newly completed M15 Bar
   datetime current_bar_time = iTime(_Symbol, PERIOD_M15, 0);
   if(current_bar_time == m_last_bar_time)
      return; // Only process on new bar open

   m_last_bar_time = current_bar_time;
   m_symbol.RefreshRates();

   // Time session filter check
   if(InpUseSessionFilter)
   {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      if(dt.hour < InpSessionStartHour || dt.hour > InpSessionEndHour)
         return;
   }

   // Read Previous Completed M15 Candle (Shift 1)
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, PERIOD_M15, 1, 2, rates) < 2)
      return;

   double bar_open  = rates[0].open;
   double bar_high  = rates[0].high;
   double bar_low   = rates[0].low;
   double bar_close = rates[0].close;

   // Read Indicator Values (Shift 1 completed bar)
   double buf_m15_9[1], buf_h1_9[1], buf_h1_21[1], buf_h1_50[1], buf_d1_9[1];
   if(CopyBuffer(h_m15_ema9, 0, 1, 1, buf_m15_9) <= 0) return;
   if(CopyBuffer(h_h1_ema9, 0, 1, 1, buf_h1_9) <= 0) return;
   if(CopyBuffer(h_h1_ema21, 0, 1, 1, buf_h1_21) <= 0) return;
   if(CopyBuffer(h_h1_ema50, 0, 1, 1, buf_h1_50) <= 0) return;
   if(CopyBuffer(h_d1_ema9, 0, 1, 1, buf_d1_9) <= 0) return;

   double m15_ema9 = buf_m15_9[0];
   double h1_ema9  = buf_h1_9[0];
   double h1_ema21 = buf_h1_21[0];
   double h1_ema50 = buf_h1_50[0];
   double d1_ema9  = buf_d1_9[0];

   // 1. Evaluate Safety Lock (H1 Bearish Cascade)
   bool is_safety_lock = (bar_close < h1_ema9 && h1_ema9 < h1_ema21 && h1_ema21 < h1_ema50);
   if(InpUseSafetyLock && is_safety_lock)
   {
      // Safety Lock is ENGAGED: Longs are prohibited
      return;
   }

   // Check if we already have an open position
   if(HasOpenPosition())
      return;

   // 2. Evaluate Bullish Trend Alignment
   bool is_bull_alignment = (bar_close > m15_ema9 && m15_ema9 > h1_ema9);
   if(InpUseDailyMacroFilter && is_bull_alignment)
   {
      is_bull_alignment = (bar_close > d1_ema9);
   }

   // 3. Evaluate Pullback Rejection Setup
   bool is_pullback = (bar_low <= (m15_ema9 + InpPullbackTolerancePts) && bar_close >= m15_ema9);
   bool is_bull_candle = (bar_close > bar_open);

   double candle_range = bar_high - bar_low;
   double lower_wick   = MathMin(bar_open, bar_close) - bar_low;
   bool is_rejection   = (candle_range > 0.0) ? ((lower_wick / candle_range) >= InpMinWickPercent) : true;

   // Trigger BUY Setup
   if(is_bull_alignment && is_pullback && is_bull_candle && is_rejection)
   {
      double swing_low = MathMin(bar_low, rates[1].low);
      double sl_price  = NormalizeDouble(swing_low - InpStopLossBufferPts, _Digits);
      double risk_pts  = m_symbol.Ask() - sl_price;

      if(risk_pts > 0.5)
      {
         double tp_price = NormalizeDouble(m_symbol.Ask() + (risk_pts * InpTargetRR), _Digits);
         ExecuteBuySetup(sl_price, tp_price, risk_pts);
      }
   }
}

//+------------------------------------------------------------------+
//| Check if open position exists with EA Magic                      |
//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Symbol() == _Symbol && m_position.Magic() == InpMagicNumber)
            return true;
      }
   }
   return false;
}

//+------------------------------------------------------------------+
//| Executes Buy Order with Position Sizing                          |
//+------------------------------------------------------------------+
void ExecuteBuySetup(double sl_price, double tp_price, double risk_pts)
{
   double lot_size = CalculateLotSize(risk_pts);
   if(lot_size <= 0.0) return;

   m_symbol.RefreshRates();
   double ask = m_symbol.Ask();

   if(m_trade.Buy(lot_size, _Symbol, ask, sl_price, tp_price, "J.A.R.V.I.S. Trend Pullback"))
   {
      PrintFormat("[+] J.A.R.V.I.S. Long Executed: Lots=%.2f | Entry=%.2f | SL=%.2f | TP=%.2f (R:R 1:%.1f)",
                  lot_size, ask, sl_price, tp_price, InpTargetRR);
   }
   else
   {
      PrintFormat("[!] Order Execution Failed. Error: %d - %s", m_trade.ResultRetcode(), m_trade.ResultComment());
   }
}

//+------------------------------------------------------------------+
//| Calculates Lot Size based on Account Balance Risk %              |
//+------------------------------------------------------------------+
double CalculateLotSize(double risk_pts)
{
   if(InpFixedLot > 0.0)
      return NormalizeDouble(InpFixedLot, 2);

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double risk_amount = balance * (InpRiskPercent / 100.0);

   double tick_value = m_symbol.TickValue();
   double tick_size  = m_symbol.TickSize();
   if(tick_value <= 0.0 || tick_size <= 0.0)
      return m_symbol.LotsMin();

   double risk_in_ticks = risk_pts / tick_size;
   double lot_size = risk_amount / (risk_in_ticks * tick_value);

   // Clamp to broker boundaries
   lot_size = MathMax(m_symbol.LotsMin(), MathMin(m_symbol.LotsMax(), lot_size));
   lot_size = MathFloor(lot_size / m_symbol.LotsStep()) * m_symbol.LotsStep();

   return NormalizeDouble(lot_size, 2);
}
