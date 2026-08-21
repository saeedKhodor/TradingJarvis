# === CODE INDEX ===
# 1. Imports & Setup (Line 18)
# 2. simulate_impulse_cascade_shorts() - Evaluates Golden Pocket ONLY on energetic downward impulse cascades (Line 38)
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
logger = logging.getLogger("TradingJarvis.ImpulseCascade")


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"].shift(1)
    tr = pd.concat([high - low, (high - close).abs(), (low - close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0/period, min_periods=period, adjust=False).mean()


def simulate_impulse_cascade_shorts(
    df: pd.DataFrame,
    min_cascade_spread: float = 3.0,  # H1_21 - H1_9 >= 3.0 pts (Clear downward momentum, not flat chop)
    target_rr: float = 2.5
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

        # 1. Price < D1 9-EMA
        if c >= d1_9:
            continue

        # 2. Strict H1 Cascade with Downward Separation (H1_21 - H1_9 >= min_cascade_spread)
        is_cascade = (c < h1_9) and (h1_9 < h1_21) and (h1_21 < h1_50)
        spread_ok = (h1_21 - h1_9) >= min_cascade_spread
        if not (is_cascade and spread_ok):
            continue

        # 3. Pullback to H1 9-EMA
        touches_h1 = (h >= h1_9 - 2.5) and (h <= h1_21 + 2.5)
        if not touches_h1:
            continue

        # 4. Bearish Candle
        if c >= h1_9 or c >= o:
            continue

        entry = c
        sl = round(h + 1.5, 2)
        risk = max(round(sl - entry, 2), 3.5)
        if risk > 25.0:
            continue

        tp = round(entry - (risk * target_rr), 2)
        be_trigger = round(entry - risk, 2)

        be_active = False
        curr_sl = sl
        won = False

        for j in range(i + 1, min(i + 36, len(df))):
            f = df.iloc[j]

            if f["low"] <= be_trigger:
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
        return {"name": f"Spread>={min_cascade_spread}", "total_trades": 0}

    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    pnl_pts = sum(t["pnl_pts"] for t in trades)
    gains = sum(t["pnl_pts"] for t in trades if t["pnl_pts"] > 0)
    losses = abs(sum(t["pnl_pts"] for t in trades if t["pnl_pts"] < 0))
    pf = gains / losses if losses > 0 else float("inf")

    return {
        "name": f"H1 EMA Separation >= {min_cascade_spread} pts",
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

        d1 = pd.DataFrame(connector.get_rates("US500.cash", count=150, timeframe="D1"))
        d1["dt"] = pd.to_datetime(d1["time"], unit="s", utc=True)
        d1.sort_values("dt", inplace=True)
        d1["d1_ema9"] = compute_ema(d1["close"], 9)

        df = pd.merge_asof(m5, h1[["dt", "h1_ema9", "h1_ema21", "h1_ema50"]], on="dt", direction="backward")
        df = pd.merge_asof(df, d1[["dt", "d1_ema9"]], on="dt", direction="backward")

        results = [
            simulate_impulse_cascade_shorts(df, min_cascade_spread=0.0),
            simulate_impulse_cascade_shorts(df, min_cascade_spread=2.0),
            simulate_impulse_cascade_shorts(df, min_cascade_spread=4.0),
            simulate_impulse_cascade_shorts(df, min_cascade_spread=6.0),
            simulate_impulse_cascade_shorts(df, min_cascade_spread=8.0)
        ]

        print("\n" + "=" * 90)
        print("    J.A.R.V.I.S. MOMENTUM CASCADE SEPARATION STUDY (100 DAYS)    ")
        print("=" * 90)
        print(f"{'Separation Filter':<40} | {'Trades':<7} | {'Win Rate':<10} | {'Total Pts':<10} | {'PF':<6}")
        print("-" * 90)
        for r in results:
            w_str = f"{r['win_rate']:.1f}% ({r['wins']}/{r['total_trades']})"
            pts_str = f"{r['total_pnl_pts']:+.1f}"
            pf_str = f"{r['profit_factor']:.2f}" if r['profit_factor'] != float("inf") else "INF"
            print(f"{r['name']:<40} | {r['total_trades']:<7} | {w_str:<10} | {pts_str:<10} | {pf_str:<6}")
        print("=" * 90 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
