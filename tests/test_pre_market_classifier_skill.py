# === CODE INDEX ===
# 1. Imports & Test Setup (Line 15)
# 2. test_cascade_day_classification() - Tests Bearish Cascade regime (Line 28)
# 3. test_bullish_expansion_classification() - Tests Bullish Expansion regime (Line 60)
# 4. test_range_sweep_classification() - Tests Range / Sweep regime (Line 90)
# 5. main() - Runs all unit tests (Line 120)
# =================

import os
import sys
import unittest
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.price_cache import PriceCache, CandleBar
from src.skills.base_skill import MarketState
from src.skills.pre_market_classifier_skill import PreMarketClassifierSkill


class TestPreMarketClassifierSkill(unittest.TestCase):

    def setUp(self):
        self.skill = PreMarketClassifierSkill(target_pts=5.0)
        self.cache = PriceCache(buffer_depth=50)

    def test_cascade_day_classification(self):
        """Test Bearish Cascade regime classification."""
        bar = CandleBar(time=1700000000, open=7680.0, high=7682.0, low=7675.0, close=7678.0, tick_volume=10, spread=50)
        state = MarketState(
            symbol="US500.cash",
            timestamp=bar.time,
            time_str="2026-08-20 13:25:00 UTC",
            latest_bar=bar,
            cache=self.cache,
            mt5_emas={
                "D1": 7750.0,
                "H1": 7705.0,
                "H1_EMA21": 7720.0,
                "H1_EMA50": 7740.0
            }
        )

        plan = self.skill.generate_daily_plan(state)
        self.assertEqual(plan["regime_code"], "CASCADE")
        self.assertEqual(plan["target_pts"], 5.0)
        self.assertIn("H1 9-EMA", plan["action"])
        print("[+] Test 1 Passed: Bearish Cascade accurately classified.")

    def test_bullish_expansion_classification(self):
        """Test Bullish Expansion regime classification."""
        bar = CandleBar(time=1700000000, open=7780.0, high=7785.0, low=7778.0, close=7782.0, tick_volume=10, spread=50)
        state = MarketState(
            symbol="US500.cash",
            timestamp=bar.time,
            time_str="2026-08-13 13:25:00 UTC",
            latest_bar=bar,
            cache=self.cache,
            mt5_emas={
                "D1": 7720.0,
                "H1": 7770.0,
                "H1_EMA21": 7750.0,
                "H1_EMA50": 7730.0
            }
        )

        plan = self.skill.generate_daily_plan(state)
        self.assertEqual(plan["regime_code"], "EXPANSION")
        self.assertEqual(plan["target_pts"], 5.0)
        self.assertIn("NY Opening Range Breakout", plan["action"])
        print("[+] Test 2 Passed: Bullish Expansion accurately classified.")

    def test_range_sweep_classification(self):
        """Test Balanced Range / Sweep regime classification."""
        bar = CandleBar(time=1700000000, open=7730.0, high=7735.0, low=7728.0, close=7732.0, tick_volume=10, spread=50)
        state = MarketState(
            symbol="US500.cash",
            timestamp=bar.time,
            time_str="2026-08-14 13:25:00 UTC",
            latest_bar=bar,
            cache=self.cache,
            mt5_emas={
                "D1": 7740.0,
                "H1": 7730.0,
                "H1_EMA21": 7731.0,
                "H1_EMA50": 7732.0
            }
        )

        plan = self.skill.generate_daily_plan(state)
        self.assertEqual(plan["regime_code"], "SWEEP_TRAP")
        self.assertEqual(plan["target_pts"], 5.0)
        self.assertIn("FADE", plan["action"])
        print("[+] Test 3 Passed: Range Sweep Trap accurately classified.")


if __name__ == "__main__":
    unittest.main()
