# === CODE INDEX ===
# 1. Imports & Setup (Line 18)
# 2. simulate_true_sniper_cascade() - Strict episode state machine based on H1 EMA order (Line 38)
# 3. main() - Runs 100-day test (Line 140)
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
logger = logging.getLogger("TradingJarvis.TrueSniper")


def simulate_true_sniper_cascade(
    df: pd.DataFrame,
    max_trades_per_cascade: int = 1,
    target_rr: float = 2.0,
    min_separation: float = 4.0
) -> Dict[str, Any]:
    trades = []
    
    # State tracking across H1 EMA cascade episodes
    in_cascade_episode = False
    cascade_trade_count = 0
    last_trade_idx = -100

    for i in range(20, len(df) - 36):
        bar = df.iloc[i]
        hour = bar["dt"].hour

        if not (7 <= hour <= 20):
            continue

        o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
        h1_9, h1_21, h1_50 = bar["h1_ema9"], bar["h1_ema21"], bar["h1_ema50"]
        d1_9 = bar["d1_ema9"]

        # H1 EMA Cascade hierarchy (persists for hours)
        h1_cascade_order = (h1_9 < h1_21) and (h1_21 < h1_50)

        # Transition into a brand new cascade episode
        if h1_cascade_order and not in_cascade_episode:
            in_cascade_episode = True
            cascade_trade_count = 0

        # Cascade officially breaks when H1 9 crosses above 21
        elif not h1_cascade_order and in_cascade_episode:
            in_cascade_episode = False
            cascade_trade_count = 0

        if not in_cascade_episode:
            continue

        # Strict limit: Max 1 or 2 trades for this ENTIRE cascade episode
        if cascade_trade_count >= max_trades_per_cascade:
            continue

        # Daily Macro Confluence (Price < Daily 9-EMA)
        if c >= d1_9:
            continue

        # Separation filter (Avoid flat compression)
        if (h1_21 - h1_9) < min_separation:
            continue

        # Price pulling back into H1 9-EMA resistance
        touches_h1 = (h >= h1_9 - 2.5) and (h <= h1_21 + 2.5)
        if not touches_h1:
            continue

        # Bearish Rejection Confirmation
        if c >= h1_9 or c >= o:
            continue

        if (i - last_trade_idx) < 6:
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
                trades.append({
                    "date": bar["dt"].strftime("%Y-%m-%d %H:%M"),
                    "trade_num": cascade_trade_count + 1,
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "risk": risk,
                    "exit": exit_p,
                    "pnl_pts": pnl,
                    "pnl_r": pnl / risk,
                    "outcome": "WIN" if pnl > 0 else "LOSS",
                    "reason": "BE" if be_active else "SL"
                })
                won = True
                break

            if f["low"] <= tp:
                pnl = risk * target_rr
                trades.append({
                    "date": bar["dt"].strftime("%Y-%m-%d %H:%M"),
                    "trade_num": cascade_trade_count + 1,
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "risk": risk,
                    "exit": tp,
                    "pnl_pts": pnl,
                    "pnl_r": target_rr,
                    "outcome": "WIN",
                    "reason": "TP"
                })
                won = True
                break

        if not won:
            end_b = df.iloc[min(i + 35, len(df) - 1)]
            pnl = entry - end_b["close"]
            trades.append({
                "date": bar["dt"].strftime("%Y-%m-%d %H:%M"),
                "trade_num": cascade_trade_count + 1,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "risk": risk,
                "exit": end_b["close"],
                "pnl_pts": pnl,
                "pnl_r": pnl / risk,
                "outcome": "WIN" if pnl > 0 else "LOSS",
                "reason": "EXPIRY"
            })

        cascade_trade_count += 1
        last_trade_idx = i

    total = len(trades)
    if total == 0:
        return {"name": f"Max {max_trades_per_cascade} Trade/Cascade", "total_trades": 0, "trades": []}

    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    losses = total - wins
    pnl_pts = sum(t["pnl_pts"] for t in trades)
    gains = sum(t["pnl_pts"] for t in trades if t["pnl_pts"] > 0)
    loss_sum = abs(sum(t["pnl_pts"] for t in trades if t["pnl_pts"] < 0))
    pf = gains / loss_sum if loss_sum > 0 else float("inf")
    avg_r = sum(t["pnl_r"] for t in trades) / total

    return {
        "name": f"Sniper: Max {max_trades_per_cascade} Trade/Cascade (RR=1:{target_rr} | Sep>={min_separation})",
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / total) * 100,
        "total_pnl_pts": pnl_pts,
        "profit_factor": pf,
        "avg_r": avg_r,
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
            simulate_true_sniper_cascade(df, max_trades_per_cascade=1, target_rr=1.5, min_separation=4.0),
            simulate_true_sniper_cascade(df, max_trades_per_cascade=1, target_rr=2.0, min_separation=4.0),
            simulate_true_sniper_cascade(df, max_trades_per_cascade=2, target_rr=2.0, min_separation=4.0),
            simulate_true_sniper_cascade(df, max_trades_per_cascade=1, target_rr=2.0, min_separation=6.0),
            simulate_true_sniper_cascade(df, max_trades_per_cascade=2, target_rr=2.0, min_separation=6.0)
        ]

        print("\n" + "=" * 95)
        print("      J.A.R.V.I.S. TRUE SNIPER STUDY: 1-2 TRADES PER CASCADE EPISODE (100 DAYS)      ")
        print("=" * 95)
        print(f"{'Strategy Policy':<50} | {'Trades':<7} | {'Win Rate':<10} | {'Total Pts':<10} | {'PF':<6}")
        print("-" * 95)
        for r in results:
            w_str = f"{r['win_rate']:.1f}% ({r['wins']}/{r['total_trades']})"
            pts_str = f"{r['total_pnl_pts']:+.1f}"
            pf_str = f"{r['profit_factor']:.2f}" if r['profit_factor'] != float("inf") else "INF"
            print(f"{r['name']:<50} | {r['total_trades']:<7} | {w_str:<10} | {pts_str:<10} | {pf_str:<6}")
        print("=" * 95 + "\n")

        # Print trade log
        print("\n" + "=" * 105)
        print(f"            CHRONOLOGICAL LOG OF THE 1-TRADE-PER-CASCADE POLICY (LAST 15 EPISODES)            ")
        print("=" * 105)
        print(f"{'Date & Time (UTC)':<18} | {'Entry':<8} | {'SL':<8} | {'TP':<8} | {'Risk':<6} | {'Exit':<8} | {'Outcome':<8} | {'PnL Pts':<9} | {'Reason':<6}")
        print("-" * 105)
        trades_to_show = results[1]["trades"]
        for t in trades_to_show[-15:]:
            out_sym = "🟢 WIN" if t["outcome"] == "WIN" else "🔴 LOSS"
            print(f"{t['date']:<18} | {t['entry']:<8.2f} | {t['sl']:<8.2f} | {t['tp']:<8.2f} | {t['risk']:<6.2f} | {t['exit']:<8.2f} | {out_sym:<8} | {t['pnl_pts']:+8.2f} | {t['reason']:<6}")
        print("=" * 105 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
