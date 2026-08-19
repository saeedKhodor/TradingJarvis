# J.A.R.V.I.S. Core Tasks & Architectural Blueprint

This document outlines the core task modules for J.A.R.V.I.S., their execution cycles, inputs, and outputs.

---

## 1. Task Roster & Execution Matrix

| Task ID | Module | Trigger / Schedule | Input Source | Output Action |
| :--- | :--- | :--- | :--- | :--- |
| **TASK-01** | `Signal Dispatcher` | Real-time event / Hook | Indicator / EA / Webhook | Formatted TG Signal Alert (`📈 / 📉`) |
| **TASK-02** | `Risk Sentinel` | Continuous polling / Per trade | Account balance / Drawdown % | TG Risk Warning / Trading Halt (`🚨`) |
| **TASK-03** | `Session Briefing` | Fixed Cron (e.g. London / NY Open) | Calendar API / Balance summary | TG Market Briefing (`🌐`) |
| **TASK-04** | `Trade Journal & Audit` | On Position Close | Broker History API | TG PnL Notification + Local CSV/JSON Log |
| **TASK-05** | `System Heartbeat` | Hourly Cron | API Ping / Connectivity status | TG Health Status (`⚙️`) |

---

## 2. Data Flow Architecture

```mermaid
flowchart TD
    Strategy[Quantitative Strategy / Indicator / EA] -->|Trade Signal| Task01[TASK-01: Signal Dispatcher]
    Broker[MetaTrader / Broker API] -->|Equity & Positions| Task02[TASK-02: Risk Sentinel]
    Broker -->|Fills & Closes| Task04[TASK-04: Trade Audit]
    Calendar[Economic Calendar / News Feed] -->|Macro Events| Task03[TASK-03: Session Briefing]

    Task01 --> Notifier[telegram_notifier.py]
    Task02 --> Notifier
    Task03 --> Notifier
    Task04 --> Notifier
    Task05[TASK-05: Heartbeat] --> Notifier

    Notifier -->|HTTPS POST| TelegramAPI[Telegram Bot API]
    TelegramAPI -->|Push Notification| TelegramUser[User Device / Channel]
```

---

## 3. Portability Checklist

When transferring this workspace to another server, VPS, or cloud container:
- [ ] Python 3.8+ installed (zero mandatory external dependencies; standard library `urllib` is supported out-of-the-box).
- [ ] `.agents/skills/trading-jarvis/` folder present in workspace root.
- [ ] `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` set in `.env` or `telegram_config.json`.
- [ ] Connectivity verified via `python .agents/skills/trading-jarvis/scripts/test_alert.py`.
