# === CODE INDEX ===
# 1. Imports & Constants (Line 18)
# 2. extract_yesterday_data() - Pulls exact MT5 OHLCV bars across M5, M15, M30, H1, D1 (Line 38)
# 3. compute_mt5_native_emas() - Computes exact MT5 MODE_EMA matching iMA() handles (Line 75)
# 4. identify_yesterday_positions() - Detects Golden Pocket Shorts, Pullbacks, and ORB entries (Line 115)
# 5. print_detailed_chronology() - Generates rich ASCII timetable of yesterday's setups (Line 185)
# 6. main() - Entry point (Line 250)
# =================

import os
import sys
import logging
from datetime import datetime, timezone
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.mt5_connector import MT5Connector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TradingJarvis.YesterdayAnalysis")


def compute_mt5_ema(series: pd.Series, period: int) -> pd.Series:
    """Computes exact MT5 MODE_EMA matching MetaTrader 5 native iMA buffer (alpha = 2/(period+1))."""
    return series.ewm(span=period, adjust=False).mean()


def analyze_yesterday_market():
    connector = MT5Connector()
    if not connector.connect():
        logger.error("Failed to connect to MT5 terminal.")
        return

    try:
        # Target date: Yesterday = 2026-08-20
        target_date_str = "2026-08-20"
        logger.info(f"Extracting MT5 market data for {target_date_str} on US500.cash...")

        # 1. Pull M5 Data (2000 bars to ensure EMA warmup)
        m5_rates = connector.get_rates("US500.cash", count=2000, timeframe="M5")
        df_m5 = pd.DataFrame(m5_rates)
        df_m5["dt"] = pd.to_datetime(df_m5["time"], unit="s", utc=True)
        df_m5.sort_values("dt", inplace=True)
        df_m5["m5_ema9"] = compute_mt5_ema(df_m5["close"], 9)

        # 2. Pull M15 Data
        m15_rates = connector.get_rates("US500.cash", count=1000, timeframe="M15")
        df_m15 = pd.DataFrame(m15_rates)
        df_m15["dt"] = pd.to_datetime(df_m15["time"], unit="s", utc=True)
        df_m15.sort_values("dt", inplace=True)
        df_m15["m15_ema9"] = compute_mt5_ema(df_m15["close"], 9)

        # 3. Pull M30 Data
        m30_rates = connector.get_rates("US500.cash", count=500, timeframe="M30")
        df_m30 = pd.DataFrame(m30_rates)
        df_m30["dt"] = pd.to_datetime(df_m30["time"], unit="s", utc=True)
        df_m30.sort_values("dt", inplace=True)
        df_m30["m30_ema9"] = compute_mt5_ema(df_m30["close"], 9)

        # 4. Pull H1 Data
        h1_rates = connector.get_rates("US500.cash", count=500, timeframe="H1")
        df_h1 = pd.DataFrame(h1_rates)
        df_h1["dt"] = pd.to_datetime(df_h1["time"], unit="s", utc=True)
        df_h1.sort_values("dt", inplace=True)
        df_h1["h1_ema9"] = compute_mt5_ema(df_h1["close"], 9)
        df_h1["h1_ema21"] = compute_mt5_ema(df_h1["close"], 21)
        df_h1["h1_ema50"] = compute_mt5_ema(df_h1["close"], 50)

        # 5. Pull D1 Data
        d1_rates = connector.get_rates("US500.cash", count=100, timeframe="D1")
        d1_df = pd.DataFrame(d1_rates)
        d1_df["dt"] = pd.to_datetime(d1_df["time"], unit="s", utc=True)
        d1_df.sort_values("dt", inplace=True)
        d1_df["d1_ema9"] = compute_mt5_ema(d1_df["close"], 9)

        # Merge HTF indicators onto M5 using asof merge (no lookahead)
        df_m5 = pd.merge_asof(df_m5, df_m15[["dt", "m15_ema9"]], on="dt", direction="backward")
        df_m5 = pd.merge_asof(df_m5, df_m30[["dt", "m30_ema9"]], on="dt", direction="backward")
        df_m5 = pd.merge_asof(df_m5, df_h1[["dt", "h1_ema9", "h1_ema21", "h1_ema50"]], on="dt", direction="backward")
        df_m5 = pd.merge_asof(df_m5, d1_df[["dt", "d1_ema9"]], on="dt", direction="backward")

        # Filter strictly for yesterday: 2026-08-20 00:00 to 23:59 UTC
        yday_m5 = df_m5[(df_m5["dt"] >= "2026-08-20 00:00:00+00:00") & (df_m5["dt"] < "2026-08-21 00:00:00+00:00")].copy()
        yday_m5.reset_index(drop=True, inplace=True)

        print("\n" + "=" * 105)
        print(f"       J.A.R.V.I.S. YESTERDAY'S MARKET AUDIT (US500.cash | 2026-08-20 UTC)       ")
        print("=" * 105)
        print(f"Total M5 Candles Ingested: {len(yday_m5)}")
        print(f"Day Open:  {yday_m5.iloc[0]['open']:.2f} | Day High: {yday_m5['high'].max():.2f} | Day Low: {yday_m5['low'].min():.2f} | Day Close: {yday_m5.iloc[-1]['close']:.2f}")
        print(f"Daily 9-EMA Baseline: {yday_m5.iloc[0]['d1_ema9']:.2f}")
        print("-" * 105)

        # Evaluate Setups
        setups = []

        # 1. Opening Range High & Low (13:30 to 13:45 UTC)
        orb_bars = yday_m5[(yday_m5["dt"].dt.hour == 13) & (yday_m5["dt"].dt.minute.isin([30, 35, 40]))]
        orb_high = orb_bars["high"].max() if len(orb_bars) >= 3 else 0.0
        orb_low  = orb_bars["low"].min() if len(orb_bars) >= 3 else 0.0
        orb_range = orb_high - orb_low

        print(f"🏛️ NY 15-Min ORB Range (13:30-13:45 UTC): High = {orb_high:.2f} | Low = {orb_low:.2f} | Range = {orb_range:.2f} pts")
        print("-" * 105)

        for i in range(len(yday_m5)):
            row = yday_m5.iloc[i]
            time_str = row["dt"].strftime("%H:%M UTC")
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]
            m5_9 = row["m5_ema9"]
            m15_9 = row["m15_ema9"]
            m30_9 = row["m30_ema9"]
            h1_9 = row["h1_ema9"]
            h1_21 = row["h1_ema21"]
            h1_50 = row["h1_ema50"]
            d1_9 = row["d1_ema9"]

            # Regimes
            is_cascade = (c < h1_9) and (h1_9 < h1_21) and (h1_21 < h1_50)
            is_bull_align = (c > m15_9) and (m15_9 > h1_9) and (c > d1_9)

            # --- SETUP A: Golden Pocket Short at H1 9-EMA or 30M 9-EMA Retest
            if is_cascade:
                touches_h1 = (h >= h1_9 - 2.5) and (h <= h1_21 + 2.5)
                touches_m30 = (h >= m30_9 - 2.5) and (h <= h1_9 + 2.5)
                upper_wick = h - max(o, c)
                c_range = h - l
                is_bear_rejection = (upper_wick / c_range >= 0.25) if c_range > 0.5 else (c < o)

                if (touches_h1 or touches_m30) and is_bear_rejection:
                    level_name = "H1 9-EMA" if touches_h1 else "30M 9-EMA"
                    sl = round(h + 1.5, 2)
                    risk = max(round(sl - c, 2), 3.5)
                    tp1 = round(c - (risk * 2.0), 2)
                    tp2 = round(c - (risk * 3.0), 2)
                    setups.append({
                        "time": time_str,
                        "type": "🔴 GOLDEN POCKET SHORT",
                        "level": level_name,
                        "entry": c,
                        "sl": sl,
                        "risk": risk,
                        "tp1": tp1,
                        "tp2": tp2,
                        "context": f"Price {c:.2f} < H1_9 {h1_9:.2f} < H1_21 {h1_21:.2f} < H1_50 {h1_50:.2f}"
                    })

            # --- SETUP B: Bullish Pullback Long (M15 9-EMA Bounce)
            elif is_bull_align:
                pullback_dip = (l <= m15_9 + 2.5) and (c >= m15_9)
                lower_wick = min(o, c) - l
                c_range = h - l
                is_bull_rejection = (lower_wick / c_range >= 0.25) if c_range > 0.5 else (c > o)

                if pullback_dip and is_bull_rejection:
                    sl = round(l - 1.5, 2)
                    risk = max(round(c - sl, 2), 3.5)
                    tp1 = round(c + (risk * 2.0), 2)
                    tp2 = round(c + (risk * 3.0), 2)
                    setups.append({
                        "time": time_str,
                        "type": "🟢 BULLISH PULLBACK LONG",
                        "level": "M15 9-EMA",
                        "entry": c,
                        "sl": sl,
                        "risk": risk,
                        "tp1": tp1,
                        "tp2": tp2,
                        "context": f"Price {c:.2f} > M15_9 {m15_9:.2f} > H1_9 {h1_9:.2f} (D1_9 {d1_9:.2f})"
                    })

            # --- SETUP C: NY 15-Min ORB Breakout (Post 13:45 UTC)
            if row["dt"].hour == 13 and row["dt"].minute == 45 and orb_range > 0:
                if c > orb_high:
                    sl = orb_low
                    risk = round(c - sl, 2)
                    setups.append({
                        "time": time_str,
                        "type": "⚡ NY ORB BULLISH BREAKOUT",
                        "level": "15-Min Range High",
                        "entry": c,
                        "sl": sl,
                        "risk": risk,
                        "tp1": round(c + orb_range * 1.5, 2),
                        "tp2": round(c + orb_range * 2.0, 2),
                        "context": f"Broke above ORB High {orb_high:.2f}"
                    })
                elif c < orb_low:
                    sl = orb_high
                    risk = round(sl - c, 2)
                    setups.append({
                        "time": time_str,
                        "type": "⚡ NY ORB BEARISH BREAKOUT",
                        "level": "15-Min Range Low",
                        "entry": c,
                        "sl": sl,
                        "risk": risk,
                        "tp1": round(c - orb_range * 1.5, 2),
                        "tp2": round(c - orb_range * 2.0, 2),
                        "context": f"Broke below ORB Low {orb_low:.2f}"
                    })

        # Print Chronological Setups Table
        print(f"{'Time (UTC)':<12} | {'Signal & Setup Type':<28} | {'Zone / EMA':<12} | {'Entry':<9} | {'Stop Loss':<9} | {'Risk':<7} | {'TP1 (1:2)':<9} | {'TP2 (1:3)':<9}")
        print("-" * 105)

        if not setups:
            print("  No clear setup met all strict multi-timeframe rejection criteria on 2026-08-20.")
        else:
            for s in setups:
                print(f"{s['time']:<12} | {s['type']:<28} | {s['level']:<12} | {s['entry']:<9.2f} | {s['sl']:<9.2f} | {s['risk']:<7.2f} | {s['tp1']:<9.2f} | {s['tp2']:<9.2f}")

        print("=" * 105 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    analyze_yesterday_market()
