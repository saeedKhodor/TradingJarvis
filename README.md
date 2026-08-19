# TradingJarvis 🛡️⚡

**J.A.R.V.I.S. Automated Trading Assistant & Telegram Telemetry Subsystem**

> *"At your service, sir. All trading systems nominal."*

---

## 📌 Overview

**TradingJarvis** is a portable, modular AI trading assistant and telemetry pipeline engineered to monitor quantitative trading strategies, enforce risk management protocols, and dispatch real-time, highly structured alerts directly to your Telegram channels.

---

## 🏗️ Core Architecture & Directory Layout

```text
TradingJarvis/
├── .agents/
│   └── skills/
│       └── trading-jarvis/
│           ├── SKILL.md                          # J.A.R.V.I.S. Persona & Skill Triggers
│           ├── scripts/
│           │   ├── telegram_notifier.py          # Core Telegram Bot API Dispatcher
│           │   └── test_alert.py                 # Diagnostic Connectivity Test
│           ├── references/
│           │   ├── alert_templates.md            # Standard alert schemas (HTML/Markdown)
│           │   └── telegram_setup.md             # BotFather & Chat ID setup guide
│           ├── examples/
│           │   └── sample_alerts.json            # Sample event payloads
│           └── resources/
│               ├── telegram_config.template.json # Configuration template
│               └── telegram_config.json          # Active credentials (git-ignored)
├── docs/
│   └── architecture.md                           # System design & task specifications
├── .env.example                                  # Environment variables template
├── .gitignore                                    # Secret & artifact protection
└── README.md                                     # Project overview & portable onboarding
```

---

## ⚙️ Core J.A.R.V.I.S. Tasks & Capabilities

1. **📈 Signal Telemetry (`SIGNAL_ALERT`)**:
   - Parses quantitative trade triggers (Instrument, Entry, Stop Loss, Take Profit, R:R).
   - Computes expected lot size & risk parameters before dispatching.

2. **⚡ Order & Execution Auditing (`ORDER_EXECUTED` / `POSITION_CLOSED`)**:
   - Real-time notification of trade fills, slippage, latency, and profit/loss outcomes.

3. **🚨 Proactive Risk Management (`RISK_BREACH`)**:
   - Monitors daily drawdown limits, maximum exposure, and hard account loss thresholds.
   - Issues immediate defensive advisories when risk boundaries are approached.

4. **🌐 Market Session Briefings (`SESSION_BRIEFING`)**:
   - Delivers pre-market London/New York intelligence briefings and economic calendar warnings.

5. **⚙️ Health & Telemetry Diagnostics (`SYSTEM_HEALTH`)**:
   - Regular heartbeats to ensure broker connection, latency, and data integrity.

---

## 🚀 Portability & Quick Setup on Any Machine

To clone and run TradingJarvis on any device:

### 1. Clone the Repository
```bash
git clone <YOUR_GITHUB_REPO_URL> TradingJarvis
cd TradingJarvis
```

### 2. Configure Credentials
Copy the template configuration:
```bash
cp .agents/skills/trading-jarvis/resources/telegram_config.template.json .agents/skills/trading-jarvis/resources/telegram_config.json
```
Edit `telegram_config.json` with your `@BotFather` bot token and numeric Telegram `chat_id`.

Alternatively, use environment variables:
```bash
cp .env.example .env
```

### 3. Run Diagnostic Self-Test
```bash
python .agents/skills/trading-jarvis/scripts/test_alert.py
```

---

## 🔒 Security Protocol

- **Never commit `.env` or `telegram_config.json`** containing live Telegram Bot tokens.
- All credential files are strictly blocked in `.gitignore`.
