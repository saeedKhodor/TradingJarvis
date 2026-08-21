# === CODE INDEX ===
# 1. Imports & Setup (Line 18)
# 2. measure_range_duration() - Calculates exact bar count & hours of sideways range (Line 38)
# 3. main() - Entry point (Line 110)
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


def measure_range_duration():
    connector = MT5Connector()
    if not connector.connect():
        return

    try:
        h1_rates = connector.get_rates("US500.cash", count=50, timeframe="H1")
        m30_rates = connector.get_rates("US500.cash", count=100, timeframe="M30")
        m5_rates = connector.get_rates("US500.cash", count=300, timeframe="M5")

        h1_df = pd.DataFrame(h1_rates)
        h1_df["dt"] = pd.to_datetime(h1_df["time"], unit="s", utc=True)
        h1_df.sort_values("dt", inplace=True)
        h1_df.reset_index(drop=True, inplace=True)

        m30_df = pd.DataFrame(m30_rates)
        m30_df["dt"] = pd.to_datetime(m30_df["time"], unit="s", utc=True)
        m30_df.sort_values("dt", inplace=True)
        m30_df.reset_index(drop=True, inplace=True)

        m5_df = pd.DataFrame(m5_rates)
        m5_df["dt"] = pd.to_datetime(m5_df["time"], unit="s", utc=True)
        m5_df.sort_values("dt", inplace=True)
        m5_df.reset_index(drop=True, inplace=True)

        # Range boundaries established after yesterday's low (2026-08-20 23:00 UTC at 7638.60)
        # Find all bars from when price entered the 7645-7673 box
        box_low = 7645.00
        box_high = 7673.50

        # On H1
        h1_in_box = h1_df[(h1_df["low"] >= (box_low - 3.0)) & (h1_df["high"] <= (box_high + 3.0))]
        start_time_h1 = h1_in_box.iloc[0]["dt"]
        end_time_h1 = h1_in_box.iloc[-1]["dt"]
        h1_bars_count = len(h1_in_box)

        # On M30
        m30_in_box = m30_df[(m30_df["dt"] >= start_time_h1)]
        m30_bars_count = len(m30_in_box)

        # On M5
        m5_in_box = m5_df[(m5_df["dt"] >= start_time_h1)]
        m5_bars_count = len(m5_in_box)

        duration_hours = (end_time_h1 - start_time_h1).total_seconds() / 3600.0

        print("\n" + "=" * 90)
        print("          J.A.R.V.I.S. SIDEWAYS RANGE DURATION & BAR COUNT AUDIT          ")
        print("=" * 90)
        print(f"• Range Box Boundaries : Floor @ {box_low:.2f}  <───>  Ceiling @ {box_high:.2f} (Span: 28.5 pts)")
        print(f"• Range Inception Time : {start_time_h1.strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"• Current Active Time  : {end_time_h1.strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"• Total Time Sideways  : {duration_hours:.1f} Hours ({int(duration_hours*60)} Minutes)")
        print("-" * 90)
        print(f"📊 BAR COUNT BREAKDOWN BY TIMEFRAME:")
        print(f"  ▶ 1-Hour Timeframe  (1H)  : {h1_bars_count} Consecutive Bars Sideways")
        print(f"  ▶ 30-Min Timeframe  (30M) : {m30_bars_count} Consecutive Bars Sideways")
        print(f"  ▶ 5-Min Timeframe   (M5)  : {m5_bars_count} Consecutive Bars Sideways")
        print("=" * 90 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    measure_range_duration()
