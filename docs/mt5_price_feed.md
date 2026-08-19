# MetaTrader 5 1-Minute (M1) Price Feed Subsystem

This document provides a technical overview of the J.A.R.V.I.S. MT5 real-time market data ingestion pipeline.

---

## 1. Overview & Components

The price feed subsystem connects directly to your local MetaTrader 5 terminal via IPC and provides a continuous stream of 1-minute candlestick bars.

```text
src/feed/
├── __init__.py           # Package exports
├── mt5_connector.py      # Terminal connection manager & safe API wrapper
├── price_cache.py        # In-memory rolling time-series buffer & indicators (EMA, ATR, High/Low)
└── price_feeder.py       # Daemon engine & bar close event dispatcher
```

---

## 2. Key Capabilities

1. **Automatic Initialization & Reconnects**:
   - `MT5Connector` handles terminal heartbeat, symbol selection in Market Watch, and auto-reconnects on disconnection.
2. **In-Memory Ring Buffer**:
   - `PriceCache` stores the latest $N$ bars (configurable, default 200 bars) per symbol in a `deque`.
   - Computes rolling EMA, ATR volatility, and range metrics on demand without redundant database queries.
3. **Synchronized Bar Close Detection**:
   - `PriceFeeder` detects the completion of each 1-minute candle, seals the historical bar, and emits `on_bar_close` events to registered strategy subscribers.
4. **Zero External Dependencies**:
   - Requires only the official `MetaTrader5` Python library and Python standard libraries.

---

## 3. Usage & CLI Examples

### Run Market Snapshot:
```powershell
python scripts/run_feed_daemon.py --snapshot
```

### Run Continuous 1-Minute Feeder:
```powershell
python scripts/run_feed_daemon.py --symbols EURUSD,GBPUSD,XAUUSD --timeframe M1
```

### Custom Symbol Watchlist in Python:
```python
from src.feed import MT5Connector, PriceCache, PriceFeeder

connector = MT5Connector()
cache = PriceCache(buffer_depth=200)
feeder = PriceFeeder(
    connector=connector,
    cache=cache,
    symbols=["EURUSD", "XAUUSD", "BTCUSD"],
    timeframe="M1"
)

# Register custom strategy callback
def on_bar(symbol, bar, cache):
    print(f"Bar closed on {symbol}: Close = {bar.close}, ATR = {cache.get_atr(symbol)}")

feeder.register_bar_handler(on_bar)
feeder.start()
```
