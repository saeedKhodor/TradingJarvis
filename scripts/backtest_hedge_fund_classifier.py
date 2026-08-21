# === CODE INDEX ===
# 1. Imports & Setup (Line 18)
# 2. classify_and_execute_playbook() - Regime-dependent 5-point extraction (Line 38)
# 3. main() - Runs 100-day test (Line 150)
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


def classify_and_execute_playbook(df: pd.DataFrame) -> Dict[str, Any]:
    df["date"] = df["dt"].dt.date
    unique_dates = sorted(df["date"].unique())

    trades = []

    for d_idx in range(1, len(unique_dates)):
        curr_d = unique_dates[d_idx]
        prev_d = unique_dates[d_idx - 1]

        prev_df = df[df["date"] == prev_d]
        curr_df = df[df["date"] == curr_d].copy()

        if len(prev_df) < 50 or len(curr_df) < 50:
            continue

        pdh = prev_df["high"].max()
        pdl = prev_df["low"].min()
        pdc = prev_df.iloc[-1]["close"]

        # Pre-Market Data (00:00 to 13:25 UTC)
        pre_df = curr_df[curr_df["dt"].dt.hour < 13]
        open_bar = curr_df[curr_df["dt"].dt.hour >= 13].iloc[0]
        open_price = open_bar["open"]
        d1_9 = open_bar["d1_ema9"]
        h1_9 = open_bar["h1_ema9"]
        h1_21 = open_bar["h1_ema21"]
        h1_50 = open_bar["h1_ema50"]

        # ----------------------------------------------------
        # 1. PRE-MARKET REGIME CLASSIFICATION (09:25 AM EST)
        # ----------------------------------------------------
        regime = "BALANCED_RANGE"
        play_type = "NONE"

        # Regime A: Cascading Breakdown Day (Like Aug 20)
        is_cascade = (open_price < h1_9) and (h1_9 < h1_21) and (h1_21 < h1_50) and (open_price < d1_9)
        if is_cascade:
            regime = "BEARISH_CASCADE"
            play_type = "GOLDEN_POCKET_SHORT"

        # Regime B: Bullish Macro Day (Price > D1 9-EMA and above PDH)
        elif (open_price > d1_9) and (open_price > h1_9) and (h1_9 > h1_21):
            regime = "BULLISH_TREND"
            play_type = "NY_ORB_LONG"

        # Regime C: PDH/PDL Liquidity Trap
        else:
            regime = "RANGE_SWEEP"
            play_type = "PDH_PDL_SWEEP"

        # ----------------------------------------------------
        # 2. EXECUTION ACCORDING TO PLAYBOOK
        # ----------------------------------------------------
        # Execution Window: 13:30 to 16:30 UTC
        trade_window = curr_df[(curr_df["dt"].dt.hour >= 13) & (curr_df["dt"].dt.hour <= 16)]
        
        trade_executed = False

        for i in range(len(trade_window) - 12):
            bar = trade_window.iloc[i]
            hour = bar["dt"].hour
            minute = bar["dt"].minute
            o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]

            # PLAY 1: Golden Pocket Short on Cascade Day
            if play_type == "GOLDEN_POCKET_SHORT" and not trade_executed:
                if (h >= bar["h1_ema9"] - 2.5) and (c < o) and (c < bar["h1_ema9"]):
                    entry = c
                    sl = entry + 5.0
                    tp = entry - 5.0
                    pnl = -5.0
                    outcome = "LOSS"

                    for j in range(i + 1, min(i + 24, len(trade_window))):
                        fb = trade_window.iloc[j]
                        if fb["low"] <= tp:
                            outcome = "WIN"
                            pnl = +5.0
                            break
                        if fb["high"] >= sl:
                            outcome = "LOSS"
                            pnl = -5.0
                            break

                    trades.append({"date": str(curr_d), "regime": regime, "play": "Short Retest", "pnl": pnl, "outcome": outcome})
                    trade_executed = True
                    break

            # PLAY 2: NY Open Bullish Expansion on Bull Trend Day
            elif play_type == "BULLISH_TREND" and not trade_executed:
                # 15-min open high break at 13:45+
                if (hour == 13 and minute >= 45) or (hour == 14 and minute <= 30):
                    if c > bar["m15_ema9"] and c > o:
                        entry = c
                        sl = entry - 5.0
                        tp = entry + 5.0
                        pnl = -5.0
                        outcome = "LOSS"

                        for j in range(i + 1, min(i + 24, len(trade_window))):
                            fb = trade_window.iloc[j]
                            if fb["high"] >= tp:
                                outcome = "WIN"
                                pnl = +5.0
                                break
                            if fb["low"] <= sl:
                                outcome = "LOSS"
                                pnl = -5.0
                                break

                        trades.append({"date": str(curr_d), "regime": regime, "play": "Bull Expansion", "pnl": pnl, "outcome": outcome})
                        trade_executed = True
                        break

            # PLAY 3: PDH/PDL Sweep Reversal on Range Days
            elif play_type == "PDH_PDL_SWEEP" and not trade_executed:
                # Sweep PDH (Short)
                if h > pdh and c < pdh and (c < o):
                    entry = c
                    sl = entry + 5.0
                    tp = entry - 5.0
                    pnl = -5.0
                    outcome = "LOSS"
                    for j in range(i + 1, min(i + 24, len(trade_window))):
                        fb = trade_window.iloc[j]
                        if fb["low"] <= tp: outcome = "WIN"; pnl = +5.0; break
                        if fb["high"] >= sl: outcome = "LOSS"; pnl = -5.0; break
                    trades.append({"date": str(curr_d), "regime": regime, "play": "PDH Fade Short", "pnl": pnl, "outcome": outcome})
                    trade_executed = True
                    break
                # Sweep PDL (Long)
                elif l < pdl and c > pdl and (c > o):
                    entry = c
                    sl = entry - 5.0
                    tp = entry + 5.0
                    pnl = -5.0
                    outcome = "LOSS"
                    for j in range(i + 1, min(i + 24, len(trade_window))):
                        fb = trade_window.iloc[j]
                        if fb["high"] >= tp: outcome = "WIN"; pnl = +5.0; break
                        if fb["low"] <= sl: outcome = "LOSS"; pnl = -5.0; break
                    trades.append({"date": str(curr_d), "regime": regime, "play": "PDL Fade Long", "pnl": pnl, "outcome": outcome})
                    trade_executed = True
                    break

    total = len(trades)
    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    losses = total - wins
    win_rate = (wins / total) * 100 if total > 0 else 0
    total_pts = sum(t["pnl"] for t in trades)

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_pts": total_pts,
        "trades": trades
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

        h1 = pd.DataFrame(connector.get_rates("US500.cash", count=2500, timeframe="H1"))
        h1["dt"] = pd.to_datetime(h1["time"], unit="s", utc=True)
        h1.sort_values("dt", inplace=True)
        h1["h1_ema9"] = compute_ema(h1["close"], 9)
        h1["h1_ema21"] = compute_ema(h1["close"], 21)
        h1["h1_ema50"] = compute_ema(h1["close"], 50)

        d1 = pd.DataFrame(connector.get_rates("US500.cash", count=150, timeframe="D1"))
        d1["dt"] = pd.to_datetime(d1["time"], unit="s", utc=True)
        d1.sort_values("dt", inplace=True)
        d1["d1_ema9"] = compute_ema(d1["close"], 9)

        df = pd.merge_asof(m5, m15[["dt", "m15_ema9"]], on="dt", direction="backward")
        df = pd.merge_asof(df, h1[["dt", "h1_ema9", "h1_ema21", "h1_ema50"]], on="dt", direction="backward")
        df = pd.merge_asof(df, d1[["dt", "d1_ema9"]], on="dt", direction="backward")

        res = classify_and_execute_playbook(df)

        print("\n" + "=" * 95)
        print("      HEDGE FUND CLASSIFIER & 5-POINT PLAYBOOK BENCHMARK (100 DAYS)      ")
        print("=" * 95)
        print(f"Total Qualified Days Traded  : {res['total_trades']}")
        print(f"Winning Days (+5.0 pts)      : {res['wins']} (🟢 {res['win_rate']:.1f}%)")
        print(f"Losing Days (-5.0 pts)       : {res['losses']}")
        print(f"Net Accumulated Points       : {res['total_pts']:+.1f} Index Points")
        print("=" * 95 + "\n")

        print("\n" + "=" * 105)
        print(f"            CHRONOLOGICAL AUDIT OF LAST 15 CLASSIFIED 5-POINT TRADES            ")
        print("=" * 105)
        print(f"{'Date':<12} | {'Classified Regime':<20} | {'Executed Play':<18} | {'Outcome':<8} | {'PnL':<8}")
        print("-" * 105)
        for t in res["trades"][-15:]:
            out_sym = "🟢 WIN" if t["outcome"] == "WIN" else "🔴 LOSS"
            print(f"{t['date']:<12} | {t['regime']:<20} | {t['play']:<18} | {out_sym:<8} | {t['pnl']:+6.1f} pts")
        print("=" * 105 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
