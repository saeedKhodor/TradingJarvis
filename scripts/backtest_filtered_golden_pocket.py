# === CODE INDEX ===
# 1. Imports & Setup (Line 18)
# 2. simulate_filtered_golden_pocket() - Evaluates Golden Pocket Shorts with Daily Trend & ATR Filters (Line 38)
# 3. main() - Runs comparative backtest across 100 days (Line 135)
# =================

import os
import sys
import logging
from typing import Dict, List, Any
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.mt5_connector import MT5Connector
from scripts.backtest_golden_pocket_multiday import compute_ema

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TradingJarvis.FilteredGoldenPocket")


def simulate_filtered_golden_pocket(
    df: pd.DataFrame,
    use_daily_macro: bool = True,
    target_rr: float = 2.5,
    use_be: bool = True,
    min_wick_ratio: float = 0.35
) -> Dict[str, Any]:
    trades = []
    cooldown_bars = 4
    last_trade_idx = -100

    for i in range(20, len(df) - 36):
        bar = df.iloc[i]
        hour = bar["dt"].hour

        if not (7 <= hour <= 20):
            continue
        if (i - last_trade_idx) < cooldown_bars:
            continue

        o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
        h1_9, h1_21, h1_50 = bar["h1_ema9"], bar["h1_ema21"], bar["h1_ema50"]
        d1_9 = bar["d1_ema9"]

        # 1. H1 Cascade
        is_cascade = (c < h1_9) and (h1_9 < h1_21) and (h1_21 < h1_50)
        if not is_cascade:
            continue

        # 2. Daily Macro Filter (Only short when Price < Daily 9-EMA)
        if use_daily_macro and c >= d1_9:
            continue

        # 3. H1 9-EMA Touch Zone
        touches_h1 = (h >= h1_9 - 2.5) and (h <= h1_21 + 2.5)
        if not touches_h1:
            continue

        # 4. Strict Rejection Pinbar (Upper wick >= min_wick_ratio and Bearish close)
        c_range = h - l
        upper_wick = h - max(o, c)
        is_pinbar = (c_range > 0.5) and ((upper_wick / c_range) >= min_wick_ratio) and (c < o)
        if not is_pinbar:
            continue

        entry = c
        sl = round(h + 1.5, 2)
        risk = max(round(sl - entry, 2), 3.5)
        if risk > 25.0:
            continue

        tp = round(entry - (risk * target_rr), 2)
        be_trigger = round(entry - (risk * 1.0), 2)

        be_active = False
        curr_sl = sl
        won = False

        for j in range(i + 1, min(i + 36, len(df))):
            f = df.iloc[j]

            if use_be and f["low"] <= be_trigger:
                be_active = True
                curr_sl = round(entry - 0.5, 2)

            if f["high"] >= curr_sl:
                exit_p = curr_sl
                pnl = entry - exit_p
                trades.append({"date": bar["dt"].strftime("%Y-%m-%d %H:%M"), "outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl, "pnl_r": pnl / risk})
                won = True
                break

            if f["low"] <= tp:
                pnl = risk * target_rr
                trades.append({"date": bar["dt"].strftime("%Y-%m-%d %H:%M"), "outcome": "WIN", "pnl_pts": pnl, "pnl_r": target_rr})
                won = True
                break

        if not won:
            end_b = df.iloc[min(i + 35, len(df) - 1)]
            pnl = entry - end_b["close"]
            trades.append({"date": bar["dt"].strftime("%Y-%m-%d %H:%M"), "outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl, "pnl_r": pnl / risk})

        last_trade_idx = i

    total = len(trades)
    if total == 0:
        return {"name": f"Daily={use_daily_macro} | Wick={min_wick_ratio}", "total_trades": 0}

    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    pnl_pts = sum(t["pnl_pts"] for t in trades)
    gains = sum(t["pnl_pts"] for t in trades if t["pnl_pts"] > 0)
    losses = abs(sum(t["pnl_pts"] for t in trades if t["pnl_pts"] < 0))
    pf = gains / losses if losses > 0 else float("inf")

    return {
        "name": f"Daily Filter={use_daily_macro} | Pinbar Wick>={int(min_wick_ratio*100)}%",
        "total_trades": total,
        "wins": wins,
        "win_rate": (wins / total) * 100,
        "total_pnl_pts": pnl_pts,
        "profit_factor": pf,
        "avg_r": sum(t["pnl_r"] for t in trades) / total
    }


def main():
    connector = MT5Connector()
    try:
        logger.info("Connecting to MT5 to run Filtered Golden Pocket study...")
        if not connector.connect():
            return

        m5_rates = connector.get_rates("US500.cash", count=29000, timeframe="M5")
        df = pd.DataFrame(m5_rates)
        df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.sort_values("dt", inplace=True)
        df.reset_index(drop=True, inplace=True)

        h1_rates = connector.get_rates("US500.cash", count=2500, timeframe="H1")
        df_h1 = pd.DataFrame(h1_rates)
        df_h1["dt"] = pd.to_datetime(df_h1["time"], unit="s", utc=True)
        df_h1.sort_values("dt", inplace=True)
        df_h1["h1_ema9"] = compute_ema(df_h1["close"], 9)
        df_h1["h1_ema21"] = compute_ema(df_h1["close"], 21)
        df_h1["h1_ema50"] = compute_ema(df_h1["close"], 50)

        d1_rates = connector.get_rates("US500.cash", count=150, timeframe="D1")
        df_d1 = pd.DataFrame(d1_rates)
        df_d1["dt"] = pd.to_datetime(df_d1["time"], unit="s", utc=True)
        df_d1.sort_values("dt", inplace=True)
        df_d1["d1_ema9"] = compute_ema(df_d1["close"], 9)

        df = pd.merge_asof(df, df_h1[["dt", "h1_ema9", "h1_ema21", "h1_ema50"]], on="dt", direction="backward")
        df = pd.merge_asof(df, df_d1[["dt", "d1_ema9"]], on="dt", direction="backward")

        results = [
            simulate_filtered_golden_pocket(df, use_daily_macro=False, min_wick_ratio=0.25),
            simulate_filtered_golden_pocket(df, use_daily_macro=True, min_wick_ratio=0.25),
            simulate_filtered_golden_pocket(df, use_daily_macro=True, min_wick_ratio=0.35),
            simulate_filtered_golden_pocket(df, use_daily_macro=True, min_wick_ratio=0.40)
        ]

        print("\n" + "=" * 95)
        print("     J.A.R.V.I.S. FILTERED GOLDEN POCKET QUANTITATIVE BENCHMARK (100 DAYS)      ")
        print("=" * 95)
        print(f"{'Strategy Architecture':<50} | {'Trades':<7} | {'Win Rate':<10} | {'Total Pts':<10} | {'PF':<6}")
        print("-" * 95)

        for r in results:
            if r.get("total_trades", 0) == 0:
                continue
            w_str = f"{r['win_rate']:.1f}% ({r['wins']}/{r['total_trades']})"
            pts_str = f"{r['total_pnl_pts']:+.1f}"
            pf_str = f"{r['profit_factor']:.2f}" if r['profit_factor'] != float("inf") else "INF"
            print(f"{r['name']:<50} | {r['total_trades']:<7} | {w_str:<10} | {pts_str:<10} | {pf_str:<6}")

        print("=" * 95 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
