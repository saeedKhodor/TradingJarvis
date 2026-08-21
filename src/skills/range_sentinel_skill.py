# === CODE INDEX ===
# 1. Imports & Constants (Line 18)
# 2. TimeframeRangeData - Dataclass for per-timeframe range state (Line 35)
# 3. RangeSentinelSkill.__init__() - Initializes multi-timeframe thresholds (Line 60)
# 4. RangeSentinelSkill.analyze_timeframe() - Core mathematical range & entropy engine (Line 85)
# 5. RangeSentinelSkill.scan_all_timeframes() - Scans 4H, 1H, 30M, 15M, 5M (Line 160)
# 6. RangeSentinelSkill.evaluate() - Arbiter callback & alert dispatcher (Line 210)
# 7. RangeSentinelSkill.format_telegram_report() - Generates executive Telegram range map (Line 265)
# =================

import time
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any

import pandas as pd
import numpy as np

from .base_skill import BaseSkill, MarketState, SkillResult

logger = logging.getLogger("TradingJarvis.Skill.RangeSentinel")


@dataclass
class TimeframeRangeData:
    timeframe: str
    is_range: bool
    range_high: float
    range_low: float
    range_span_pts: float
    flip_rate_pct: float
    high_std: float
    low_std: float
    range_score: int
    price_location_pct: float
    zone_label: str
    bar_count: int
    duration_hours: float
    recent_colors: List[str] = field(default_factory=list)


