# === CODE INDEX ===
# 1. Imports & Constants (Line 18)
# 2. calculate_ema() - Vectorized EMA calculation on price series (Line 38)
# 3. load_multi_timeframe_history() - Queries MT5 for multi-timeframe rates (Line 58)
# 4. align_timeframes() - Merges higher-timeframe EMAs into base intraday bars (Line 105)
# 5. run_backtest_study() - Evaluates returns, win rates, and MFE/MAE across regimes (Line 150)
# 6. print_study_report() - Generates structured quantitative report (Line 230)
# 7. main() - CLI entry point (Line 285)
# =================

import os
import sys
import time
import argparse
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

import pandas as pd
import numpy as np

# Add project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.mt5_connector import MT5Connector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TradingJarvis.Backtest")


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculates Exponential Moving Average with standard alpha multiplier."""
    return series.ewm(span=period, adjust=False).mean()


def load_multi_timeframe_history(
    connector: MT5Connector,
    symbol: str = "US500.cash",
    days: int = 100
) -> Dict[str, pd.DataFrame]:
    """Fetches historical OHLCV data for multiple timeframes from MT5."""
    if not connector.is_connected():
        if not connector.connect():
            raise RuntimeError("Failed to connect to MetaTrader 5.")

    # Calculate required bar counts
    counts = {
        "M5": days * 288 + 200,   # ~29,000 bars
        "M15": days * 96 + 200,   # ~9,800 bars
        "H1": days * 24 + 100,    # ~2,500 bars
        "H4": days * 6 + 50,      # ~650 bars
        "D1": days + 50           # ~150 bars
    }

    dfs = {}
    for tf, cnt in counts.items():
        logger.info(f"Fetching {cnt} bars for [{symbol}] on {tf}...")
        rates = connector.get_rates(symbol, count=cnt, timeframe=tf)
        if not rates or len(rates) == 0:
            logger.warning(f"Could not load data for {tf}.")
            continue
        
        df = pd.DataFrame(rates)
        df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.sort_values("dt", inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        # Calculate 9-EMA
        df["ema9"] = calculate_ema(df["close"], 9)
        
        if tf == "H1":
            df["ema21"] = calculate_ema(df["close"], 21)
            df["ema50"] = calculate_ema(df["close"], 50)
            
        dfs[tf] = df
        logger.info(f"Loaded {len(df)} bars for {tf} from {df['dt'].iloc[0].strftime('%Y-%m-%d')} to {df['dt'].iloc[-1].strftime('%Y-%m-%d')}")

    return dfs


def align_timeframes(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Merges higher timeframe EMAs onto the M15 base execution timeframe using merge_asof."""
    base_df = dfs["M15"].copy()
    base_df.rename(columns={"ema9": "m15_ema9"}, inplace=True)

    # Merge H1 EMAs
    h1_df = dfs["H1"][["dt", "ema9", "ema21", "ema50"]].copy()
    h1_df.rename(columns={"ema9": "h1_ema9", "ema21": "h1_ema21", "ema50": "h1_ema50"}, inplace=True)
    merged = pd.merge_asof(base_df, h1_df, on="dt", direction="backward")

    # Merge H4 EMA
    if "H4" in dfs:
        h4_df = dfs["H4"][["dt", "ema9"]].copy()
        h4_df.rename(columns={"ema9": "h4_ema9"}, inplace=True)
        merged = pd.merge_asof(merged, h4_df, on="dt", direction="backward")

    # Merge D1 EMA
    if "D1" in dfs:
        d1_df = dfs["D1"][["dt", "ema9"]].copy()
        d1_df.rename(columns={"ema9": "d1_ema9"}, inplace=True)
        merged = pd.merge_asof(merged, d1_df, on="dt", direction="backward")

    # Drop warm-up rows (first 60 bars)
    merged = merged.iloc[60:].reset_index(drop=True)
    return merged


