# === CODE INDEX ===
# 1. Imports & Setup (Line 18)
# 2. test_rsi_trend_sniper() - High-probability oversold dip buying in HTF trends (Line 42)
# 3. test_orb_15min_breakout() - NY Open (13:30 UTC / 09:30 EST) Opening Range Breakout (Line 115)
# 4. test_bollinger_squeeze_breakout() - Volatility expansion after compression (Line 175)
# 5. print_advanced_report() - Comparative performance summary table (Line 230)
# 6. main() - Entry point (Line 275)
# =================

import os
import sys
import logging
from typing import Dict, List, Any

import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.mt5_connector import MT5Connector
from scripts.backtest_trend_alignment import calculate_ema
from scripts.backtest_vwap_mean_reversion import calculate_rsi

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TradingJarvis.AdvancedModels")


def test_rsi_trend_sniper(df: pd.DataFrame, rsi_thresh: float = 35.0, tp_rr: float = 1.5) -> Dict[str, Any]:
    """
    RSI Trend Sniper:
    - Long: Price > H1_EMA50 (and Price > D1_EMA9) + M5 RSI(14) <= rsi_thresh + Bullish candle close
    - Exit: Target 1.5R with Stop Loss moved to Breakeven at +1.0R
    """
    trades = []
    last_idx = -100

    for i in range(20, len(df) - 30):
        bar = df.iloc[i]
        hour = bar["dt"].hour

        if not (8 <= hour <= 20):
            continue
        if (i - last_idx) < 6:
            continue

        is_uptrend = (bar["close"] > bar["h1_ema50"]) and (bar["close"] > bar["d1_ema9"])
        is_oversold = bar["rsi14"] <= rsi_thresh and (bar["close"] > bar["open"])

        if is_uptrend and is_oversold:
            entry = bar["close"]
            sl = bar["low"] - 2.5
            risk = entry - sl
            if risk < 3.5:
                risk = 3.5
            tp = entry + (risk * tp_rr)
            be_trigger = entry + (risk * 0.8)

            be_active = False
            curr_sl = sl
            won = False

            for j in range(i + 1, min(i + 36, len(df))):
                f_bar = df.iloc[j]
                if f_bar["high"] >= be_trigger:
                    be_active = True
                    curr_sl = entry + 0.5

                if f_bar["low"] <= curr_sl:
                    pnl = -risk if not be_active else +0.5
                    trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl, "pnl_r": pnl / risk})
                    won = True
                    break

                if f_bar["high"] >= tp:
                    trades.append({"outcome": "WIN", "pnl_pts": risk * tp_rr, "pnl_r": tp_rr})
                    won = True
                    break

            if not won:
                end_bar = df.iloc[min(i + 35, len(df) - 1)]
                pnl = end_bar["close"] - entry
                trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl, "pnl_r": pnl / risk})
            last_idx = i

    total = len(trades)
    if total == 0:
        return {"name": f"RSI Trend Sniper (RSI<={rsi_thresh})", "total_trades": 0}
    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    pnl_pts = sum(t["pnl_pts"] for t in trades)
    gains = sum(t["pnl_pts"] for t in trades if t["pnl_pts"] > 0)
    losses = abs(sum(t["pnl_pts"] for t in trades if t["pnl_pts"] < 0))
    pf = gains / losses if losses > 0 else float("inf")

    return {
        "name": f"1. RSI Trend Sniper (RSI<={rsi_thresh} / {tp_rr}R)",
        "total_trades": total,
        "win_rate": (wins / total) * 100,
        "total_pnl_pts": pnl_pts,
        "profit_factor": pf
    }


