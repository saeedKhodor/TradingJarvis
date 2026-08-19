# === CODE INDEX ===
# 1. Imports & CandleBar Data Structure (Line 16)
# 2. PriceCache.__init__() - Initializes cache collections and capacity limits (Line 48)
# 3. PriceCache.update_bars() - Ingests multiple OHLCV bar records (Line 63)
# 4. PriceCache.update_single_bar() - Ingests or updates a single bar (Line 84)
# 5. PriceCache.get_bars() - Retrieves rolling candle history for a symbol (Line 104)
# 6. PriceCache.get_latest_bar() - Returns the most recent candle in memory (Line 115)
# 7. PriceCache.get_ema() - Calculates Exponential Moving Average on buffered closes (Line 124)
# 8. PriceCache.get_atr() - Calculates Average True Range for volatility telemetry (Line 146)
# 9. PriceCache.get_high_low() - Retrieves highest high and lowest low over lookback (Line 175)
# =================

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("TradingJarvis.PriceCache")


@dataclass
class CandleBar:
    """Represents a single candlestick bar with OHLCV data."""
    time: int
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    spread: int
    real_volume: int = 0

    @property
    def dt(self) -> datetime:
        """Returns UTC datetime representation of bar time."""
        return datetime.fromtimestamp(self.time, tz=timezone.utc)

    @property
    def range_size(self) -> float:
        """Total high-low range of the bar."""
        return round(self.high - self.low, 6)

    @property
    def body_size(self) -> float:
        """Absolute body size (close - open)."""
        return round(abs(self.close - self.open), 6)

    @property
    def is_bullish(self) -> bool:
        """True if close > open."""
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        """True if close < open."""
        return self.close < self.open


class PriceCache:
    """Maintains an in-memory rolling time-series buffer of candle bars per symbol."""

    def __init__(self, buffer_depth: int = 200):
        self.buffer_depth = buffer_depth
        self._cache: Dict[str, deque] = {}

    def _get_queue(self, symbol: str) -> deque:
        """Returns or creates the ring buffer for a given symbol."""
        if symbol not in self._cache:
            self._cache[symbol] = deque(maxlen=self.buffer_depth)
        return self._cache[symbol]

    def update_bars(self, symbol: str, bars_data: List[Dict]) -> int:
        """
        Updates the cache with a list of bar dictionaries.
        Preserves chronological ordering and prevents duplicate timestamps.
        """
        q = self._get_queue(symbol)
        count = 0
        for b in bars_data:
            bar = CandleBar(
                time=b["time"],
                open=b["open"],
                high=b["high"],
                low=b["low"],
                close=b["close"],
                tick_volume=b.get("tick_volume", 0),
                spread=b.get("spread", 0),
                real_volume=b.get("real_volume", 0)
            )
            if self.update_single_bar(symbol, bar):
                count += 1
        return count

    def update_single_bar(self, symbol: str, bar: CandleBar) -> bool:
        """
        Inserts a new bar or updates the current forming bar if timestamp matches.
        """
        q = self._get_queue(symbol)
        if len(q) > 0 and q[-1].time == bar.time:
            # Overwrite forming bar with latest price ticks
            q[-1] = bar
            return False
        elif len(q) > 0 and bar.time < q[-1].time:
            # Historical bar out of order, ignore
            return False
        else:
            q.append(bar)
            return True

    def get_bars(self, symbol: str, count: Optional[int] = None) -> List[CandleBar]:
        """Retrieves list of bars in chronological order (oldest -> newest)."""
        q = self._get_queue(symbol)
        bars = list(q)
        if count is not None and count > 0:
            return bars[-count:]
        return bars

    def get_latest_bar(self, symbol: str) -> Optional[CandleBar]:
        """Returns the most recent bar for a symbol."""
        q = self._get_queue(symbol)
        return q[-1] if len(q) > 0 else None

    def get_previous_bar(self, symbol: str) -> Optional[CandleBar]:
        """Returns the completed bar immediately preceding the latest."""
        q = self._get_queue(symbol)
        return q[-2] if len(q) >= 2 else None

    def get_ema(self, symbol: str, period: int = 14) -> Optional[float]:
        """Calculates Exponential Moving Average on buffered close prices."""
        bars = self.get_bars(symbol)
        if len(bars) < period:
            return None

        closes = [b.close for b in bars]
        # Initial SMA
        sma = sum(closes[:period]) / period
        multiplier = 2 / (period + 1)
        
        ema = sma
        for close in closes[period:]:
            ema = (close - ema) * multiplier + ema

        return round(ema, 6)

    def get_atr(self, symbol: str, period: int = 14) -> Optional[float]:
        """Calculates Average True Range (ATR) on buffered bars."""
        bars = self.get_bars(symbol)
        if len(bars) <= period:
            return None

        true_ranges = []
        for i in range(1, len(bars)):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i - 1].close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)

        if len(true_ranges) < period:
            return None

        # Simple average of TR for the last N periods
        atr = sum(true_ranges[-period:]) / period
        return round(atr, 6)

    def get_high_low(self, symbol: str, lookback: int = 20) -> Tuple[Optional[float], Optional[float]]:
        """Returns the highest high and lowest low over the lookback window."""
        bars = self.get_bars(symbol, count=lookback)
        if not bars:
            return None, None

        highest = max(b.high for b in bars)
        lowest = min(b.low for b in bars)
        return highest, lowest
