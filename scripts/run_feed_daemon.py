# === CODE INDEX ===
# 1. Imports & Logging Configuration (Line 18)
# 2. telegram_bar_handler() - Dispatches 1-minute bar telemetry to Telegram (Line 48)
# 3. on_bar_closed_telemetry() - Console logger for completed candlestick bars (Line 78)
# 4. print_market_snapshot() - Displays real-time prices, EMA, and ATR table (Line 105)
# 5. run_single_snapshot() - Executes one-off diagnostic query of watchlist (Line 145)
# 6. run_test_bar_alert() - Fetches latest M1 bar and transmits immediate Telegram alert (Line 165)
# 7. main() - CLI entry point, Arbiter setup, and daemon loop runner (Line 205)
# =================

import os
import sys
import time
import argparse
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any

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
from src.engine.arbiter import SkillArbiter
from src.skills.safety_lock_skill import SafetyLockSkill
from src.skills.pre_market_classifier_skill import PreMarketClassifierSkill
from src.skills.range_sentinel_skill import RangeSentinelSkill

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


def telegram_bar_handler(symbol: str, bar: CandleBar, cache: PriceCache, connector: Optional[MT5Connector] = None) -> None:
    """Dispatches a structured Telegram alert on each completed candlestick bar with MT5 native EMAs."""
    if not TELEGRAM_AVAILABLE:
        logger.warning("Telegram notifier module is not available.")
        return

    ema_14 = cache.get_ema(symbol, period=14)
    atr_14 = cache.get_atr(symbol, period=14)
    time_str = bar.dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    # Read MT5 native indicators if connector is available
    mt5_emas = None
    if connector:
        native_data = connector.get_native_indicators(symbol)
        if native_data and "emas" in native_data:
            mt5_emas = native_data["emas"]
            logger.info(f"Retrieved {len(mt5_emas)} native MT5 EMA values for [{symbol}]")

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
        atr=atr_14,
        mt5_emas=mt5_emas
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
    """Fetches the latest completed M1 bar and evaluates Safety Lock + bar alerts."""
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

    # Run Skill Arbiter evaluation
    arbiter = SkillArbiter(connector=connector, enable_telegram=True)
    arbiter.register_skill(SafetyLockSkill())
    
    print("\n[*] Evaluating J.A.R.V.I.S. Specialist Skills (Safety Lock / Cascade)...")
    results = arbiter.process_market_bar(symbol, latest_closed_bar, cache)
    print(f"[+] Skills evaluation complete. Triggered events: {len(results)}")

    print(f"\n[*] Transmitting J.A.R.V.I.S. 1-Minute Telegram Telemetry Alert...")
    telegram_bar_handler(symbol, latest_closed_bar, cache, connector=connector)
    connector.disconnect()
    return True


def main():
    parser = argparse.ArgumentParser(description="J.A.R.V.I.S. MetaTrader 5 Multi-Skill Price Feeder Engine")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols list (e.g. US500.cash)")
    parser.add_argument("--timeframe", type=str, default="M1", help="Timeframe (default: M1)")
    parser.add_argument("--iterations", type=int, help="Limit number of polling cycles")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Poll interval in seconds")
    parser.add_argument("--snapshot", action="store_true", help="Print single snapshot and exit")
    parser.add_argument("--test-alert", action="store_true", help="Fetch latest M1 bar, evaluate skills, and send TG alert")
    parser.add_argument("--telegram", action="store_true", default=True, help="Enable Telegram alerts for skills and sentinel events")
    parser.add_argument("--notify-bars", action="store_true", default=False, help="Send routine Telegram alerts on every 1-min bar close (testing only)")

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

    # Initialize Arbiter & Register Skills (Handles actual strategy & safety alerts)
    arbiter = SkillArbiter(connector=connector, enable_telegram=args.telegram)
    safety_skill = SafetyLockSkill()
    pre_market_skill = PreMarketClassifierSkill(target_pts=5.0)
    range_skill = RangeSentinelSkill()
    arbiter.register_skill(safety_skill)
    arbiter.register_skill(pre_market_skill)
    arbiter.register_skill(range_skill)

    # Attach console telemetry logger
    feeder.register_bar_handler(on_bar_closed_telemetry)

    # Attach Arbiter Multi-Skill Processor (Evaluates conditions silently every minute, alerts only on triggers)
    feeder.register_bar_handler(lambda sym, bar, c: arbiter.process_market_bar(sym, bar, c))

    # Attach routine 1-minute bar alert handler ONLY if explicitly requested with --notify-bars
    if args.notify_bars:
        feeder.register_bar_handler(lambda sym, bar, c: telegram_bar_handler(sym, bar, c, connector=connector))

    # Initialize Telegram Commander (Interactive Directives & Remote Reboot)
    commander = None
    if args.telegram:
        def status_provider():
            latest_bar = cache.get_latest_bar(symbols[0])
            acc = connector.get_account_info() or {}
            native_data = connector.get_native_indicators(symbols[0]) or {}
            mt5_emas = native_data.get("emas", {})

            # Build current market state for deep skill telemetry
            current_state = None
            if latest_bar:
                from src.skills.base_skill import MarketState
                current_state = MarketState(
                    symbol=symbols[0],
                    timestamp=latest_bar.time,
                    time_str=latest_bar.dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    latest_bar=latest_bar,
                    cache=cache,
                    mt5_emas=mt5_emas,
                    account_info=acc
                )

            skill_1_status = safety_skill.get_status(current_state)
            daily_plan = pre_market_skill.generate_daily_plan(current_state) if current_state else None
            
            # Scan ranges on-demand
            try:
                range_skill.scan_all_timeframes(connector)
                range_report = range_skill.format_telegram_report(latest_bar.close if latest_bar else 0.0, symbols[0])
            except Exception as e:
                logger.warning(f"Error scanning ranges in status_provider: {e}")
                range_report = None

            return {
                "symbol": symbols[0],
                "price": f"{latest_bar.close:.2f}" if latest_bar else "N/A",
                "mt5_connected": connector.is_connected(),
                "safety_status": safety_skill.last_status_str,
                "balance": f"${acc.get('balance', 100000):,.2f}",
                "equity": f"${acc.get('equity', 100000):,.2f}",
                "skills_count": len(arbiter._skills),
                "daily_plan": daily_plan,
                "range_report": range_report,
                "skill_details": {
                    "1": skill_1_status,
                    "safetylock": skill_1_status,
                    "safetylock_cascade": skill_1_status,
                    "cascade": skill_1_status
                }
            }

        def on_reboot():
            feeder.stop()
            connector.disconnect()

        try:
            from src.bot.telegram_commander import TelegramCommander
            commander = TelegramCommander(
                status_provider=status_provider,
                on_reboot_callback=on_reboot
            )
            commander.start()
        except Exception as e:
            logger.warning(f"Could not start Telegram Commander: {e}")

    try:
        # Start feed
        feeder.start(max_iterations=args.iterations)
    finally:
        if commander:
            commander.stop()


if __name__ == "__main__":
    main()
