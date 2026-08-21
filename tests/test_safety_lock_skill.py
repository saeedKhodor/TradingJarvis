# === CODE INDEX ===
# 1. Imports & Test Setup (Line 12)
# 2. test_safety_lock_cascade_engagement() - Tests cascade condition detection (Line 25)
# 3. test_safety_lock_h1_retest() - Tests H1 9-EMA pullback touch alert (Line 60)
# 4. test_safety_lock_m30_retest() - Tests 30M 9-EMA pullback touch alert (Line 85)
# 5. test_safety_lock_release() - Tests recovery and lock release (Line 110)
# 6. main() - Runs all unit tests (Line 135)
# =================

import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.price_cache import PriceCache, CandleBar
from src.skills.base_skill import MarketState
from src.skills.safety_lock_skill import SafetyLockSkill


class TestSafetyLockSkill(unittest.TestCase):

    def setUp(self):
        self.skill = SafetyLockSkill(retest_tolerance_pts=2.0, retest_cooldown_sec=10)
        self.cache = PriceCache(buffer_depth=50)

    def test_safety_lock_cascade_engagement(self):
        """Test that Price < H1_9 < H1_21 < H1_50 triggers LOCKED IN CASH."""
        bar = CandleBar(time=1700000000, open=7680.0, high=7682.0, low=7675.0, close=7678.0, tick_volume=10, spread=50)
        
        # Cascade hierarchy: Price (7678) < H1_9 (7690) < H1_21 (7700) < H1_50 (7720)
        state = MarketState(
            symbol="US500.cash",
            timestamp=bar.time,
            time_str="2026-08-19 11:00:00 UTC",
            latest_bar=bar,
            cache=self.cache,
            mt5_emas={
                "H1": 7690.0,
                "H1_EMA21": 7700.0,
                "H1_EMA50": 7720.0,
                "M30": 7685.0
            }
        )

        result = self.skill.evaluate(state)
        self.assertIsNotNone(result)
        self.assertEqual(result.alert_type, "SAFETY_LOCK_ENGAGED")
        self.assertEqual(result.severity, "CRITICAL")
        self.assertTrue(self.skill.is_locked_in_cash)
        print("[+] Test 1 Passed: Safety Lock successfully engaged on bearish cascade.")

    def test_safety_lock_h1_retest(self):
        """Test that pullback touching H1 9-EMA triggers retest advisory."""
        # First engage lock
        bar1 = CandleBar(time=1700000000, open=7680.0, high=7682.0, low=7675.0, close=7678.0, tick_volume=10, spread=50)
        state1 = MarketState(
            symbol="US500.cash",
            timestamp=bar1.time,
            time_str="2026-08-19 11:00:00 UTC",
            latest_bar=bar1,
            cache=self.cache,
            mt5_emas={"H1": 7690.0, "H1_EMA21": 7700.0, "H1_EMA50": 7720.0, "M30": 7685.0}
        )
        self.skill.evaluate(state1)

        # Pullback bar touches H1 9-EMA (High: 7690.5, H1_9: 7690.0)
        bar2 = CandleBar(time=1700000060, open=7685.0, high=7690.5, low=7684.0, close=7688.0, tick_volume=15, spread=50)
        state2 = MarketState(
            symbol="US500.cash",
            timestamp=bar2.time,
            time_str="2026-08-19 11:01:00 UTC",
            latest_bar=bar2,
            cache=self.cache,
            mt5_emas={"H1": 7690.0, "H1_EMA21": 7700.0, "H1_EMA50": 7720.0, "M30": 7685.0}
        )
        result = self.skill.evaluate(state2)
        self.assertIsNotNone(result)
        self.assertEqual(result.alert_type, "GOLDEN_POCKET_SHORT_H1")
        self.assertIn("tp1", result.metadata)
        self.assertIn("tp2", result.metadata)
        print("[+] Test 2 Passed: Golden Pocket H1 9-EMA short setup triggered.")

    def test_safety_lock_m30_retest(self):
        """Test that pullback touching 30M 9-EMA triggers Golden Pocket short setup."""
        # Engage lock
        bar1 = CandleBar(time=1700000000, open=7670.0, high=7672.0, low=7665.0, close=7668.0, tick_volume=10, spread=50)
        state1 = MarketState(
            symbol="US500.cash",
            timestamp=bar1.time,
            time_str="2026-08-19 11:00:00 UTC",
            latest_bar=bar1,
            cache=self.cache,
            mt5_emas={"H1": 7690.0, "H1_EMA21": 7700.0, "H1_EMA50": 7720.0, "M30": 7675.0}
        )
        self.skill.evaluate(state1)

        # Pullback bar touches 30M 9-EMA (High: 7675.5, M30_9: 7675.0)
        bar2 = CandleBar(time=1700000060, open=7670.0, high=7675.5, low=7668.0, close=7672.0, tick_volume=15, spread=50)
        state2 = MarketState(
            symbol="US500.cash",
            timestamp=bar2.time,
            time_str="2026-08-19 11:01:00 UTC",
            latest_bar=bar2,
            cache=self.cache,
            mt5_emas={"H1": 7690.0, "H1_EMA21": 7700.0, "H1_EMA50": 7720.0, "M30": 7675.0}
        )
        result = self.skill.evaluate(state2)
        self.assertIsNotNone(result)
        self.assertEqual(result.alert_type, "GOLDEN_POCKET_SHORT_M30")
        self.assertIn("tp1", result.metadata)
        print("[+] Test 3 Passed: Golden Pocket 30M 9-EMA short setup triggered.")

    def test_safety_lock_release(self):
        """Test that breaking above H1 9-EMA releases safety lock."""
        # Engage lock
        bar1 = CandleBar(time=1700000000, open=7680.0, high=7682.0, low=7675.0, close=7678.0, tick_volume=10, spread=50)
        state1 = MarketState(
            symbol="US500.cash",
            timestamp=bar1.time,
            time_str="2026-08-19 11:00:00 UTC",
            latest_bar=bar1,
            cache=self.cache,
            mt5_emas={"H1": 7690.0, "H1_EMA21": 7700.0, "H1_EMA50": 7720.0, "M30": 7685.0}
        )
        self.skill.evaluate(state1)
        self.assertTrue(self.skill.is_locked_in_cash)

        # Price breaks above H1 9-EMA (Close: 7695.0 > H1_9: 7690.0)
        bar2 = CandleBar(time=1700000060, open=7688.0, high=7698.0, low=7686.0, close=7695.0, tick_volume=20, spread=50)
        state2 = MarketState(
            symbol="US500.cash",
            timestamp=bar2.time,
            time_str="2026-08-19 11:01:00 UTC",
            latest_bar=bar2,
            cache=self.cache,
            mt5_emas={"H1": 7690.0, "H1_EMA21": 7700.0, "H1_EMA50": 7720.0, "M30": 7685.0}
        )
        result = self.skill.evaluate(state2)
        self.assertIsNotNone(result)
        self.assertEqual(result.alert_type, "SAFETY_LOCK_RELEASED")
        self.assertFalse(self.skill.is_locked_in_cash)
        print("[+] Test 4 Passed: Safety lock successfully released when cascade breaks.")


if __name__ == "__main__":
    unittest.main()
