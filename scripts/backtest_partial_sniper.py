# === CODE INDEX ===
# 1. Imports & Setup (Line 18)
# 2. simulate_partial_tp_sniper() - Tests 50% Partial at 1.0R + Breakeven + 2.5R Runner (Line 38)
# 3. main() - Runs 100-day test (Line 135)
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


def simulate_partial_tp_sniper(
    df: pd.DataFrame,
    take_partial_at_1r: bool = True,
    runner_target_rr: float = 2.5
) -> Dict[str, Any]:
    trades = []
    in_cascade_episode = False
    cascade_trade_count = 0
    last_trade_idx = -100

    for i in range(20, len(df) - 36):
        bar = df.iloc[i]
        dt = bar["dt"]
        hour = dt.hour
        minute = dt.minute

        # Prime Sessions: London (07:00-11:00) & NY Core (13:30-17:00 UTC)
        is_london = (7 <= hour < 11)
        is_ny_core = (hour == 13 and minute >= 30) or (14 <= hour < 17)
        if not (is_london or is_ny_core):
            continue

        o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
        h1_9, h1_21, h1_50 = bar["h1_ema9"], bar["h1_ema21"], bar["h1_ema50"]
        d1_9 = bar["d1_ema9"]

        # H1 Cascade State Tracking
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
        if (h1_21 - h1_9) < 5.0:
            continue

        # Pullback Zone
        touches_h1 = (h >= h1_9 - 2.5) and (h <= h1_21 + 2.5)
        if not touches_h1:
            continue

        # Rejection
        c_range = h - l
        upper_wick = h - max(o, c)
        is_strong_rejection = (c_range >= 1.5) and ((upper_wick / c_range) >= 0.30) and (c < o) and (c < h1_9)
        if not is_strong_rejection:
            continue

        if (i - last_trade_idx) < 6:
            continue

        entry = c
        risk = max(round(h + 1.5 - entry, 2), 4.0)
        sl = round(entry + risk, 2)
        if risk > 25.0:
            continue

        tp_partial = round(entry - risk, 2)            # 1.0R Target
        tp_runner  = round(entry - (risk * runner_target_rr), 2)  # 2.5R Runner Target

        partial_taken = False
        be_active = False
        curr_sl = sl
        won = False
        total_pnl = 0.0

        for j in range(i + 1, min(i + 36, len(df))):
            f = df.iloc[j]

            # 1. Partial TP trigger at 1.0R
            if take_partial_at_1r and not partial_taken and f["low"] <= tp_partial:
                partial_taken = True
                be_active = True
                curr_sl = round(entry - 0.5, 2)  # Move SL to BE for runner

            # 2. SL hit
            if f["high"] >= curr_sl:
                if partial_taken:
                    # 50% booked at +1.0R, 50% closed at BE (+0.5 pts)
                    total_pnl = (0.5 * risk) + (0.5 * 0.5)
                    trades.append({"date": bar["dt"].strftime("%Y-%m-%d %H:%M"), "outcome": "WIN", "pnl_pts": total_pnl, "pnl_r": total_pnl / risk, "reason": "PARTIAL+BE"})
                else:
                    total_pnl = -risk
                    trades.append({"date": bar["dt"].strftime("%Y-%m-%d %H:%M"), "outcome": "LOSS", "pnl_pts": total_pnl, "pnl_r": -1.0, "reason": "SL"})
                won = True
                break

            # 3. Full Runner Target hit
            if f["low"] <= tp_runner:
                if partial_taken:
                    total_pnl = (0.5 * risk) + (0.5 * risk * runner_target_rr)
                else:
                    total_pnl = risk * runner_target_rr
                trades.append({"date": bar["dt"].strftime("%Y-%m-%d %H:%M"), "outcome": "WIN", "pnl_pts": total_pnl, "pnl_r": total_pnl / risk, "reason": "FULL_TP"})
                won = True
                break

        if not won:
            end_b = df.iloc[min(i + 35, len(df) - 1)]
            pnl_final = entry - end_b["close"]
            if partial_taken:
                total_pnl = (0.5 * risk) + (0.5 * pnl_final)
            else:
                total_pnl = pnl_final
            trades.append({"date": bar["dt"].strftime("%Y-%m-%d %H:%M"), "outcome": "WIN" if total_pnl > 0 else "LOSS", "pnl_pts": total_pnl, "pnl_r": total_pnl / risk, "reason": "EXPIRY"})

        cascade_trade_count += 1
        last_trade_idx = i

    total = len(trades)
    if total == 0:
        return {"total_trades": 0}

    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    losses = total - wins
    pnl_pts = sum(t["pnl_pts"] for t in trades)
    gains = sum(t["pnl_pts"] for t in trades if t["pnl_pts"] > 0)
    loss_sum = abs(sum(t["pnl_pts"] for t in trades if t["pnl_pts"] < 0))
    pf = gains / loss_sum if loss_sum > 0 else float("inf")

    return {
        "name": f"Partial Scaling (50% @ 1.0R + Runner @ {runner_target_rr}R)",
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / total) * 100,
        "total_pnl_pts": pnl_pts,
        "profit_factor": pf,
        "avg_r": sum(t["pnl_r"] for t in trades) / total,
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

        raw_sniper = simulate_partial_tp_sniper(df, take_partial_at_1r=False, runner_target_rr=2.0)
        scaled_sniper = simulate_partial_tp_sniper(df, take_partial_at_1r=True, runner_target_rr=2.5)

        print("\n" + "=" * 95)
        print("      J.A.R.V.I.S. SCALED PARTIAL SNIPER BENCHMARK (100 DAYS)      ")
        print("=" * 95)
        print(f"{'Strategy Configuration':<50} | {'Trades':<7} | {'Win Rate':<10} | {'Total Pts':<10} | {'PF':<6}")
        print("-" * 95)
        for r in [raw_sniper, scaled_sniper]:
            w_str = f"{r['win_rate']:.1f}% ({r['wins']}/{r['total_trades']})"
            pts_str = f"{r['total_pnl_pts']:+.1f}"
            pf_str = f"{r['profit_factor']:.2f}" if r['profit_factor'] != float("inf") else "INF"
            print(f"{r['name']:<50} | {r['total_trades']:<7} | {w_str:<10} | {pts_str:<10} | {pf_str:<6}")
        print("=" * 95 + "\n")

        print("\n" + "=" * 105)
        print("            CHRONOLOGICAL AUDIT OF ALL SCALED SNIPER TRADES (100 DAYS)            ")
        print("=" * 105)
        print(f"{'Date & Time (UTC)':<18} | {'Outcome':<8} | {'PnL (Pts)':<10} | {'PnL (R)':<8} | {'Resolution':<12}")
        print("-" * 105)
        for t in scaled_sniper["trades"]:
            out_sym = "🟢 WIN" if t["outcome"] == "WIN" else "🔴 LOSS"
            print(f"{t['date']:<18} | {out_sym:<8} | {t['pnl_pts']:<+10.2f} | {t['pnl_r']:<+8.2f}R | {t['reason']:<12}")
        print("=" * 105 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
