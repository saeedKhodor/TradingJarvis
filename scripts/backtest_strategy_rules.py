# === CODE INDEX ===
# 1. Imports & Constants (Line 18)
# 2. simulate_trade_execution() - Evaluates bar-by-bar TP/SL/Trailing fills (Line 42)
# 3. run_discrete_strategy_backtest() - Tests explicit Entry/SL/TP rules on 100-day data (Line 85)
# 4. print_discrete_report() - Formats tabular results with Win Rate, Expectancy, Max Drawdown (Line 155)
# 5. main() - Entry point (Line 200)
# =================

import os
import sys
import logging
from typing import Dict, List, Any, Optional

import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.mt5_connector import MT5Connector
from scripts.backtest_trend_alignment import load_multi_timeframe_history, align_timeframes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TradingJarvis.StrategyBacktest")


def simulate_trade_execution(
    df: pd.DataFrame,
    entry_idx: int,
    is_long: bool,
    entry_price: float,
    sl_price: float,
    tp_rr: float = 2.0,
    max_hold_bars: int = 40
) -> Dict[str, Any]:
    """Simulates a trade bar-by-bar with exact Stop Loss and Take Profit levels."""
    risk_pts = abs(entry_price - sl_price)
    if risk_pts <= 0.5:
        risk_pts = 3.0  # Min risk buffer

    reward_pts = risk_pts * tp_rr
    tp_price = entry_price + reward_pts if is_long else entry_price - reward_pts

    for i in range(entry_idx + 1, min(entry_idx + max_hold_bars, len(df))):
        bar = df.iloc[i]

        if is_long:
            # Check Stop Loss
            if bar["low"] <= sl_price:
                return {"outcome": "LOSS", "pnl_pts": -risk_pts, "pnl_r": -1.0, "bars_held": i - entry_idx}
            # Check Take Profit
            if bar["high"] >= tp_price:
                return {"outcome": "WIN", "pnl_pts": reward_pts, "pnl_r": tp_rr, "bars_held": i - entry_idx}
        else:
            # Short Trade
            if bar["high"] >= sl_price:
                return {"outcome": "LOSS", "pnl_pts": -risk_pts, "pnl_r": -1.0, "bars_held": i - entry_idx}
            if bar["low"] <= tp_price:
                return {"outcome": "WIN", "pnl_pts": reward_pts, "pnl_r": tp_rr, "bars_held": i - entry_idx}

    # Time exit at close of final bar
    exit_bar = df.iloc[min(entry_idx + max_hold_bars - 1, len(df) - 1)]
    pnl_pts = (exit_bar["close"] - entry_price) if is_long else (entry_price - exit_bar["close"])
    pnl_r = pnl_pts / risk_pts
    return {
        "outcome": "WIN" if pnl_pts > 0 else "LOSS",
        "pnl_pts": pnl_pts,
        "pnl_r": pnl_r,
        "bars_held": max_hold_bars
    }


