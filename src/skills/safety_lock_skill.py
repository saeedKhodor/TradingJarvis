# === CODE INDEX ===
# 1. Imports & Constants (Line 16)
# 2. SafetyLockSkill.__init__() - Initializes state machine and parameters (Line 30)
# 3. SafetyLockSkill.check_cascade_condition() - Validates H1 Close < 9-EMA < 21-EMA < 50-EMA (Line 60)
# 4. SafetyLockSkill.check_ema_interaction() - Detects pullback touches to H1 or 30M 9-EMA (Line 95)
# 5. SafetyLockSkill.evaluate() - Main evaluation entry point for market state (Line 130)
# 6. SafetyLockSkill.reset() - Resets state and alert timestamps (Line 190)
# =================

import time
import logging
from typing import Optional, Dict, Any

from .base_skill import BaseSkill, MarketState, SkillResult

logger = logging.getLogger("TradingJarvis.Skill.SafetyLock")


class SafetyLockSkill(BaseSkill):
    """
    Safety Lock (Bearish Cascade Sentinel) Skill.
    Condition: H1 Close < H1 9-EMA < H1 21-EMA < H1 50-EMA
    When active: Enforces 'LOCKED IN CASH' defensive posture.
    Alerts:
      1. Cascade Initialization & Release.
      2. Price Retest / Interaction with H1 9-EMA during cascade.
      3. Price Retest / Interaction with 30M 9-EMA during cascade.
    """

    def __init__(
        self,
        name: str = "SafetyLock_Cascade",
        retest_tolerance_pts: float = 2.0,
        retest_cooldown_sec: int = 900  # 15 min cooldown between same-level retest alerts
    ):
        super().__init__(name=name, enabled=True)
        self.retest_tolerance_pts = retest_tolerance_pts
        self.retest_cooldown_sec = retest_cooldown_sec

        # State tracking
        self.is_locked_in_cash: bool = False
        self.last_h1_retest_alert: float = 0.0
        self.last_m30_retest_alert: float = 0.0
        self.last_status_str: str = "NORMAL"

    def check_cascade_condition(self, state: MarketState) -> Optional[bool]:
        """
        Evaluates the bearish cascade:
        H1 Close < H1 9-EMA < H1 21-EMA < H1 50-EMA
        """
        h1_ema9 = state.get_ema("H1")
        h1_ema21 = state.get_ema("H1_EMA21")
        h1_ema50 = state.get_ema("H1_EMA50")
        current_price = state.price

        if h1_ema9 is None or h1_ema21 is None or h1_ema50 is None:
            # Insufficient MT5 native indicator data
            return None

        # Verify strict descending hierarchy: Price < EMA9 < EMA21 < EMA50
        is_cascade = (current_price < h1_ema9) and (h1_ema9 < h1_ema21) and (h1_ema21 < h1_ema50)
        return is_cascade

    def check_ema_interaction(
        self,
        bar_high: float,
        bar_low: float,
        target_ema: float
    ) -> bool:
        """
        Returns True if the candlestick bar high/low intersected or came within tolerance of target EMA.
        """
        if target_ema is None or target_ema <= 0:
            return False

        # Check if the candle physically touched or penetrated the EMA, or came within tolerance points
        penetrated = (bar_high >= target_ema - self.retest_tolerance_pts) and (bar_low <= target_ema + self.retest_tolerance_pts)
        return penetrated

    def evaluate(self, state: MarketState) -> Optional[SkillResult]:
        """Evaluates cascade condition and interaction alerts on H1/30M 9-EMA."""
        if not self.enabled:
            return None

        is_cascade = self.check_cascade_condition(state)
        if is_cascade is None:
            return None

        current_time = time.time()
        bar = state.latest_bar
        h1_ema9 = state.get_ema("H1")
        h1_ema21 = state.get_ema("H1_EMA21")
        h1_ema50 = state.get_ema("H1_EMA50")
        m30_ema9 = state.get_ema("M30")

        # --- Transition 1: Cascade Initialized (LOCKED IN CASH)
        if is_cascade and not self.is_locked_in_cash:
            self.is_locked_in_cash = True
            self.last_status_str = "LOCKED_IN_CASH"
            
            msg = (
                f"<b>Status:</b> <code>LOCKED IN CASH (DEFENSIVE POSTURE)</code>\n"
                f"<b>Instrument:</b> <code>{state.symbol}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🛑 <b>Cascade Hierarchy Confirmed:</b>\n"
                f"• Current Price : <code>{state.price:.2f}</code>\n"
                f"• H1 9-EMA      : <code>{h1_ema9:.2f}</code>\n"
                f"• H1 21-EMA     : <code>{h1_ema21:.2f}</code>\n"
                f"• H1 50-EMA     : <code>{h1_ema50:.2f}</code>\n\n"
                f"💡 <i>Sir, all long entries are prohibited. Capital is locked in cash.</i>"
            )
            return SkillResult(
                skill_name=self.name,
                alert_type="SAFETY_LOCK_ENGAGED",
                title="🚨 SAFETY LOCK ENGAGED | LOCKED IN CASH",
                message=msg,
                should_notify=True,
                severity="CRITICAL",
                metadata={"state": "LOCKED_IN_CASH", "price": state.price, "h1_ema9": h1_ema9}
            )

        # --- Transition 2: Cascade Broken / Released
        if not is_cascade and self.is_locked_in_cash:
            self.is_locked_in_cash = False
            self.last_status_str = "NORMAL"

            msg = (
                f"<b>Status:</b> <code>SAFETY LOCK RELEASED</code>\n"
                f"<b>Instrument:</b> <code>{state.symbol}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"• Current Price : <code>{state.price:.2f}</code>\n"
                f"• H1 9-EMA      : <code>{h1_ema9:.2f}</code>\n\n"
                f"💡 <i>Sir, the H1 bearish cascade structure has broken. Normal evaluation resumed.</i>"
            )
            return SkillResult(
                skill_name=self.name,
                alert_type="SAFETY_LOCK_RELEASED",
                title="🟢 SAFETY LOCK RELEASED",
                message=msg,
                should_notify=True,
                severity="NOTICE",
                metadata={"state": "NORMAL", "price": state.price}
            )

        # --- Sub-Events: Price Retests H1 9-EMA or 30M 9-EMA while in Cascade
        if self.is_locked_in_cash:
            # Check H1 9-EMA Retest
            if h1_ema9 and self.check_ema_interaction(bar.high, bar.low, h1_ema9):
                if current_time - self.last_h1_retest_alert >= self.retest_cooldown_sec:
                    self.last_h1_retest_alert = current_time
                    msg = (
                        f"<b>Advisory:</b> <code>PULLBACK TEST AT H1 9-EMA</code>\n"
                        f"<b>Instrument:</b> <code>{state.symbol}</code>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🎯 <b>Price / H1 9-EMA:</b> <code>{state.price:.2f}</code> / <code>{h1_ema9:.2f}</code>\n"
                        f"📊 <b>Cascade Status:</b> <code>LOCKED IN CASH</code>\n"
                        f"🛑 <b>H1 21 / 50 EMAs:</b> <code>{h1_ema21:.2f}</code> / <code>{h1_ema50:.2f}</code>\n\n"
                        f"💡 <i>Sir, price is testing the H1 9-EMA resistance during the bearish cascade.</i>"
                    )
                    return SkillResult(
                        skill_name=self.name,
                        alert_type="CASCADE_RETEST_H1_EMA9",
                        title="⚠️ CASCADE RETEST: H1 9-EMA INTERACTION",
                        message=msg,
                        should_notify=True,
                        severity="WARNING",
                        metadata={"level": "H1_EMA9", "price": state.price, "h1_ema9": h1_ema9}
                    )

            # Check 30M 9-EMA Retest
            if m30_ema9 and self.check_ema_interaction(bar.high, bar.low, m30_ema9):
                if current_time - self.last_m30_retest_alert >= self.retest_cooldown_sec:
                    self.last_m30_retest_alert = current_time
                    msg = (
                        f"<b>Advisory:</b> <code>PULLBACK TEST AT 30M 9-EMA</code>\n"
                        f"<b>Instrument:</b> <code>{state.symbol}</code>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🎯 <b>Price / 30M 9-EMA:</b> <code>{state.price:.2f}</code> / <code>{m30_ema9:.2f}</code>\n"
                        f"📊 <b>Cascade Status:</b> <code>LOCKED IN CASH</code>\n\n"
                        f"💡 <i>Sir, price is interacting with the 30M 9-EMA resistance within the cascade.</i>"
                    )
                    return SkillResult(
                        skill_name=self.name,
                        alert_type="CASCADE_RETEST_M30_EMA9",
                        title="⚠️ CASCADE RETEST: 30M 9-EMA INTERACTION",
                        message=msg,
                        should_notify=True,
                        severity="WARNING",
                        metadata={"level": "M30_EMA9", "price": state.price, "m30_ema9": m30_ema9}
                    )

        return None

    def get_status(self, state: Optional[MarketState] = None) -> Dict[str, Any]:
        """Returns deep diagnostic telemetry for Safety Lock cascade state and retest proximity."""
        data = {
            "name": self.name,
            "enabled": self.enabled,
            "is_locked_in_cash": self.is_locked_in_cash,
            "status_str": self.last_status_str,
            "retest_tolerance_pts": self.retest_tolerance_pts,
            "retest_cooldown_sec": self.retest_cooldown_sec
        }

        if state:
            h1_ema9 = state.get_ema("H1")
            h1_ema21 = state.get_ema("H1_EMA21")
            h1_ema50 = state.get_ema("H1_EMA50")
            m30_ema9 = state.get_ema("M30")
            price = state.price

            data["price"] = price
            data["h1_ema9"] = h1_ema9
            data["h1_ema21"] = h1_ema21
            data["h1_ema50"] = h1_ema50
            data["m30_ema9"] = m30_ema9

            # Cascade condition check
            is_cascade = self.check_cascade_condition(state)
            data["cascade_active"] = is_cascade

            # Proximity calculations
            if h1_ema9:
                data["dist_to_h1_9"] = round(price - h1_ema9, 2)
            if m30_ema9:
                data["dist_to_m30_9"] = round(price - m30_ema9, 2)

        return data

    def reset(self) -> None:
        """Resets state machine."""
        self.is_locked_in_cash = False
        self.last_h1_retest_alert = 0.0
        self.last_m30_retest_alert = 0.0
        self.last_status_str = "NORMAL"
