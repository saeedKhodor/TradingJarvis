# === CODE INDEX ===
# 1. Imports & Constants (Line 18)
# 2. PreMarketClassifierSkill.__init__() - Initializes parameters and state (Line 38)
# 3. PreMarketClassifierSkill.generate_daily_plan() - Core classification & plan formulation (Line 60)
# 4. PreMarketClassifierSkill.evaluate() - Periodic evaluation on bar close (Line 150)
# 5. PreMarketClassifierSkill.format_telegram_briefing() - Renders clean hedge fund markdown report (Line 190)
# =================

import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from .base_skill import BaseSkill, MarketState, SkillResult

logger = logging.getLogger("TradingJarvis.Skill.PreMarketClassifier")


class PreMarketClassifierSkill(BaseSkill):
    """
    Evaluates market microstructure ahead of the Wall Street Cash Open (09:25 AM EST / 13:25 UTC).
    Classifies the day into 1 of 3 institutional archetypes and provides an actionable +5.0 point harvest plan.
    """

    def __init__(
        self,
        target_pts: float = 5.0,
        pre_market_hour_utc: int = 13,
        pre_market_min_utc: int = 25,
        min_cascade_separation: float = 3.0,
        enabled: bool = True
    ):
        super().__init__(name="PreMarketClassifierSkill", enabled=enabled)
        self.target_pts = target_pts
        self.pre_market_hour_utc = pre_market_hour_utc
        self.pre_market_min_utc = pre_market_min_utc
        self.min_cascade_separation = min_cascade_separation

        self.last_dispatched_date: Optional[str] = None
        self.cached_plan: Optional[Dict[str, Any]] = None

    def generate_daily_plan(self, state: MarketState) -> Dict[str, Any]:
        """
        Performs full quantitative classification and formulates the +5.0 point tactical trade.
        """
        price = state.price
        d1_9 = state.get_ema("D1") or price
        h1_9 = state.get_ema("H1") or price
        h1_21 = state.get_ema("H1_EMA21") or price
        h1_50 = state.get_ema("H1_EMA50") or price
        m15_9 = state.get_ema("M15") or price

        # Read bars from cache to compute PDH, PDL, Overnight range
        bars = state.cache.get_bars(100)
        if len(bars) > 10:
            highs = [b.high for b in bars]
            lows = [b.low for b in bars]
            overnight_high = max(highs[-24:]) if len(highs) >= 24 else max(highs)
            overnight_low = min(lows[-24:]) if len(lows) >= 24 else min(lows)
        else:
            overnight_high = price + 10.0
            overnight_low = price - 10.0

        # Archetype Classification
        # 1. Bearish Cascade (Requires downward EMA order AND clear separation >= min_cascade_separation)
        is_cascade = (price < d1_9) and (h1_9 < h1_21) and (h1_21 < h1_50) and ((h1_21 - h1_9) >= self.min_cascade_separation)

        # 2. Bullish Trend Expansion
        is_bull_expansion = (price > d1_9) and (price > h1_9) and (h1_9 > h1_21) and ((h1_9 - h1_21) >= self.min_cascade_separation)

        if is_cascade:
            archetype = "📉 BEARISH CASCADE (MOMENTUM SHORT)"
            regime_code = "CASCADE"
            action = "SELL SHORT on H1 9-EMA Dynamic Pullback"
            entry_zone = f"{h1_9 - 1.5:.2f} - {h1_9 + 1.0:.2f}"
            invalidation_sl = round(h1_21 + 1.5, 2)
            tp_target = round(price - self.target_pts, 2)
            key_rationale = (
                f"Macro breakdown confirmed (Price < D1 9-EMA @ {d1_9:.2f}). "
                f"H1 EMAs are cascading downwards ({h1_9:.2f} < {h1_21:.2f} < {h1_50:.2f}). "
                f"Optimal execution: Short the first M5 bearish rejection off H1 9-EMA dynamic ceiling."
            )

        elif is_bull_expansion:
            archetype = "📈 BULLISH EXPANSION (MOMENTUM LONG)"
            regime_code = "EXPANSION"
            action = "BUY on 15-Minute NY Opening Range Breakout"
            entry_zone = f"Above 15-min High (approx > {overnight_high:.2f})"
            invalidation_sl = round(price - 5.0, 2)
            tp_target = round(price + self.target_pts, 2)
            key_rationale = (
                f"Macro uptrend active (Price > D1 9-EMA @ {d1_9:.2f}). "
                f"Higher-timeframe moving averages aligned upwards. "
                f"Optimal execution: Enter long on the 13:45 UTC 15-min opening range breakout."
            )

        else:
            archetype = "🔄 BALANCED RANGE (LIQUIDITY TRAP & REVERSAL)"
            regime_code = "SWEEP_TRAP"
            action = "FADE Previous High/Low Liquidity Sweeps"
            entry_zone = f"Fade sweeps above {overnight_high:.2f} or below {overnight_low:.2f}"
            invalidation_sl = round(price + 5.0, 2)
            tp_target = round(price - self.target_pts, 2)
            key_rationale = (
                f"Market is compressing inside prior value area. "
                f"Wait for London/Pre-market liquidity sweep at {overnight_high:.2f} or {overnight_low:.2f}. "
                f"Fade the false breakout back into central value for a clean +5.0 pt snapback."
            )

        plan = {
            "symbol": state.symbol,
            "timestamp": state.timestamp,
            "time_str": state.time_str,
            "price": price,
            "d1_9": d1_9,
            "h1_9": h1_9,
            "h1_21": h1_21,
            "overnight_high": overnight_high,
            "overnight_low": overnight_low,
            "archetype": archetype,
            "regime_code": regime_code,
            "action": action,
            "entry_zone": entry_zone,
            "invalidation_sl": invalidation_sl,
            "target_pts": self.target_pts,
            "tp_target": tp_target,
            "key_rationale": key_rationale
        }

        self.cached_plan = plan
        return plan

    def evaluate(self, state: MarketState) -> Optional[SkillResult]:
        """
        Evaluates incoming bar and dispatches the Pre-Market Briefing if within the 13:25 UTC window.
        """
        dt = datetime.utcfromtimestamp(state.timestamp)
        today_str = dt.strftime("%Y-%m-%d")

        # Check if we are at 13:25 UTC (09:25 AM EST) and haven't dispatched today
        is_pre_market_time = (dt.hour == self.pre_market_hour_utc) and (dt.minute >= self.pre_market_min_utc)

        if is_pre_market_time and self.last_dispatched_date != today_str:
            plan = self.generate_daily_plan(state)
            self.last_dispatched_date = today_str

            msg = self.format_telegram_briefing(plan)
            return SkillResult(
                skill_name=self.name,
                alert_type="PRE_MARKET_DAILY_PLAN",
                title=f"🏛️ J.A.R.V.I.S. MORNING BRIEFING: {plan['symbol']}",
                message=msg,
                should_notify=True,
                severity="NOTICE",
                metadata=plan
            )

        return None

    def format_telegram_briefing(self, plan: Dict[str, Any]) -> str:
        """Renders an executive hedge-fund morning game plan."""
        return (
            f"🏛️ *J.A.R.V.I.S. PRE-MARKET TACTICAL BRIEFING*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *Symbol*: `{plan['symbol']}` | *Price*: `{plan['price']:.2f}`\n"
            f"🎯 *Mission Goal*: *Extract +{plan['target_pts']:.1f} Guaranteed Index Points*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🧭 *Classified Archetype*:\n"
            f"*{plan['archetype']}*\n\n"
            f"📋 *TACTICAL PLAYBOOK*:\n"
            f"• *Strategy*: {plan['action']}\n"
            f"• *Entry Trigger Zone*: `{plan['entry_zone']}`\n"
            f"• *Invalidation Stop*: `{plan['invalidation_sl']:.2f}`\n"
            f"• *Harvest Target (+5 Pts)*: `{plan['tp_target']:.2f}`\n"
            f"• *Execution Window*: `13:45 - 14:30 UTC` (First Volume Burst)\n\n"
            f"🔬 *Institutional Thesis*:\n"
            f"_{plan['key_rationale']}_\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ *Discipline Protocol*: *Take 1 trade, lock +5.0 pts, and shut down.*"
        )
