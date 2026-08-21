//+------------------------------------------------------------------+
//|                             TradingJarvis_GoldenPocketShort.mq5   |
//|                       Copyright 2026, J.A.R.V.I.S. Quantitative   |
//|                                https://github.com/saeedKhodor     |
//+------------------------------------------------------------------+
// === CODE INDEX ===
// 1. Properties & Includes (Line 20)
// 2. Input Parameters (Risk, R:R, Rejection Wicks, Sessions) (Line 30)
// 3. Global State & Indicator Handles (Line 55)
// 4. OnInit() - Handle Initialization & Validation (Line 80)
// 5. OnDeinit() - Cleanup (Line 115)
// 6. OnTick() - Cascade Evaluation & Pullback Short Trigger (Line 130)
// 7. ManageBreakeven() - Trailing & Breakeven Management (Line 205)
// 8. ExecuteShortSetup() - Position Sizing & Order Placement (Line 235)
// 9. CalculateLotSize() - Account-Risk Sizing (Line 270)
// ==================================================================
#property copyright   "J.A.R.V.I.S. Trading"
#property link        "https://github.com/saeedKhodor/TradingJarvis"
#property version     "1.00"
#property description "J.A.R.V.I.S. Golden Pocket H1 9-EMA Pullback Short Strategy during Bearish Cascades"

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>
#include <Trade\PositionInfo.mqh>

//--- Input Parameters
input group "=== Risk & Money Management ==="
input double   InpFixedLot             = 0.1;        // Fixed Lot Size (0.0 = Risk %)
input double   InpRiskPercent          = 1.0;        // Risk per trade (% of Balance)
input double   InpTargetRR             = 2.5;        // Target Reward-to-Risk (R:R Ratio)
input double   InpMinRiskPoints        = 4.0;        // Minimum Stop Loss Distance (Index Points)
input double   InpMaxRiskPoints        = 30.0;       // Maximum Stop Loss Distance (Index Points)
input double   InpStopBufferPoints     = 1.5;        // Stop Loss Buffer above High (Pts)
input bool     InpUseBreakeven         = true;       // Move Stop to Breakeven at +1.0R
input ulong    InpMagicNumber          = 108804;     // EA Magic Number

input group "=== Pullback & Rejection Filters ==="
input double   InpTolerancePoints      = 2.5;        // Max tolerance points around H1 9-EMA
input double   InpMinUpperWickRatio    = 0.25;       // Min Upper Wick Ratio (0.25 = 25% Pinbar)

input group "=== Session Filters (UTC) ==="
input bool     InpUseSessionFilter     = true;       // Restrict Execution to Liquid Sessions
input int      InpSessionStartHour     = 7;          // London Start (07:00 UTC)
input int      InpSessionEndHour       = 20;         // NY Close (20:00 UTC)

//--- Global State
CTrade         m_trade;
CSymbolInfo    m_symbol;
CPositionInfo  m_position;

int            h_h1_ema9    = INVALID_HANDLE;
int            h_h1_ema21   = INVALID_HANDLE;
int            h_h1_ema50   = INVALID_HANDLE;
int            h_m30_ema9   = INVALID_HANDLE;

