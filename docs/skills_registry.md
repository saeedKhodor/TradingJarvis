# J.A.R.V.I.S. Skills & Features Registry

This registry documents all active, in-development, and planned trading skills for J.A.R.V.I.S.

---

## 🏛️ Active Skills

### 1. `SafetyLock_Cascade` (Skill ID: `SKILL-01`)
- **File**: [`src/skills/safety_lock_skill.py`](../src/skills/safety_lock_skill.py)
- **Primary Instrument**: `US500.cash`
- **Core Condition**:
  $$\text{H1 Close} < \text{H1 9-EMA} < \text{H1 21-EMA} < \text{H1 50-EMA}$$
- **Behavior & Actions**:
  - Sets strategy state to **`LOCKED IN CASH`** (defensive lock, long trades prohibited).
  - Emits `🚨 SAFETY LOCK ENGAGED` upon cascade confirmation.
  - Emits `⚠️ CASCADE RETEST: H1 9-EMA INTERACTION` when price pulls back to H1 9-EMA during cascade.
  - Emits `⚠️ CASCADE RETEST: 30M 9-EMA INTERACTION` when price pulls back to 30M 9-EMA during cascade.
  - Emits `🟢 SAFETY LOCK RELEASED` when price breaks above H1 9-EMA.
- **Anti-Spam Controls**: 15-minute cooldown between repetitive retest notifications.
- **Test Suite**: [`tests/test_safety_lock_skill.py`](../tests/test_safety_lock_skill.py) (All 4 unit tests passing).

---

## 🏗️ Core Infrastructure & Telemetry Subsystems

| Module | Location | Purpose |
| :--- | :--- | :--- |
| **MT5 Connector** | [`src/feed/mt5_connector.py`](../src/feed/mt5_connector.py) | IPC connection to MetaTrader 5, terminal health, Market Watch, native indicator ingestion. |
| **Price Cache** | [`src/feed/price_cache.py`](../src/feed/price_cache.py) | In-memory 200-bar rolling ring buffer with on-the-fly EMA and ATR calculations. |
| **Price Feeder** | [`src/feed/price_feeder.py`](../src/feed/price_feeder.py) | Ingestion daemon synchronized to minute bar close boundaries. |
| **Skill Arbiter** | [`src/engine/arbiter.py`](../src/engine/arbiter.py) | Central brain coordinating all registered skills, filtering noise, and dispatching Telegram alerts. |
| **Telegram Dispatcher** | [`.agents/skills/trading-jarvis/scripts/telegram_notifier.py`](../.agents/skills/trading-jarvis/scripts/telegram_notifier.py) | Formats and dispatches J.A.R.V.I.S. Telegram messages with HTML parse mode and status icons. |
| **MQL5 Native Bridge** | [`mql5/TradingJarvisBridge.mq5`](../mql5/TradingJarvisBridge.mq5) | Native MT5 Expert Advisor creating `iMA()` handles for M1–D1 9-EMAs + H1 21/50-EMAs and streaming to Common Files. |
| **One-Click Launcher** | [`run_jarvis.bat`](../run_jarvis.bat) | Windows batch script with UTF-8 support to launch the background sentinel daemon. |

---

## 🔮 Roadmap Skills Backlog

1. **`BullishTrend_Ribbon` (SKILL-02)**:
   - Condition: $\text{Price} > \text{M5 9-EMA} > \text{M15 9-EMA} > \text{H1 9-EMA}$.
   - Action: Pre-arms long entry bias.
2. **`CandleRejection_Trigger` (SKILL-03)**:
   - Condition: M1 pinbar rejection off M5/M15 9-EMA with above-average tick volume.
   - Action: Computes Entry, Stop Loss, Take Profit, and R:R ratio for Telegram execution alert.
3. **`Risk_Sentinel` (SKILL-04)**:
   - Condition: Daily floating drawdown exceeds threshold (e.g. 2.5%) or spread widens past max tolerance.
   - Action: Issues emergency risk alert and stops new orders.
