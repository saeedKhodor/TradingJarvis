# === CODE INDEX ===
# 1. Imports & Setup (Line 18)
# 2. simulate_daily_5pt_harvest() - Tests 5-pt extraction across last 100 days (Line 38)
# 3. main() - Runs 100-day test (Line 125)
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


def simulate_daily_5pt_harvest(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Simulates a disciplined Hedge Fund 5-Point Daily Extraction model:
    - Exactly 1 trade per day maximum.
    - Setup: NY Open 15-Min Breakout (13:45 UTC) OR First M15 9-EMA Rejection.
    - Target: Exactly +5.0 Points.
    - Stop Loss: 5.0 Points (1:1.0 R:R).
    """
    df["date"] = df["dt"].dt.date
    unique_dates = sorted(df["date"].unique())

    daily_trades = []

    for d in unique_dates:
        day_df = df[df["date"] == d].copy()
        if len(day_df) < 50:
            continue

        # 1. Calculate NY Open 15-Minute Range (13:30 to 13:45 UTC)
        ny_open_df = day_df[(day_df["dt"].dt.hour == 13) & (day_df["dt"].dt.minute.isin([30, 35, 40]))]
        if len(ny_open_df) < 3:
            continue

        orb_high = ny_open_df["high"].max()
        orb_low  = ny_open_df["low"].min()
        orb_range = orb_high - orb_low

        # Skip days with massive erratic opening range (> 12.0 pts)
        if orb_range > 12.0 or orb_range < 1.5:
            continue

        # 2. Execution Window: 13:45 to 16:30 UTC
        post_open_df = day_df[((day_df["dt"].dt.hour == 13) & (day_df["dt"].dt.minute >= 45)) |
                              ((day_df["dt"].dt.hour >= 14) & (day_df["dt"].dt.hour <= 16))]

        trade_taken = False

        for idx in range(len(post_open_df) - 12):
            bar = post_open_df.iloc[idx]
            o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
            m15_9 = bar["m15_ema9"]

            # Strategy: Breakout with Trend Direction (Price vs M15 9-EMA)
            # Bullish Breakout
            if not trade_taken and c > orb_high and c > m15_9:
                entry = c
                sl = entry - 5.0
                tp = entry + 5.0
                outcome = "LOSS"
                pnl = -5.0

                for f_idx in range(idx + 1, min(idx + 24, len(post_open_df))):
                    f_bar = post_open_df.iloc[f_idx]
                    if f_bar["high"] >= tp:
                        outcome = "WIN"
                        pnl = +5.0
                        break
                    if f_bar["low"] <= sl:
                        outcome = "LOSS"
                        pnl = -5.0
                        break

                daily_trades.append({
                    "date": str(d),
                    "time": bar["dt"].strftime("%H:%M UTC"),
                    "type": "BUY (Bullish ORB)",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "pnl": pnl,
                    "outcome": outcome
                })
                trade_taken = True
                break

            # Bearish Breakdown
            elif not trade_taken and c < orb_low and c < m15_9:
                entry = c
                sl = entry + 5.0
                tp = entry - 5.0
                outcome = "LOSS"
                pnl = -5.0

                for f_idx in range(idx + 1, min(idx + 24, len(post_open_df))):
                    f_bar = post_open_df.iloc[f_idx]
                    if f_bar["low"] <= tp:
                        outcome = "WIN"
                        pnl = +5.0
                        break
                    if f_bar["high"] >= sl:
                        outcome = "LOSS"
                        pnl = -5.0
                        break

                daily_trades.append({
                    "date": str(d),
                    "time": bar["dt"].strftime("%H:%M UTC"),
                    "type": "SELL (Bearish ORB)",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "pnl": pnl,
                    "outcome": outcome
                })
                trade_taken = True
                break

    total = len(daily_trades)
    wins = sum(1 for t in daily_trades if t["outcome"] == "WIN")
    losses = total - wins
    win_rate = (wins / total) * 100 if total > 0 else 0
    total_pts = sum(t["pnl"] for t in daily_trades)

    return {
        "total_days_traded": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_pts": total_pts,
        "trades": daily_trades
    }


def main():
    connector = MT5Connector()
    try:
        if not connector.connect():
            return

        m5 = pd.DataFrame(connector.get_rates("US500.cash", count=29000, timeframe="M5"))
        m5["dt"] = pd.to_datetime(m5["time"], unit="s", utc=True)
        m5.sort_values("dt", inplace=True)
        m5.reset_index(drop=True, inplace=True)

        m15 = pd.DataFrame(connector.get_rates("US500.cash", count=10000, timeframe="M15"))
        m15["dt"] = pd.to_datetime(m15["time"], unit="s", utc=True)
        m15.sort_values("dt", inplace=True)
        m15["m15_ema9"] = compute_ema(m15["close"], 9)

        df = pd.merge_asof(m5, m15[["dt", "m15_ema9"]], on="dt", direction="backward")

        res = simulate_daily_5pt_harvest(df)

        print("\n" + "=" * 95)
        print("      HEDGE FUND QUANTITATIVE STUDY: 5-POINTS PER DAY HARVEST (100 DAYS)      ")
        print("=" * 95)
        print(f"Total Trading Days Qualified : {res['total_days_traded']}")
        print(f"Winning Days (+5.0 pts)      : {res['wins']} (🟢 {res['win_rate']:.1f}%)")
        print(f"Losing Days (-5.0 pts)       : {res['losses']}")
        print(f"Net Accumulated Points       : {res['total_pts']:+.1f} Index Points")
        print("=" * 95 + "\n")

        print("\n" + "=" * 105)
        print(f"            CHRONOLOGICAL LOG OF LAST 15 DAILY 5-POINT TRADES            ")
        print("=" * 105)
        print(f"{'Date':<12} | {'Time (UTC)':<10} | {'Setup Type':<22} | {'Entry':<8} | {'SL':<8} | {'TP':<8} | {'Outcome':<8} | {'PnL':<8}")
        print("-" * 105)
        for t in res["trades"][-15:]:
            out_sym = "🟢 WIN" if t["outcome"] == "WIN" else "🔴 LOSS"
            print(f"{t['date']:<12} | {t['time']:<10} | {t['type']:<22} | {t['entry']:<8.2f} | {t['sl']:<8.2f} | {t['tp']:<8.2f} | {out_sym:<8} | {t['pnl']:+6.1f} pts")
        print("=" * 105 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