datetime       m_last_bar_time = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   if(!m_symbol.Name(_Symbol))
   {
      Print("[!] Error initializing CSymbolInfo for ", _Symbol);
      return INIT_FAILED;
   }
   m_symbol.Refresh();

   m_trade.SetExpertMagicNumber(InpMagicNumber);
   m_trade.SetDeviationInPoints(30);
   m_trade.SetTypeFilling(ORDER_FILLING_FOK);

   // Create Higher-Timeframe Indicator Handles
   h_h1_ema9  = iMA(_Symbol, PERIOD_H1, 9, 0, MODE_EMA, PRICE_CLOSE);
   h_h1_ema21 = iMA(_Symbol, PERIOD_H1, 21, 0, MODE_EMA, PRICE_CLOSE);
   h_h1_ema50 = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   h_m30_ema9 = iMA(_Symbol, PERIOD_M30, 9, 0, MODE_EMA, PRICE_CLOSE);

   if(h_h1_ema9 == INVALID_HANDLE || h_h1_ema21 == INVALID_HANDLE ||
      h_h1_ema50 == INVALID_HANDLE || h_m30_ema9 == INVALID_HANDLE)
   {
      Print("[!] Error creating indicator handles.");
      return INIT_FAILED;
   }

   Print("[+] J.A.R.V.I.S. Golden Pocket Short EA Initialized Successfully on ", _Symbol);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   IndicatorRelease(h_h1_ema9);
   IndicatorRelease(h_h1_ema21);
   IndicatorRelease(h_h1_ema50);
   IndicatorRelease(h_m30_ema9);
   Print("[*] J.A.R.V.I.S. Golden Pocket Short EA Deinitialized.");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   if(InpUseBreakeven)
      ManageBreakeven();

   // Synchronize on M5 or M15 completed candle
   datetime current_bar_time = iTime(_Symbol, _Period, 0);
   if(current_bar_time == m_last_bar_time)
      return;

   m_last_bar_time = current_bar_time;
   m_symbol.RefreshRates();

   // Session filter check
   if(InpUseSessionFilter)
   {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      if(dt.hour < InpSessionStartHour || dt.hour > InpSessionEndHour)
         return;
   }

   // Read Previous Completed Candle (Shift 1)
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 1, 2, rates) < 2)
      return;

   double c_open  = rates[0].open;
   double c_high  = rates[0].high;
   double c_low   = rates[0].low;
   double c_close = rates[0].close;

   // Read Indicators (Shift 1)
   double buf_h1_9[1], buf_h1_21[1], buf_h1_50[1], buf_m30_9[1];
   if(CopyBuffer(h_h1_ema9, 0, 1, 1, buf_h1_9) <= 0) return;
   if(CopyBuffer(h_h1_ema21, 0, 1, 1, buf_h1_21) <= 0) return;
   if(CopyBuffer(h_h1_ema50, 0, 1, 1, buf_h1_50) <= 0) return;
   if(CopyBuffer(h_m30_ema9, 0, 1, 1, buf_m30_9) <= 0) return;

   double h1_9  = buf_h1_9[0];
   double h1_21 = buf_h1_21[0];
   double h1_50 = buf_h1_50[0];
   double m30_9 = buf_m30_9[0];

   // 1. Verify H1 Bearish Cascade Condition: Price < 9-EMA < 21-EMA < 50-EMA
   bool is_cascade = (c_close < h1_9 && h1_9 < h1_21 && h1_21 < h1_50);
   if(!is_cascade)
      return;

   if(HasOpenPosition())
      return;

   // 2. Evaluate Pullback interaction with H1 9-EMA or 30M 9-EMA
   bool touches_h1_9  = (c_high >= (h1_9 - InpTolerancePoints) && c_high <= (h1_21 + InpTolerancePoints));
   bool touches_m30_9 = (c_high >= (m30_9 - InpTolerancePoints) && c_high <= (h1_9 + InpTolerancePoints));

   if(!touches_h1_9 && !touches_m30_9)
      return;

   // 3. Evaluate Bearish Rejection
   double range = c_high - c_low;
   double upper_wick = c_high - MathMax(c_open, c_close);
   bool is_bearish_candle = (c_close < c_open);
   bool is_rejection = (range > 0.0) ? ((upper_wick / range) >= InpMinUpperWickRatio) : false;

   // Trigger Golden Pocket Short
   if((touches_h1_9 || touches_m30_9) && (is_bearish_candle || is_rejection))
   {
      double sl_price = NormalizeDouble(c_high + InpStopBufferPoints, _Digits);
      double risk_pts = sl_price - c_close;

      if(risk_pts >= InpMinRiskPoints && risk_pts <= InpMaxRiskPoints)
      {
         double tp_price = NormalizeDouble(c_close - (risk_pts * InpTargetRR), _Digits);
         string comment = touches_h1_9 ? "Golden Pocket H1-9 Short" : "Golden Pocket M30-9 Short";
         ExecuteShortSetup(c_close, sl_price, tp_price, risk_pts, comment);
      }
   }
}

//+------------------------------------------------------------------+
//| Manage Breakeven (+1.0R profit triggers BE)                      |
//+------------------------------------------------------------------+
void ManageBreakeven()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Symbol() == _Symbol && m_position.Magic() == InpMagicNumber)
         {
            if(m_position.PositionType() == POSITION_TYPE_SELL)
            {
               double open_p = m_position.PriceOpen();
               double sl_p   = m_position.StopLoss();
               double curr_p = m_position.PriceCurrent();
               double initial_risk = (sl_p > open_p) ? (sl_p - open_p) : 10.0;

               // If in profit by 1.0R, move SL to Open - 0.5 pts
               if((open_p - curr_p) >= initial_risk)
               {
                  double new_sl = NormalizeDouble(open_p - 0.5, _Digits);
                  if(sl_p > new_sl || sl_p == 0.0)
                  {
                     m_trade.PositionModify(m_position.Ticket(), new_sl, m_position.TakeProfit());
                     PrintFormat("[+] Breakeven Applied for SELL Ticket #%d at %.2f", m_position.Ticket(), new_sl);
                  }
               }
            }
         }
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
//| Executes Short Order                                             |
//+------------------------------------------------------------------+
void ExecuteShortSetup(double entry, double sl, double tp, double risk_pts, string comment)
{
   double lot_size = CalculateLotSize(risk_pts);
   if(lot_size <= 0.0) return;

   m_symbol.RefreshRates();
   double bid = m_symbol.Bid();

   if(m_trade.Sell(lot_size, _Symbol, bid, sl, tp, comment))
   {
      PrintFormat("[+] SELL Short Executed: Lots=%.2f | Entry=%.2f | SL=%.2f | TP=%.2f (R:R 1:%.1f)",
                  lot_size, bid, sl, tp, InpTargetRR);
   }
   else
   {
      PrintFormat("[!] Short Execution Failed. Error: %d - %s", m_trade.ResultRetcode(), m_trade.ResultComment());
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
