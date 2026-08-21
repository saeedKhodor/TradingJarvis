import os
import sys
import logging

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.mt5_connector import MT5Connector
from src.feed.price_cache import PriceCache
from src.skills.base_skill import MarketState
from src.skills.pre_market_classifier_skill import PreMarketClassifierSkill


def main():
    connector = MT5Connector()
    if not connector.connect():
        print("Failed to connect to MT5.")
        return

    try:
        cache = PriceCache()
        rates = connector.get_rates("US500.cash", count=100, timeframe="M5")
        cache.update_bars("US500.cash", rates)
        latest = cache.get_latest_bar("US500.cash")
        native_data = connector.get_native_indicators("US500.cash") or {}
        emas = native_data.get("emas", {})

        state = MarketState(
            symbol="US500.cash",
            timestamp=latest.time,
            time_str=latest.dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
            latest_bar=latest,
            cache=cache,
            mt5_emas=emas
        )

        skill = PreMarketClassifierSkill()
        plan = skill.generate_daily_plan(state)
        print("\n" + "=" * 80)
        print("     LIVE J.A.R.V.I.S. MORNING TACTICAL BRIEFING OUTPUT TEST")
        print("=" * 80)
        print(skill.format_telegram_briefing(plan))
        print("=" * 80 + "\n")
    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
