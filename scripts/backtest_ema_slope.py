# === CODE INDEX ===
# 1. Imports & Setup (Line 18)
# 2. test_ema_slope_impact() - Tests win rate and PF across H1 9-EMA & M15 9-EMA slopes (Line 38)
# 3. main() - Runs 100-day MT5 test (Line 120)
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


def test_ema_slope_impact(df: pd.DataFrame, min_h1_slope: float = 0.0) -> Dict[str, Any]:
    """
    Evaluates Golden Pocket Short entries conditioned on H1 9-EMA slope over the last 3 hours:
    H1_Slope = H1_EMA9[t] - H1_EMA9[t-3] (negative means downward sloping).
    """
    trades = []
    in_cascade_episode = False
    cascade_trade_count = 0
    last_trade_idx = -100

    for i in range(20, len(df) - 36):
        bar = df.iloc[i]
        dt = bar["dt"]
        hour = dt.hour
        minute = dt.minute

        # Prime sessions
        is_london = (7 <= hour < 11)
        is_ny_core = (hour == 13 and minute >= 30) or (14 <= hour < 17)
        if not (is_london or is_ny_core):
            continue

        o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
        h1_9, h1_21, h1_50 = bar["h1_ema9"], bar["h1_ema21"], bar["h1_ema50"]
        d1_9 = bar["d1_ema9"]
        h1_slope = bar["h1_slope_3"]  # Slope over 3 bars

        h1_cascade_order = (h1_9 < h1_21) and (h1_21 < h1_50)
        if h1_cascade_order and not in_cascade_episode:
            in_cascade_episode = True
            cascade_trade_count = 0
        elif not h1_cascade_order and in_cascade_episode:
            in_cascade_episode = False
            cascade_trade_count = 0

        if not in_cascade_episode:
            continue
        if cascade_trade_count >= 1:
            continue
        if c >= d1_9:
            continue

        # SLOPE FILTER: Must be sloping downward at least min_h1_slope points over 3 bars
        if h1_slope > -min_h1_slope:
            continue

        # Pullback Zone
        touches_h1 = (h >= h1_9 - 2.5) and (h <= h1_21 + 2.5)
        if not touches_h1:
            continue

        # Rejection
        c_range = h - l
        upper_wick = h - max(o, c)
        if not ((c_range >= 1.5) and ((upper_wick / c_range) >= 0.25) and (c < o) and (c < h1_9)):
            continue

        if (i - last_trade_idx) < 6:
            continue

        entry = c
        risk = max(round(h + 1.5 - entry, 2), 4.0)
        sl = round(entry + risk, 2)
        if risk > 25.0:
            continue

        tp = round(entry - (risk * 2.0), 2)
        be_trigger = round(entry - risk, 2)

        be_active = False
        curr_sl = sl
        won = False

        for j in range(i + 1, min(i + 36, len(df))):
            f = df.iloc[j]

            # Partial TP at 1.0R
            if not be_active and f["low"] <= be_trigger:
                be_active = True
                curr_sl = round(entry - 0.5, 2)

            if f["high"] >= curr_sl:
                if be_active:
                    total_pnl = (0.5 * risk) + (0.5 * 0.5)
                    trades.append({"outcome": "WIN", "pnl_pts": total_pnl, "pnl_r": total_pnl / risk, "slope": h1_slope})
                else:
                    total_pnl = -risk
                    trades.append({"outcome": "LOSS", "pnl_pts": total_pnl, "pnl_r": -1.0, "slope": h1_slope})
                won = True
                break

            if f["low"] <= tp:
                total_pnl = risk * 2.0
                trades.append({"outcome": "WIN", "pnl_pts": total_pnl, "pnl_r": 2.0, "slope": h1_slope})
                won = True
                break

        if not won:
            end_b = df.iloc[min(i + 35, len(df) - 1)]
            pnl_final = entry - end_b["close"]
            trades.append({"outcome": "WIN" if pnl_final > 0 else "LOSS", "pnl_pts": pnl_final, "pnl_r": pnl_final / risk, "slope": h1_slope})

        cascade_trade_count += 1
        last_trade_idx = i

    total = len(trades)
    if total == 0:
        return {"name": f"H1 Slope <= -{min_h1_slope} pts", "total_trades": 0}

    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    losses = total - wins
    pnl_pts = sum(t["pnl_pts"] for t in trades)
    gains = sum(t["pnl_pts"] for t in trades if t["pnl_pts"] > 0)
    loss_sum = abs(sum(t["pnl_pts"] for t in trades if t["pnl_pts"] < 0))
    pf = gains / loss_sum if loss_sum > 0 else float("inf")

    return {
        "name": f"H1 9-EMA Downward Slope <= -{min_h1_slope:.1f} pts/3-bars",
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / total) * 100,
        "total_pnl_pts": pnl_pts,
        "profit_factor": pf,
        "avg_r": sum(t["pnl_r"] for t in trades) / total
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

        h1 = pd.DataFrame(connector.get_rates("US500.cash", count=2500, timeframe="H1"))
        h1["dt"] = pd.to_datetime(h1["time"], unit="s", utc=True)
        h1.sort_values("dt", inplace=True)
        h1["h1_ema9"] = compute_ema(h1["close"], 9)
        h1["h1_ema21"] = compute_ema(h1["close"], 21)
        h1["h1_ema50"] = compute_ema(h1["close"], 50)
        h1["h1_slope_3"] = h1["h1_ema9"] - h1["h1_ema9"].shift(3)  # Rate of change over 3 hours

        d1 = pd.DataFrame(connector.get_rates("US500.cash", count=150, timeframe="D1"))
        d1["dt"] = pd.to_datetime(d1["time"], unit="s", utc=True)
        d1.sort_values("dt", inplace=True)
        d1["d1_ema9"] = compute_ema(d1["close"], 9)

        df = pd.merge_asof(m5, h1[["dt", "h1_ema9", "h1_ema21", "h1_ema50", "h1_slope_3"]], on="dt", direction="backward")
        df = pd.merge_asof(df, d1[["dt", "d1_ema9"]], on="dt", direction="backward")

        results = [
            test_ema_slope_impact(df, min_h1_slope=0.0),   # Any downward slope
            test_ema_slope_impact(df, min_h1_slope=2.0),   # Slope <= -2.0 pts
            test_ema_slope_impact(df, min_h1_slope=4.0),   # Slope <= -4.0 pts
            test_ema_slope_impact(df, min_h1_slope=6.0)    # Steep Slope <= -6.0 pts
        ]

        print("\n" + "=" * 95)
        print("      J.A.R.V.I.S. EMA SLOPE (VELOCITY) IMPACT STUDY (100 DAYS)      ")
        print("=" * 95)
        print(f"{'Slope Requirement':<45} | {'Trades':<7} | {'Win Rate':<10} | {'Total Pts':<10} | {'PF':<6}")
        print("-" * 95)
        for r in results:
            w_str = f"{r['win_rate']:.1f}% ({r['wins']}/{r['total_trades']})"
            pts_str = f"{r['total_pnl_pts']:+.1f}"
            pf_str = f"{r['profit_factor']:.2f}" if r['profit_factor'] != float("inf") else "INF"
            print(f"{r['name']:<45} | {r['total_trades']:<7} | {w_str:<10} | {pts_str:<10} | {pf_str:<6}")
        print("=" * 95 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
