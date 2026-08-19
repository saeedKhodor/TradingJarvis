# === CODE INDEX ===
# 1. Imports & Constants (Line 18)
# 2. calculate_session_vwap() - Computes daily session VWAP and Standard Deviation Bands (Line 38)
# 3. run_vwap_reversion_backtest() - Evaluates mean-reversion entries from +/-2.0 sigma (Line 80)
# 4. run_rsi_trend_pullback_backtest() - Evaluates M5 RSI oversold dips in H1 uptrends (Line 150)
# 5. print_comparative_report() - Outputs comparative statistical table (Line 210)
# 6. main() - Entry point (Line 260)
# =================

import os
import sys
import logging
from typing import Dict, List, Any, Optional

import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.mt5_connector import MT5Connector
from scripts.backtest_trend_alignment import calculate_ema

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TradingJarvis.HighWinRateStudy")


def calculate_session_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Calculates daily Session VWAP and Standard Deviation Bands (+/- 1.0, 2.0, 2.5 sigma)."""
    df = df.copy()
    df["date"] = df["dt"].dt.date
    df["typical_price"] = (df["high"] + df["low"] + df["close"]) / 3.0
    df["vol_price"] = df["typical_price"] * df["tick_volume"]

    # Group by day to reset VWAP daily
    df["cum_vol"] = df.groupby("date")["tick_volume"].cumsum()
    df["cum_vol_price"] = df.groupby("date")["vol_price"].cumsum()
    df["vwap"] = df["cum_vol_price"] / df["cum_vol"]

    # Rolling daily variance & standard deviation
    df["sq_diff"] = ((df["typical_price"] - df["vwap"]) ** 2) * df["tick_volume"]
    df["cum_sq_diff"] = df.groupby("date")["sq_diff"].cumsum()
    df["vwap_std"] = np.sqrt(df["cum_sq_diff"] / df["cum_vol"]).replace(0, np.nan).ffill().fillna(5.0)

    df["vwap_upper_1"] = df["vwap"] + df["vwap_std"] * 1.0
    df["vwap_lower_1"] = df["vwap"] - df["vwap_std"] * 1.0
    df["vwap_upper_2"] = df["vwap"] + df["vwap_std"] * 2.0
    df["vwap_lower_2"] = df["vwap"] - df["vwap_std"] * 2.0
    df["vwap_upper_25"] = df["vwap"] + df["vwap_std"] * 2.5
    df["vwap_lower_25"] = df["vwap"] - df["vwap_std"] * 2.5

    return df


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculates Wilder's RSI."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def run_vwap_reversion_backtest(df: pd.DataFrame, band_mult: float = 2.0, tp_target: str = "band_1") -> Dict[str, Any]:
    """
    Simulates VWAP Mean Reversion:
    - Long: Price dips below Lower Band (-2.0 sigma) -> target VWAP or Lower Band 1 (-1.0 sigma)
    - Short: Price spikes above Upper Band (+2.0 sigma) -> target VWAP or Upper Band 1 (+1.0 sigma)
    """
    trades = []
    cooldown = 6
    last_trade_idx = -100

    for i in range(10, len(df) - 30):
        bar = df.iloc[i]
        hour = bar["dt"].hour

        # NY Active hours (14:00 to 20:00 UTC)
        if not (14 <= hour <= 20):
            continue

        if (i - last_trade_idx) < cooldown:
            continue

        upper_band = bar[f"vwap_upper_{int(band_mult)}"] if band_mult in [1.0, 2.0] else bar["vwap_upper_25"]
        lower_band = bar[f"vwap_lower_{int(band_mult)}"] if band_mult in [1.0, 2.0] else bar["vwap_lower_25"]
        target_upper = bar["vwap_upper_1"] if tp_target == "band_1" else bar["vwap"]
        target_lower = bar["vwap_lower_1"] if tp_target == "band_1" else bar["vwap"]
        std_val = bar["vwap_std"]

        # 1. Long Mean Reversion Setup (Price stretched below lower 2.0-sigma band)
        if bar["low"] <= lower_band and bar["close"] > bar["open"]:
            entry = bar["close"]
            sl = bar["low"] - (std_val * 0.5)
            risk = entry - sl
            if risk < 3.0:
                risk = 3.0
            
            # Simulate forward
            won = False
            for j in range(i + 1, min(i + 24, len(df))):
                f_bar = df.iloc[j]
                if f_bar["low"] <= sl:
                    trades.append({"outcome": "LOSS", "pnl_pts": -risk, "pnl_r": -1.0})
                    won = True
                    break
                if f_bar["high"] >= target_lower:
                    gain = target_lower - entry
                    trades.append({"outcome": "WIN", "pnl_pts": gain, "pnl_r": gain / risk})
                    won = True
                    break
            if not won:
                end_bar = df.iloc[min(i + 23, len(df) - 1)]
                pnl = end_bar["close"] - entry
                trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl, "pnl_r": pnl / risk})
            last_trade_idx = i

        # 2. Short Mean Reversion Setup (Price stretched above upper 2.0-sigma band)
        elif bar["high"] >= upper_band and bar["close"] < bar["open"]:
            entry = bar["close"]
            sl = bar["high"] + (std_val * 0.5)
            risk = sl - entry
            if risk < 3.0:
                risk = 3.0

            won = False
            for j in range(i + 1, min(i + 24, len(df))):
                f_bar = df.iloc[j]
                if f_bar["high"] >= sl:
                    trades.append({"outcome": "LOSS", "pnl_pts": -risk, "pnl_r": -1.0})
                    won = True
                    break
                if f_bar["low"] <= target_upper:
                    gain = entry - target_upper
                    trades.append({"outcome": "WIN", "pnl_pts": gain, "pnl_r": gain / risk})
                    won = True
                    break
            if not won:
                end_bar = df.iloc[min(i + 23, len(df) - 1)]
                pnl = entry - end_bar["close"]
                trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl, "pnl_r": pnl / risk})
            last_trade_idx = i

    total = len(trades)
    if total == 0:
        return {"name": f"VWAP +/-{band_mult} sigma", "total_trades": 0}
    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    win_rate = (wins / total) * 100
    pnl_pts = sum(t["pnl_pts"] for t in trades)
    gains = sum(t["pnl_pts"] for t in trades if t["pnl_pts"] > 0)
    losses = abs(sum(t["pnl_pts"] for t in trades if t["pnl_pts"] < 0))
    pf = gains / losses if losses > 0 else float("inf")

    return {
        "name": f"VWAP +/-{band_mult} sigma Reversion ({tp_target})",
        "total_trades": total,
        "win_rate": win_rate,
        "total_pnl_pts": pnl_pts,
        "profit_factor": pf
    }


def run_rsi_trend_pullback_backtest(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Simulates RSI Oversold Pullback in Trend:
    - Long: Price > H1 50-EMA AND M5 RSI(14) <= 32 -> TP = 1.5R (with Breakeven at 1.0R)
    """
    df["rsi14"] = calculate_rsi(df["close"], 14)
    trades = []
    last_idx = -100

    for i in range(20, len(df) - 30):
        bar = df.iloc[i]
        hour = bar["dt"].hour

        if not (8 <= hour <= 20):
            continue
        if (i - last_idx) < 8:
            continue

        # Check Trend + RSI Oversold dip
        is_uptrend = "h1_ema50" in bar and bar["close"] > bar["h1_ema50"]
        is_oversold = bar["rsi14"] <= 32.0 and bar["close"] > bar["open"]

        if is_uptrend and is_oversold:
            entry = bar["close"]
            sl = bar["low"] - 3.0
            risk = entry - sl
            if risk < 4.0:
                risk = 4.0
            tp = entry + (risk * 1.5)
            be_level = entry + risk

            be_active = False
            curr_sl = sl
            won = False

            for j in range(i + 1, min(i + 36, len(df))):
                f_bar = df.iloc[j]
                # Check BE Trigger
                if f_bar["high"] >= be_level:
                    be_active = True
                    curr_sl = entry + 0.5  # Lock small gain

                # Check SL
                if f_bar["low"] <= curr_sl:
                    pnl = -risk if not be_active else +0.5
                    trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl, "pnl_r": pnl / risk})
                    won = True
                    break

                # Check TP
                if f_bar["high"] >= tp:
                    trades.append({"outcome": "WIN", "pnl_pts": risk * 1.5, "pnl_r": 1.5})
                    won = True
                    break

            if not won:
                end_bar = df.iloc[min(i + 35, len(df) - 1)]
                pnl = end_bar["close"] - entry
                trades.append({"outcome": "WIN" if pnl > 0 else "LOSS", "pnl_pts": pnl, "pnl_r": pnl / risk})
            last_idx = i

    total = len(trades)
    if total == 0:
        return {"name": "RSI Trend Pullback", "total_trades": 0}
    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    win_rate = (wins / total) * 100
    pnl_pts = sum(t["pnl_pts"] for t in trades)
    gains = sum(t["pnl_pts"] for t in trades if t["pnl_pts"] > 0)
    losses = abs(sum(t["pnl_pts"] for t in trades if t["pnl_pts"] < 0))
    pf = gains / losses if losses > 0 else float("inf")

    return {
        "name": "RSI Oversold in H1 Trend (with Breakeven)",
        "total_trades": total,
        "win_rate": win_rate,
        "total_pnl_pts": pnl_pts,
        "profit_factor": pf
    }


