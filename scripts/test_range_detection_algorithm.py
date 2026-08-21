# === CODE INDEX ===
# 1. Imports & Setup (Line 18)
# 2. calculate_h1_range_metrics() - Quantifies Color Flip Ratio, Boundary Variance, and Overlap (Line 38)
# 3. test_h1_range_scanner() - Scans recent MT5 H1 history and identifies range vs trend regimes (Line 80)
# 4. main() - Entry point (Line 140)
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def calculate_h1_range_metrics(h1_df: pd.DataFrame, window: int = 6) -> pd.DataFrame:
    """
    Computes mathematical range metrics across a rolling window of H1 bars:
    1. Color Flip Ratio: % of bars that flipped color from previous bar.
    2. High Boundary StdDev: Variance of the highs (flat ceiling when small).
    3. Low Boundary StdDev: Variance of the lows (flat floor when small).
    4. Overlap Ratio: % of shared vertical range between consecutive bars.
    """
    df = h1_df.copy()
    
    # 1. Candle Color (1 = Green, -1 = Red, 0 = Doji)
    df["color"] = np.where(df["close"] > df["open"], 1, np.where(df["close"] < df["open"], -1, 0))
    df["color_flip"] = (df["color"] != df["color"].shift(1)) & (df["color"] != 0) & (df["color"].shift(1) != 0)
    
    # Rolling Color Flip Rate over window (e.g. last 6 hours)
    df["flip_rate"] = df["color_flip"].rolling(window).mean()
    
    # 2. Boundary Variance (Standard Deviation of Highs & Lows)
    df["high_std"] = df["high"].rolling(window).std()
    df["low_std"]  = df["low"].rolling(window).std()
    df["total_window_range"] = df["high"].rolling(window).max() - df["low"].rolling(window).min()
    
    # 3. Range Score (0 to 100)
    # High score = High Color Alternation + Low Boundary Variance relative to total range
    df["is_h1_range"] = (df["flip_rate"] >= 0.50) & (df["total_window_range"] <= 25.0)
    
    return df


def scan_recent_h1_ranges():
    connector = MT5Connector()
    if not connector.connect():
        return

    try:
        rates = connector.get_rates("US500.cash", count=120, timeframe="H1")
        df = pd.DataFrame(rates)
        df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.sort_values("dt", inplace=True)
        df.reset_index(drop=True, inplace=True)

        analyzed_df = calculate_h1_range_metrics(df, window=6)

        print("\n" + "=" * 105)
        print("          J.A.R.V.I.S. H1 RANGE DETECTION ALGORITHM AUDIT (LAST 25 H1 BARS)          ")
        print("=" * 105)
        print(f"{'Date & Time (UTC)':<18} | {'Open':<8} | {'High':<8} | {'Low':<8} | {'Close':<8} | {'Color':<6} | {'Flip Rate':<10} | {'6H Range':<9} | {'Regime Detected':<16}")
        print("-" * 105)

        for i in range(len(analyzed_df) - 25, len(analyzed_df)):
            row = analyzed_df.iloc[i]
            col_str = "🟢 GREEN" if row["color"] == 1 else ("🔴 RED" if row["color"] == -1 else "⚪ DOJI")
            flip_str = f"{row['flip_rate']*100:.0f}%" if pd.notnull(row["flip_rate"]) else "N/A"
            rng_str = f"{row['total_window_range']:.1f} pts" if pd.notnull(row["total_window_range"]) else "N/A"
            regime = "🔄 H1 RANGE" if row["is_h1_range"] else "⚡ TREND / EXPANSION"
            print(f"{row['dt'].strftime('%Y-%m-%d %H:%M'):<18} | {row['open']:<8.2f} | {row['high']:<8.2f} | {row['low']:<8.2f} | {row['close']:<8.2f} | {col_str:<6} | {flip_str:<10} | {rng_str:<9} | {regime:<16}")

        print("=" * 105 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    scan_recent_h1_ranges()
