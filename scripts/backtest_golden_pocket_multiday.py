# === CODE INDEX ===
# 1. Imports & Constants (Line 18)
# 2. compute_emas() - Computes MT5-identical EMAs for M5, M15, M30, H1, D1 (Line 38)
# 3. simulate_golden_pocket_trades() - Evaluates Golden Pocket Short entries during cascades (Line 75)
# 4. print_golden_pocket_summary() - Outputs comprehensive statistical tables and trade log (Line 165)
# 5. main() - Entry point (Line 240)
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
logger = logging.getLogger("TradingJarvis.GoldenPocketStudy")


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Computes exact MT5-equivalent EMA (alpha = 2/(period+1))."""
    return series.ewm(span=period, adjust=False).mean()


def simulate_golden_pocket_trades(
    df: pd.DataFrame,
    target_rr: float = 2.5,
    use_breakeven: bool = True,
    level_filter: str = "ALL"  # "ALL", "H1_ONLY", "M30_ONLY"
) -> Dict[str, Any]:
    trades = []
    cooldown_bars = 4  # 20 minutes cooldown between consecutive entries
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
        h1_9, h1_21, h1_50 = bar["h1_ema9"], bar["h1_ema21"], bar["h1_ema50"]
        m30_9 = bar["m30_ema9"]

        # 1. Strict H1 Bearish Cascade Condition
        is_cascade = (c < h1_9) and (h1_9 < h1_21) and (h1_21 < h1_50)
        if not is_cascade:
            continue

        # 2. Golden Pocket Retest
        touches_h1 = (h >= h1_9 - 2.5) and (h <= h1_21 + 2.5)
        touches_m30 = (h >= m30_9 - 2.5) and (h <= h1_9 + 2.5)

        if level_filter == "H1_ONLY" and not touches_h1:
            continue
        if level_filter == "M30_ONLY" and not touches_m30:
            continue
        if not (touches_h1 or touches_m30):
            continue

        # 3. Bearish Rejection Confirmation
        c_range = h - l
        upper_wick = h - max(o, c)
        is_rejection = (upper_wick / c_range >= 0.25) if c_range > 0.5 else (c < o)
        if not (is_rejection or c < o):
            continue

        # Trade Parameters
        entry = c
        sl = round(h + 1.5, 2)
        risk = max(round(sl - entry, 2), 3.5)
        if risk > 25.0:  # Skip distorted wild spikes
            continue

        tp = round(entry - (risk * target_rr), 2)
        be_trigger = round(entry - risk, 2)

        be_active = False
        curr_sl = sl
        won = False
        exit_price = entry
        exit_reason = "TIMEOUT"

        # Forward simulate up to 36 bars (3 hours max hold)
        for j in range(i + 1, min(i + 36, len(df))):
            f = df.iloc[j]

            # Check Breakeven Trigger
            if use_breakeven and f["low"] <= be_trigger:
                be_active = True
                curr_sl = round(entry - 0.5, 2)  # Lock 0.5 pt profit

            # Check Stop Loss
            if f["high"] >= curr_sl:
                exit_price = curr_sl
                exit_reason = "BE" if be_active else "SL"
                pnl = entry - exit_price
                trades.append({
                    "date": bar["dt"].strftime("%Y-%m-%d %H:%M"),
                    "level": "H1 9-EMA" if touches_h1 else "30M 9-EMA",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "risk": risk,
                    "exit": exit_price,
                    "pnl_pts": pnl,
                    "pnl_r": pnl / risk,
                    "outcome": "WIN" if pnl > 0 else "LOSS",
                    "reason": exit_reason
                })
                won = True
                break

            # Check Take Profit
            if f["low"] <= tp:
                exit_price = tp
                exit_reason = "TP"
                pnl = risk * target_rr
                trades.append({
                    "date": bar["dt"].strftime("%Y-%m-%d %H:%M"),
                    "level": "H1 9-EMA" if touches_h1 else "30M 9-EMA",
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "risk": risk,
                    "exit": exit_price,
                    "pnl_pts": pnl,
                    "pnl_r": target_rr,
                    "outcome": "WIN",
                    "reason": exit_reason
                })
                won = True
                break

        if not won:
            end_b = df.iloc[min(i + 35, len(df) - 1)]
            pnl = entry - end_b["close"]
            trades.append({
                "date": bar["dt"].strftime("%Y-%m-%d %H:%M"),
                "level": "H1 9-EMA" if touches_h1 else "30M 9-EMA",
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
        return {"total_trades": 0, "trades": []}

    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    losses = total - wins
    pnl_pts = sum(t["pnl_pts"] for t in trades)
    gains = sum(t["pnl_pts"] for t in trades if t["pnl_pts"] > 0)
    loss_sum = abs(sum(t["pnl_pts"] for t in trades if t["pnl_pts"] < 0))
    pf = gains / loss_sum if loss_sum > 0 else float("inf")
    avg_r = sum(t["pnl_r"] for t in trades) / total

    return {
        "name": f"Golden Pocket (RR=1:{target_rr} | BE={use_breakeven} | {level_filter})",
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / total) * 100,
        "total_pnl_pts": pnl_pts,
        "profit_factor": pf,
        "avg_r": avg_r,
        "trades": trades
    }


def print_golden_pocket_summary(results: List[Dict[str, Any]]) -> None:
    print("\n" + "=" * 95)
    print("      J.A.R.V.I.S. GOLDEN POCKET SHORT MULTI-DAY QUANTITATIVE STUDY       ")
    print("=" * 95)
    print(f"{'Strategy Variant':<45} | {'Trades':<7} | {'Win Rate':<10} | {'Total Pts':<11} | {'Avg R':<7} | {'PF':<6}")
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


def print_recent_trades_log(trades: List[Dict[str, Any]], count: int = 15) -> None:
    print("\n" + "=" * 105)
    print(f"            RECENT GOLDEN POCKET SHORT TRADES AUDIT (LAST {count} SETUPS)            ")
    print("=" * 105)
    print(f"{'Date & Time (UTC)':<18} | {'Zone':<11} | {'Entry':<8} | {'SL':<8} | {'TP':<8} | {'Risk':<6} | {'Exit':<8} | {'Outcome':<8} | {'PnL Pts':<8} | {'Reason':<6}")
    print("-" * 105)

    recent = trades[-count:] if len(trades) >= count else trades
    for t in recent:
        out_sym = "🟢 WIN" if t["outcome"] == "WIN" else "🔴 LOSS"
        print(f"{t['date']:<18} | {t['level']:<11} | {t['entry']:<8.2f} | {t['sl']:<8.2f} | {t['tp']:<8.2f} | {t['risk']:<6.2f} | {t['exit']:<8.2f} | {out_sym:<8} | {t['pnl_pts']:+7.2f} | {t['reason']:<6}")

    print("=" * 105 + "\n")


def main():
    connector = MT5Connector()
    try:
        logger.info("Connecting to MT5 to extract multi-timeframe bars for Golden Pocket study...")
        if not connector.connect():
            return

        # 1. Pull M5 Data (29,000 bars = ~100 trading days)
        m5_rates = connector.get_rates("US500.cash", count=29000, timeframe="M5")
        df = pd.DataFrame(m5_rates)
        df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.sort_values("dt", inplace=True)
        df.reset_index(drop=True, inplace=True)

        # 2. Pull M30 Data
        m30_rates = connector.get_rates("US500.cash", count=5000, timeframe="M30")
        df_m30 = pd.DataFrame(m30_rates)
        df_m30["dt"] = pd.to_datetime(df_m30["time"], unit="s", utc=True)
        df_m30.sort_values("dt", inplace=True)
        df_m30["m30_ema9"] = compute_ema(df_m30["close"], 9)

        # 3. Pull H1 Data
        h1_rates = connector.get_rates("US500.cash", count=2500, timeframe="H1")
        df_h1 = pd.DataFrame(h1_rates)
        df_h1["dt"] = pd.to_datetime(df_h1["time"], unit="s", utc=True)
        df_h1.sort_values("dt", inplace=True)
        df_h1["h1_ema9"] = compute_ema(df_h1["close"], 9)
        df_h1["h1_ema21"] = compute_ema(df_h1["close"], 21)
        df_h1["h1_ema50"] = compute_ema(df_h1["close"], 50)

        # Merge HTF EMAs
        df = pd.merge_asof(df, df_m30[["dt", "m30_ema9"]], on="dt", direction="backward")
        df = pd.merge_asof(df, df_h1[["dt", "h1_ema9", "h1_ema21", "h1_ema50"]], on="dt", direction="backward")

        results = [
            simulate_golden_pocket_trades(df, target_rr=2.0, use_breakeven=True, level_filter="ALL"),
            simulate_golden_pocket_trades(df, target_rr=2.5, use_breakeven=True, level_filter="ALL"),
            simulate_golden_pocket_trades(df, target_rr=3.0, use_breakeven=True, level_filter="ALL"),
            simulate_golden_pocket_trades(df, target_rr=2.5, use_breakeven=False, level_filter="ALL"),
            simulate_golden_pocket_trades(df, target_rr=2.5, use_breakeven=True, level_filter="H1_ONLY"),
            simulate_golden_pocket_trades(df, target_rr=2.5, use_breakeven=True, level_filter="M30_ONLY")
        ]

        print_golden_pocket_summary(results)

        # Print trade audit of the best variant (H1_ONLY / 2.5R)
        best_res = results[4]  # H1_ONLY
        print_recent_trades_log(best_res["trades"], count=15)

    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
