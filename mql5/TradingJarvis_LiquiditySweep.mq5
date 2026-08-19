//+------------------------------------------------------------------+
//|                                TradingJarvis_LiquiditySweep.mq5   |
//|                       Copyright 2026, J.A.R.V.I.S. Quantitative   |
//|                                https://github.com/saeedKhodor     |
//+------------------------------------------------------------------+
// === CODE INDEX ===
// 1. Properties & Trade Library Includes (Line 20)
// 2. Input Parameters (Risk, R:R, Sweep Buffers, Sessions) (Line 30)
// 3. Global State Variables & Daily Levels (Line 55)
// 4. OnInit() - Initialization & Historical Level Setup (Line 75)
// 5. OnDeinit() - Cleanup (Line 105)
// 6. OnTick() - Bar Ingestion & State Machine (Line 120)
// 7. UpdateDailyLevels() - Extracts PDH, PDL, and Day Midpoint (Line 160)
// 8. CheckLiquiditySweeps() - Detects Failed Breakouts & Reversals (Line 190)
// 9. ExecuteSweepTrade() - Position Sizing & Order Placement (Line 250)
// 10. CalculateLotSize() - Account-Risk Sizing (Line 290)
// ==================================================================
#property copyright   "J.A.R.V.I.S. Trading"
#property link        "https://github.com/saeedKhodor/TradingJarvis"
#property version     "1.00"
#property description "J.A.R.V.I.S. Daily Liquidity Sweep (PDH/PDL Trap & Reversal) Expert Advisor for MT5 Strategy Tester"

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>
#include <Trade\PositionInfo.mqh>

//--- Input Parameters
input group "=== Risk & Money Management ==="
input double   InpFixedLot             = 0.1;        // Fixed Lot Size (0.0 = Dynamic Risk %)
input double   InpRiskPercent          = 1.0;        // Risk per trade (% of Balance)
input double   InpTargetRR             = 2.5;        // Target Reward-to-Risk (R:R Ratio)
input double   InpMinRiskPoints        = 6.0;        // Minimum Stop Loss Distance (Index Points)
input double   InpMaxRiskPoints        = 35.0;       // Maximum Stop Loss Distance (Index Points)
input double   InpStopBufferPoints     = 2.0;        // Stop Loss Buffer past Sweep Extreme (Pts)
input ulong    InpMagicNumber          = 108802;     // EA Magic Number

input group "=== Liquidity Sweep Parameters ==="
input double   InpMinSweepPenetration  = 1.5;        // Min points pierced beyond PDH/PDL to count as sweep
input int      InpMaxSweepBars         = 6;          // Max M5 bars allowed outside range before invalidation
input bool     InpUseMidpointTarget    = false;      // Target Day Midpoint (Equilibrium) if closer than R:R

input group "=== Session Filters (UTC) ==="
input bool     InpUseSessionFilter     = true;       // Restrict Execution to Liquid Sessions
input int      InpSessionStartHour     = 7;          // London Session Start (07:00 UTC)
input int      InpSessionEndHour       = 20;         // NY Session End (20:00 UTC)

//--- Global Objects & State
CTrade         m_trade;
CSymbolInfo    m_symbol;
CPositionInfo  m_position;

datetime       m_last_bar_time = 0;
datetime       m_current_day_time = 0;

double         m_pdh = 0.0; // Previous Day High
double         m_pdl = 0.0; // Previous Day Low
double         m_day_midpoint = 0.0;

