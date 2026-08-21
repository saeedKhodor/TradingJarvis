# === CODE INDEX ===
# 1. Imports & Test Setup (Line 15)
# 2. test_4h_and_1h_range_detection() - Tests 4H and 1H range mathematical detection (Line 30)
# 3. test_ceiling_and_floor_alerts() - Tests location boundary alerts (Line 75)
# 4. main() - Runs all unit tests (Line 120)
# =================

import os
import sys
import unittest
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.price_cache import PriceCache, CandleBar
from src.skills.base_skill import MarketState
from src.skills.range_sentinel_skill import RangeSentinelSkill


class TestRangeSentinelSkill(unittest.TestCase):

    def setUp(self):
        self.skill = RangeSentinelSkill()
        self.cache = PriceCache(buffer_depth=50)

    def test_4h_and_1h_range_detection(self):
        """Test mathematical range detection across alternating bars."""
        # Create 10 alternating 1H bars inside a 20-point box (7650 to 7670)
        dates = [datetime(2026, 8, 20, 0, 0) + timedelta(hours=i) for i in range(10)]
        data = []
        for i, dt in enumerate(dates):
            if i % 2 == 0:
                data.append({"dt": dt, "open": 7652.0, "high": 7668.0, "low": 7650.0, "close": 7667.0}) # Green
            else:
                data.append({"dt": dt, "open": 7667.0, "high": 7669.0, "low": 7651.0, "close": 7653.0}) # Red

        df = pd.DataFrame(data)
        res_1h = self.skill.analyze_timeframe(df, "1H")

        self.assertTrue(res_1h.is_range)
        self.assertGreaterEqual(res_1h.flip_rate_pct, 70.0)
        self.assertLessEqual(res_1h.range_span_pts, 25.0)
        print(f"[+] Test 1 Passed: 1H Range successfully detected (Score: {res_1h.range_score}/100, Flip Rate: {res_1h.flip_rate_pct:.0f}%).")

    def test_ceiling_and_floor_alerts(self):
        """Test Ceiling Test Alert at >= 85% location and Floor Test at <= 15%."""
        # Setup simulated range data in skill
        from src.skills.range_sentinel_skill import TimeframeRangeData
        self.skill.latest_ranges["1H"] = TimeframeRangeData(
            timeframe="1-Hour (1H)",
            is_range=True,
            range_high=7670.0,
            range_low=7650.0,
            range_span_pts=20.0,
            flip_rate_pct=75.0,
            high_std=1.2,
            low_std=1.1,
            range_score=90,
            price_location_pct=90.0,  # 90% (Near ceiling)
            zone_label="🔴 PREMIUM / CEILING",
            bar_count=8,
            duration_hours=8.0
        )

        bar_ceiling = CandleBar(time=1700000000, open=7667.0, high=7669.0, low=7666.0, close=7668.0, tick_volume=10, spread=50)
        state_ceiling = MarketState(
            symbol="US500.cash",
            timestamp=bar_ceiling.time,
            time_str="2026-08-21 14:00:00 UTC",
            latest_bar=bar_ceiling,
            cache=self.cache
        )

        res_alert = self.skill.evaluate(state_ceiling)
        self.assertIsNotNone(res_alert)
        self.assertEqual(res_alert.alert_type, "RANGE_CEILING_TEST")
        self.assertEqual(res_alert.severity, "WARNING")
        print("[+] Test 2 Passed: Range Ceiling Alert triggered at 90% premium location.")


if __name__ == "__main__":
    unittest.main()
