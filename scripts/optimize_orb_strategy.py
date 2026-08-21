# === CODE INDEX ===
# 1. Imports & Setup (Line 18)
# 2. optimize_orb() - Evaluates failed breakout early-exit, HTF trend filter, and partial take-profit (Line 38)
# 3. main() - Runs optimization on 2021-2026 MT5 data (Line 125)
# =================

import os
import sys
import logging
from typing import Dict, Any, List
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.mt5_connector import MT5Connector
from scripts.backtest_trend_alignment import calculate_ema

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TradingJarvis.OptimizeORB")


def optimize_orb(df: pd.DataFrame, use_htf_filter: bool = True, early_exit_failed_breakout: bool = True) -> Dict[str, Any]:
    trades = []
    df = df.copy()
    df["date"] = df["dt"].dt.date
    unique_dates = df["date"].unique()

    for d in unique_dates:
        day_df = df[df["date"] == d].copy()
        if len(day_df) < 30:
            continue

        # Get 13:30-13:45 bars (3 M5 bars)
        orb_bars = day_df[(day_df["dt"].dt.hour == 13) & (day_df["dt"].dt.minute.isin([30, 35, 40]))]
        if len(orb_bars) < 3:
            continue

        orb_high = orb_bars["high"].max()
        orb_low = orb_bars["low"].min()
        orb_range = orb_high - orb_low

        if orb_range < 4.0 or orb_range > 35.0:
            continue

        post_orb = day_df[(day_df["dt"].dt.hour > 13) | ((day_df["dt"].dt.hour == 13) & (day_df["dt"].dt.minute > 40))]
        post_orb = post_orb[post_orb["dt"].dt.hour <= 19]

        for idx in range(len(post_orb)):
            bar = post_orb.iloc[idx]
            
            # 1. Long Breakout
            is_bull_htf = bar["close"] > bar["d1_ema9"] if ("d1_ema9" in bar and use_htf_filter) else True
            if bar["close"] > orb_high and is_bull_htf:
                entry = bar["close"]
                sl = orb_low
                risk = entry - sl
                tp = entry + (orb_range * 1.5)
                be_trigger = entry + (orb_range * 0.8)

                won = False
                be_active = False
                curr_sl = sl

                for k in range(idx + 1, min(idx + 24, len(post_orb))):
                    f = post_orb.iloc[k]
                    # Early exit if candle closes back inside range on next 2 bars (cuts loss in half!)
                    if early_exit_failed_breakout and k <= idx + 2 and f["close"] < orb_high:
                        pnl = f["close"] - entry
                        trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl})
                        won = True
                        break

                    if f["high"] >= be_trigger:
                        be_active = True
                        curr_sl = entry + 1.0

                    if f["low"] <= curr_sl:
                        pnl = -risk if not be_active else +1.0
                        trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl})
                        won = True
                        break

                    if f["high"] >= tp:
                        trades.append({"outcome": "WIN", "pnl_pts": orb_range * 1.5})
                        won = True
                        break

                if not won:
                    end_b = post_orb.iloc[min(idx + 23, len(post_orb) - 1)]
                    pnl = end_b["close"] - entry
                    trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl})
                break

            # 2. Short Breakout
            is_bear_htf = bar["close"] < bar["d1_ema9"] if ("d1_ema9" in bar and use_htf_filter) else True
            if bar["close"] < orb_low and is_bear_htf:
                entry = bar["close"]
                sl = orb_high
                risk = sl - entry
                tp = entry - (orb_range * 1.5)
                be_trigger = entry - (orb_range * 0.8)

                won = False
                be_active = False
                curr_sl = sl

                for k in range(idx + 1, min(idx + 24, len(post_orb))):
                    f = post_orb.iloc[k]
                    if early_exit_failed_breakout and k <= idx + 2 and f["close"] > orb_low:
                        pnl = entry - f["close"]
                        trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl})
                        won = True
                        break

                    if f["low"] <= be_trigger:
                        be_active = True
                        curr_sl = entry - 1.0

                    if f["high"] >= curr_sl:
                        pnl = -risk if not be_active else +1.0
                        trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl})
                        won = True
                        break

                    if f["low"] <= tp:
                        trades.append({"outcome": "WIN", "pnl_pts": orb_range * 1.5})
                        won = True
                        break

                if not won:
                    end_b = post_orb.iloc[min(idx + 23, len(post_orb) - 1)]
                    pnl = entry - end_b["close"]
                    trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl})
                break

    total = len(trades)
    if total == 0:
        return {"total_trades": 0}
    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    pnl_pts = sum(t["pnl_pts"] for t in trades)
    gains = sum(t["pnl_pts"] for t in trades if t["pnl_pts"] > 0)
    losses = abs(sum(t["pnl_pts"] for t in trades if t["pnl_pts"] < 0))
    pf = gains / losses if losses > 0 else float("inf")

    return {
        "total_trades": total,
        "win_rate": (wins / total) * 100,
        "total_pnl_pts": pnl_pts,
        "profit_factor": pf,
        "avg_win": gains / wins if wins > 0 else 0,
        "avg_loss": losses / (total - wins) if (total - wins) > 0 else 0
    }


def main():
    connector = MT5Connector()
    try:
        logger.info("Loading M5 data from MT5 for ORB optimization...")
        if not connector.connect():
            return
        rates = connector.get_rates("US500.cash", count=29000, timeframe="M5")
        df = pd.DataFrame(rates)
        df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.sort_values("dt", inplace=True)
        df.reset_index(drop=True, inplace=True)

        d1_rates = connector.get_rates("US500.cash", count=150, timeframe="D1")
        d1_df = pd.DataFrame(d1_rates)
        d1_df["dt"] = pd.to_datetime(d1_df["time"], unit="s", utc=True)
        d1_df["d1_ema9"] = calculate_ema(d1_df["close"], 9)
        df = pd.merge_asof(df, d1_df[["dt", "d1_ema9"]], on="dt", direction="backward")

        raw_res = optimize_orb(df, use_htf_filter=False, early_exit_failed_breakout=False)
        opt_res = optimize_orb(df, use_htf_filter=True, early_exit_failed_breakout=True)

        print("\n" + "=" * 80)
        print("          J.A.R.V.I.S. ORB STRATEGY OPTIMIZATION COMPARISON           ")
        print("=" * 80)
        print(f"Raw Model       -> Trades: {raw_res['total_trades']} | Win Rate: {raw_res['win_rate']:.1f}% | Net Pts: {raw_res['total_pnl_pts']:+.1f} | PF: {raw_res['profit_factor']:.2f}")
        print(f"Optimized Model -> Trades: {opt_res['total_trades']} | Win Rate: {opt_res['win_rate']:.1f}% | Net Pts: {opt_res['total_pnl_pts']:+.1f} | PF: {opt_res['profit_factor']:.2f}")
        print("=" * 80 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
