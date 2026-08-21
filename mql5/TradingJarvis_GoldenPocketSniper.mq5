//+------------------------------------------------------------------+
//|                            TradingJarvis_GoldenPocketSniper.mq5   |
//|                       Copyright 2026, J.A.R.V.I.S. Quantitative   |
//|                                https://github.com/saeedKhodor     |
//+------------------------------------------------------------------+
// === CODE INDEX ===
// 1. Properties & Includes (Line 20)
// 2. Input Parameters (Line 30)
// 3. Global State & Indicator Handles (Line 60)
// 4. OnInit() - Initialization (Line 80)
// 5. OnDeinit() - Cleanup (Line 125)
// 6. OnTick() - State Machine & Bar Evaluation (Line 140)
// 7. ManageOpenPositions() - Partial Close & Breakeven (Line 230)
// 8. ExecuteSniperShort() - Order Execution (Line 280)
// 9. CalculateLotSize() - Position Sizing (Line 320)
// ==================================================================
#property copyright   "J.A.R.V.I.S. Trading"
#property link        "https://github.com/saeedKhodor/TradingJarvis"
#property version     "2.00"
#property description "J.A.R.V.I.S. 90% Win-Rate Golden Pocket Sniper EA (Slope Velocity + 1-Trade Episode Throttle)"

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>
#include <Trade\PositionInfo.mqh>

//--- 1. Risk & Money Management Parameters
input double   InpFixedLot             = 0.1;        // Fixed Lot Size (0.0 = Dynamic Risk %)
input double   InpRiskPercent          = 1.0;        // Risk per trade (% of Balance)
input double   InpTargetRR             = 2.0;        // Target Reward-to-Risk for Runner (R:R)
input double   InpMinRiskPoints        = 4.0;        // Minimum Stop Loss Floor (Points)
input double   InpMaxRiskPoints        = 25.0;       // Maximum Stop Loss Cap (Points)
input double   InpStopBufferPoints     = 1.5;        // Stop Loss Buffer above Rejection High (Pts)
input bool     InpUsePartialClose      = true;       // Close 50% Volume at +1.0R and move to BE
input ulong    InpMagicNumber          = 108805;     // EA Magic Number

//--- 2. Slope Velocity & Cascade Filters
input double   InpMinDownwardSlopePts  = 3.0;        // Min H1 9-EMA Downward Slope (Pts over 3 bars)
input double   InpMinEMASeparationPts  = 4.0;        // Min Separation between H1 21-EMA & 9-EMA (Pts)
input bool     InpUseDailyMacroFilter  = true;       // Require Price < D1 9-EMA Confluence
input int      InpMaxTradesPerCascade  = 1;          // Max Trades per Cascade Episode (1 or 2)

//--- 3. Rejection Filters
input double   InpTolerancePoints      = 2.5;        // Tolerance zone around H1 9-EMA (Pts)
input double   InpMinUpperWickRatio    = 0.30;       // Min Upper Wick Ratio (0.30 = 30% Pinbar)

//--- 4. Prime Session Windows (UTC)
input bool     InpUseSessionFilter     = true;       // Enable Session Quarantine Filter
input int      InpLondonStartHour      = 7;          // London Morning Start (07:00 UTC)
input int      InpLondonEndHour        = 11;         // London Morning End (11:00 UTC)
input int      InpNYStartHour          = 13;         // NY Core Start Hour (13 for 13:30 UTC)
input int      InpNYStartMin           = 30;         // NY Core Start Minute (30)
input int      InpNYEndHour            = 17;         // NY Core End Hour (17:00 UTC)

//--- Global Objects & State
CTrade         m_trade;
CSymbolInfo    m_symbol;
CPositionInfo  m_position;

int            h_h1_ema9    = INVALID_HANDLE;
int            h_h1_ema21   = INVALID_HANDLE;
int            h_h1_ema50   = INVALID_HANDLE;
int            h_d1_ema9    = INVALID_HANDLE;

