# === CODE INDEX ===
# 1. Imports & Constants (Line 18)
# 2. detect_range_episodes() - State-machine algorithm to segment historical ranges (Line 38)
# 3. analyze_monthly_ranges_all_tfs() - Runs detection across 1H, 30M, 15M, and 5M (Line 110)
# 4. print_comprehensive_range_report() - Formats executive tables and breakdown (Line 180)
# 5. main() - Entry point (Line 250)
# =================

import os
import sys
import logging
from typing import Dict, List, Any, Tuple
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.mt5_connector import MT5Connector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TradingJarvis.MonthlyRanges")


def detect_range_episodes(
    df: pd.DataFrame,
    window_bars: int = 6,
    max_range_pts: float = 30.0,
    min_flip_rate: float = 0.50,
    timeframe_label: str = "1H"
) -> Dict[str, Any]:
    """
    Scans a continuous time series to identify distinct Range Episodes:
    - Condition: Rolling Window Range <= max_range_pts AND Color Flip Rate >= min_flip_rate
    - Merges consecutive range bars into continuous 'Range Episodes'
    """
    df = df.copy()
    df["color"] = np.where(df["close"] > df["open"], 1, np.where(df["close"] < df["open"], -1, 0))
    df["color_flip"] = (df["color"] != df["color"].shift(1)) & (df["color"] != 0) & (df["color"].shift(1) != 0)

    df["rolling_high"] = df["high"].rolling(window_bars).max()
    df["rolling_low"]  = df["low"].rolling(window_bars).min()
    df["rolling_span"] = df["rolling_high"] - df["rolling_low"]
    df["flip_rate"]    = df["color_flip"].rolling(window_bars).mean()

    # Active range condition per bar
    df["is_range_bar"] = (df["rolling_span"] <= max_range_pts) & (df["flip_rate"] >= min_flip_rate)

    # Segment into distinct episodes
    episodes = []
    in_episode = False
    ep_start_idx = 0

    for i in range(len(df)):
        is_rng = df.iloc[i]["is_range_bar"]

        if is_rng and not in_episode:
            in_episode = True
            ep_start_idx = max(0, i - window_bars + 1)
        elif not is_rng and in_episode:
            in_episode = False
            ep_end_idx = i
            ep_df = df.iloc[ep_start_idx:ep_end_idx]
            if len(ep_df) >= window_bars:
                ep_high = ep_df["high"].max()
                ep_low  = ep_df["low"].min()
                ep_span = ep_high - ep_low
                start_dt = ep_df.iloc[0]["dt"]
                end_dt   = ep_df.iloc[-1]["dt"]
                duration_hrs = (end_dt - start_dt).total_seconds() / 3600.0

                episodes.append({
                    "start_dt": start_dt,
                    "end_dt": end_dt,
                    "bar_count": len(ep_df),
                    "duration_hours": duration_hrs,
                    "high": ep_high,
                    "low": ep_low,
                    "span_pts": ep_span,
                    "flip_rate": ep_df["color_flip"].mean() * 100
                })

    # Close trailing episode if still active
    if in_episode:
        ep_df = df.iloc[ep_start_idx:]
        if len(ep_df) >= window_bars:
            ep_high = ep_df["high"].max()
            ep_low  = ep_df["low"].min()
            ep_span = ep_high - ep_low
            start_dt = ep_df.iloc[0]["dt"]
            end_dt   = ep_df.iloc[-1]["dt"]
            duration_hrs = (end_dt - start_dt).total_seconds() / 3600.0
            episodes.append({
                "start_dt": start_dt,
                "end_dt": end_dt,
                "bar_count": len(ep_df),
                "duration_hours": duration_hrs,
                "high": ep_high,
                "low": ep_low,
                "span_pts": ep_span,
                "flip_rate": ep_df["color_flip"].mean() * 100
            })

    total_bars = len(df)
    range_bars_count = df["is_range_bar"].sum()
    range_time_pct = (range_bars_count / total_bars) * 100 if total_bars > 0 else 0

    if not episodes:
        return {
            "timeframe": timeframe_label,
            "total_episodes": 0,
            "range_time_pct": 0.0,
            "avg_bar_count": 0.0,
            "avg_duration_hrs": 0.0,
            "avg_span_pts": 0.0,
            "max_span_pts": 0.0,
            "min_span_pts": 0.0,
            "episodes": []
        }

    avg_bar_count = sum(e["bar_count"] for e in episodes) / len(episodes)
    avg_duration_hrs = sum(e["duration_hours"] for e in episodes) / len(episodes)
    avg_span_pts = sum(e["span_pts"] for e in episodes) / len(episodes)
    max_span_pts = max(e["span_pts"] for e in episodes)
    min_span_pts = min(e["span_pts"] for e in episodes)

    return {
        "timeframe": timeframe_label,
        "total_bars_scanned": total_bars,
        "total_episodes": len(episodes),
        "range_time_pct": range_time_pct,
        "avg_bar_count": avg_bar_count,
        "avg_duration_hrs": avg_duration_hrs,
        "avg_span_pts": avg_span_pts,
        "max_span_pts": max_span_pts,
        "min_span_pts": min_span_pts,
        "episodes": episodes
    }