bool           m_pdh_swept_today = false;
bool           m_pdl_swept_today = false;
double         m_sweep_high = 0.0;
double         m_sweep_low = 0.0;
int            m_bars_outside_pdh = 0;
int            m_bars_outside_pdl = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   if(!m_symbol.Name(_Symbol))
   {
      Print("[!] Error: Failed to initialize CSymbolInfo for ", _Symbol);
      return INIT_FAILED;
   }
   m_symbol.Refresh();

   m_trade.SetExpertMagicNumber(InpMagicNumber);
   m_trade.SetDeviationInPoints(30);
   m_trade.SetTypeFilling(ORDER_FILLING_FOK);

   m_last_bar_time = 0;
   m_current_day_time = 0;

   Print("[+] J.A.R.V.I.S. Liquidity Sweep EA Initialized Successfully on ", _Symbol);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("[*] J.A.R.V.I.S. Liquidity Sweep EA Deinitialized.");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // Synchronize to completed bar (M5 / M15)
   datetime current_bar_time = iTime(_Symbol, _Period, 0);
   if(current_bar_time == m_last_bar_time)
      return;

   m_last_bar_time = current_bar_time;
   m_symbol.RefreshRates();

   // 1. Update Daily Levels on Day Change
   UpdateDailyLevels();

   if(m_pdh <= 0.0 || m_pdl <= 0.0)
      return;

   // 2. Check Session Filter
   if(InpUseSessionFilter)
   {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      if(dt.hour < InpSessionStartHour || dt.hour > InpSessionEndHour)
         return;
   }

   // 3. Process Liquidity Sweeps
   CheckLiquiditySweeps();
}

//+------------------------------------------------------------------+
//| Extracts Previous Day High, Low, and Equilibrium                 |
//+------------------------------------------------------------------+
void UpdateDailyLevels()
{
   datetime today_time = iTime(_Symbol, PERIOD_D1, 0);
   if(today_time != m_current_day_time)
   {
      m_current_day_time = today_time;

      MqlRates daily_rates[];
      ArraySetAsSeries(daily_rates, true);
      if(CopyRates(_Symbol, PERIOD_D1, 1, 1, daily_rates) >= 1)
      {
         m_pdh = daily_rates[0].high;
         m_pdl = daily_rates[0].low;
         m_day_midpoint = (m_pdh + m_pdl) / 2.0;

         // Reset daily sweep triggers
         m_pdh_swept_today = false;
         m_pdl_swept_today = false;
         m_sweep_high = m_pdh;
         m_sweep_low = m_pdl;
         m_bars_outside_pdh = 0;
         m_bars_outside_pdl = 0;

         PrintFormat("[*] New Day Initialized | PDH: %.2f | PDL: %.2f | Midpoint: %.2f", m_pdh, m_pdl, m_day_midpoint);
      }
   }
}

