import os
import sys
import logging

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.feed.mt5_connector import MT5Connector
from src.skills.range_sentinel_skill import RangeSentinelSkill


def main():
    connector = MT5Connector()
    if not connector.connect():
        print("[!] MT5 connection failed.")
        return

    try:
        range_skill = RangeSentinelSkill()
        results = range_skill.scan_all_timeframes(connector)
        
        rates = connector.get_rates("US500.cash", count=1, timeframe="M1")
        price = rates[0]["close"] if rates else 7668.0

        print("\n" + "=" * 80)
        print("     LIVE J.A.R.V.I.S. 5-TIMEFRAME (4H to 5M) TELEGRAM RANGE RADAR TEST")
        print("=" * 80)
        print(range_skill.format_telegram_report(price, "US500.cash"))
        print("=" * 80 + "\n")

    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