class RangeSentinelSkill(BaseSkill):
    """
    Quantitative Multi-Timeframe Range & Entropy Sentinel (SKILL-04).
    Monitors 4H, 1H, 30M, 15M, and 5M compression regimes, boundary variance,
    and dispatches actionable alerts at range extremes.
    """

    def __init__(
        self,
        alert_cooldown_sec: int = 900,  # 15 min cooldown per alert
        enabled: bool = True
    ):
        super().__init__(name="RangeSentinelSkill", enabled=enabled)
        self.alert_cooldown_sec = alert_cooldown_sec
        self.last_alert_time: Dict[str, float] = {}

        # Multi-Timeframe Calibration Thresholds
        self.tf_configs = {
            "4H":  {"window": 6,  "max_span": 55.0, "min_flip": 45.0, "label": "4-Hour (4H)"},
            "1H":  {"window": 8,  "max_span": 30.0, "min_flip": 50.0, "label": "1-Hour (1H)"},
            "30M": {"window": 8,  "max_span": 22.0, "min_flip": 50.0, "label": "30-Min (30M)"},
            "15M": {"window": 8,  "max_span": 15.0, "min_flip": 50.0, "label": "15-Min (15M)"},
            "5M":  {"window": 10, "max_span": 10.0, "min_flip": 50.0, "label": "5-Min (5M)"}
        }

        self.latest_ranges: Dict[str, TimeframeRangeData] = {}

    def analyze_timeframe(self, df: pd.DataFrame, tf_key: str) -> TimeframeRangeData:
        """Computes mathematical range metrics for a specific timeframe DataFrame."""
        cfg = self.tf_configs[tf_key]
        window = cfg["window"]
        max_span = cfg["max_span"]
        min_flip = cfg["min_flip"]

        df = df.copy()
        df["color"] = np.where(df["close"] > df["open"], 1, np.where(df["close"] < df["open"], -1, 0))
        df["color_flip"] = (df["color"] != df["color"].shift(1)) & (df["color"] != 0) & (df["color"].shift(1) != 0)

        recent = df.iloc[-window:].copy()
        current_price = df.iloc[-1]["close"]

        # 1. Color Flip Entropy
        flip_count = recent["color_flip"].sum()
        flip_rate = (flip_count / max(1, window - 1)) * 100.0

        # 2. Boundary Levels & Variance
        highs = recent["high"]
        lows = recent["low"]
        range_high = float(highs.max())
        range_low  = float(lows.min())
        range_span = float(range_high - range_low)

        high_std = float(highs.std()) if len(highs) > 1 else 0.0
        low_std  = float(lows.std())  if len(lows) > 1 else 0.0

        # 3. Location % inside Range (0% = Floor, 50% = POC, 100% = Ceiling)
        if range_span > 0:
            price_location_pct = float(((current_price - range_low) / range_span) * 100.0)
        else:
            price_location_pct = 50.0

        if price_location_pct <= 15.0:
            zone_label = "🟢 DISCOUNT / FLOOR (Demand Trap Zone)"
        elif price_location_pct >= 85.0:
            zone_label = "🔴 PREMIUM / CEILING (Supply Trap Zone)"
        else:
            zone_label = "🟡 FAIR VALUE / POC (Chop Zone)"

        # 4. Range Quality Scoring (0 - 100)
        score = 0
        if flip_rate >= min_flip: score += 35
        if flip_rate >= 70.0: score += 15
        if range_span <= max_span: score += 30
        if (high_std + low_std) <= (max_span * 0.35): score += 20

        is_range = (score >= 60) and (range_span <= (max_span * 1.15))

        # Calculate approximate duration
        start_dt = recent.iloc[0]["dt"]
        end_dt   = recent.iloc[-1]["dt"]
        duration_hrs = (end_dt - start_dt).total_seconds() / 3600.0

        recent_colors = ["🟢" if c == 1 else ("🔴" if c == -1 else "⚪") for c in recent["color"].values]

        return TimeframeRangeData(
            timeframe=cfg["label"],
            is_range=is_range,
            range_high=range_high,
            range_low=range_low,
            range_span_pts=range_span,
            flip_rate_pct=flip_rate,
            high_std=high_std,
            low_std=low_std,
            range_score=score,
            price_location_pct=price_location_pct,
            zone_label=zone_label,
            bar_count=window,
            duration_hours=duration_hrs,
            recent_colors=recent_colors
        )

    def scan_all_timeframes(self, connector) -> Dict[str, TimeframeRangeData]:
        """Queries MT5 and evaluates 4H, 1H, 30M, 15M, and 5M timeframes."""
        tf_map = {
            "4H":  ("H4",  50),
            "1H":  ("H1",  100),
            "30M": ("M30", 100),
            "15M": ("M15", 150),
            "5M":  ("M5",  200)
        }

        results = {}
        for key, (mt5_tf, count) in tf_map.items():
            rates = connector.get_rates("US500.cash", count=count, timeframe=mt5_tf)
            if rates:
                df = pd.DataFrame(rates)
                df["dt"] = pd.to_datetime(df["time"], unit="s", utc=True)
                df.sort_values("dt", inplace=True)
                df.reset_index(drop=True, inplace=True)
                data = self.analyze_timeframe(df, key)
                results[key] = data
            else:
                logger.warning(f"Could not retrieve {key} rates for range scanning.")

        self.latest_ranges = results
        return results

    def evaluate(self, state: MarketState) -> Optional[SkillResult]:
        """Evaluates live market state for range boundary alerts."""
        now = time.time()
        price = state.price

        # Check if 1H or 30M ranges are active in latest scan
        h1_data = self.latest_ranges.get("1H")
        if not h1_data or not h1_data.is_range:
            return None

        # 1. Check Ceiling Test Alert (Price >= 85% near Range High)
        if h1_data.price_location_pct >= 85.0:
            last_t = self.last_alert_time.get("H1_CEILING", 0)
            if (now - last_t) >= self.alert_cooldown_sec:
                self.last_alert_time["H1_CEILING"] = now
                msg = (
                    f"🔴 *1H RANGE CEILING TEST DETECTED*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 *Symbol*: `{state.symbol}` | *Price*: `{price:.2f}`\n"
                    f"🏛️ *Range Ceiling (Supply)*: `{h1_data.range_high:.2f}`\n"
                    f"🎯 *Range Floor (Demand)*: `{h1_data.range_low:.2f}`\n"
                    f"📐 *Range Span*: `{h1_data.range_span_pts:.2f} pts` (Location: *{h1_data.price_location_pct:.1f}%*)\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💡 *Tactical Advisory*:\n"
                    f"• *VETO Long Breakouts* (High probability trap at ceiling).\n"
                    f"• Watch for M5 bearish rejection wick to fade back toward `{h1_data.range_low:.2f}`."
                )
                return SkillResult(
                    skill_name=self.name,
                    alert_type="RANGE_CEILING_TEST",
                    title=f"🔴 1H RANGE CEILING TEST: {state.symbol}",
                    message=msg,
                    should_notify=True,
                    severity="WARNING"
                )

        # 2. Check Floor Test Alert (Price <= 15% near Range Low)
        elif h1_data.price_location_pct <= 15.0:
            last_t = self.last_alert_time.get("H1_FLOOR", 0)
            if (now - last_t) >= self.alert_cooldown_sec:
                self.last_alert_time["H1_FLOOR"] = now
                msg = (
                    f"🟢 *1H RANGE FLOOR TEST DETECTED*\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 *Symbol*: `{state.symbol}` | *Price*: `{price:.2f}`\n"
                    f"🏛️ *Range Floor (Demand)*: `{h1_data.range_low:.2f}`\n"
                    f"🎯 *Range Ceiling (Supply)*: `{h1_data.range_high:.2f}`\n"
                    f"📐 *Range Span*: `{h1_data.range_span_pts:.2f} pts` (Location: *{h1_data.price_location_pct:.1f}%*)\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💡 *Tactical Advisory*:\n"
                    f"• *VETO Short Breakdowns* (High probability trap at floor).\n"
                    f"• Watch for M5 bullish hammer wick to fade back toward `{h1_data.range_high:.2f}`."
                )
                return SkillResult(
                    skill_name=self.name,
                    alert_type="RANGE_FLOOR_TEST",
                    title=f"🟢 1H RANGE FLOOR TEST: {state.symbol}",
                    message=msg,
                    should_notify=True,
                    severity="NOTICE"
                )

        return None

    def format_telegram_report(self, price: float, symbol: str = "US500.cash") -> str:
        """Renders the complete multi-timeframe range dashboard for Telegram."""
        if not self.latest_ranges:
            return "<i>Sir, range data is currently loading from MetaTrader 5...</i>"

        lines = [
            f"🏛️ <b>J.A.R.V.I.S. MULTI-TIMEFRAME RANGE RADAR</b>",
            f"━━━━━━━━━━━━━━━━━━━━",
            f"📊 <b>Symbol:</b> <code>{symbol}</code> | <b>Price:</b> <code>{price:.2f}</code>",
            f"━━━━━━━━━━━━━━━━━━━━"
        ]

        tf_order = ["4H", "1H", "30M", "15M", "5M"]
        for k in tf_order:
            d = self.latest_ranges.get(k)
            if not d:
                continue

            status_icon = "🟢" if d.is_range else "⚡"
            status_text = "ACTIVE RANGE" if d.is_range else "TREND / EXPANSION"
            
            # Progress bar visualization (10 segments)
            filled = int(round(d.price_location_pct / 10.0))
            filled = max(0, min(10, filled))
            bar_visual = "▰" * filled + "▱" * (10 - filled)

            lines.append(f"\n{status_icon} <b>{d.timeframe}</b> <code>[{status_text}]</code>")
            lines.append(f"• <b>Bounds:</b> <code>{d.range_low:.2f}</code> ── <code>{d.range_high:.2f}</code> (<b>Span:</b> <code>{d.range_span_pts:.1f} pts</code>)")
            lines.append(f"• <b>Location:</b> <code>[{bar_visual}] {d.price_location_pct:.1f}%</code>")
            lines.append(f"• <b>Colors:</b> {' '.join(d.recent_colors[-6:])} (<b>Flip:</b> <code>{d.flip_rate_pct:.0f}%</code>)")
            lines.append(f"• <b>State:</b> <i>{d.zone_label}</i>")

        lines.append(f"\n━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"🛡️ <i>Guidance: Fade range boundaries (Location &lt;15% or &gt;85%). Veto breakouts inside the POC.</i>")

        return "\n".join(lines)
