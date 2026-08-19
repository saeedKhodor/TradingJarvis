# === CODE INDEX ===
# 1. Imports & Constants (Line 18)
# 2. MT5Connector.__init__() - Initializes connector state and config (Line 50)
# 3. MT5Connector.connect() - Initializes MT5 terminal connection and logs in if needed (Line 74)
# 4. MT5Connector.disconnect() - Shuts down MT5 IPC connection (Line 120)
# 5. MT5Connector.is_connected() - Verifies active terminal connection status (Line 133)
# 6. MT5Connector.get_account_info() - Retrieves account equity, balance, leverage (Line 146)
# 7. MT5Connector.ensure_symbol() - Selects symbol in Market Watch (Line 167)
# 8. MT5Connector.get_rates() - Fetches OHLCV rates for a symbol & timeframe (Line 189)
# 9. MT5Connector.get_current_tick() - Retrieves real-time bid, ask, and spread (Line 230)
# 10. MT5Connector.get_native_indicators() - Ingests native MT5 9-EMA buffers from Common Files (Line 258)
# =================

import os
import sys
import json
import logging
from typing import Optional, Dict, Any, List
import MetaTrader5 as mt5

logger = logging.getLogger("TradingJarvis.MT5Connector")


class MT5Connector:
    """Manages MetaTrader 5 terminal connection, session lifecycle, and data querying."""

    TIMEFRAME_MAP = {
        "M1": mt5.TIMEFRAME_M1,
        "M2": mt5.TIMEFRAME_M2,
        "M3": mt5.TIMEFRAME_M3,
        "M4": mt5.TIMEFRAME_M4,
        "M5": mt5.TIMEFRAME_M5,
        "M6": mt5.TIMEFRAME_M6,
        "M10": mt5.TIMEFRAME_M10,
        "M12": mt5.TIMEFRAME_M12,
        "M15": mt5.TIMEFRAME_M15,
        "M20": mt5.TIMEFRAME_M20,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H2": mt5.TIMEFRAME_H2,
        "H4": mt5.TIMEFRAME_H4,
        "H6": mt5.TIMEFRAME_H6,
        "H8": mt5.TIMEFRAME_H8,
        "H12": mt5.TIMEFRAME_H12,
        "D1": mt5.TIMEFRAME_D1,
        "W1": mt5.TIMEFRAME_W1,
        "MN1": mt5.TIMEFRAME_MN1,
    }

    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self._connected = False

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """Loads configuration from JSON file or defaults."""
        if not config_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config_path = os.path.join(base_dir, "config", "trading_config.json")
            if not os.path.exists(config_path):
                config_path = os.path.join(base_dir, "config", "trading_config.template.json")

        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load config from {config_path}: {e}")

        return {}

    def connect(self) -> bool:
        """Initializes connection to MetaTrader 5 terminal."""
        terminal_cfg = self.config.get("terminal", {})
        path = terminal_cfg.get("path")
        login = terminal_cfg.get("login")
        server = terminal_cfg.get("server")
        password = terminal_cfg.get("password")
        timeout = terminal_cfg.get("timeout_ms", 60000)

        init_kwargs = {}
        if path:
            init_kwargs["path"] = path
        if timeout:
            init_kwargs["timeout"] = timeout
        if login:
            init_kwargs["login"] = int(login)
        if server:
            init_kwargs["server"] = server
        if password:
            init_kwargs["password"] = password

        logger.info("Initializing MetaTrader 5 connection...")
        if init_kwargs:
            initialized = mt5.initialize(**init_kwargs)
        else:
            initialized = mt5.initialize()

        if not initialized:
            err_code, err_msg = mt5.last_error()
            logger.error(f"MT5 initialization failed. Error [{err_code}]: {err_msg}")
            self._connected = False
            return False

        # Verify terminal info
        t_info = mt5.terminal_info()
        if not t_info or not t_info.connected:
            logger.warning("MT5 initialized but terminal is currently disconnected from trade server.")
        
        self._connected = True
        logger.info(f"MT5 initialized successfully. Terminal: {t_info.name if t_info else 'Unknown'}")
        return True

    def disconnect(self) -> None:
        """Shuts down MT5 IPC connection."""
        if self._connected:
            mt5.shutdown()
            self._connected = False
            logger.info("MT5 connection shutdown complete.")

    def is_connected(self) -> bool:
        """Checks if terminal is active and connected."""
        if not self._connected:
            return False
        t_info = mt5.terminal_info()
        return bool(t_info and t_info.connected)

    def get_terminal_info(self) -> Optional[Dict[str, Any]]:
        """Retrieves terminal runtime metadata."""
        if not self.is_connected():
            return None
        info = mt5.terminal_info()
        return info._asdict() if info else None

    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Retrieves active account balance, equity, and margin details."""
        if not self.is_connected():
            return None
        acc = mt5.account_info()
        return acc._asdict() if acc else None

    def ensure_symbol(self, symbol: str) -> bool:
        """Ensures that a symbol is visible and selected in Market Watch."""
        if not self.is_connected():
            return False

        s_info = mt5.symbol_info(symbol)
        if s_info is None:
            logger.error(f"Symbol '{symbol}' not found in MT5 broker symbol pool.")
            return False

        if not s_info.visible:
            if not mt5.symbol_select(symbol, True):
                logger.error(f"Failed to enable symbol '{symbol}' in Market Watch.")
                return False

        return True

    def get_rates(
        self,
        symbol: str,
        count: int = 100,
        timeframe: str = "M1",
        start_pos: int = 0
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetches the latest OHLCV candle rates.
        start_pos: 0 indicates the current (forming or latest) candle.
        """
        if not self.is_connected():
            if not self.connect():
                return None

        if not self.ensure_symbol(symbol):
            return None

        tf_constant = self.TIMEFRAME_MAP.get(timeframe.upper(), mt5.TIMEFRAME_M1)
        rates = mt5.copy_rates_from_pos(symbol, tf_constant, start_pos, count)

        if rates is None or len(rates) == 0:
            err_code, err_msg = mt5.last_error()
            logger.error(f"Failed to copy rates for {symbol} ({timeframe}). Error [{err_code}]: {err_msg}")
            return None

        formatted = []
        for r in rates:
            formatted.append({
                "time": int(r["time"]),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "tick_volume": int(r["tick_volume"]),
                "spread": int(r["spread"]),
                "real_volume": int(r["real_volume"])
            })

        return formatted

    def get_current_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Retrieves latest real-time tick info for a symbol."""
        if not self.is_connected():
            if not self.connect():
                return None

        if not self.ensure_symbol(symbol):
            return None

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None

        s_info = mt5.symbol_info(symbol)
        point = s_info.point if s_info else 0.00001
        spread = (tick.ask - tick.bid) / point if point > 0 else 0

        return {
            "symbol": symbol,
            "time": int(tick.time),
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "last": float(tick.last),
            "volume": int(tick.volume),
            "spread_points": round(spread, 1)
        }

    def get_common_files_path(self) -> Optional[str]:
        """Returns the MT5 Common/Files directory path."""
        t_info = self.get_terminal_info()
        if t_info and "commondata_path" in t_info:
            return os.path.join(t_info["commondata_path"], "Files")
        # Standard fallback path on Windows
        appdata = os.environ.get("APPDATA")
        if appdata:
            return os.path.join(appdata, "MetaQuotes", "Terminal", "Common", "Files")
        return None

    def get_native_indicators(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Reads native 9-EMA indicator buffer data directly exported by TradingJarvisBridge in MT5.
        """
        common_files = self.get_common_files_path()
        if not common_files or not os.path.exists(common_files):
            return None

        # Look for symbol-specific file first, then general file
        sym_file = os.path.join(common_files, f"jarvis_indicators_{symbol}.json")
        gen_file = os.path.join(common_files, "jarvis_indicators.json")

        target_file = sym_file if os.path.exists(sym_file) else (gen_file if os.path.exists(gen_file) else None)
        if not target_file:
            return None

        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("symbol") == symbol or not symbol:
                    return data
        except Exception as e:
            logger.debug(f"Failed to read native indicators from {target_file}: {e}")

        return None

