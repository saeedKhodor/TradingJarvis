# === CODE INDEX ===
# 1. Imports & Initialization (Line 16)
# 2. PriceFeeder.__init__() - Initializes feeder with connector, cache, and symbols (Line 32)
# 3. PriceFeeder.register_bar_handler() - Adds subscriber callback for bar close events (Line 60)
# 4. PriceFeeder.initialize_history() - Warms up cache with initial historical bars (Line 68)
# 5. PriceFeeder.poll_once() - Polls all symbols once and fires bar close handlers (Line 95)
# 6. PriceFeeder.start() - Continuous ingestion loop with minute synchronization (Line 146)
# 7. PriceFeeder.stop() - Gracefully shuts down the feed engine (Line 185)
# =================

import time
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Any

from .mt5_connector import MT5Connector
from .price_cache import PriceCache, CandleBar

logger = logging.getLogger("TradingJarvis.PriceFeeder")

BarCloseHandler = Callable[[str, CandleBar, PriceCache], None]


class PriceFeeder:
    """Ingests real-time 1-minute market data from MT5 and emits bar close events."""

    def __init__(
        self,
        connector: Optional[MT5Connector] = None,
        cache: Optional[PriceCache] = None,
        symbols: Optional[List[str]] = None,
        timeframe: str = "M1",
        buffer_depth: int = 200,
        poll_interval_sec: float = 1.0,
        align_to_minute_close: bool = True
    ):
        self.connector = connector or MT5Connector()
        self.cache = cache or PriceCache(buffer_depth=buffer_depth)
        self.symbols = symbols or self.connector.config.get("feed", {}).get("symbols", ["EURUSD", "GBPUSD", "XAUUSD"])
        self.timeframe = timeframe or self.connector.config.get("feed", {}).get("timeframe", "M1")
        self.buffer_depth = buffer_depth
        self.poll_interval_sec = poll_interval_sec
        self.align_to_minute_close = align_to_minute_close

        self._running = False
        self._last_bar_time: Dict[str, int] = {}
        self._bar_handlers: List[BarCloseHandler] = []

    def register_bar_handler(self, handler: BarCloseHandler) -> None:
        """Registers a callback function to be executed when a new M1 bar closes."""
        if handler not in self._bar_handlers:
            self._bar_handlers.append(handler)
            logger.debug(f"Registered bar handler: {handler.__name__ if hasattr(handler, '__name__') else handler}")

    def initialize_history(self, count: Optional[int] = None) -> Dict[str, int]:
        """Pre-loads initial historical candles into the PriceCache."""
        fetch_count = count or self.buffer_depth
        results = {}

        if not self.connector.is_connected():
            if not self.connector.connect():
                logger.error("Cannot initialize history: MT5 connection failed.")
                return {}

        logger.info(f"Warming up cache with {fetch_count} {self.timeframe} bars for {len(self.symbols)} symbols...")
        for sym in self.symbols:
            rates = self.connector.get_rates(sym, count=fetch_count, timeframe=self.timeframe, start_pos=0)
            if rates:
                inserted = self.cache.update_bars(sym, rates)
                latest = self.cache.get_latest_bar(sym)
                if latest:
                    self._last_bar_time[sym] = latest.time
                results[sym] = len(rates)
                logger.info(f"Loaded {len(rates)} bars for [{sym}] | Latest: {latest.dt.strftime('%H:%M:%S UTC') if latest else 'N/A'}")
            else:
                logger.warning(f"Failed to load initial history for [{sym}]")
                results[sym] = 0

        return results

    def poll_once(self) -> Dict[str, Optional[CandleBar]]:
        """
        Polls the latest 2 bars for each symbol, checks for completed bar closes,
        updates the cache, and triggers registered subscriber handlers.
        """
        newly_closed_bars: Dict[str, Optional[CandleBar]] = {}

        if not self.connector.is_connected():
            if not self.connector.connect():
                return newly_closed_bars

        for sym in self.symbols:
            rates = self.connector.get_rates(sym, count=2, timeframe=self.timeframe, start_pos=0)
            if not rates or len(rates) < 1:
                continue

            # rates[-1] is the current forming bar, rates[-2] is the completed bar
            current_bar_data = rates[-1]
            current_bar_time = current_bar_data["time"]

            # Ingest into cache
            self.cache.update_bars(sym, rates)

            last_known_time = self._last_bar_time.get(sym)
            
            # If current bar time has progressed beyond last known time, the previous bar is officially closed
            if last_known_time is not None and current_bar_time > last_known_time:
                closed_bar = self.cache.get_previous_bar(sym)
                if closed_bar:
                    newly_closed_bars[sym] = closed_bar
                    self._emit_bar_close(sym, closed_bar)
                self._last_bar_time[sym] = current_bar_time
            elif last_known_time is None:
                self._last_bar_time[sym] = current_bar_time

        return newly_closed_bars

    def _emit_bar_close(self, symbol: str, bar: CandleBar) -> None:
        """Dispatches bar close event to all registered subscriber callbacks."""
        logger.info(
            f"🔔 [Bar Closed] {symbol} {self.timeframe} @ {bar.dt.strftime('%H:%M:%S UTC')} | "
            f"O: {bar.open:.5f} H: {bar.high:.5f} L: {bar.low:.5f} C: {bar.close:.5f} | "
            f"Vol: {bar.tick_volume} | Spread: {bar.spread}"
        )
        for handler in self._bar_handlers:
            try:
                handler(symbol, bar, self.cache)
            except Exception as e:
                logger.error(f"Error in bar handler {handler}: {e}", exc_info=True)

    def start(self, max_iterations: Optional[int] = None) -> None:
        """Starts the continuous 1-minute polling loop."""
        self._running = True
        self.initialize_history()
        
        iteration = 0
        logger.info(f"⚡ J.A.R.V.I.S. Price Feeder is online. Monitoring {len(self.symbols)} symbols on {self.timeframe}...")

        try:
            while self._running:
                iteration += 1
                self.poll_once()

                if max_iterations is not None and iteration >= max_iterations:
                    logger.info(f"Reached max iterations limit ({max_iterations}). Stopping feeder.")
                    break

                # Sleep interval
                if self.align_to_minute_close and self.timeframe == "M1":
                    # Sleep short intervals to catch the top of the minute precisely
                    time.sleep(self.poll_interval_sec)
                else:
                    time.sleep(self.poll_interval_sec)

        except KeyboardInterrupt:
            logger.info("J.A.R.V.I.S. Price Feeder received interrupt signal. Shutting down...")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stops the feeder engine and closes MT5 connection."""
        self._running = False
        self.connector.disconnect()
        logger.info("J.A.R.V.I.S. Price Feeder stopped.")
