# === CODE INDEX ===
# 1. Imports & Constants (Line 18)
# 2. analyze_timeframe_range() - Computes range metrics, boundary levels, and zone location (Line 38)
# 3. run_multi_timeframe_scan() - Scans both 30M and 1H timeframes on live MT5 data (Line 110)
# 4. main() - Entry point (Line 185)
# =================

import os
import sys
import logging
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.mt5_connector import MT5Connector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TradingJarvis.RangeScanner")


def analyze_timeframe_range(df: pd.DataFrame, timeframe_name: str, window: int = 8) -> Dict[str, Any]:
    """
    Analyzes whether a specific timeframe (30M or 1H) is currently in an active range.
    """
    df = df.copy()
    df["color"] = np.where(df["close"] > df["open"], 1, np.where(df["close"] < df["open"], -1, 0))
    df["color_flip"] = (df["color"] != df["color"].shift(1)) & (df["color"] != 0) & (df["color"].shift(1) != 0)

    recent_bars = df.iloc[-window:].copy()
    current_price = df.iloc[-1]["close"]

    # 1. Color Flip Entropy
    flip_count = recent_bars["color_flip"].sum()
    flip_rate = (flip_count / (window - 1)) * 100

    # 2. Boundary Levels & Variance
    highs = recent_bars["high"]
    lows = recent_bars["low"]
    
    range_high = highs.max()
    range_low  = lows.min()
    range_span = range_high - range_low

    high_std = highs.std()
    low_std  = lows.std()

    # 3. Value Area & Current Price Location
    # Location: 0% = Range Low (Discount), 50% = Equilibrium (POC), 100% = Range High (Premium)
    if range_span > 0:
        price_location_pct = ((current_price - range_low) / range_span) * 100
    else:
        price_location_pct = 50.0

    # Location Zone Label
    if price_location_pct <= 25.0:
        zone_label = "🟢 DISCOUNT / BUY ZONE (Near Floor)"
    elif price_location_pct >= 75.0:
        zone_label = "🔴 PREMIUM / SELL ZONE (Near Ceiling)"
    else:
        zone_label = "🟡 EQUILIBRIUM / POC (Chop Zone - Stand Down)"

    # 4. Range Quality Scoring (0 - 100)
    # Higher score = High flips + tight range span + small boundary variance
    score = 0
    if flip_rate >= 50.0: score += 35
    if flip_rate >= 70.0: score += 15
    if range_span <= 30.0: score += 30
    if (high_std + low_std) <= 8.0: score += 20

    is_range = (score >= 60) and (range_span <= 35.0)

    return {
        "timeframe": timeframe_name,
        "window_bars": window,
        "current_price": current_price,
        "range_high": range_high,
        "range_low": range_low,
        "range_span_pts": range_span,
        "high_std": high_std,
        "low_std": low_std,
        "flip_rate_pct": flip_rate,
        "range_score": score,
        "is_range": is_range,
        "price_location_pct": price_location_pct,
        "zone_label": zone_label,
        "recent_colors": ["🟢" if c == 1 else ("🔴" if c == -1 else "⚪") for c in recent_bars["color"].values]
    }


def run_multi_timeframe_scan():
    connector = MT5Connector()
    if not connector.connect():
        print("[!] Failed to connect to MetaTrader 5.")
        return

    try:
        # Fetch 30M and H1 rates
        m30_rates = connector.get_rates("US500.cash", count=100, timeframe="M30")
        h1_rates  = connector.get_rates("US500.cash", count=100, timeframe="H1")

        m30_df = pd.DataFrame(m30_rates)
        m30_df["dt"] = pd.to_datetime(m30_df["time"], unit="s", utc=True)
        m30_df.sort_values("dt", inplace=True)
        m30_df.reset_index(drop=True, inplace=True)

        h1_df = pd.DataFrame(h1_rates)
        h1_df["dt"] = pd.to_datetime(h1_df["time"], unit="s", utc=True)
        h1_df.sort_values("dt", inplace=True)
        h1_df.reset_index(drop=True, inplace=True)

        m30_res = analyze_timeframe_range(m30_df, "30-MINUTE (30M)", window=10)
        h1_res  = analyze_timeframe_range(h1_df,  "1-HOUR (1H)",     window=8)

        print("\n" + "=" * 90)
        print("          J.A.R.V.I.S. DUAL-TIMEFRAME (30M & 1H) RANGE DIAGNOSTIC REPORT          ")
        print("=" * 90)

        for res in [m30_res, h1_res]:
            status_tag = "🟢 ACTIVE RANGE CONFIRMED" if res["is_range"] else "⚡ TREND / EXPANSION MODE"
            print(f"\n📊 TIMEFRAME: {res['timeframe']}  |  STATUS: {status_tag}")
            print("─" * 90)
            print(f"• Current Price       : {res['current_price']:.2f}")
            print(f"• Range Ceiling (Top) : {res['range_high']:.2f}")
            print(f"• Range Floor (Bottom): {res['range_low']:.2f}")
            print(f"• Total Range Span    : {res['range_span_pts']:.2f} Index Points")
            print(f"• Candle Colors ({res['window_bars']} bars): {' '.join(res['recent_colors'])}")
            print(f"• Color Flip Rate     : {res['flip_rate_pct']:.1f}% (Alternation Frequency)")
            print(f"• Boundary Flatness   : High-Std: {res['high_std']:.2f} | Low-Std: {res['low_std']:.2f}")
            print(f"• Range Quality Score : {res['range_score']}/100")
            print(f"• Price Location (%): {res['price_location_pct']:.1f}% from Floor to Ceiling")
            print(f"• Strategic Action    : {res['zone_label']}")

        print("\n" + "=" * 90)
        print("🏛️ INSTITUTIONAL SYNTHESIS:")
        if h1_res["is_range"] or m30_res["is_range"]:
            active_tf = "1H & 30M" if (h1_res["is_range"] and m30_res["is_range"]) else ("1H" if h1_res["is_range"] else "30M")
            print(f"• Market is in a confirmed {active_tf} Equilibrium Box.")
            print(f"• Macro Range Bounds: Floor @ {h1_res['range_low']:.2f}  <───>  Ceiling @ {h1_res['range_high']:.2f}")
            print(f"• Tactical Play: VETO M5 momentum breakouts. Fade outer liquidity sweeps.")
        else:
            print("• Market is currently in directional trend/expansion mode. Trade momentum continuations.")
        print("=" * 90 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    run_multi_timeframe_scan()