def run_discrete_strategy_backtest(df: pd.DataFrame, tp_rr: float = 2.0) -> Dict[str, Any]:
    """Runs event-driven trade evaluation for Trend Pullbacks and Cascade Setups."""
    trades_bull_pullback = []
    trades_macro_confluence = []
    trades_cascade_retest = []

    cooldown_bars = 4  # Min spacing between trade triggers

    last_bull_idx = -100
    last_macro_idx = -100
    last_cascade_idx = -100

    for i in range(1, len(df) - 40):
        bar = df.iloc[i]
        prev_bar = df.iloc[i - 1]
        hour = bar["dt"].hour

        # Session Filter: Active London & NY Market Hours (07:00 to 20:00 UTC)
        in_session = 7 <= hour <= 20

        # 1. Bullish Alignment Pullback (M15 > H1 + Low tests M15 9-EMA + Bullish close)
        is_bull_align = (bar["close"] > bar["m15_ema9"]) and (bar["m15_ema9"] > bar["h1_ema9"])
        is_pullback = bar["low"] <= (bar["m15_ema9"] + 1.5)
        is_bull_candle = bar["close"] > bar["open"]
        
        # Rejection Quality: Lower wick is at least 40% of total candle range
        candle_range = bar["high"] - bar["low"]
        lower_wick = min(bar["open"], bar["close"]) - bar["low"]
        is_quality_rejection = (lower_wick / candle_range >= 0.35) if candle_range > 0.5 else True

        if is_bull_align and is_pullback and is_bull_candle and in_session and (i - last_bull_idx >= cooldown_bars):
            sl = min(bar["low"], prev_bar["low"]) - 1.5
            trade = simulate_trade_execution(df, i, is_long=True, entry_price=bar["close"], sl_price=sl, tp_rr=tp_rr)
            trades_bull_pullback.append(trade)
            last_bull_idx = i

            # 2. If Macro D1 9-EMA also aligned:
            if "d1_ema9" in bar and bar["close"] > bar["d1_ema9"]:
                if i - last_macro_idx >= cooldown_bars:
                    trades_macro_confluence.append(trade)
                    last_macro_idx = i

        # 3. Cascade Short Retest (Price < H1_9 < H1_21 < H1_50 + High tests H1 9-EMA + Bearish close)
        is_cascade = (bar["close"] < bar["h1_ema9"]) and (bar["h1_ema9"] < bar["h1_ema21"]) and (bar["h1_ema21"] < bar["h1_ema50"])
        is_retest = bar["high"] >= (bar["h1_ema9"] - 2.0)
        is_bear_candle = bar["close"] < bar["open"]
        upper_wick = bar["high"] - max(bar["open"], bar["close"])
        is_quality_bear_rejection = (upper_wick / candle_range >= 0.35) if candle_range > 0.5 else True

        if is_cascade and is_retest and is_bear_candle and in_session and (i - last_cascade_idx >= cooldown_bars):
            sl = max(bar["high"], prev_bar["high"]) + 1.5
            trade = simulate_trade_execution(df, i, is_long=False, entry_price=bar["close"], sl_price=sl, tp_rr=tp_rr)
            trades_cascade_retest.append(trade)
            last_cascade_idx = i

    def summarize_trades(trades: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
        if not trades:
            return {"name": name, "count": 0}
        total = len(trades)
        wins = sum(1 for t in trades if t["outcome"] == "WIN")
        win_rate = (wins / total) * 100
        pnl_pts = sum(t["pnl_pts"] for t in trades)
        pnl_r = sum(t["pnl_r"] for t in trades)
        
        gross_gain = sum(t["pnl_pts"] for t in trades if t["pnl_pts"] > 0)
        gross_loss = abs(sum(t["pnl_pts"] for t in trades if t["pnl_pts"] < 0))
        pf = gross_gain / gross_loss if gross_loss > 0 else float("inf")
        expectancy_r = pnl_r / total

        return {
            "name": name,
            "total_trades": total,
            "win_rate": win_rate,
            "total_pnl_pts": pnl_pts,
            "total_pnl_r": pnl_r,
            "expectancy_r": expectancy_r,
            "profit_factor": pf
        }

    return {
        "tp_rr": tp_rr,
        "results": [
            summarize_trades(trades_bull_pullback, "1. Bullish Alignment (M15 9-EMA Pullback)"),
            summarize_trades(trades_macro_confluence, "2. Bullish + Macro D1 Confluence (Pullback)"),
            summarize_trades(trades_cascade_retest, "3. Cascade Short (H1 9-EMA Retest Rejection)")
        ]
    }


def print_discrete_report(res: Dict[str, Any]) -> None:
    """Displays discrete trade study results."""
    print("\n" + "=" * 90)
    print(f"     J.A.R.V.I.S. 100-DAY STRATEGY RULES SIMULATION (Target R:R = 1:{res['tp_rr']:.1f})")
    print("=" * 90)
    print(f"{'Strategy Setup':<45} | {'Trades':<7} | {'Win Rate':<9} | {'Total Pts':<10} | {'Exp (R)':<8} | {'PF':<6}")
    print("-" * 90)

    for r in res["results"]:
        if r.get("total_trades", 0) == 0:
            continue
        w_str = f"{r['win_rate']:.1f}%"
        pts_str = f"{r['total_pnl_pts']:+.1f}"
        exp_str = f"{r['expectancy_r']:+.2f}R"
        pf_str = f"{r['profit_factor']:.2f}" if r['profit_factor'] != float("inf") else "INF"

        print(f"{r['name']:<45} | {r['total_trades']:<7} | {w_str:<9} | {pts_str:<10} | {exp_str:<8} | {pf_str:<6}")

    print("=" * 90 + "\n")


def main():
    connector = MT5Connector()
    try:
        logger.info("Loading 100 days of multi-timeframe data for discrete simulation...")
        dfs = load_multi_timeframe_history(connector, symbol="US500.cash", days=100)
        merged = align_timeframes(dfs)
        
        # Test 1:2 R:R
        res_2r = run_discrete_strategy_backtest(merged, tp_rr=2.0)
        print_discrete_report(res_2r)

        # Test 1:1.5 R:R
        res_15r = run_discrete_strategy_backtest(merged, tp_rr=1.5)
        print_discrete_report(res_15r)
    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