def test_orb_15min_breakout(df: pd.DataFrame, tp_mult: float = 1.0) -> Dict[str, Any]:
    """
    NY Open 15-Minute Opening Range Breakout (ORB):
    - Marks High & Low between 13:30 and 13:45 UTC (09:30-09:45 EST)
    - Trades breakout with 1.0x range size target & BE at 0.5x range
    """
    trades = []
    df = df.copy()
    df["date"] = df["dt"].dt.date
    unique_dates = df["date"].unique()

    for d in unique_dates:
        day_df = df[df["date"] == d].copy()
        if len(day_df) < 30:
            continue

        # Get 13:30-13:45 bars (3 M5 bars)
        orb_bars = day_df[(day_df["dt"].dt.hour == 13) & (day_df["dt"].dt.minute.isin([30, 35, 40]))]
        if len(orb_bars) < 3:
            continue

        orb_high = orb_bars["high"].max()
        orb_low = orb_bars["low"].min()
        orb_range = orb_high - orb_low

        if orb_range < 4.0 or orb_range > 30.0:
            continue  # Avoid distorted gap days

        post_orb = day_df[(day_df["dt"].dt.hour > 13) | ((day_df["dt"].dt.hour == 13) & (day_df["dt"].dt.minute > 40))]
        post_orb = post_orb[post_orb["dt"].dt.hour <= 19]

        trade_taken = False
        for idx in range(len(post_orb)):
            bar = post_orb.iloc[idx]
            
            # Long Breakout
            if bar["close"] > orb_high:
                entry = bar["close"]
                sl = orb_low
                risk = entry - sl
                tp = entry + (orb_range * tp_mult)
                be_trigger = entry + (orb_range * 0.5)

                won = False
                be_active = False
                curr_sl = sl
                for k in range(idx + 1, min(idx + 24, len(post_orb))):
                    f = post_orb.iloc[k]
                    if f["high"] >= be_trigger:
                        be_active = True
                        curr_sl = entry + 0.5
                    if f["low"] <= curr_sl:
                        pnl = -risk if not be_active else +0.5
                        trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl})
                        won = True
                        break
                    if f["high"] >= tp:
                        trades.append({"outcome": "WIN", "pnl_pts": orb_range * tp_mult})
                        won = True
                        break
                if not won:
                    end_b = post_orb.iloc[min(idx + 23, len(post_orb) - 1)]
                    pnl = end_b["close"] - entry
                    trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl})
                trade_taken = True
                break

            # Short Breakout
            elif bar["close"] < orb_low:
                entry = bar["close"]
                sl = orb_high
                risk = sl - entry
                tp = entry - (orb_range * tp_mult)
                be_trigger = entry - (orb_range * 0.5)

                won = False
                be_active = False
                curr_sl = sl
                for k in range(idx + 1, min(idx + 24, len(post_orb))):
                    f = post_orb.iloc[k]
                    if f["low"] <= be_trigger:
                        be_active = True
                        curr_sl = entry - 0.5
                    if f["high"] >= curr_sl:
                        pnl = -risk if not be_active else +0.5
                        trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl})
                        won = True
                        break
                    if f["low"] <= tp:
                        trades.append({"outcome": "WIN", "pnl_pts": orb_range * tp_mult})
                        won = True
                        break
                if not won:
                    end_b = post_orb.iloc[min(idx + 23, len(post_orb) - 1)]
                    pnl = entry - end_b["close"]
                    trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl})
                trade_taken = True
                break

    total = len(trades)
    if total == 0:
        return {"name": "2. NY Open 15-Min ORB Breakout", "total_trades": 0}
    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    pnl_pts = sum(t["pnl_pts"] for t in trades)
    gains = sum(t["pnl_pts"] for t in trades if t["pnl_pts"] > 0)
    losses = abs(sum(t["pnl_pts"] for t in trades if t["pnl_pts"] < 0))
    pf = gains / losses if losses > 0 else float("inf")

    return {
        "name": f"2. NY Open 15-Min ORB ({tp_mult}x Range)",
        "total_trades": total,
        "win_rate": (wins / total) * 100,
        "total_pnl_pts": pnl_pts,
        "profit_factor": pf
    }


def print_advanced_report(results: List[Dict[str, Any]]) -> None:
    """Displays comparative results."""
    print("\n" + "=" * 90)
    print("      J.A.R.V.I.S. QUANTITATIVE MODEL TOURNAMENT (US500.cash / 100 Days)")
    print("=" * 90)
    print(f"{'Strategy Architecture':<45} | {'Trades':<7} | {'Win Rate':<10} | {'Total Pts':<10} | {'PF':<6}")
    print("-" * 90)

    for r in results:
        if r.get("total_trades", 0) == 0:
            continue
        w_str = f"{r['win_rate']:.1f}%"
        pts_str = f"{r['total_pnl_pts']:+.1f}"
        pf_str = f"{r['profit_factor']:.2f}" if r['profit_factor'] != float("inf") else "INF"

        print(f"{r['name']:<45} | {r['total_trades']:<7} | {w_str:<10} | {pts_str:<10} | {pf_str:<6}")

    print("=" * 90 + "\n")


def main():
    connector = MT5Connector()
    try:
        logger.info("Loading 100 days of M5 data from MT5 for model tournament...")
        if not connector.connect():
            return
        rates = connector.get_rates("US500.cash", count=29000, timeframe="M5")
        df = pd.DataFrame(rates)
        df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.sort_values("dt", inplace=True)
        df.reset_index(drop=True, inplace=True)

        # Merge H1 50-EMA & D1 9-EMA
        h1_rates = connector.get_rates("US500.cash", count=2500, timeframe="H1")
        h1_df = pd.DataFrame(h1_rates)
        h1_df["dt"] = pd.to_datetime(h1_df["time"], unit="s", utc=True)
        h1_df["h1_ema50"] = calculate_ema(h1_df["close"], 50)
        df = pd.merge_asof(df, h1_df[["dt", "h1_ema50"]], on="dt", direction="backward")

        d1_rates = connector.get_rates("US500.cash", count=150, timeframe="D1")
        d1_df = pd.DataFrame(d1_rates)
        d1_df["dt"] = pd.to_datetime(d1_df["time"], unit="s", utc=True)
        d1_df["d1_ema9"] = calculate_ema(d1_df["close"], 9)
        df = pd.merge_asof(df, d1_df[["dt", "d1_ema9"]], on="dt", direction="backward")

        df["rsi14"] = calculate_rsi(df["close"], 14)

        results = [
            test_rsi_trend_sniper(df, rsi_thresh=35.0, tp_rr=1.5),
            test_rsi_trend_sniper(df, rsi_thresh=30.0, tp_rr=1.5),
            test_rsi_trend_sniper(df, rsi_thresh=35.0, tp_rr=2.0),
            test_orb_15min_breakout(df, tp_mult=1.0),
            test_orb_15min_breakout(df, tp_mult=1.5)
        ]

        print_advanced_report(results)

    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
