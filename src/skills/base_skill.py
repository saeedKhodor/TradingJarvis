# === CODE INDEX ===
# 1. Imports & Dataclass Definitions (Line 16)
# 2. MarketState - Structured container for market bar and indicator telemetry (Line 26)
# 3. SkillResult - Standardized output from individual skill evaluation (Line 60)
# 4. BaseSkill - Abstract base class for all J.A.R.V.I.S. trading skills (Line 85)
# =================

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List

from ..feed.price_cache import PriceCache, CandleBar

logger = logging.getLogger("TradingJarvis.Skills")


@dataclass
class MarketState:
    """Structured container encapsulating real-time market data, indicators, and cache."""
    symbol: str
    timestamp: int
    time_str: str
    latest_bar: CandleBar
    cache: PriceCache
    mt5_emas: Dict[str, float] = field(default_factory=dict)
    account_info: Optional[Dict[str, Any]] = None

    @property
    def price(self) -> float:
        """Current close price of the forming or latest bar."""
        return self.latest_bar.close

    def get_ema(self, timeframe_key: str) -> Optional[float]:
        """Retrieves a specific MT5 native EMA value (e.g. 'H1', 'M30', 'H1_EMA21')."""
        return self.mt5_emas.get(timeframe_key)


@dataclass
class SkillResult:
    """Standardized result returned by a trading skill evaluation."""
    skill_name: str
    alert_type: str
    title: str
    message: str
    should_notify: bool = False
    severity: str = "INFO"  # INFO, NOTICE, WARNING, CRITICAL, EMERGENCY
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseSkill(ABC):
    """Abstract base class for all J.A.R.V.I.S. specialist trading skills."""

    def __init__(self, name: str, enabled: bool = True):
        self.name = name
        self.enabled = enabled
        self.logger = logging.getLogger(f"TradingJarvis.Skill.{name}")

    @abstractmethod
    def evaluate(self, state: MarketState) -> Optional[SkillResult]:
        """
        Evaluates the current market state and returns a SkillResult if an action or alert is warranted.
        """
        pass

    def get_status(self, state: Optional[MarketState] = None) -> Dict[str, Any]:
        """Returns diagnostic status and metric values for this skill."""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "status": "ARMED" if self.enabled else "DISABLED"
        }

    def reset(self) -> None:
        """Resets internal state machines if needed."""
        pass
