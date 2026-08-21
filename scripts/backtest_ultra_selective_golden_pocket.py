# === CODE INDEX ===
# 1. Imports & Setup (Line 18)
# 2. simulate_ultra_selective_golden_pocket() - Implements the 5 picky sniper filters (Line 38)
# 3. print_picky_report() - Outputs comparative benchmark and trade audit (Line 140)
# 4. main() - Entry point (Line 195)
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
logger = logging.getLogger("TradingJarvis.UltraSelective")


def simulate_ultra_selective_golden_pocket(
    df: pd.DataFrame,
    allowed_sessions: str = "PRIME_ONLY",  # London (07:00-11:00) & NY Open (13:30-17:00 UTC)
    min_wick_ratio: float = 0.35,
    min_risk_floor: float = 5.0,
    target_rr: float = 2.0
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

        # FILTER 1 & 2: Ultra-Strict Prime Session Windows
        # Allowed: London Morning (07:00 to 11:00 UTC) OR NY Core Open (13:30 to 17:00 UTC)
        # Blocked: Pre-Market (11:30 to 13:30) and Late NY Close (> 17:00 UTC)
        if allowed_sessions == "PRIME_ONLY":
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

        # FILTER 3: Strictly 1 Trade per Cascade Episode
        if cascade_trade_count >= 1:
            continue

        # FILTER 4: Daily Macro Confluence (Price < Daily 9-EMA)
        if c >= d1_9:
            continue

        # FILTER 5: Downward Separation (H1_21 - H1_9 >= 5.0 pts)
        if (h1_21 - h1_9) < 5.0:
            continue

        # Pullback Zone (High touches H1 9-EMA ceiling)
        touches_h1 = (h >= h1_9 - 2.5) and (h <= h1_21 + 2.5)
        if not touches_h1:
            continue

        # FILTER 6: Strict Bearish Rejection Pinbar (Upper wick >= min_wick_ratio and Close < Open)
        c_range = h - l
        upper_wick = h - max(o, c)
        is_strong_rejection = (c_range >= 1.5) and ((upper_wick / c_range) >= min_wick_ratio) and (c < o) and (c < h1_9)
        if not is_strong_rejection:
            continue

        if (i - last_trade_idx) < 6:
            continue

        entry = c
        # FILTER 7: Realistic Stop Loss Floor (Min 5.0 pts)
        raw_sl = h + 1.5
        risk = max(round(raw_sl - entry, 2), min_risk_floor)
        sl = round(entry + risk, 2)
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
        return {"name": "Picky Sniper Model", "total_trades": 0, "trades": []}

    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    losses = total - wins
    pnl_pts = sum(t["pnl_pts"] for t in trades)
    gains = sum(t["pnl_pts"] for t in trades if t["pnl_pts"] > 0)
    loss_sum = abs(sum(t["pnl_pts"] for t in trades if t["pnl_pts"] < 0))
    pf = gains / loss_sum if loss_sum > 0 else float("inf")
    avg_r = sum(t["pnl_r"] for t in trades) / total

    return {
        "name": f"Picky Sniper (RR=1:{target_rr} | Wick>={int(min_wick_ratio*100)}% | RiskFloor>={min_risk_floor}pts)",
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / total) * 100,
        "total_pnl_pts": pnl_pts,
        "profit_factor": pf,
        "avg_r": avg_r,
        "trades": trades
    }


def print_picky_report(results: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 95)
    print("      J.A.R.V.I.S. ULTRA-SELECTIVE PICKY SNIPER BENCHMARK (100 DAYS)      ")
    print("=" * 95)
    print(f"{'Strategy Configuration':<50} | {'Trades':<7} | {'Win Rate':<10} | {'Total Pts':<10} | {'PF':<6}")
    print("-" * 95)
    for r in results:
        if r.get("total_trades", 0) == 0:
            continue
        w_str = f"{r['win_rate']:.1f}% ({r['wins']}/{r['total_trades']})"
        pts_str = f"{r['total_pnl_pts']:+.1f}"
        pf_str = f"{r['profit_factor']:.2f}" if r['profit_factor'] != float("inf") else "INF"
        print(f"{r['name']:<50} | {r['total_trades']:<7} | {w_str:<10} | {pts_str:<10} | {pf_str:<6}")
    print("=" * 95 + "\n")


def print_trade_audit_table(trades: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 105)
    print(f"            CHRONOLOGICAL AUDIT OF ALL PICKY SNIPER TRADES ({len(trades)} TOTAL)            ")
    print("=" * 105)
    print(f"{'Date & Time (UTC)':<18} | {'Entry':<8} | {'SL':<8} | {'TP':<8} | {'Risk':<6} | {'Exit':<8} | {'Outcome':<8} | {'PnL Pts':<9} | {'Reason':<6}")
    print("-" * 105)
    for t in trades:
        out_sym = "🟢 WIN" if t["outcome"] == "WIN" else "🔴 LOSS"
        print(f"{t['date']:<18} | {t['entry']:<8.2f} | {t['sl']:<8.2f} | {t['tp']:<8.2f} | {t['risk']:<6.2f} | {t['exit']:<8.2f} | {out_sym:<8} | {t['pnl_pts']:+8.2f} | {t['reason']:<6}")
    print("=" * 105 + "\n")


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
            simulate_ultra_selective_golden_pocket(df, min_wick_ratio=0.30, min_risk_floor=4.0, target_rr=2.0),
            simulate_ultra_selective_golden_pocket(df, min_wick_ratio=0.35, min_risk_floor=5.0, target_rr=2.0),
            simulate_ultra_selective_golden_pocket(df, min_wick_ratio=0.35, min_risk_floor=5.0, target_rr=2.5),
            simulate_ultra_selective_golden_pocket(df, min_wick_ratio=0.40, min_risk_floor=5.0, target_rr=2.0)
        ]

        print_picky_report(results)
        print_trade_audit_table(results[1]["trades"])

    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
