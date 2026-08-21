# === CODE INDEX ===
# 1. Imports & Setup (Line 18)
# 2. analyze_last_10_days() - Comprehensive 10-Day Institutional Microstructure Audit (Line 38)
# 3. main() - Entry point (Line 135)
# =================

import os
import sys
import logging
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.mt5_connector import MT5Connector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def analyze_last_10_days():
    connector = MT5Connector()
    if not connector.connect():
        return

    try:
        # Pull 15 days of M5 data
        rates = connector.get_rates("US500.cash", count=6000, timeframe="M5")
        df = pd.DataFrame(rates)
        df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.sort_values("dt", inplace=True)
        df.reset_index(drop=True, inplace=True)

        df["date"] = df["dt"].dt.date
        unique_dates = sorted(df["date"].unique())[-11:]

        days_summary = []

        for d in unique_dates:
            day_df = df[df["date"] == d].copy()
            if len(day_df) < 50:
                continue

            day_open = day_df.iloc[0]["open"]
            day_high = day_df["high"].max()
            day_low = day_df["low"].min()
            day_close = day_df.iloc[-1]["close"]
            day_range = day_high - day_low

            # 1. Asian / London Range (00:00 to 12:00 UTC)
            pre_df = day_df[day_df["dt"].dt.hour < 13]
            pre_high = pre_df["high"].max() if len(pre_df) > 0 else day_open
            pre_low = pre_df["low"].min() if len(pre_df) > 0 else day_open
            pre_range = pre_high - pre_low

            # 2. NY Open 15-Min Range (13:30 to 13:45 UTC)
            ny_open_df = day_df[(day_df["dt"].dt.hour == 13) & (day_df["dt"].dt.minute.isin([30, 35, 40]))]
            ny_open_high = ny_open_df["high"].max() if len(ny_open_df) >= 3 else 0.0
            ny_open_low  = ny_open_df["low"].min() if len(ny_open_df) >= 3 else 0.0
            ny_open_range = ny_open_high - ny_open_low

            # 3. Post-Open Momentum (13:45 to 16:00 UTC)
            post_mask = ((day_df["dt"].dt.hour == 13) & (day_df["dt"].dt.minute > 40)) | \
                        ((day_df["dt"].dt.hour >= 14) & (day_df["dt"].dt.hour <= 16))
            post_open_df = day_df[post_mask]

            first_5pt_time = "N/A"
            first_5pt_type = "N/A"
            max_expansion = 0.0

            if ny_open_range > 0 and len(post_open_df) > 0:
                for idx in range(len(post_open_df)):
                    bar = post_open_df.iloc[idx]
                    t_str = bar["dt"].strftime("%H:%M UTC")

                    # If price broke above NY Open High by >= 5 pts
                    if bar["high"] >= (ny_open_high + 5.0):
                        first_5pt_time = t_str
                        first_5pt_type = "🟢 Bullish Breakout"
                        max_expansion = bar["high"] - ny_open_high
                        break
                    # If price broke below NY Open Low by >= 5 pts
                    elif bar["low"] <= (ny_open_low - 5.0):
                        first_5pt_time = t_str
                        first_5pt_type = "🔴 Bearish Breakdown"
                        max_expansion = ny_open_low - bar["low"]
                        break

            # Day Taxonomy Classification
            day_type = "UNKNOWN"
            if abs(day_close - day_open) >= (day_range * 0.60):
                day_type = "📈 TREND UP" if day_close > day_open else "📉 TREND DOWN"
            elif day_range <= 30.0:
                day_type = "🔄 BALANCED CHOP"
            else:
                day_type = "⚡ EXPANSION ROTATION"

            days_summary.append({
                "date": str(d),
                "open": day_open,
                "high": day_high,
                "low": day_low,
                "close": day_close,
                "range": day_range,
                "pre_range": pre_range,
                "ny_15m_range": ny_open_range,
                "day_type": day_type,
                "first_5pt_time": first_5pt_time,
                "first_5pt_type": first_5pt_type,
                "max_expansion": max_expansion
            })

        print("\n" + "=" * 115)
        print("          HEDGE FUND STRATEGY REPORT: LAST 10 TRADING DAYS 5-POINT EXTRACTION AUDIT          ")
        print("=" * 115)
        print(f"{'Date':<12} | {'Day Range':<10} | {'Pre-Range':<10} | {'15m Open Range':<15} | {'Day Classification':<20} | {'First 5-Pt Event & Time':<30}")
        print("-" * 115)

        for d in days_summary[-10:]:
            print(f"{d['date']:<12} | {d['range']:<10.2f} | {d['pre_range']:<10.2f} | {d['ny_15m_range']:<15.2f} | {d['day_type']:<20} | {d['first_5pt_type']} ({d['first_5pt_time']})")

        print("=" * 115 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    analyze_last_10_days()
