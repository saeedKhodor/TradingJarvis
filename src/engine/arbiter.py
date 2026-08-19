# === CODE INDEX ===
# 1. Imports & Initialization (Line 16)
# 2. SkillArbiter.__init__() - Initializes skills pool and notification handlers (Line 30)
# 3. SkillArbiter.register_skill() - Adds a new trading skill to the evaluator pool (Line 48)
# 4. SkillArbiter.process_market_bar() - Builds MarketState and executes all skills (Line 60)
# 5. SkillArbiter.dispatch_alert() - Formats and sends skill result to Telegram (Line 105)
# =================

import os
import sys
import time
import logging
from typing import List, Optional, Dict, Any

from ..feed.price_cache import PriceCache, CandleBar
from ..feed.mt5_connector import MT5Connector
from ..skills.base_skill import BaseSkill, MarketState, SkillResult

# Telegram Notifier Import
SKILL_SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".agents", "skills", "trading-jarvis", "scripts"
)
if SKILL_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SKILL_SCRIPTS_DIR)

try:
    from telegram_notifier import send_raw_telegram_message, format_jarvis_message
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False

logger = logging.getLogger("TradingJarvis.Arbiter")


class SkillArbiter:
    """Coordinates and evaluates multiple specialized trading skills per market bar close."""

    def __init__(self, connector: Optional[MT5Connector] = None, enable_telegram: bool = True):
        self.connector = connector or MT5Connector()
        self.enable_telegram = enable_telegram
        self._skills: List[BaseSkill] = []

    def register_skill(self, skill: BaseSkill) -> None:
        """Registers an evaluator skill into the active pool."""
        if skill not in self._skills:
            self._skills.append(skill)
            logger.info(f"Registered trading skill: [{skill.name}]")

    def process_market_bar(
        self,
        symbol: str,
        bar: CandleBar,
        cache: PriceCache
    ) -> List[SkillResult]:
        """
        Builds MarketState, queries MT5 native indicators, and runs all registered skills.
        """
        # Fetch native MT5 indicators
        native_data = self.connector.get_native_indicators(symbol) or {}
        mt5_emas = native_data.get("emas", {})
        account_info = self.connector.get_account_info()

        # Build standardized MarketState
        state = MarketState(
            symbol=symbol,
            timestamp=bar.time,
            time_str=bar.dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
            latest_bar=bar,
            cache=cache,
            mt5_emas=mt5_emas,
            account_info=account_info
        )

        results: List[SkillResult] = []
        for skill in self._skills:
            if not skill.enabled:
                continue
            try:
                result = skill.evaluate(state)
                if result:
                    results.append(result)
                    logger.info(f"[{skill.name}] Generated event: {result.alert_type} ({result.severity})")
                    if result.should_notify and self.enable_telegram:
                        self.dispatch_alert(result)
            except Exception as e:
                logger.error(f"Error executing skill [{skill.name}]: {e}", exc_info=True)

        return results

    def dispatch_alert(self, result: SkillResult) -> bool:
        """Transmits the skill result alert directly to Telegram."""
        if not TELEGRAM_AVAILABLE:
            logger.warning("Telegram dispatcher unavailable.")
            return False

        icon_map = {
            "INFO": "ℹ️",
            "NOTICE": "🔵",
            "WARNING": "⚠️",
            "CRITICAL": "🚨",
            "EMERGENCY": "🛑"
        }
        icon = icon_map.get(result.severity.upper(), "🛡️")

        formatted = format_jarvis_message(
            title=result.title,
            content=result.message,
            icon=icon
        )

        logger.info(f"Dispatching [{result.alert_type}] to Telegram...")
        return send_raw_telegram_message(formatted)
