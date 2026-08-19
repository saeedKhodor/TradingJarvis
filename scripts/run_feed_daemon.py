# === CODE INDEX ===
# 1. Imports & Logging Configuration (Line 16)
# 2. on_bar_closed_telemetry() - Sample J.A.R.V.I.S. bar close telemetry processor (Line 38)
# 3. print_market_snapshot() - Displays real-time prices, EMA, and ATR table (Line 60)
# 4. run_single_snapshot() - Executes one-off diagnostic query of watchlist (Line 100)
# 5. main() - CLI entry point and daemon loop runner (Line 130)
# =================

import os
import sys
import time
import argparse
import logging
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.feed.mt5_connector import MT5Connector
from src.feed.price_cache import PriceCache, CandleBar
from src.feed.price_feeder import PriceFeeder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("TradingJarvis.FeedRunner")


def on_bar_closed_telemetry(symbol: str, bar: CandleBar, cache: PriceCache) -> None:
    """Processes newly closed candlestick bar and outputs technical telemetry."""
    ema_14 = cache.get_ema(symbol, period=14)
    atr_14 = cache.get_atr(symbol, period=14)
    direction = "🟢 BULLISH" if bar.is_bullish else ("🔴 BEARISH" if bar.is_bearish else "⚪ NEUTRAL")

    print("\n" + "=" * 65)
    print(f" 🛡️  J.A.R.V.I.S. TELEMETRY | BAR CLOSED [{symbol}] @ {bar.dt.strftime('%H:%M:%S UTC')}")
    print("=" * 65)
    print(f"  Candle Type   : {direction}")
    print(f"  Open / Close  : {bar.open:.5f}  -->  {bar.close:.5f}")
    print(f"  High / Low    : {bar.high:.5f}  /    {bar.low:.5f}")
    print(f"  Range / Body  : {bar.range_size:.5f}  /    {bar.body_size:.5f}")
    print(f"  Tick Volume   : {bar.tick_volume} ticks | Spread: {bar.spread}")
    print(f"  Technical EMA : {ema_14 if ema_14 is not None else 'Calculating...'}")
    print(f"  ATR (14) Vol  : {atr_14 if atr_14 is not None else 'Calculating...'}")
    print("=" * 65 + "\n")


def print_market_snapshot(feeder: PriceFeeder) -> None:
    """Prints a structured ASCII table of the latest market status for all symbols."""
    print("\n" + "=" * 80)
    print("           J.A.R.V.I.S. REAL-TIME MARKET SNAPSHOT (MT5 M1 FEED)           ")
    print("=" * 80)
    print(f"{'Symbol':<10} | {'Time (UTC)':<12} | {'Close':<10} | {'Bid/Ask Spread':<16} | {'EMA(14)':<10} | {'ATR(14)':<10}")
    print("-" * 80)

    for sym in feeder.symbols:
        bar = feeder.cache.get_latest_bar(sym)
        tick = feeder.connector.get_current_tick(sym)
        ema = feeder.cache.get_ema(sym, period=14)
        atr = feeder.cache.get_atr(sym, period=14)

        time_str = bar.dt.strftime("%H:%M:%S") if bar else "N/A"
        close_str = f"{bar.close:.5f}" if bar else "N/A"
        spread_str = f"{tick['spread_points']} pts" if tick else "N/A"
        ema_str = f"{ema:.5f}" if ema else "N/A"
        atr_str = f"{atr:.5f}" if atr else "N/A"

        print(f"{sym:<10} | {time_str:<12} | {close_str:<10} | {spread_str:<16} | {ema_str:<10} | {atr_str:<10}")

    print("=" * 80 + "\n")


def run_single_snapshot(symbols_list: list) -> bool:
    """Performs a single-pass connection, history load, and market snapshot."""
    connector = MT5Connector()
    if not connector.connect():
        print("[!] J.A.R.V.I.S. Error: Failed to connect to MetaTrader 5.", file=sys.stderr)
        return False

    cache = PriceCache(buffer_depth=100)
    feeder = PriceFeeder(connector=connector, cache=cache, symbols=symbols_list)
    feeder.initialize_history(count=50)
    print_market_snapshot(feeder)
    connector.disconnect()
    return True


def main():
    parser = argparse.ArgumentParser(description="J.A.R.V.I.S. MetaTrader 5 1-Minute Price Feeder")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols list (e.g. EURUSD,GBPUSD,XAUUSD)")
    parser.add_argument("--timeframe", type=str, default="M1", help="Timeframe (default: M1)")
    parser.add_argument("--iterations", type=int, help="Limit number of polling cycles")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Poll interval in seconds")
    parser.add_argument("--snapshot", action="store_true", help="Print single snapshot and exit")

    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else ["EURUSD", "GBPUSD", "XAUUSD"]

    if args.snapshot:
        success = run_single_snapshot(symbols)
        sys.exit(0 if success else 1)

    connector = MT5Connector()
    cache = PriceCache(buffer_depth=200)
    feeder = PriceFeeder(
        connector=connector,
        cache=cache,
        symbols=symbols,
        timeframe=args.timeframe,
        poll_interval_sec=args.poll_interval
    )

    # Attach telemetry handler
    feeder.register_bar_handler(on_bar_closed_telemetry)

    # Start feed
    feeder.start(max_iterations=args.iterations)


if __name__ == "__main__":
    main()