def print_comparative_report(results: List[Dict[str, Any]]) -> None:
    """Displays report in structured ASCII."""
    print("\n" + "=" * 90)
    print("      J.A.R.V.I.S. HIGH WIN-RATE STRATEGY BENCHMARK (US500.cash / 100 Days)")
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
        logger.info("Loading M5 data from MT5 for VWAP & RSI study...")
        if not connector.connect():
            return
        rates = connector.get_rates("US500.cash", count=29000, timeframe="M5")
        df = pd.DataFrame(rates)
        df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.sort_values("dt", inplace=True)
        df.reset_index(drop=True, inplace=True)

        # Merge H1 50-EMA
        h1_rates = connector.get_rates("US500.cash", count=2500, timeframe="H1")
        h1_df = pd.DataFrame(h1_rates)
        h1_df["dt"] = pd.to_datetime(h1_df["time"], unit="s", utc=True)
        h1_df["h1_ema50"] = calculate_ema(h1_df["close"], 50)
        df = pd.merge_asof(df, h1_df[["dt", "h1_ema50"]], on="dt", direction="backward")

        df = calculate_session_vwap(df)

        results = [
            run_vwap_reversion_backtest(df, band_mult=2.0, tp_target="band_1"),
            run_vwap_reversion_backtest(df, band_mult=2.0, tp_target="vwap"),
            run_vwap_reversion_backtest(df, band_mult=2.5, tp_target="band_1"),
            run_rsi_trend_pullback_backtest(df)
        ]

        print_comparative_report(results)

    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
