# === CODE INDEX ===
# 1. Imports & Setup (Line 18)
# 2. run_full_trade_audit() - Extracts all 16 trades (wins & losses) (Line 38)
# 3. main() - Entry point (Line 115)
# =================

import os
import sys
import logging
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.mt5_connector import MT5Connector
from scripts.backtest_golden_pocket_multiday import compute_ema
from scripts.backtest_sniper_cascade import simulate_true_sniper_cascade

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def run_full_trade_audit():
    connector = MT5Connector()
    if not connector.connect():
        return

    try:
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

        res = simulate_true_sniper_cascade(df, max_trades_per_cascade=1, target_rr=2.0, min_separation=6.0)
        trades = res["trades"]

        losses = [t for t in trades if t["outcome"] == "LOSS"]
        wins = [t for t in trades if t["outcome"] == "WIN"]

        print("\n" + "=" * 105)
        print(f"            COMPLETE LIST OF ALL LOSING DAYS & TRADES ({len(losses)} LOSSES)            ")
        print("=" * 105)
        print(f"{'Date & Time (UTC)':<18} | {'Entry':<9} | {'Stop Loss':<9} | {'Risk (Pts)':<10} | {'Exit Price':<10} | {'Loss (Pts)':<10} | {'Reason':<8}")
        print("-" * 105)
        for t in losses:
            print(f"{t['date']:<18} | {t['entry']:<9.2f} | {t['sl']:<9.2f} | {t['risk']:<10.2f} | {t['exit']:<10.2f} | {t['pnl_pts']:<10.2f} | {t['reason']:<8}")

        print("\n" + "=" * 105)
        print(f"            COMPLETE LIST OF ALL WINNING DAYS & TRADES ({len(wins)} WINS)            ")
        print("=" * 105)
        print(f"{'Date & Time (UTC)':<18} | {'Entry':<9} | {'Stop Loss':<9} | {'Risk (Pts)':<10} | {'Exit Price':<10} | {'Profit (Pts)':<12} | {'Reason':<8}")
        print("-" * 105)
        for t in wins:
            print(f"{t['date']:<18} | {t['entry']:<9.2f} | {t['sl']:<9.2f} | {t['risk']:<10.2f} | {t['exit']:<10.2f} | {t['pnl_pts']:<+12.2f} | {t['reason']:<8}")
        print("=" * 105 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    run_full_trade_audit()