def analyze_all_timeframes():
    connector = MT5Connector()
    if not connector.connect():
        print("[!] MT5 connection failed.")
        return

    try:
        # Pull 30 days of data for each timeframe
        # Approx: H1 ~ 500 bars, 30M ~ 1000 bars, 15M ~ 2000 bars, 5M ~ 6000 bars
        h1_rates  = connector.get_rates("US500.cash", count=550, timeframe="H1")
        m30_rates = connector.get_rates("US500.cash", count=1100, timeframe="M30")
        m15_rates = connector.get_rates("US500.cash", count=2200, timeframe="M15")
        m5_rates  = connector.get_rates("US500.cash", count=6600, timeframe="M5")

        def to_df(rates):
            df = pd.DataFrame(rates)
            df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df.sort_values("dt", inplace=True)
            df.reset_index(drop=True, inplace=True)
            return df

        h1_df  = to_df(h1_rates)
        m30_df = to_df(m30_rates)
        m15_df = to_df(m15_rates)
        m5_df  = to_df(m5_rates)

        # Calibrated thresholds for each timeframe
        res_h1  = detect_range_episodes(h1_df,  window_bars=6, max_range_pts=28.0, min_flip_rate=0.45, timeframe_label="1-Hour (1H)")
        res_m30 = detect_range_episodes(m30_df, window_bars=8, max_range_pts=20.0, min_flip_rate=0.45, timeframe_label="30-Min (30M)")
        res_m15 = detect_range_episodes(m15_df, window_bars=8, max_range_pts=14.0, min_flip_rate=0.45, timeframe_label="15-Min (15M)")
        res_m5  = detect_range_episodes(m5_df,  window_bars=10, max_range_pts=9.0,  min_flip_rate=0.45, timeframe_label="5-Min (M5)")

        print("\n" + "=" * 105)
        print("          J.A.R.V.I.S. 30-DAY MULTI-TIMEFRAME RANGE & ENTROPY STUDY (US500.cash)          ")
        print("=" * 105)
        print(f"{'Timeframe':<14} | {'Total Ranges':<14} | {'Time in Range %':<16} | {'Avg Bar Count':<14} | {'Avg Duration':<14} | {'Avg Span (Pts)':<15} | {'Span Range (Min-Max)'}")
        print("-" * 105)

        for r in [res_h1, res_m30, res_m15, res_m5]:
            dur_str = f"{r['avg_duration_hrs']:.1f} Hours" if r['avg_duration_hrs'] >= 1.0 else f"{int(r['avg_duration_hrs']*60)} Mins"
            span_range = f"{r['min_span_pts']:.1f} - {r['max_span_pts']:.1f} pts"
            print(f"{r['timeframe']:<14} | {r['total_episodes']:<14} | {r['range_time_pct']:<15.1f}% | {r['avg_bar_count']:<13.1f} bars | {dur_str:<14} | {r['avg_span_pts']:<14.2f} pts | {span_range}")

        print("=" * 105 + "\n")

        # Print chronological list of top 1H range episodes over the month
        print("\n" + "=" * 105)
        print("                 CHRONOLOGICAL AUDIT OF MAJOR 1-HOUR (1H) RANGES IN LAST 30 DAYS                 ")
        print("=" * 105)
        print(f"{'Start Time (UTC)':<18} | {'End Time (UTC)':<18} | {'Duration':<12} | {'Bar Count':<10} | {'Range Floor':<12} | {'Range Ceiling':<14} | {'Span (Pts)'}")
        print("-" * 105)

        for ep in res_h1["episodes"][-12:]:
            dur_str = f"{ep['duration_hours']:.1f} Hours"
            print(f"{ep['start_dt'].strftime('%Y-%m-%d %H:%M'):<18} | {ep['end_dt'].strftime('%Y-%m-%d %H:%M'):<18} | {dur_str:<12} | {ep['bar_count']:<9} bars | {ep['low']:<12.2f} | {ep['high']:<14.2f} | {ep['span_pts']:.2f} pts")

        print("=" * 105 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    analyze_all_timeframes()
