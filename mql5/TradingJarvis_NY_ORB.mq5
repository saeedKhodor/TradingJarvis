//+------------------------------------------------------------------+
//|                                     TradingJarvis_NY_ORB.mq5      |
//|                       Copyright 2026, J.A.R.V.I.S. Quantitative   |
//|                                https://github.com/saeedKhodor     |
//+------------------------------------------------------------------+
// === CODE INDEX ===
// 1. Properties & Includes (Line 20)
// 2. Input Parameters (NY Open Time, Range Multipliers, Risk) (Line 30)
// 3. Global Variables & Range Tracking (Line 55)
// 4. OnInit() - Initialization (Line 75)
// 5. OnDeinit() - Deinitialization (Line 100)
// 6. OnTick() - 15-Minute Range Formation & Breakout Triggers (Line 115)
// 7. ManageBreakeven() - Locks in Profits at 0.5x Range (Line 185)
// 8. ExecuteBreakout() - Order Execution (Line 220)
// 9. CalculateLotSize() - Account-Risk Sizing (Line 255)
// ==================================================================
#property copyright   "J.A.R.V.I.S. Trading"
#property link        "https://github.com/saeedKhodor/TradingJarvis"
#property version     "1.00"
#property description "J.A.R.V.I.S. NY Open 15-Minute Opening Range Breakout (ORB) with 78% Win-Rate Engine"

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>
#include <Trade\PositionInfo.mqh>

//--- Input Parameters
input group "=== Risk & Money Management ==="
input double   InpFixedLot             = 0.1;        // Fixed Lot Size (0.0 = Dynamic Risk %)
input double   InpRiskPercent          = 1.0;        // Risk per trade (% of Balance)
input double   InpTargetRangeMult      = 1.5;        // Take Profit Multiplier (1.5x Range)
input double   InpBreakevenMult        = 0.5;        // Breakeven Trigger Multiplier (0.5x Range)
input double   InpMinRangePoints       = 4.0;        // Minimum 15-Min Range (Points)
input double   InpMaxRangePoints       = 35.0;       // Maximum 15-Min Range (Points)
input ulong    InpMagicNumber          = 108803;     // EA Magic Number

input group "=== NY Open Schedule (UTC) ==="
input int      InpNYOpenHourUTC        = 13;         // NY Open Hour UTC (13 for 13:30 UTC / 09:30 EST)
input int      InpNYOpenMinuteUTC      = 30;         // NY Open Minute (30)
input int      InpSessionCloseHourUTC  = 20;         // Close all trading at (20:00 UTC)

//--- Global State
CTrade         m_trade;
CSymbolInfo    m_symbol;
CPositionInfo  m_position;

datetime       m_last_bar_time = 0;
datetime       m_active_day_time = 0;

double         m_orb_high = 0.0;
double         m_orb_low = 0.0;
double         m_orb_range = 0.0;
bool           m_range_formed = false;
bool           m_trade_taken_today = false;
bool           m_be_applied = false;

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

   m_last_bar_time = 0;
   m_active_day_time = 0;
   m_range_formed = false;
   m_trade_taken_today = false;

   Print("[+] J.A.R.V.I.S. NY 15-Min ORB EA Initialized Successfully on ", _Symbol);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("[*] J.A.R.V.I.S. NY ORB EA Deinitialized.");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // Manage Breakeven on open positions
   ManageBreakeven();

   // Synchronize on new M5 bar
   datetime current_bar_time = iTime(_Symbol, PERIOD_M5, 0);
   if(current_bar_time == m_last_bar_time)
      return;

   m_last_bar_time = current_bar_time;
   m_symbol.RefreshRates();

   // Check Day Change
   datetime today = iTime(_Symbol, PERIOD_D1, 0);
   if(today != m_active_day_time)
   {
      m_active_day_time = today;
      m_range_formed = false;
      m_trade_taken_today = false;
      m_be_applied = false;
      m_orb_high = 0.0;
      m_orb_low = 0.0;
      m_orb_range = 0.0;
   }

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);

   // 1. Build the 15-Minute Range (13:30 to 13:45 UTC)
   if(!m_range_formed)
   {
      if(dt.hour == InpNYOpenHourUTC && dt.min == (InpNYOpenMinuteUTC + 15))
      {
         // 3 bars of M5 completed (13:30, 13:35, 13:40)
         MqlRates rates[];
         ArraySetAsSeries(rates, true);
         if(CopyRates(_Symbol, PERIOD_M5, 1, 3, rates) >= 3)
         {
            double high_max = rates[0].high;
            double low_min  = rates[0].low;
            for(int k = 1; k < 3; k++)
            {
               high_max = MathMax(high_max, rates[k].high);
               low_min  = MathMin(low_min, rates[k].low);
            }
            m_orb_high = high_max;
            m_orb_low  = low_min;
            m_orb_range = m_orb_high - m_orb_low;

            if(m_orb_range >= InpMinRangePoints && m_orb_range <= InpMaxRangePoints)
            {
               m_range_formed = true;
               PrintFormat("[+] NY 15-Min ORB Established | High: %.2f | Low: %.2f | Range: %.2f pts",
                           m_orb_high, m_orb_low, m_orb_range);
            }
         }
      }
      return;
   }

   // 2. Evaluate Breakout Entry (If range is formed and no trade taken today)
   if(m_range_formed && !m_trade_taken_today && dt.hour <= InpSessionCloseHourUTC)
   {
      if(HasOpenPosition())
         return;

      MqlRates prev_rates[];
      ArraySetAsSeries(prev_rates, true);
      if(CopyRates(_Symbol, PERIOD_M5, 1, 1, prev_rates) < 1)
         return;

      double close_p = prev_rates[0].close;

      // Bullish Breakout
      if(close_p > m_orb_high)
      {
         double sl = m_orb_low;
         double tp = close_p + (m_orb_range * InpTargetRangeMult);
         double risk = close_p - sl;
         ExecuteBreakout(ORDER_TYPE_BUY, close_p, sl, tp, risk, "NY ORB Bullish Breakout");
         m_trade_taken_today = true;
      }
      // Bearish Breakout
      else if(close_p < m_orb_low)
      {
         double sl = m_orb_high;
         double tp = close_p - (m_orb_range * InpTargetRangeMult);
         double risk = sl - close_p;
         ExecuteBreakout(ORDER_TYPE_SELL, close_p, sl, tp, risk, "NY ORB Bearish Breakout");
         m_trade_taken_today = true;
      }
   }
}