def run_backtest_study(df: pd.DataFrame) -> Dict[str, Any]:
    """Evaluates forward returns, win rate, and risk-reward metrics across key alignment regimes."""
    # Compute forward returns (1-bar / 15m, 4-bars / 1h, 16-bars / 4h)
    df["fwd_ret_15m"] = df["close"].shift(-1) - df["close"]
    df["fwd_ret_1h"] = df["close"].shift(-4) - df["close"]
    df["fwd_ret_4h"] = df["close"].shift(-16) - df["close"]

    # Calculate Max Favorable (MFE) and Adverse (MAE) Excursion over the next 4 hours (16 bars)
    rolling_max = df["high"].iloc[::-1].rolling(window=16, min_periods=1).max().iloc[::-1]
    rolling_min = df["low"].iloc[::-1].rolling(window=16, min_periods=1).min().iloc[::-1]
    df["mfe_4h"] = rolling_max - df["close"]  # Max upside gain
    df["mae_4h"] = df["close"] - rolling_min  # Max downside drawdown

    # Define Regimes & Setups:
    # 1. Broad Bullish Alignment: Close > M15_EMA9 > H1_EMA9
    bull_mask = (df["close"] > df["m15_ema9"]) & (df["m15_ema9"] > df["h1_ema9"])
    
    # 2. Bullish Alignment + Macro D1 9-EMA Confluence:
    bull_macro_mask = bull_mask & (df["close"] > df["d1_ema9"])

    # 3. Pullback Setup (Golden Zone): In Bullish Alignment AND price low dips near M15 9-EMA (within 3 pts) while closing above it
    bull_pullback_mask = bull_mask & (df["low"] <= df["m15_ema9"] + 2.0) & (df["close"] >= df["m15_ema9"])

    # 4. First Transition Bar (Fresh Trend Ignition):
    bull_transition_mask = bull_mask & (~bull_mask.shift(1).fillna(False))

    # 5. Safety Lock (Bearish Cascade): Close < H1_EMA9 < H1_EMA21 < H1_EMA50
    cascade_mask = (df["close"] < df["h1_ema9"]) & (df["h1_ema9"] < df["h1_ema21"]) & (df["h1_ema21"] < df["h1_ema50"])

    # 6. Short on Cascade Retest: In Cascade AND high touches H1 9-EMA (within 3 pts) while closing below it
    cascade_short_pullback_mask = cascade_mask & (df["high"] >= df["h1_ema9"] - 3.0) & (df["close"] <= df["h1_ema9"])

    # 7. Choppy / Range
    choppy_mask = ~bull_mask & ~cascade_mask

    def calc_regime_stats(mask: pd.Series, name: str, is_short: bool = False) -> Dict[str, Any]:
        subset = df[mask].dropna(subset=["fwd_ret_1h", "fwd_ret_4h"])
        if len(subset) == 0:
            return {"name": name, "bars_count": 0}

        ret_1h = -subset["fwd_ret_1h"] if is_short else subset["fwd_ret_1h"]
        ret_4h = -subset["fwd_ret_4h"] if is_short else subset["fwd_ret_4h"]

        win_1h = (ret_1h > 0).mean() * 100
        win_4h = (ret_4h > 0).mean() * 100
        avg_ret_1h = ret_1h.mean()
        avg_ret_4h = ret_4h.mean()
        
        # MFE / MAE for directional trade
        if not is_short:
            avg_mfe = subset["mfe_4h"].mean()
            avg_mae = subset["mae_4h"].mean()
        else:
            avg_mfe = (subset["close"] - df.loc[subset.index, "low"].iloc[::-1].rolling(16, min_periods=1).min().iloc[::-1]).mean()
            avg_mae = (df.loc[subset.index, "high"].iloc[::-1].rolling(16, min_periods=1).max().iloc[::-1] - subset["close"]).mean()

        edge_ratio = avg_mfe / avg_mae if avg_mae > 0 else 1.0

        gains = ret_4h[ret_4h > 0].sum()
        losses = abs(ret_4h[ret_4h < 0].sum())
        profit_factor = gains / losses if losses > 0 else float("inf")

        pct_of_time = (len(subset) / len(df)) * 100

        return {
            "name": name,
            "bars_count": len(subset),
            "pct_time": pct_of_time,
            "win_rate_1h": win_1h,
            "win_rate_4h": win_4h,
            "avg_ret_1h_pts": avg_ret_1h,
            "avg_ret_4h_pts": avg_ret_4h,
            "avg_mfe_pts": avg_mfe,
            "avg_mae_pts": avg_mae,
            "edge_ratio": edge_ratio,
            "profit_factor": profit_factor
        }

    results = {
        "total_bars": len(df),
        "start_date": df["dt"].iloc[0].strftime("%Y-%m-%d"),
        "end_date": df["dt"].iloc[-1].strftime("%Y-%m-%d"),
        "regimes": [
            calc_regime_stats(bull_mask, "1. Bullish Regime (M15 > H1)"),
            calc_regime_stats(bull_macro_mask, "2. Bullish + Macro D1 Confluence"),
            calc_regime_stats(bull_transition_mask, "3. Trend Ignition (1st Breakout)"),
            calc_regime_stats(bull_pullback_mask, "4. Pullback Retest at M15 9-EMA"),
            calc_regime_stats(cascade_mask, "5. Safety Lock (H1 Cascade)"),
            calc_regime_stats(cascade_short_pullback_mask, "6. Short on H1 9-EMA Retest", is_short=True),
            calc_regime_stats(choppy_mask, "7. Choppy / Neutral Transition")
        ]
    }
    return results