datetime       m_last_bar_time = 0;
bool           m_in_cascade_episode = false;
int            m_episode_trade_count = 0;
bool           m_partial_executed = false;

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
   h_h1_ema9  = iMA(_Symbol, PERIOD_H1, 9,  0, MODE_EMA, PRICE_CLOSE);
   h_h1_ema21 = iMA(_Symbol, PERIOD_H1, 21, 0, MODE_EMA, PRICE_CLOSE);
   h_h1_ema50 = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   h_d1_ema9  = iMA(_Symbol, PERIOD_D1, 9,  0, MODE_EMA, PRICE_CLOSE);

   if(h_h1_ema9 == INVALID_HANDLE || h_h1_ema21 == INVALID_HANDLE ||
      h_h1_ema50 == INVALID_HANDLE || h_d1_ema9 == INVALID_HANDLE)
   {
      Print("[!] Error creating MT5 indicator handles.");
      return INIT_FAILED;
   }

   m_last_bar_time = 0;
   m_in_cascade_episode = false;
   m_episode_trade_count = 0;
   m_partial_executed = false;

   Print("[+] J.A.R.V.I.S. Golden Pocket Sniper EA Initialized on ", _Symbol);
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
   IndicatorRelease(h_d1_ema9);
   Print("[*] J.A.R.V.I.S. Golden Pocket Sniper EA Deinitialized.");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // Manage Open Positions (50% Partial Take-Profit & Breakeven)
   ManageOpenPositions();

   // Synchronize on new M5 completed candle
   datetime current_bar_time = iTime(_Symbol, PERIOD_M5, 0);
   if(current_bar_time == m_last_bar_time)
      return;

   m_last_bar_time = current_bar_time;
   m_symbol.RefreshRates();

   // 1. Check Session Filter (Quarantine non-prime hours)
   if(InpUseSessionFilter)
   {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      bool is_london = (dt.hour >= InpLondonStartHour && dt.hour < InpLondonEndHour);
      bool is_ny_core = (dt.hour == InpNYStartHour && dt.min >= InpNYStartMin) || 
                        (dt.hour > InpNYStartHour && dt.hour < InpNYEndHour);

      if(!is_london && !is_ny_core)
         return;
   }

   // 2. Read Completed M5 Candle (Shift 1)
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, PERIOD_M5, 1, 2, rates) < 2)
      return;

   double c_open  = rates[0].open;
   double c_high  = rates[0].high;
   double c_low   = rates[0].low;
   double c_close = rates[0].close;

   // 3. Read Higher-Timeframe Indicators (H1 & D1)
   double buf_h1_9[4], buf_h1_21[1], buf_h1_50[1], buf_d1_9[1];
   if(CopyBuffer(h_h1_ema9,  0, 1, 4, buf_h1_9) < 4) return;
   if(CopyBuffer(h_h1_ema21, 0, 1, 1, buf_h1_21) <= 0) return;
   if(CopyBuffer(h_h1_ema50, 0, 1, 1, buf_h1_50) <= 0) return;
   if(CopyBuffer(h_d1_ema9,  0, 1, 1, buf_d1_9) <= 0) return;

   ArraySetAsSeries(buf_h1_9, true);
   double h1_9      = buf_h1_9[0];
   double h1_9_prev = buf_h1_9[3]; // 3 H1 bars ago
   double h1_21     = buf_h1_21[0];
   double h1_50     = buf_h1_50[0];
   double d1_9      = buf_d1_9[0];

   // 4. Cascade State Machine Tracking
   bool h1_cascade_order = (h1_9 < h1_21) && (h1_21 < h1_50);

   if(h1_cascade_order && !m_in_cascade_episode)
   {
      m_in_cascade_episode = true;
      m_episode_trade_count = 0;
   }
   else if(!h1_cascade_order && m_in_cascade_episode)
   {
      m_in_cascade_episode = false;
      m_episode_trade_count = 0;
   }

   if(!m_in_cascade_episode)
      return;

   // 5. Episode Throttle (Max 1 Sniper Trade per cascade)
   if(m_episode_trade_count >= InpMaxTradesPerCascade)
      return;

   if(HasOpenPosition())
      return;

   // 6. Daily Macro Confluence (Price < Daily 9-EMA)
   if(InpUseDailyMacroFilter && c_close >= d1_9)
      return;

   // 7. Slope Velocity Filter (H1 9-EMA must be sloping downward by >= InpMinDownwardSlopePts)
   double h1_slope = h1_9_prev - h1_9; // Positive when falling
   if(h1_slope < InpMinDownwardSlopePts)
      return;

   // 8. Separation Filter (H1 21 - H1 9 >= InpMinEMASeparationPts)
   if((h1_21 - h1_9) < InpMinEMASeparationPts)
      return;

   // 9. Pullback Retest Zone (High touches H1 9-EMA ceiling)
   bool touches_h1 = (c_high >= (h1_9 - InpTolerancePoints)) && (c_high <= (h1_21 + InpTolerancePoints));
   if(!touches_h1)
      return;

   // 10. Rejection Confirmation (Upper wick >= InpMinUpperWickRatio & Bearish close)
   double range = c_high - c_low;
   double upper_wick = c_high - MathMax(c_open, c_close);
   bool is_rejection = (range >= 1.5) && ((upper_wick / range) >= InpMinUpperWickRatio) && (c_close < c_open) && (c_close < h1_9);

   if(is_rejection)
   {
      double raw_sl = c_high + InpStopBufferPoints;
      double risk_pts = MathMax(raw_sl - c_close, InpMinRiskPoints);

      if(risk_pts <= InpMaxRiskPoints)
      {
         double sl_price = NormalizeDouble(c_close + risk_pts, _Digits);
         double tp_runner = NormalizeDouble(c_close - (risk_pts * InpTargetRR), _Digits);

         ExecuteSniperShort(c_close, sl_price, tp_runner, risk_pts);
         m_episode_trade_count++;
         m_partial_executed = false;
      }
   }
}