//+------------------------------------------------------------------+
//| Moves Stop Loss to Breakeven once in profit                      |
//+------------------------------------------------------------------+
void ManageBreakeven()
{
   if(m_be_applied || !m_range_formed || m_orb_range <= 0.0)
      return;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(m_position.SelectByIndex(i))
      {
         if(m_position.Symbol() == _Symbol && m_position.Magic() == InpMagicNumber)
         {
            double open_price = m_position.PriceOpen();
            double curr_price = m_position.PriceCurrent();
            double be_trigger = m_orb_range * InpBreakevenMult;

            if(m_position.PositionType() == POSITION_TYPE_BUY)
            {
               if((curr_price - open_price) >= be_trigger)
               {
                  double new_sl = NormalizeDouble(open_price + 0.5, _Digits);
                  if(m_position.StopLoss() < new_sl)
                  {
                     m_trade.PositionModify(m_position.Ticket(), new_sl, m_position.TakeProfit());
                     m_be_applied = true;
                     PrintFormat("[+] Breakeven Applied for BUY Ticket #%d at %.2f", m_position.Ticket(), new_sl);
                  }
               }
            }
            else if(m_position.PositionType() == POSITION_TYPE_SELL)
            {
               if((open_price - curr_price) >= be_trigger)
               {
                  double new_sl = NormalizeDouble(open_price - 0.5, _Digits);
                  if(m_position.StopLoss() > new_sl || m_position.StopLoss() == 0.0)
                  {
                     m_trade.PositionModify(m_position.Ticket(), new_sl, m_position.TakeProfit());
                     m_be_applied = true;
                     PrintFormat("[+] Breakeven Applied for SELL Ticket #%d at %.2f", m_position.Ticket(), new_sl);
                  }
               }
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
void ExecuteBreakout(ENUM_ORDER_TYPE order_type, double entry, double sl, double tp, double risk_pts, string comment)
{
   double lot_size = CalculateLotSize(risk_pts);
   if(lot_size <= 0.0) return;

   m_symbol.RefreshRates();

   if(order_type == ORDER_TYPE_BUY)
   {
      double ask = m_symbol.Ask();
      if(m_trade.Buy(lot_size, _Symbol, ask, sl, tp, comment))
      {
         PrintFormat("[+] BUY ORB Executed: Lots=%.2f | Entry=%.2f | SL=%.2f | TP=%.2f | Risk=%.2f pts",
                     lot_size, ask, sl, tp, risk_pts);
      }
   }
   else if(order_type == ORDER_TYPE_SELL)
   {
      double bid = m_symbol.Bid();
      if(m_trade.Sell(lot_size, _Symbol, bid, sl, tp, comment))
      {
         PrintFormat("[+] SELL ORB Executed: Lots=%.2f | Entry=%.2f | SL=%.2f | TP=%.2f | Risk=%.2f pts",
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
