# === CODE INDEX ===
# 1. Imports & Constants (Line 18)
# 2. compute_ema() - Exact MT5 EMA formula (Line 38)
# 3. simulate_exact_yesterday_model() - Tests Golden Pocket only on strict H1 Cascade + D1 Confluence days (Line 70)
# 4. print_yesterday_model_report() - Outputs detailed breakdown and trade log (Line 160)
# 5. main() - Entry point (Line 230)
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
logger = logging.getLogger("TradingJarvis.YesterdayExactModel")


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Computes exact MT5-equivalent EMA (alpha = 2/(period+1))."""
    return series.ewm(span=period, adjust=False).mean()


def simulate_exact_yesterday_model(
    df: pd.DataFrame,
    target_rr: float = 2.5,
    use_be: bool = True,
    be_trigger_r: float = 1.0,
    trail_sl: bool = False
) -> Dict[str, Any]:
    """
    Exact August 20th Model Rules:
    1. Daily Macro: Price < D1 9-EMA
    2. H1 Bearish Cascade: Price < H1 9-EMA < H1 21-EMA < H1 50-EMA
    3. M15 Trend: M15 Close < M15 9-EMA
    4. Pullback: High tests H1 9-EMA zone (High >= H1_9 - 2.5 and High <= H1_21 + 2.5)
    5. Rejection: Candle closes bearish (Close < Open) and Close < H1 9-EMA
    6. Stop Loss: High + 1.5 pts (Min risk = 3.5 pts)
    7. Exit: Target 2.5R (with Breakeven at 1.0R)
    """
    trades = []
    cooldown_bars = 4
    last_trade_idx = -100

    for i in range(20, len(df) - 36):
        bar = df.iloc[i]
        hour = bar["dt"].hour

        # Session filter: London & NY active hours (07:00 to 20:00 UTC)
        if not (7 <= hour <= 20):
            continue

        if (i - last_trade_idx) < cooldown_bars:
            continue

        o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
        m15_9 = bar["m15_ema9"]
        h1_9, h1_21, h1_50 = bar["h1_ema9"], bar["h1_ema21"], bar["h1_ema50"]
        d1_9 = bar["d1_ema9"]

        # 1. Daily Macro Filter (Exact Yesterday Condition)
        if c >= d1_9:
            continue

        # 2. Strict H1 Bearish Cascade (Exact Yesterday Condition)
        is_cascade = (c < h1_9) and (h1_9 < h1_21) and (h1_21 < h1_50)
        if not is_cascade:
            continue

        # 3. Pullback interaction with H1 9-EMA resistance
        touches_h1 = (h >= h1_9 - 2.5) and (h <= h1_21 + 2.5)
        if not touches_h1:
            continue

        # 4. Bearish Rejection (Candle closed bearish and below H1 9-EMA)
        if c >= h1_9 or c >= o:
            continue

        entry = c
        sl = round(h + 1.5, 2)
        risk = max(round(sl - entry, 2), 3.5)
        if risk > 25.0:
            continue

        tp = round(entry - (risk * target_rr), 2)
        be_trigger = round(entry - (risk * be_trigger_r), 2)

        be_active = False
        curr_sl = sl
        won = False

        for j in range(i + 1, min(i + 36, len(df))):
            f = df.iloc[j]

            # Breakeven check
            if use_be and f["low"] <= be_trigger:
                be_active = True
                curr_sl = round(entry - 0.5, 2)

            # Stop Loss check
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

            # Take Profit check
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

        last_trade_idx = i

    total = len(trades)
    if total == 0:
        return {"name": "Exact Yesterday Model", "total_trades": 0, "trades": []}

    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    losses = total - wins
    pnl_pts = sum(t["pnl_pts"] for t in trades)
    gains = sum(t["pnl_pts"] for t in trades if t["pnl_pts"] > 0)
    loss_sum = abs(sum(t["pnl_pts"] for t in trades if t["pnl_pts"] < 0))
    pf = gains / loss_sum if loss_sum > 0 else float("inf")
    avg_r = sum(t["pnl_r"] for t in trades) / total

    return {
        "name": f"Yesterday Exact Model (RR=1:{target_rr} | BE={use_be})",
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / total) * 100,
        "total_pnl_pts": pnl_pts,
        "profit_factor": pf,
        "avg_r": avg_r,
        "trades": trades
    }


def print_yesterday_model_report(results: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 95)
    print("      J.A.R.V.I.S. EXACT YESTERDAY CASCADE MODEL BENCHMARK (100 DAYS)      ")
    print("=" * 95)
    print(f"{'Configuration':<45} | {'Trades':<7} | {'Win Rate':<10} | {'Total Pts':<11} | {'Avg R':<7} | {'PF':<6}")
    print("-" * 95)

    for r in results:
        if r.get("total_trades", 0) == 0:
            continue
        w_str = f"{r['win_rate']:.1f}% ({r['wins']}/{r['total_trades']})"
        pts_str = f"{r['total_pnl_pts']:+.1f}"
        r_str = f"{r['avg_r']:+.2f}R"
        pf_str = f"{r['profit_factor']:.2f}" if r['profit_factor'] != float("inf") else "INF"
        print(f"{r['name']:<45} | {r['total_trades']:<7} | {w_str:<10} | {pts_str:<11} | {r_str:<7} | {pf_str:<6}")

    print("=" * 95 + "\n")


def print_all_trades_log(trades: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 105)
    print(f"            CHRONOLOGICAL TRADE LOG OF ALL EXECUTED TRADES ({len(trades)} SETUPS)            ")
    print("=" * 105)
    print(f"{'Date & Time (UTC)':<18} | {'Entry':<8} | {'Stop Loss':<9} | {'TP':<8} | {'Risk':<6} | {'Exit':<8} | {'Outcome':<8} | {'PnL Pts':<9} | {'Reason':<6}")
    print("-" * 105)

    for t in trades:
        out_sym = "🟢 WIN" if t["outcome"] == "WIN" else "🔴 LOSS"
        print(f"{t['date']:<18} | {t['entry']:<8.2f} | {t['sl']:<9.2f} | {t['tp']:<8.2f} | {t['risk']:<6.2f} | {t['exit']:<8.2f} | {out_sym:<8} | {t['pnl_pts']:+8.2f} | {t['reason']:<6}")

    print("=" * 105 + "\n")


def main():
    connector = MT5Connector()
    try:
        logger.info("Connecting to MT5 to run 100-day Yesterday Exact Model study...")
        if not connector.connect():
            return

        m5_rates = connector.get_rates("US500.cash", count=29000, timeframe="M5")
        df = pd.DataFrame(m5_rates)
        df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.sort_values("dt", inplace=True)
        df.reset_index(drop=True, inplace=True)

        m15_rates = connector.get_rates("US500.cash", count=10000, timeframe="M15")
        df_m15 = pd.DataFrame(m15_rates)
        df_m15["dt"] = pd.to_datetime(df_m15["time"], unit="s", utc=True)
        df_m15.sort_values("dt", inplace=True)
        df_m15["m15_ema9"] = compute_ema(df_m15["close"], 9)

        h1_rates = connector.get_rates("US500.cash", count=2500, timeframe="H1")
        df_h1 = pd.DataFrame(h1_rates)
        df_h1["dt"] = pd.to_datetime(df_h1["time"], unit="s", utc=True)
        df_h1.sort_values("dt", inplace=True)
        df_h1["h1_ema9"] = compute_ema(df_h1["close"], 9)
        df_h1["h1_ema21"] = compute_ema(df_h1["close"], 21)
        df_h1["h1_ema50"] = compute_ema(df_h1["close"], 50)

        d1_rates = connector.get_rates("US500.cash", count=150, timeframe="D1")
        df_d1 = pd.DataFrame(d1_rates)
        df_d1["dt"] = pd.to_datetime(df_d1["time"], unit="s", utc=True)
        df_d1.sort_values("dt", inplace=True)
        df_d1["d1_ema9"] = compute_ema(df_d1["close"], 9)

        df = pd.merge_asof(df, df_m15[["dt", "m15_ema9"]], on="dt", direction="backward")
        df = pd.merge_asof(df, df_h1[["dt", "h1_ema9", "h1_ema21", "h1_ema50"]], on="dt", direction="backward")
        df = pd.merge_asof(df, df_d1[["dt", "d1_ema9"]], on="dt", direction="backward")

        results = [
            simulate_exact_yesterday_model(df, target_rr=2.0, use_be=True),
            simulate_exact_yesterday_model(df, target_rr=2.5, use_be=True),
            simulate_exact_yesterday_model(df, target_rr=3.0, use_be=True),
            simulate_exact_yesterday_model(df, target_rr=2.5, use_be=False)
        ]

        print_yesterday_model_report(results)
        print_all_trades_log(results[1]["trades"])

    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
