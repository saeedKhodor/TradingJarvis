# === CODE INDEX ===
# 1. Imports & Logging Configuration (Line 18)
# 2. telegram_bar_handler() - Dispatches 1-minute bar telemetry to Telegram (Line 42)
# 3. on_bar_closed_telemetry() - Console logger for completed candlestick bars (Line 68)
# 4. print_market_snapshot() - Displays real-time prices, EMA, and ATR table (Line 92)
# 5. run_single_snapshot() - Executes one-off diagnostic query of watchlist (Line 132)
# 6. run_test_bar_alert() - Fetches latest M1 bar and transmits immediate Telegram alert (Line 150)
# 7. main() - CLI entry point and daemon loop runner (Line 182)
# =================

import os
import sys
import time
import argparse
import logging
from datetime import datetime

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# Add skill scripts directory to sys.path for Telegram Notifier
SKILL_SCRIPTS_DIR = os.path.join(BASE_DIR, ".agents", "skills", "trading-jarvis", "scripts")
if SKILL_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SKILL_SCRIPTS_DIR)

from src.feed.mt5_connector import MT5Connector
from src.feed.price_cache import PriceCache, CandleBar
from src.feed.price_feeder import PriceFeeder

try:
    from telegram_notifier import send_bar_telemetry, load_config
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("TradingJarvis.FeedRunner")


def telegram_bar_handler(symbol: str, bar: CandleBar, cache: PriceCache) -> None:
    """Dispatches a structured Telegram alert on each completed candlestick bar."""
    if not TELEGRAM_AVAILABLE:
        logger.warning("Telegram notifier module is not available.")
        return

    ema_14 = cache.get_ema(symbol, period=14)
    atr_14 = cache.get_atr(symbol, period=14)
    time_str = bar.dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    logger.info(f"Transmitting Telegram M1 telemetry for [{symbol}] @ {time_str}...")
    success = send_bar_telemetry(
        symbol=symbol,
        timeframe="M1",
        time_str=time_str,
        open_p=bar.open,
        high_p=bar.high,
        low_p=bar.low,
        close_p=bar.close,
        volume=bar.tick_volume,
        spread=bar.spread,
        ema=ema_14,
        atr=atr_14
    )
    if success:
        logger.info(f"[J.A.R.V.I.S.] Telegram telemetry for [{symbol}] delivered successfully.")
    else:
        logger.error(f"[J.A.R.V.I.S.] Failed to deliver Telegram telemetry for [{symbol}].")


def on_bar_closed_telemetry(symbol: str, bar: CandleBar, cache: PriceCache) -> None:
    """Processes newly closed candlestick bar and outputs technical telemetry to console."""
    ema_14 = cache.get_ema(symbol, period=14)
    atr_14 = cache.get_atr(symbol, period=14)
    direction = "🟢 BULLISH" if bar.is_bullish else ("🔴 BEARISH" if bar.is_bearish else "⚪ NEUTRAL")

    print("\n" + "=" * 65)
    print(f" 🛡️  J.A.R.V.I.S. TELEMETRY | BAR CLOSED [{symbol}] @ {bar.dt.strftime('%H:%M:%S UTC')}")
    print("=" * 65)
    print(f"  Candle Type   : {direction}")
    print(f"  Open / Close  : {bar.open:.2f}  -->  {bar.close:.2f}")
    print(f"  High / Low    : {bar.high:.2f}  /    {bar.low:.2f}")
    print(f"  Range / Body  : {bar.range_size:.2f}  /    {bar.body_size:.2f}")
    print(f"  Tick Volume   : {bar.tick_volume} ticks | Spread: {bar.spread}")
    print(f"  Technical EMA : {ema_14 if ema_14 is not None else 'Calculating...'}")
    print(f"  ATR (14) Vol  : {atr_14 if atr_14 is not None else 'Calculating...'}")
    print("=" * 65 + "\n")