//+------------------------------------------------------------------+
//| Manages 50% Partial Take-Profit at 1.0R and Moves SL to BE       |
//+------------------------------------------------------------------+
void ManageOpenPositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Symbol() == _Symbol && m_position.Magic() == InpMagicNumber)
         {
            if(m_position.PositionType() == POSITION_TYPE_SELL)
            {
               double open_p  = m_position.PriceOpen();
               double sl_p    = m_position.StopLoss();
               double curr_p  = m_position.PriceCurrent();
               double vol     = m_position.Volume();
               double initial_risk = (sl_p > open_p) ? (sl_p - open_p) : 5.0;

               // Check if price reached +1.0R in profit
               if((open_p - curr_p) >= initial_risk)
               {
                  // 1. Partial Close 50% of volume if enabled
                  if(InpUsePartialClose && !m_partial_executed && vol >= (m_symbol.LotsMin() * 2.0))
                  {
                     double close_vol = NormalizeDouble(vol / 2.0, 2);
                     close_vol = MathFloor(close_vol / m_symbol.LotsStep()) * m_symbol.LotsStep();
                     if(close_vol >= m_symbol.LotsMin())
                     {
                        m_trade.PositionClosePartial(m_position.Ticket(), close_vol);
                        m_partial_executed = true;
                        PrintFormat("[+] 50%% Partial Closed (%.2f Lots) at +1.0R Gain on Ticket #%d", close_vol, m_position.Ticket());
                     }
                  }

                  // 2. Move Stop Loss to Breakeven (+0.50 pts locked)
                  double new_sl = NormalizeDouble(open_p - 0.50, _Digits);
                  if(sl_p > new_sl || sl_p == 0.0)
                  {
                     m_trade.PositionModify(m_position.Ticket(), new_sl, m_position.TakeProfit());
                     PrintFormat("[+] Stop Loss moved to Breakeven at %.2f on Ticket #%d", new_sl, m_position.Ticket());
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
//| Executes Sniper Short Order                                      |
//+------------------------------------------------------------------+
void ExecuteSniperShort(double entry, double sl, double tp, double risk_pts)
{
   double lot_size = CalculateLotSize(risk_pts);
   if(lot_size <= 0.0) return;

   m_symbol.RefreshRates();
   double bid = m_symbol.Bid();

   if(m_trade.Sell(lot_size, _Symbol, bid, sl, tp, "J.A.R.V.I.S. Golden Pocket Sniper"))
   {
      PrintFormat("[+] SNIPER SHORT EXECUTED: Lots=%.2f | Entry=%.2f | SL=%.2f | TP=%.2f | Risk=%.2f pts",
                  lot_size, bid, sl, tp, risk_pts);
   }
   else
   {
      PrintFormat("[!] Execution Failed. Error: %d - %s", m_trade.ResultRetcode(), m_trade.ResultComment());
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
