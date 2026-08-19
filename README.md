# TradingJarvis 🛡️⚡

**J.A.R.V.I.S. Automated Multi-Skill Quantitative Trading Assistant & Telegram Sentinel**

> *"At your service, sir. All trading systems nominal."*

---

## 📌 Overview

**TradingJarvis** is a portable, modular AI trading assistant and telemetry pipeline engineered to monitor quantitative market data from MetaTrader 5, evaluate specialized trading skills in real time, enforce risk protocols, and dispatch actionable, structured alerts to your Telegram bot ([`@Eltsstrategy_bot`](https://t.me/Eltsstrategy_bot)).

---

## 🏛️ Active Skills Roster

All specialist skills inherit from [`BaseSkill`](./src/skills/base_skill.py) and are coordinated by the [`SkillArbiter`](./src/engine/arbiter.py):

| Skill ID | Skill Name | Timeframe | Condition / Directives | Telegram Alerts |
| :--- | :--- | :--- | :--- | :--- |
| **SKILL-01** | **`SafetyLock_Cascade`** | H1, M30, M1 | $\text{H1 Close} < \text{H1 9-EMA} < \text{H1 21-EMA} < \text{H1 50-EMA}$<br/>Enforces **`LOCKED IN CASH`** mode. | `🚨 SAFETY LOCK ENGAGED`<br/>`⚠️ CASCADE RETEST: H1 9-EMA`<br/>`⚠️ CASCADE RETEST: 30M 9-EMA`<br/>`🟢 SAFETY LOCK RELEASED` |

*See full specifications in the [Master Skills Registry](./docs/skills_registry.md).*

---

## 🏗️ Core Architecture & Directory Layout

```text
TradingJarvis/
├── .agents/
│   └── skills/
│       └── trading-jarvis/
│           ├── SKILL.md                          # J.A.R.V.I.S. Persona & Skill Rules
│           ├── scripts/
│           │   ├── telegram_notifier.py          # Core Telegram Bot API Dispatcher
│           │   └── test_alert.py                 # Diagnostic Connectivity Tester
│           ├── references/                       # Schema templates & setup guides
│           └── resources/                        # Credential templates
├── config/                                       # Active & template trading configs
├── docs/
│   ├── architecture.md                           # System architecture & task matrix
│   ├── mt5_price_feed.md                         # MT5 data ingestion documentation
│   ├── skills_registry.md                        # Master skills and features registry
│   └── session_logs/                             # Session logs & conversation backups
├── mql5/
│   └── TradingJarvisBridge.mq5                   # Native MT5 Multi-Timeframe EMA Bridge
├── src/
│   ├── feed/                                     # MT5Connector, PriceCache, PriceFeeder
│   ├── skills/                                   # BaseSkill & Specialist Skills (SafetyLock)
│   └── engine/                                   # Central SkillArbiter Engine
├── scripts/
│   └── run_feed_daemon.py                        # Main CLI Runner & Telemetry Dispatcher
├── tests/
│   └── test_safety_lock_skill.py                 # Unit Test Suite
├── run_jarvis.bat                                # Windows One-Click UTF-8 Launcher
└── README.md
```

---

## 🚀 Quick Start & One-Click Execution

### 1. Configure Credentials
Copy the template configuration:
```bash
cp .agents/skills/trading-jarvis/resources/telegram_config.template.json .agents/skills/trading-jarvis/resources/telegram_config.json
```
Insert your Telegram `bot_token` and `chat_id`.

### 2. Attach Native Bridge in MT5
- In MetaTrader 5 Navigator, drag **`TradingJarvisBridge`** onto your **`US500.cash`** chart.

### 3. Launch J.A.R.V.I.S.
Double-click [**`run_jarvis.bat`**](./run_jarvis.bat) or run:
```powershell
python scripts/run_feed_daemon.py --symbols US500.cash --timeframe M1 --telegram
```

---

## 🔒 Security Protocol

- **Never commit `.env` or `telegram_config.json`** containing live Telegram Bot tokens.
- All credential files are strictly excluded via `.gitignore`.