def print_study_report(results: Dict[str, Any]) -> None:
    """Displays comprehensive backtest report in structured ASCII."""
    print("\n" + "=" * 90)
    print("        J.A.R.V.I.S. 100-DAY QUANTITATIVE STUDY: TREND ALIGNMENT & BIAS        ")
    print(f"        Instrument: US500.cash | Sample: {results['start_date']} to {results['end_date']} ({results['total_bars']} bars)")
    print("=" * 90)
    print(f"{'Regime Name':<32} | {'% Time':<7} | {'Win 1H':<7} | {'Win 4H':<7} | {'Avg 4H Pts':<10} | {'MFE/MAE':<8} | {'PF':<6}")
    print("-" * 90)

    for r in results["regimes"]:
        if r["bars_count"] == 0:
            continue
        pct_str = f"{r['pct_time']:.1f}%"
        w1_str = f"{r['win_rate_1h']:.1f}%"
        w4_str = f"{r['win_rate_4h']:.1f}%"
        ret_str = f"{r['avg_ret_4h_pts']:+.2f}"
        edge_str = f"{r['edge_ratio']:.2f}x"
        pf_str = f"{r['profit_factor']:.2f}" if r['profit_factor'] != float("inf") else "INF"

        print(f"{r['name']:<32} | {pct_str:<7} | {w1_str:<7} | {w4_str:<7} | {ret_str:<10} | {edge_str:<8} | {pf_str:<6}")

    print("=" * 90 + "\n")


def main():
    parser = argparse.ArgumentParser(description="J.A.R.V.I.S. 100-Day Trend Alignment Quantitative Study")
    parser.add_argument("--symbol", type=str, default="US500.cash", help="Target symbol")
    parser.add_argument("--days", type=int, default=100, help="Number of historical trading days (default: 100)")
    args = parser.parse_args()

    connector = MT5Connector()
    try:
        logger.info(f"Connecting to MT5 to analyze past {args.days} days of [{args.symbol}]...")
        dfs = load_multi_timeframe_history(connector, symbol=args.symbol, days=args.days)
        merged = align_timeframes(dfs)
        results = run_backtest_study(merged)
        print_study_report(results)
    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