//+------------------------------------------------------------------+
//| Evaluates PDH/PDL Sweep Reversal Conditions                      |
//+------------------------------------------------------------------+
void CheckLiquiditySweeps()
{
   if(HasOpenPosition())
      return;

   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 1, 2, rates) < 2)
      return;

   double c_open  = rates[0].open;
   double c_high  = rates[0].high;
   double c_low   = rates[0].low;
   double c_close = rates[0].close;

   // ================================================================
   // SETUP A: BEARISH LIQUIDITY SWEEP (PDH Trap & Reversal)
   // ================================================================
   if(!m_pdh_swept_today)
   {
      // Check if price is or was above PDH
      if(c_high >= (m_pdh + InpMinSweepPenetration))
      {
         m_sweep_high = MathMax(m_sweep_high, c_high);
         m_bars_outside_pdh++;

         // Check for Bearish Reversal back inside the range
         if(c_close < m_pdh && c_close < c_open && m_bars_outside_pdh <= InpMaxSweepBars)
         {
            double sl_price = NormalizeDouble(m_sweep_high + InpStopBufferPoints, _Digits);
            double risk_pts = sl_price - c_close;

            if(risk_pts >= InpMinRiskPoints && risk_pts <= InpMaxRiskPoints)
            {
               double tp_price = NormalizeDouble(c_close - (risk_pts * InpTargetRR), _Digits);
               if(InpUseMidpointTarget && m_day_midpoint < c_close && m_day_midpoint > tp_price)
                  tp_price = NormalizeDouble(m_day_midpoint, _Digits);

               ExecuteSweepTrade(ORDER_TYPE_SELL, c_close, sl_price, tp_price, risk_pts, "PDH Sweep Reversal");
               m_pdh_swept_today = true;
            }
         }
      }
   }

   // ================================================================
   // SETUP B: BULLISH LIQUIDITY SWEEP (PDL Trap & Reversal)
   // ================================================================
   if(!m_pdl_swept_today)
   {
      // Check if price is or was below PDL
      if(c_low <= (m_pdl - InpMinSweepPenetration))
      {
         m_sweep_low = MathMin(m_sweep_low, c_low);
         m_bars_outside_pdl++;

         // Check for Bullish Reversal back inside the range
         if(c_close > m_pdl && c_close > c_open && m_bars_outside_pdl <= InpMaxSweepBars)
         {
            double sl_price = NormalizeDouble(m_sweep_low - InpStopBufferPoints, _Digits);
            double risk_pts = c_close - sl_price;

            if(risk_pts >= InpMinRiskPoints && risk_pts <= InpMaxRiskPoints)
            {
               double tp_price = NormalizeDouble(c_close + (risk_pts * InpTargetRR), _Digits);
               if(InpUseMidpointTarget && m_day_midpoint > c_close && m_day_midpoint < tp_price)
                  tp_price = NormalizeDouble(m_day_midpoint, _Digits);

               ExecuteSweepTrade(ORDER_TYPE_BUY, c_close, sl_price, tp_price, risk_pts, "PDL Sweep Reversal");
               m_pdl_swept_today = true;
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Check if open position exists                                    |
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
//| Executes Buy/Sell Order with Risk Sizing                         |
//+------------------------------------------------------------------+
void ExecuteSweepTrade(ENUM_ORDER_TYPE order_type, double entry, double sl, double tp, double risk_pts, string comment)
{
   double lot_size = CalculateLotSize(risk_pts);
   if(lot_size <= 0.0) return;

   m_symbol.RefreshRates();

   if(order_type == ORDER_TYPE_BUY)
   {
      double ask = m_symbol.Ask();
      if(m_trade.Buy(lot_size, _Symbol, ask, sl, tp, comment))
      {
         PrintFormat("[+] BUY Sweep Executed: Lots=%.2f | Entry=%.2f | SL=%.2f | TP=%.2f | Risk=%.2f pts",
                     lot_size, ask, sl, tp, risk_pts);
      }
   }
   else if(order_type == ORDER_TYPE_SELL)
   {
      double bid = m_symbol.Bid();
      if(m_trade.Sell(lot_size, _Symbol, bid, sl, tp, comment))
      {
         PrintFormat("[+] SELL Sweep Executed: Lots=%.2f | Entry=%.2f | SL=%.2f | TP=%.2f | Risk=%.2f pts",
                     lot_size, bid, sl, tp, risk_pts);
      }
   }
}

//+------------------------------------------------------------------+
//| Safe Position Sizing based on Account Risk                       |
//+------------------------------------------------------------------+
double CalculateLotSize(double risk_pts)
{
   if(InpFixedLot > 0.0)
      return NormalizeDouble(InpFixedLot, 2);

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double risk_amount = balance * (InpRiskPercent / 100.0);

   double tick_value = m_symbol.TickValue();
   double tick_size  = m_symbol.TickSize();
   if(tick_value <= 0.0 || tick_size <= 0.0 || risk_pts <= 0.0)
      return m_symbol.LotsMin();

   double risk_in_ticks = risk_pts / tick_size;
   double lot_size = risk_amount / (risk_in_ticks * tick_value);

   lot_size = MathMax(m_symbol.LotsMin(), MathMin(m_symbol.LotsMax(), lot_size));
   lot_size = MathFloor(lot_size / m_symbol.LotsStep()) * m_symbol.LotsStep();

   return NormalizeDouble(lot_size, 2);
}