def print_market_snapshot(feeder: PriceFeeder) -> None:
    """Prints a structured ASCII table of the latest market status for all symbols."""
    print("\n" + "=" * 80)
    print("           J.A.R.V.I.S. REAL-TIME MARKET SNAPSHOT (MT5 M1 FEED)           ")
    print("=" * 80)
    print(f"{'Symbol':<12} | {'Time (UTC)':<12} | {'Close':<10} | {'Bid/Ask Spread':<16} | {'EMA(14)':<10} | {'ATR(14)':<10}")
    print("-" * 80)

    for sym in feeder.symbols:
        bar = feeder.cache.get_latest_bar(sym)
        tick = feeder.connector.get_current_tick(sym)
        ema = feeder.cache.get_ema(sym, period=14)
        atr = feeder.cache.get_atr(sym, period=14)

        time_str = bar.dt.strftime("%H:%M:%S") if bar else "N/A"
        close_str = f"{bar.close:.2f}" if bar else "N/A"
        spread_str = f"{tick['spread_points']} pts" if tick else "N/A"
        ema_str = f"{ema:.2f}" if ema else "N/A"
        atr_str = f"{atr:.2f}" if atr else "N/A"

        print(f"{sym:<12} | {time_str:<12} | {close_str:<10} | {spread_str:<16} | {ema_str:<10} | {atr_str:<10}")

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


def run_test_bar_alert(symbol: str = "US500.cash") -> bool:
    """Fetches the latest completed M1 bar for a symbol and sends an immediate Telegram alert."""
    print(f"\n[*] Fetching latest completed M1 bar for [{symbol}] from MT5...")
    connector = MT5Connector()
    if not connector.connect():
        print("[!] J.A.R.V.I.S. Error: Failed to connect to MetaTrader 5.", file=sys.stderr)
        return False

    cache = PriceCache(buffer_depth=50)
    rates = connector.get_rates(symbol, count=30, timeframe="M1")
    if not rates or len(rates) < 2:
        print(f"[!] J.A.R.V.I.S. Error: No rates available for {symbol}.", file=sys.stderr)
        connector.disconnect()
        return False

    cache.update_bars(symbol, rates)
    latest_closed_bar = cache.get_previous_bar(symbol) or cache.get_latest_bar(symbol)
    
    print(f"[+] Loaded latest bar for [{symbol}] @ {latest_closed_bar.dt.strftime('%H:%M:%S UTC')}")
    print(f"    Open: {latest_closed_bar.open:.2f} | High: {latest_closed_bar.high:.2f} | Low: {latest_closed_bar.low:.2f} | Close: {latest_closed_bar.close:.2f}")

    print(f"\n[*] Transmitting J.A.R.V.I.S. 1-Minute Telegram Telemetry Alert...")
    telegram_bar_handler(symbol, latest_closed_bar, cache)
    connector.disconnect()
    return True


def main():
    parser = argparse.ArgumentParser(description="J.A.R.V.I.S. MetaTrader 5 1-Minute Price Feeder")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols list (e.g. US500.cash)")
    parser.add_argument("--timeframe", type=str, default="M1", help="Timeframe (default: M1)")
    parser.add_argument("--iterations", type=int, help="Limit number of polling cycles")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Poll interval in seconds")
    parser.add_argument("--snapshot", action="store_true", help="Print single snapshot and exit")
    parser.add_argument("--test-alert", action="store_true", help="Fetch latest M1 bar and send immediate TG alert")
    parser.add_argument("--telegram", action="store_true", default=True, help="Enable Telegram alerts on bar close")

    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else ["US500.cash"]

    if args.test_alert:
        success = run_test_bar_alert(symbols[0])
        sys.exit(0 if success else 1)

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

    # Attach console telemetry handler
    feeder.register_bar_handler(on_bar_closed_telemetry)

    # Attach Telegram alert handler if enabled
    if args.telegram:
        feeder.register_bar_handler(telegram_bar_handler)

    # Start feed
    feeder.start(max_iterations=args.iterations)


if __name__ == "__main__":
    main()
